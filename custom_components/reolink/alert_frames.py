"""reolink.save_keyframes: a recording range as keyframe JPEGs, for describing camera alerts.

Not part of upstream HA: added by camera-card. Works on a recording still in progress.
Keyframes only (~1 per 2s) because decoding the full 4K stream takes ~10s on a small host; this takes ~1s.
"""
import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

import probatio
from reolink_aio.exceptions import ReolinkError

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .baichuan_cut import CUT_LOCK, download_cut, to_mp4
from .const import DOMAIN
from .util import get_host

FRAME_DIR = Path("/cache/alert_frames")  # HDD mount; the container's /tmp is on the SD card
TIMEOUT = 20  # a long playback cut can hold CUT_LOCK; give up so the alert still goes out


def _keyframes(media: bytes, out: Path, width: int) -> list[str]:
    FRAME_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=FRAME_DIR) as d:
        to_mp4(media, f"{d}/clip.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-skip_frame", "nokey", "-i", f"{d}/clip.mp4",
                        "-vf", f"scale={width}:-2", "-fps_mode", "vfr", "-q:v", "4", f"{d}/k%02d.jpg"], check=True)
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir()
        for f in sorted(Path(d).glob("k*.jpg")):
            f.rename(out / f.name)
    return [str(f) for f in sorted(out.glob("k*.jpg"))]


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
        files = await hass.async_add_executor_job(_keyframes, media, FRAME_DIR / f"ch{ch}", call.data["width"])
    except (ReolinkError, LookupError, TimeoutError, OSError, subprocess.CalledProcessError) as err:
        raise HomeAssistantError(f"keyframes for ch {ch} {start}..{end}: {err}") from err
    return {"files": files}


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
        }),
        supports_response=SupportsResponse.ONLY,
    )
