"""Endpoints for our camera card: recordings with tags over any date range, and a still per moment.

Not part of upstream HA: added by camera-card. Both use HA's normal auth; the card
fetches them with the logged-in user's token. Recordings play through the media source as before.
"""
import asyncio
import datetime as dt
import os
import tempfile
import threading
from http import HTTPStatus
import logging
from pathlib import Path
import time

from aiohttp import web
from reolink_aio.exceptions import ReolinkError

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .descriptions import FILE as SAID_FILE, said
from .util import get_host

_LOGGER = logging.getLogger(__name__)
STILL_DIR = Path("/cache/reolink_stills")  # HDD mount
STILL_CAP = 200 * 1024 * 1024  # ~8000 stills; refetching one costs well under a second
MAX_DAYS = 62


def _entry(hass: HomeAssistant):
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise web.HTTPServiceUnavailable(text="Reolink integration not loaded")
    return entries[0]  # ponytail: one NVR; take an entry id parameter if a second ever appears


def _recordings(entry_id: str, stream: str, pairs: list, said_path: Path) -> list[dict]:
    # a day's search also returns the previous day's late clips
    unique = {(ch, f.start_time_id, f.end_time_id): (ch, f) for ch, f in pairs}
    return [_recording(entry_id, ch, stream, f, said_path) for ch, f in sorted(unique.values(), key=lambda p: p[1].start_time_id)]


def _local(t: dt.datetime) -> str:
    # The NVR's clock is HA's local time, but reolink_aio 0.21.18 computes DST rule dates days off
    # (2026's end lands on Nov 8): label the NVR's wall clock with HA's zone instead.
    return t.replace(tzinfo=dt_util.get_default_time_zone()).isoformat()


def _recording(entry_id: str, ch: int, stream: str, f, said_path: Path) -> dict:
    untagged = getattr(f, "bc_triggers", None) is None
    tags = [] if untagged else [t.name.lower() for t in f.triggers if t.name not in ("MOTION", "TIMER")]
    tz = dt_util.get_default_time_zone()  # NVR wall clock; see _local
    start, end = (t.replace(tzinfo=tz).timestamp() for t in (f.start_time, f.end_time))
    return {
        "ch": ch,
        "start": _local(f.start_time),
        "end": _local(f.end_time),
        "tags": tags,
        "said": said(said_path, ch, start, end),  # what alerts said during it (descriptions.py)
        "untagged": untagged,  # the NVR's tag search had nothing for it; not the same as plain motion
        "id": f"media-source://{DOMAIN}/FILE|{entry_id}|{ch}|{stream}|{f.file_name}|{f.start_time_id}|{f.end_time_id}",
    }


class RecordingsView(HomeAssistantView):
    """GET /api/reolink/recordings?from=YYYY-MM-DD&to=YYYY-MM-DD[&channels=0,5]: every recording, oldest first."""

    requires_auth = True
    url = "/api/reolink/recordings"
    name = "api:reolink_recordings"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request) -> web.Response:
        from .media_source import OLDEST_DAY, WARM_STREAM, ReolinkVODMediaSource  # media_source imports views; avoid a cycle

        entry = _entry(self.hass)
        host = get_host(self.hass, entry.entry_id)
        try:
            first = dt.date.fromisoformat(request.query["from"])
            last = dt.date.fromisoformat(request.query.get("to", request.query["from"]))
            chans = [int(c) for c in request.query["channels"].split(",")] if "channels" in request.query else list(host.api.channels)
        except (KeyError, ValueError) as err:
            return web.Response(status=HTTPStatus.BAD_REQUEST, text=f"bad query: {err}")
        if not 0 <= (last - first).days < MAX_DAYS or not set(chans) <= set(host.api.channels):
            return web.Response(status=HTTPStatus.BAD_REQUEST, text="bad range or channel")

        # day lists live in media_source's module caches; a bare instance shares them without starting
        # another set of background warmers
        source = ReolinkVODMediaSource(self.hass)
        last = min(last, (host.api.time() or dt.datetime.now()).date())  # a future day would search live, for nothing
        pairs = []
        day = first
        while day <= last:
            for ch in chans:
                if day < OLDEST_DAY.get((entry.entry_id, ch), dt.date.min):
                    continue  # the NVR has overwritten it; searching would only cost an NVR round trip
                try:
                    files = await source._async_day_vods(entry.entry_id, ch, WARM_STREAM, day.year, day.month, day.day)
                except Exception as err:  # noqa: BLE001 - incl. baichuan_vod_type's RuntimeError on a failed tag search
                    _LOGGER.warning("Recordings for ch %s on %s failed: %s", ch, day, err)
                    return web.Response(status=HTTPStatus.BAD_GATEWAY, text=str(err))
                pairs.extend((ch, f) for f in files)
            day += dt.timedelta(days=1)
        # building ~500 rows a day is ~0.5 s for a month on the Pi: off the event loop
        out = await self.hass.async_add_executor_job(_recordings, entry.entry_id, WARM_STREAM, pairs, Path(self.hass.config.path(SAID_FILE)))
        cams = [{"ch": ch, "name": host.api.camera_name(ch),
                 "oldest": str(d) if (d := OLDEST_DAY.get((entry.entry_id, ch))) else None}
                for ch in host.api.channels]
        return self.json({"cameras": cams, "recordings": out})


_prune_lock = threading.Lock()  # writers never delete, so under the lock no file vanishes mid-scan


def _prune_stills() -> None:
    with _prune_lock:
        files = sorted(((p.stat(), p) for p in STILL_DIR.glob("*.jpg")), key=lambda e: e[0].st_mtime)  # oldest-used first
        total = sum(st.st_size for st, _ in files)
        for st, p in files:
            if total <= STILL_CAP:
                break
            total -= st.st_size
            p.unlink(missing_ok=True)


def _write_still(path: Path, jpg: bytes) -> None:
    STILL_DIR.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STILL_DIR, suffix=".part")
    with os.fdopen(fd, "wb") as f:
        f.write(jpg)
    os.replace(tmp, path)
    _prune_stills()


class StillView(HomeAssistantView):
    """GET /api/reolink/still/{ch}/{epoch seconds}: a JPEG of that moment, cached on the HDD.

    Epoch seconds, not wall-clock, so a phone in another timezone still asks for the right moment.
    """

    requires_auth = True
    url = "/api/reolink/still/{ch}/{stamp}"
    name = "api:reolink_still"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._nvr = asyncio.Semaphore(2)  # the NVR drops connections past ~10; a scrolled list asks for dozens
        self._inflight: dict[Path, asyncio.Future] = {}  # one NVR fetch per moment, however many ask

    async def get(self, request: web.Request, ch: str, stamp: str) -> web.StreamResponse:
        entry = _entry(self.hass)
        host = get_host(self.hass, entry.entry_id)
        try:
            when = dt.datetime.fromtimestamp(int(stamp), dt_util.get_default_time_zone()).replace(tzinfo=None)  # NVR wall clock; see _local
            channel = int(ch)
            if channel not in host.api.channels:
                raise ValueError(f"no channel {channel}")
        except (ValueError, OverflowError, OSError) as err:  # fromtimestamp raises the latter two on absurd stamps
            return web.Response(status=HTTPStatus.BAD_REQUEST, text=str(err))
        # built only from validated parts: the raw URL never reaches the filesystem
        path = STILL_DIR / f"{entry.entry_id}_{channel}_{when:%Y%m%d%H%M%S}.jpg"
        if path.exists():
            await self.hass.async_add_executor_job(lambda: path.touch())  # mark recently used
        else:
            if (fut := self._inflight.get(path)) is None:
                fut = self._inflight[path] = asyncio.ensure_future(self._fetch(host, channel, when, path))
                fut.add_done_callback(lambda _: self._inflight.pop(path, None))
            try:
                await asyncio.shield(fut)
            except (ReolinkError, TimeoutError) as err:
                _LOGGER.debug("Still for ch %s at %s failed: %s", channel, when, err)
                return web.Response(status=HTTPStatus.BAD_GATEWAY, text=str(err))
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=604800"})

    async def _fetch(self, host, channel: int, when: dt.datetime, path: Path) -> None:
        async with self._nvr:
            jpg = await host.api.baichuan.snapshot_past(channel, when)
        await self.hass.async_add_executor_job(_write_still, path, jpg)
