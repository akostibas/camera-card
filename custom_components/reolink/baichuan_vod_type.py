"""Make the NVR's recording trigger (person/vehicle/animal) search reliable.

Not part of upstream HA: added by camera-card. reolink_aio's search_vod_type:
- refuses a channel without a camera UID (RLC-810A behind an RLN8-410 never reports one), though the
  NVR answers the same search with a blank UID;
- fails with status 400 when searches overlap, and request_vod_files swallows that, returning the
  files untagged, which the finished-day cache then keeps for good.
"""
import asyncio

from reolink_aio.api import Host
from reolink_aio.baichuan.baichuan import Baichuan
from reolink_aio.const import UNKNOWN
from reolink_aio.exceptions import ReolinkError


class _BlankUid:
    def __init__(self, api: Host) -> None:
        self._api = api

    def __getattr__(self, name: str):
        return getattr(self._api, name)

    def camera_uid(self, channel: int | None) -> str:
        uid = self._api.camera_uid(channel)
        return "" if uid == UNKNOWN else uid


class _Searcher:
    # Lives for one call only: search_vod_type reads attributes of self but never assigns them.
    def __init__(self, bc: Baichuan) -> None:
        self._bc = bc
        self.http_api = _BlankUid(bc.http_api)

    def __getattr__(self, name: str):
        return getattr(self._bc, name)


def install(api: Host) -> None:
    bc = api.baichuan
    lock = asyncio.Lock()

    async def search_vod_type(channel: int, *args, **kwargs):
        target = bc if api.camera_uid(channel) != UNKNOWN else _Searcher(bc)
        async with lock:
            try:
                return await Baichuan.search_vod_type(target, channel, *args, **kwargs)
            except ReolinkError as err:
                # not a ReolinkError, so request_vod_files lets it through and nothing gets cached
                raise RuntimeError(f"Recording trigger search failed: {err}") from err

    bc.search_vod_type = search_vod_type
