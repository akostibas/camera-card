"""Expose Reolink IP camera VODs as media sources."""

import asyncio
import datetime as dt
import logging
import os
from pathlib import Path
import pickle
import time
from typing import override

from reolink_aio.enums import VodRequestType
from reolink_aio.typings import VOD_file, VOD_trigger

from homeassistant.components.camera import DOMAIN as CAM_DOMAIN, DynamicStreamSettings
from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.components.stream import create_stream
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN
from .baichuan_days import days_with_footage
from .util import get_host
from .views import async_generate_playback_proxy_url

_LOGGER = logging.getLogger(__name__)
# camera-card: the NVR answers one search at a time, 1-5s each, and the camera
# card repeats identical queries.
# Finished days never change: kept until the NVR overwrites them, saved to the HDD, and pre-loaded.
_FINISHED_DAY_VODS: dict[tuple, list] = {}
# bump the name when what's cached changes (v3: reliable trigger tags, baichuan_vod_type.py)
_VOD_CACHE_FILE = Path("/cache/reolink_vods.v3.pickle")
WARM_DAYS = 30  # only when the NVR won't say which days it still has
OLDEST_DAY: dict[tuple[str, int], dt.date] = {}  # (entry, channel) -> the NVR's oldest day with footage
WARM_STREAM = "sub"  # the camera card's media_resolution: low
# Today's files and the day list change. They're answered at once from the last fetch, which is
# topped up in the background once older than LIVE_AGE (the card re-asks while today is in view),
# and by a loop every TODAY_REFRESH so a first look is instant and never far behind.
LIVE_AGE = 60
TODAY_REFRESH = 60 * int(os.environ.get("REOLINK_TODAY_REFRESH_MINUTES", "30"))
_LATEST: dict[tuple, tuple[float, object]] = {}
_INFLIGHT: dict[tuple, asyncio.Future] = {}


async def _update(key: tuple, fetch, top_up=None):
    """Fetch key now, sharing a fetch already running, and remember the result.

    top_up(previous) extends the last result instead of fetching it all again.
    """
    if (task := _INFLIGHT.get(key)) is None:
        hit = _LATEST.get(key)
        task = _INFLIGHT[key] = asyncio.ensure_future(top_up(hit[1]) if hit and top_up else fetch())

        def done(task: asyncio.Future) -> None:
            _INFLIGHT.pop(key, None)
            if not task.cancelled() and task.exception() is None:
                _LATEST[key] = (time.monotonic(), task.result())

        task.add_done_callback(done)
    return await asyncio.shield(task)


def _log_failure(task: asyncio.Future) -> None:
    if not task.cancelled() and (err := task.exception()):
        _LOGGER.debug("Background recording-list update failed: %s", err)


async def _latest(key: tuple, fetch, top_up=None):
    """Answer from the last fetch; once it's older than LIVE_AGE, update it in the background."""
    if (hit := _LATEST.get(key)) is None:
        return await _update(key, fetch, top_up)
    if time.monotonic() - hit[0] > LIVE_AGE and key not in _INFLIGHT:
        asyncio.ensure_future(_update(key, fetch, top_up)).add_done_callback(_log_failure)
    return hit[1]


# Saved as each file's raw NVR fields: VOD_file's timezone holds closures and won't pickle.
def _load_vod_cache() -> dict[tuple, list[tuple]]:
    try:
        return pickle.loads(_VOD_CACHE_FILE.read_bytes())
    except FileNotFoundError:
        return {}
    except Exception:  # noqa: BLE001 - the warmer refills it
        _LOGGER.warning("Ignoring unreadable %s", _VOD_CACHE_FILE, exc_info=True)
        return {}


def _restore_vod(data: dict, bc_triggers, tzinfo) -> VOD_file:
    file = VOD_file(data, tzinfo)
    file.bc_triggers = bc_triggers
    return file


def _save_vod_cache(snapshot: dict[tuple, list[tuple]]) -> None:
    tmp = _VOD_CACHE_FILE.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(snapshot))
    tmp.replace(_VOD_CACHE_FILE)

VOD_SPLIT_TIME = dt.timedelta(minutes=5)


async def async_get_media_source(hass: HomeAssistant) -> ReolinkVODMediaSource:
    """Set up camera media source. Its cache warmers start in async_setup."""
    return ReolinkVODMediaSource(hass)


def res_name(stream: str) -> str:
    """Return the user friendly name for a stream."""
    match stream:
        case "main":
            return "High res."
        case "autotrack_sub":
            return "Telephoto low res."
        case "autotrack_main":
            return "Telephoto high res."
        case _:
            return "Low res."


class ReolinkVODMediaSource(MediaSource):
    """Provide Reolink camera VODs as media sources."""

    name: str = "Reolink"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize ReolinkVODMediaSource."""
        super().__init__(DOMAIN)
        self.hass = hass

    @override
    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        identifier = ["UNKNOWN"]
        if item.identifier is not None:
            identifier = item.identifier.split("|", 6)
        if identifier[0] != "FILE":
            raise Unresolvable(
                translation_domain=DOMAIN,
                translation_key="unknown_media_item",
                translation_placeholders={"identifier": str(item.identifier)},
            )

        _, config_entry_id, channel_str, stream_res, filename, start_time, end_time = (
            identifier
        )
        channel = int(channel_str)

        host = get_host(self.hass, config_entry_id)

        def get_vod_type() -> VodRequestType:
            if host.api.is_nvr:
                return VodRequestType.NVR_DOWNLOAD
            if filename.endswith((".mp4", ".vref")):
                return VodRequestType.PLAYBACK
            return VodRequestType.RTMP

        vod_type = get_vod_type()

        if vod_type is VodRequestType.NVR_DOWNLOAD:
            filename = f"{start_time}_{end_time}"

        if vod_type in {
            VodRequestType.DOWNLOAD,
            VodRequestType.NVR_DOWNLOAD,
            VodRequestType.PLAYBACK,
        }:
            proxy_url = async_generate_playback_proxy_url(
                config_entry_id, channel, filename, stream_res, vod_type.value
            )
            return PlayMedia(proxy_url, "video/mp4")

        mime_type, url = await host.api.get_vod_source(
            channel, filename, stream_res, vod_type
        )
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Opening VOD stream from %s: %s",
                host.api.camera_name(channel),
                host.api.hide_password(url),
            )

        stream = create_stream(self.hass, url, {}, DynamicStreamSettings())
        stream.add_provider("hls", timeout=3600)
        stream_url: str = stream.endpoint_url("hls")
        stream_url = stream_url.replace("master_", "")
        return PlayMedia(stream_url, mime_type)

    async def _async_day_vods(
        self,
        config_entry_id: str,
        channel: int,
        stream: str,
        year: int,
        month: int,
        day: int,
        event: str | None = None,
        fresh: bool = False,
    ) -> list:
        """Return a day's VOD files: cached for good once the day is over, else see _latest.

        fresh waits for an update rather than answering from the last fetch.
        """
        cache_key = (config_entry_id, channel, stream, year, month, day, event)
        if (vod_files := _FINISHED_DAY_VODS.get(cache_key)) is not None:
            return vod_files
        host = get_host(self.hass, config_entry_id)
        start = dt.datetime(year, month, day, hour=0, minute=0, second=0)
        end = dt.datetime(year, month, day, hour=23, minute=59, second=59)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Requesting VODs of %s on %s/%s/%s",
                host.api.camera_name(channel),
                year,
                month,
                day,
            )

        async def fetch(since: dt.datetime = start) -> list:
            _, files = await host.api.request_vod_files(
                channel,
                since,
                end,
                stream=stream,
                split_time=VOD_SPLIT_TIME,
                trigger=VOD_trigger[event] if event is not None else None,
            )
            return files

        async def top_up(previous: list) -> list:
            # NVR search time grows with the window, so only search from the last clip on (it may
            # have still been recording). The NVR also returns earlier clips from that hour.
            if not previous:
                return await fetch()
            since = max(f.start_time for f in previous).replace(tzinfo=None)
            merged = {f.start_time_id: f for f in previous}
            merged.update((f.start_time_id, f) for f in await fetch(since))
            return sorted(merged.values(), key=lambda f: f.start_time)

        # an hour's grace: the recording running at midnight is still being written
        if end + dt.timedelta(hours=1) < dt.datetime.now():
            vod_files = await _update(cache_key, fetch)
            _LATEST.pop(cache_key, None)
            _FINISHED_DAY_VODS[cache_key] = vod_files
            return vod_files
        return await (_update if fresh else _latest)(cache_key, fetch, top_up)

    async def async_keep_today(self) -> None:
        """Refresh today's lists every TODAY_REFRESH, so opening the timeline needn't wait on the NVR."""
        while True:
            entries = self.hass.config_entries.async_loaded_entries(DOMAIN)
            for entry in entries:
                host = get_host(self.hass, entry.entry_id)
                today = (host.api.time() or dt.datetime.now()).date()
                for key in [k for k in _LATEST if len(k) == 7 and dt.date(*k[3:6]) < today]:
                    del _LATEST[key]  # yesterday's is cached for good once finished
                for channel in host.api.channels:
                    try:
                        await self._async_day_vods(
                            entry.entry_id, channel, WARM_STREAM, today.year, today.month, today.day, fresh=True
                        )
                    except Exception:  # noqa: BLE001 - NVR hiccup; next pass retries
                        _LOGGER.debug("Refreshing today on channel %s failed", channel, exc_info=True)
            # retry soon until the integration is loaded
            await asyncio.sleep(TODAY_REFRESH if entries else 5)  # started before the entry loads

    async def async_warm(self) -> None:
        """Pre-load the last WARM_DAYS finished days, so scrolling back doesn't wait on the NVR."""
        saved = await self.hass.async_add_executor_job(_load_vod_cache)
        while True:
            entries = self.hass.config_entries.async_loaded_entries(DOMAIN)
            added = 0
            for entry in entries:
                host = get_host(self.hass, entry.entry_id)
                for key in [k for k in saved if k[0] == entry.entry_id]:
                    _FINISHED_DAY_VODS.setdefault(
                        key, [_restore_vod(*f, host.api.timezone()) for f in saved.pop(key)]
                    )
                today = (host.api.time() or dt.datetime.now()).date()
                for channel in host.api.channels:
                    try:
                        have = await days_with_footage(host.api.baichuan, channel, today)
                    except Exception:  # noqa: BLE001 - next pass retries
                        _LOGGER.warning("Day list for channel %s failed; warming the last %s days", channel, WARM_DAYS, exc_info=True)
                        have = set()
                    if have:
                        # The NVR overwrites oldest first: drop days before its oldest. Its oldest day may be
                        # part overwritten, so it isn't kept or warmed; viewing it searches it fresh.
                        oldest = OLDEST_DAY[(entry.entry_id, channel)] = min(have)
                        for key in [k for k in _FINISHED_DAY_VODS
                                    if k[:2] == (entry.entry_id, channel) and dt.date(*k[3:6]) <= oldest]:
                            del _FINISHED_DAY_VODS[key]
                            added += dt.date(*key[3:6]) < oldest  # dropping the oldest day alone needn't resave
                        days = sorted((d for d in have if oldest < d < today), reverse=True)
                    else:
                        days = [today - dt.timedelta(days=n) for n in range(1, WARM_DAYS + 1)]
                    # ponytail: one search at a time, newest first; a user's query waits behind at most one
                    for day in days:
                        key = (entry.entry_id, channel, WARM_STREAM, day.year, day.month, day.day, None)
                        if key in _FINISHED_DAY_VODS:
                            continue
                        try:
                            await self._async_day_vods(*key)
                        except Exception:  # noqa: BLE001 - NVR hiccup; next pass retries
                            _LOGGER.debug("Warming %s failed", key, exc_info=True)
                        added += 1
            # backstop in case the day list stays broken: nothing the NVR holds is a year old
            for key in [k for k in _FINISHED_DAY_VODS if dt.date(*k[3:6]) < dt.date.today() - dt.timedelta(days=365)]:
                del _FINISHED_DAY_VODS[key]
                added += 1
            if added:
                try:
                    await self.hass.async_add_executor_job(
                        _save_vod_cache,
                        {
                            key: [(f.data, f.bc_triggers) for f in files]
                            for key, files in _FINISHED_DAY_VODS.items()
                        },
                    )
                except Exception:  # noqa: BLE001 - keep warming; only restarts lose out
                    _LOGGER.warning("Saving %s failed", _VOD_CACHE_FILE, exc_info=True)
                _LOGGER.debug("Warmed %s recording lists", added)
            # retry soon until the integration is loaded, then hourly picks up each new day
            await asyncio.sleep(3600 if entries else 5)

    @override
    async def async_browse_media(
        self,
        item: MediaSourceItem,
    ) -> BrowseMediaSource:
        """Return media."""
        if not item.identifier:
            return await self._async_generate_root()

        identifier = item.identifier.split("|", 7)
        item_type = identifier[0]

        if item_type == "CAM":
            _, config_entry_id, channel_str = identifier
            return await self._async_generate_resolution_select(
                config_entry_id, int(channel_str)
            )
        if item_type == "RES":
            _, config_entry_id, channel_str, stream = identifier
            return await self._async_generate_camera_days(
                config_entry_id, int(channel_str), stream
            )
        if item_type == "DAY":
            (
                _,
                config_entry_id,
                channel_str,
                stream,
                year_str,
                month_str,
                day_str,
            ) = identifier
            return await self._async_generate_camera_files(
                config_entry_id,
                int(channel_str),
                stream,
                int(year_str),
                int(month_str),
                int(day_str),
            )
        if item_type == "EVE":
            (
                _,
                config_entry_id,
                channel_str,
                stream,
                year_str,
                month_str,
                day_str,
                event,
            ) = identifier
            return await self._async_generate_camera_files(
                config_entry_id,
                int(channel_str),
                stream,
                int(year_str),
                int(month_str),
                int(day_str),
                event,
            )

        raise Unresolvable(
            translation_domain=DOMAIN,
            translation_key="unknown_media_item",
            translation_placeholders={"identifier": str(item.identifier)},
        )

    async def _async_generate_root(self) -> BrowseMediaSource:
        """Return all available reolink cameras as root browsing structure."""
        children: list[BrowseMediaSource] = []

        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        for config_entry in self.hass.config_entries.async_loaded_entries(DOMAIN):
            channels: list[str] = []
            host = config_entry.runtime_data.host
            entities = er.async_entries_for_config_entry(
                entity_reg, config_entry.entry_id
            )
            for entity in entities:
                if (
                    entity.disabled
                    or entity.device_id is None
                    or entity.domain != CAM_DOMAIN
                ):
                    continue

                device = device_reg.async_get(entity.device_id)
                ch_id = entity.unique_id.split("_")[1]
                if ch_id in channels or device is None:
                    continue
                channels.append(ch_id)

                ch: int | str = ch_id
                if len(ch_id) > 3:
                    ch = host.api.channel_for_uid(ch_id)

                if not host.api.supported(int(ch), "replay") or not host.api.hdd_info:
                    # playback stream not supported by this
                    # camera or no storage installed
                    continue

                device_name = device.name
                if device.name_by_user is not None:
                    device_name = device.name_by_user

                if host.api.is_dual_lens:
                    device_name = f"{device_name} lens {ch}"

                children.append(
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=f"CAM|{config_entry.entry_id}|{ch}",
                        media_class=MediaClass.CHANNEL,
                        media_content_type=MediaType.PLAYLIST,
                        title=device_name,
                        thumbnail=f"/api/camera_proxy/{entity.entity_id}",
                        can_play=False,
                        can_expand=True,
                    )
                )

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.APP,
            media_content_type="",
            title="Reolink",
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def _async_generate_resolution_select(
        self, config_entry_id: str, channel: int
    ) -> BrowseMediaSource:
        """Allow the user to select the high or low playback resolution."""
        host = get_host(self.hass, config_entry_id)

        main_enc = await host.api.get_encoding(channel, "main")
        if main_enc == "h265":
            _LOGGER.debug(
                "Reolink camera %s uses h265 encoding for main stream,"
                "playback at high resolution may not work in all browsers/apps",
                host.api.camera_name(channel),
            )

        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"RES|{config_entry_id}|{channel}|sub",
                media_class=MediaClass.CHANNEL,
                media_content_type=MediaType.PLAYLIST,
                title="Low resolution",
                can_play=False,
                can_expand=True,
            ),
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"RES|{config_entry_id}|{channel}|main",
                media_class=MediaClass.CHANNEL,
                media_content_type=MediaType.PLAYLIST,
                title="High resolution",
                can_play=False,
                can_expand=True,
            ),
        ]

        if host.api.supported(channel, "autotrack_stream"):
            children.extend(
                [
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=f"RES|{config_entry_id}|{channel}|autotrack_sub",
                        media_class=MediaClass.CHANNEL,
                        media_content_type=MediaType.PLAYLIST,
                        title="Telephoto low resolution",
                        can_play=False,
                        can_expand=True,
                    ),
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=f"RES|{config_entry_id}|{channel}|autotrack_main",
                        media_class=MediaClass.CHANNEL,
                        media_content_type=MediaType.PLAYLIST,
                        title="Telephoto high resolution",
                        can_play=False,
                        can_expand=True,
                    ),
                ]
            )

        title = host.api.camera_name(channel)
        if host.api.is_dual_lens:
            title = f"{host.api.camera_name(channel)} lens {channel}"

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"RESs|{config_entry_id}|{channel}",
            media_class=MediaClass.CHANNEL,
            media_content_type=MediaType.PLAYLIST,
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def _async_generate_camera_days(
        self, config_entry_id: str, channel: int, stream: str
    ) -> BrowseMediaSource:
        """Return all days on which recordings are available for a reolink camera."""
        host = get_host(self.hass, config_entry_id)

        # We want today of the camera, not necessarily today of the server
        now = host.api.time() or await host.api.async_get_time()
        start = now - dt.timedelta(days=31)
        end = now

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Requesting recording days of %s from %s to %s",
                host.api.camera_name(channel),
                start,
                end,
            )
        statuses, _ = await _latest(
            ("RES", config_entry_id, channel, stream),
            lambda: host.api.request_vod_files(
                channel, start, end, status_only=True, stream=stream
            ),
        )
        children: list[BrowseMediaSource] = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"DAY|{config_entry_id}|{channel}|{stream}|{status.year}|{status.month}|{day}",
                media_class=MediaClass.DIRECTORY,
                media_content_type=MediaType.PLAYLIST,
                title=f"{status.year}/{status.month}/{day}",
                can_play=False,
                can_expand=True,
            )
            for status in statuses
            for day in status.days
        ]

        title = f"{host.api.camera_name(channel)} {res_name(stream)}"
        if host.api.is_dual_lens:
            title = f"{host.api.camera_name(channel)} lens {channel} {res_name(stream)}"

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"DAYS|{config_entry_id}|{channel}|{stream}",
            media_class=MediaClass.CHANNEL,
            media_content_type=MediaType.PLAYLIST,
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def _async_generate_camera_files(
        self,
        config_entry_id: str,
        channel: int,
        stream: str,
        year: int,
        month: int,
        day: int,
        event: str | None = None,
    ) -> BrowseMediaSource:
        """Return all recording files on a specific day of a Reolink camera."""
        host = get_host(self.hass, config_entry_id)

        children: list[BrowseMediaSource] = []
        vod_files = await self._async_day_vods(
            config_entry_id, channel, stream, year, month, day, event
        )

        if event is None and host.api.is_nvr and not host.api.is_hub:
            triggers = VOD_trigger.NONE
            for file in vod_files:
                triggers |= file.triggers

            children.extend(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"EVE|{config_entry_id}|{channel}|{stream}|{year}|{month}|{day}|{trigger.name}",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.PLAYLIST,
                    title=str(trigger.name).title(),
                    can_play=False,
                    can_expand=True,
                )
                for trigger in triggers
            )

        for file in vod_files:
            file_name = f"{file.start_time.time()} {file.duration}"
            if file.triggers != file.triggers.NONE:
                file_name += " " + " ".join(
                    str(trigger.name).title() for trigger in file.triggers
                )

            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"FILE|{config_entry_id}|{channel}|{stream}|{file.file_name}|{file.start_time_id}|{file.end_time_id}",
                    media_class=MediaClass.VIDEO,
                    media_content_type=MediaType.VIDEO,
                    title=file_name,
                    can_play=True,
                    can_expand=False,
                )
            )

        title = (
            f"{host.api.camera_name(channel)} {res_name(stream)} {year}/{month}/{day}"
        )
        if host.api.is_dual_lens:
            title = (
                f"{host.api.camera_name(channel)} lens"
                f" {channel} {res_name(stream)}"
                f" {year}/{month}/{day}"
            )
        if event:
            title = f"{title} {event.title()}"

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"FILES|{config_entry_id}|{channel}|{stream}",
            media_class=MediaClass.CHANNEL,
            media_content_type=MediaType.PLAYLIST,
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
        )
