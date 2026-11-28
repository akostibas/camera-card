"""reolink.save_keyframes: a recording range as keyframe JPEGs, for describing camera alerts.

Not part of upstream HA: added by camera-card. Works on a recording still in progress.
Keyframes only (~1 per 2s) because decoding the full 4K stream takes ~10s on a small host; this takes ~1s.
With `focus` (a detection sensor), returns only `pictures` keyframes, chosen from while that sensor was on.
"""
import asyncio
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import probatio
from reolink_aio.exceptions import ReolinkError

from homeassistant.components.recorder import get_instance, history
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .baichuan_cut import CUT_LOCK, download_cut, to_mp4
from .const import DOMAIN
from .keyframe_pick import pick, windows
from .util import get_host

FRAME_DIR = Path("/cache/alert_frames")  # HDD mount; the container's /tmp is on the SD card
TIMEOUT = 20  # a long playback cut can hold CUT_LOCK; give up so the alert still goes out
KEEP = 30 * 60  # seconds a call's pictures stay; the slowest reader is describe.py, well under a minute


def _prune(parent: Path) -> None:
    """Drops earlier calls' folders once their readers are surely done."""
    cutoff = time.time() - KEEP
    for d in parent.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)


def _keyframes(media: bytes, parent: Path, width: int) -> tuple[list[str], list[float]]:
    """The keyframe JPEGs, and each one's seconds from the start of the cut."""
    # A folder per call: a shared one let one alert's pictures overwrite another's before Gemini read them
    parent.mkdir(parents=True, exist_ok=True)
    _prune(parent)
    out = Path(tempfile.mkdtemp(dir=parent))
    out.chmod(0o755)  # mkdtemp makes it owner-only; bin/testdata copies pictures off the host over ssh
    to_mp4(media, f"{out}/clip.mp4")
    try:
        times = subprocess.run(["ffprobe", "-v", "error", "-skip_frame", "nokey", "-select_streams", "v:0",
                                "-show_entries", "frame=pts_time", "-of", "csv=p=0", f"{out}/clip.mp4"],
                               capture_output=True, text=True, check=True).stdout.split()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-skip_frame", "nokey", "-i", f"{out}/clip.mp4",
                        "-vf", f"scale={width}:-2", "-fps_mode", "vfr", "-q:v", "4", f"{out}/k%02d.jpg"], check=True)
    finally:
        Path(f"{out}/clip.mp4").unlink(missing_ok=True)
    # by number: as text, k100 sorts before k11 and every picture past k10 gets another's time
    files = [str(f) for f in sorted(out.glob("k*.jpg"), key=lambda f: int(f.stem[1:]))]
    if len(times) != len(files):
        raise OSError(f"{len(files)} keyframes but {len(times)} times")
    return files, [float(t) for t in times]


def _seen(hass: HomeAssistant, entity_id: str, start, end) -> list[tuple[float, float]]:
    """Offsets from `start` while `entity_id` was on. Runs in the recorder's executor."""
    states = history.state_changes_during_period(hass, start, end, entity_id, no_attributes=True).get(entity_id, [])
    return windows([((s.last_changed - start).total_seconds(), s.state == "on") for s in states],
                   (end - start).total_seconds())


async def _async_save_keyframes(call: ServiceCall) -> ServiceResponse:
    hass = call.hass
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError("Reolink integration not loaded")
    host = get_host(hass, entries[0].entry_id)  # ponytail: one NVR, as in card_api
    ch = call.data["channel"]
    # NVR clock is HA's local wall clock (see card_api._local)
    start, end = (dt_util.as_local(call.data[k]).replace(tzinfo=None) for k in ("start", "end"))
    try:
        async with asyncio.timeout(TIMEOUT):  # only the wait: cancelling a cut mid-stream would desync the connection
            await CUT_LOCK.acquire()
        try:
            media = await download_cut(host.api.baichuan, host.api.uid, ch, "main", start, end)
        finally:
            CUT_LOCK.release()
        files, times = await hass.async_add_executor_job(_keyframes, media, FRAME_DIR / f"ch{ch}", call.data["width"])
    except (ReolinkError, LookupError, TimeoutError, OSError, subprocess.CalledProcessError) as err:
        raise HomeAssistantError(f"keyframes for ch {ch} {start}..{end}: {err}") from err
    if not (focus := call.data.get("focus")):
        return {"files": files}
    # ponytail: assumes the cut starts at `start`; the NVR may begin it up to a keyframe (~2s) earlier, inside PAD
    span = call.data["start"], call.data["end"]
    seen = await get_instance(hass).async_add_executor_job(_seen, hass, focus, *(dt_util.as_utc(t) for t in span))
    chosen = pick(times, seen, call.data["pictures"])
    return {"files": [files[i] for i in chosen], "seen": [list(w) for w in seen], "times": [times[i] for i in chosen]}


def async_setup_alert_frames(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "save_keyframes",
        _async_save_keyframes,
        schema=probatio.Schema({
            probatio.Required("channel"): cv.positive_int,
            probatio.Required("start"): cv.datetime,
            probatio.Required("end"): cv.datetime,
            probatio.Optional("width", default=1280): cv.positive_int,
            probatio.Optional("focus"): cv.entity_id,
            probatio.Optional("pictures", default=16): cv.positive_int,
        }),
        supports_response=SupportsResponse.ONLY,
    )
