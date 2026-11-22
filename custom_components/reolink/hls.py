"""Play an NVR recording as HLS while it downloads, so it starts in seconds rather than after the cut.

Not part of upstream HA: added by camera-card. The NVR sends a cut at ~2.4 MB/s
(a 5-min main-stream clip takes ~50 s), so the card shouldn't wait for all of it. iPhones play HLS
natively; desktop browsers through HA's own HLS player.
"""
import asyncio
import contextlib
import datetime as dt
import os
from http import HTTPStatus
import logging
from pathlib import Path
import re
import secrets
import shutil
import time

from aiohttp import web
from reolink_aio.exceptions import ReolinkError

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.media_source import Unresolvable
from homeassistant.core import HomeAssistant

from .baichuan_cut import CUT_LOCK, BcMediaReader, stream_cut
from .const import DOMAIN
from .mpegts import TsMux
from .util import get_host

_LOGGER = logging.getLogger(__name__)
HLS_DIR = Path("/cache/reolink_hls")  # HDD mount
KEEP = 15  # recently played clips kept for instant replays and saves
TOKEN_TTL = 3600  # a replay asks /play again for a fresh one
PLAYLIST_WAIT = 60  # s: covers one 5-min main-stream cut (~50 s) queued ahead
FINISH_WAIT = 4  # s after the tap: under the ~5s an unfinished playlist costs; a 5-min sub clip cuts in ~3s
_ENDED = "#EXT-X-ENDLIST"
_START = "#EXT-X-START:TIME-OFFSET=0,PRECISE=YES\n"  # an unfinished (event) playlist would otherwise open at its end
_FILE = re.compile(r"(index\.m3u8|seg\d{4}\.ts)")

_tokens: dict[str, tuple[str, float]] = {}  # token -> (clip key, issued)
_jobs: dict[str, asyncio.Task] = {}  # clip key -> running or finished writer
_cutting: str | None = None  # the clip holding CUT_LOCK, if any


def _finished(d: Path) -> bool:
    p = d / "index.m3u8"
    return p.exists() and _ENDED in p.read_text()


def _mtime(d: Path) -> float:
    try:
        return d.stat().st_mtime
    except OSError:  # a failed writer deleting its folder
        return 0


def _mark_and_prune(key: str, keep: set[str]) -> bool:
    """Mark key most recently played, prune past KEEP, and say whether key is already fully written."""
    HLS_DIR.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        os.utime(HLS_DIR / key)  # most recently played; never creates anything, unlike Path.touch
    dirs = sorted((d for d in HLS_DIR.iterdir() if d.is_dir()), key=_mtime, reverse=True)
    for d in dirs[KEEP:]:
        if d.name not in keep:
            shutil.rmtree(d, ignore_errors=True)
    return _finished(HLS_DIR / key)


async def _write(hass: HomeAssistant, host, key: str, ch: int, stream: str, start: dt.datetime, end: dt.datetime) -> None:
    global _cutting
    d = HLS_DIR / key
    # a leftover partial folder has no ENDLIST, and ffmpeg overwrites what's in it
    await hass.async_add_executor_job(lambda: d.mkdir(parents=True, exist_ok=True))
    reader, held, proc, mux = BcMediaReader(), [], None, None

    async def start_ffmpeg(frames: list) -> tuple[asyncio.subprocess.Process, TsMux]:
        video = next(f for f in frames if f[0] != "aac")
        # Sound only if it showed up with the first frames: ffmpeg probes every stream it is promised
        # before writing anything, so a silent camera would hold playback back.
        m = TsMux(video[1] == "H265", any(f[0] == "aac" for f in frames))
        p = await asyncio.create_subprocess_exec(
            "ffmpeg", "-v", "error", "-f", "mpegts", "-i", "pipe:0",
            "-c", "copy", "-f", "hls", "-hls_time", "2", "-hls_list_size", "0",
            "-hls_playlist_type", "event", "-hls_flags", "temp_file",
            "-hls_segment_filename", str(d / "seg%04d.ts"), str(d / "index.m3u8"),
            stdin=asyncio.subprocess.PIPE)
        p.stdin.write(m.header + wrap(m, frames))
        return p, m

    def wrap(m: TsMux, frames: list) -> bytes:
        return b"".join(m.audio(f[2]) if f[0] == "aac" else m.video(f[2], f[3]) for f in frames)

    async def drain() -> None:
        try:
            await asyncio.wait_for(proc.stdin.drain(), 30)  # an ffmpeg that stops reading would hold the lock
        except TimeoutError:
            raise RuntimeError("ffmpeg stopped reading the clip") from None

    def add(frames: list) -> None:
        # NVR leads with ~8s of audio before the first frame; drop it to stay in sync
        for f in frames:
            if f[0] != "aac" or any(h[0] != "aac" for h in held):
                held.append(f)

    try:
        # aclosing: if ffmpeg dies mid-cut, the generator still drains the NVR before the lock is released
        async with CUT_LOCK, contextlib.aclosing(stream_cut(host.api.baichuan, host.api.uid, ch, stream, start, end)) as cut:
            _cutting = key
            async for chunk in cut:
                frames = reader.feed(chunk)
                if proc is None:
                    # Hold until the second keyframe, to learn whether the clip has sound. It costs nothing:
                    # ffmpeg can't close the first segment before then anyway.
                    add(frames)
                    if sum(f[0] == "I" for f in held) < 2:
                        continue
                    (proc, mux), frames, held = await start_ffmpeg(held), [], []
                proc.stdin.write(wrap(mux, frames))
                await drain()
            if proc is None:  # a cut shorter than one keyframe interval
                if not any(f[0] != "aac" for f in held):
                    raise ValueError("no video in the cut")
                proc, mux = await start_ffmpeg(held)
            await drain()
            proc.stdin.close()
            # still holding the lock: a tap now must not cancel us while ffmpeg writes the last segment
            try:
                rc = await asyncio.wait_for(proc.wait(), 30)  # a hung ffmpeg would hold the lock, blocking every clip
            except TimeoutError:
                raise RuntimeError("ffmpeg hung finishing the clip") from None  # the except below kills it
            if rc:
                raise RuntimeError(f"ffmpeg exited {proc.returncode}")
            _cutting = None
    except BaseException:
        if _cutting == key:
            _cutting = None
        if proc and proc.returncode is None:
            proc.kill()
        await hass.async_add_executor_job(shutil.rmtree, d, True)
        raise


def _key(entry_id: str, ch: int, stream: str, start: dt.datetime, end: dt.datetime) -> str:
    return f"{entry_id}_{ch}_{stream}_{start:%Y%m%d%H%M%S}_{end:%Y%m%d%H%M%S}"


class PlayView(HomeAssistantView):
    """GET /api/reolink/play?id=<FILE media id>: start (or reuse) a clip; returns {"url": <HLS playlist>}."""

    requires_auth = True
    url = "/api/reolink/play"
    name = "api:reolink_play"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request) -> web.Response:
        try:
            # media-source://reolink/FILE|entry|ch|stream|filename|start|end, as the recordings endpoint gives it
            _, entry_id, ch, stream, _, start_s, end_s = request.query["id"].split("/")[-1].split("|")
            ch = int(ch)
            start, end = (dt.datetime.strptime(t, "%Y%m%d%H%M%S") for t in (start_s, end_s))
            if stream not in ("main", "sub"):
                raise ValueError(f"unsupported stream {stream}")
            host = get_host(self.hass, entry_id)
        except (KeyError, ValueError, Unresolvable) as err:
            return web.Response(status=HTTPStatus.BAD_REQUEST, text=f"bad id: {err}")
        if ch not in host.api.channels:
            return web.Response(status=HTTPStatus.BAD_REQUEST, text=f"no channel {ch}")

        # built only from validated parts: the raw query never reaches the filesystem
        key = _key(entry_id, ch, stream, start, end)
        running = {k for k, t in _jobs.items() if not t.done()} | {key}
        finished = await self.hass.async_add_executor_job(_mark_and_prune, key, running)
        # no awaits from here to the task's creation: two quick taps on one clip share a writer
        job = _jobs.get(key)
        if not finished and (job is None or job.done()):  # a failed writer deleted its folder: retry
            _jobs[key] = self.hass.async_create_background_task(
                _write(self.hass, host, key, ch, stream, start, end), f"reolink hls {key}")
        # Tapping through clips: drop writers still queued for the cut lock, so the newest tap is next.
        # The one cutting must finish (the NVR can't be stopped).
        for k, t in list(_jobs.items()):
            if k not in (key, _cutting) and not t.done():
                t.cancel()
        for k in [k for k, t in _jobs.items() if t.done() and k != key]:
            del _jobs[k]  # finished clips are found on disk; failed ones are retried
        now = time.time()
        for t in [t for t, (_, at) in _tokens.items() if now - at > TOKEN_TTL]:
            del _tokens[t]
        token = secrets.token_urlsafe(16)
        _tokens[token] = (key, now)
        return self.json({"url": f"/api/reolink/hls/{token}/index.m3u8"})


class HlsView(HomeAssistantView):
    """GET /api/reolink/hls/{token}/{file}: the playlist and segments. The random token is the auth,
    as with HA's own stream URLs: players fetch segments without the user's credentials."""

    requires_auth = False
    url = "/api/reolink/hls/{token}/{file}"
    name = "api:reolink_hls"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, token: str, file: str) -> web.StreamResponse:
        hit = _tokens.get(token)
        if hit is None or time.time() - hit[1] > TOKEN_TTL or not _FILE.fullmatch(file):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        key = hit[0]
        path = HLS_DIR / key / file
        if file != "index.m3u8":
            return web.FileResponse(path, headers={"Content-Type": "video/mp2t"}) if path.exists() else web.Response(status=HTTPStatus.NOT_FOUND)
        job = _jobs.get(key)
        if job is None and not await self.hass.async_add_executor_job(path.exists):
            return web.Response(status=HTTPStatus.NOT_FOUND)  # pruned, or lost to a restart: play again
        for _ in range(PLAYLIST_WAIT * 5):
            if path.exists():
                break
            if job is not None and job.done():
                if not job.cancelled() and job.exception() is None:
                    return web.Response(status=HTTPStatus.NOT_FOUND)  # finished, then pruned: play again
                err = "cancelled" if job.cancelled() else job.exception()
                _LOGGER.warning("Reolink clip %s failed: %s", key, err)
                return web.Response(status=HTTPStatus.BAD_GATEWAY, text=str(err))
            await asyncio.sleep(0.2)
        else:
            return web.Response(status=HTTPStatus.GATEWAY_TIMEOUT, text="no video yet")
        # A player given an unfinished playlist takes it for a live stream: it waits a reload (~4s) to start
        # and skips the opening. Most clips finish within FINISH_WAIT of the tap, so hand those over whole.
        while job is not None and not job.done() and time.time() - hit[1] < FINISH_WAIT:
            await asyncio.sleep(0.1)
        try:
            text = await self.hass.async_add_executor_job(path.read_text)
        except FileNotFoundError:  # the writer failed while we waited, and deleted its folder
            return web.Response(status=HTTPStatus.BAD_GATEWAY, text="clip failed")
        text = text.replace("#EXTM3U\n", "#EXTM3U\n" + _START, 1)
        return web.Response(text=text, content_type="application/vnd.apple.mpegurl", headers={"Cache-Control": "no-cache"})
