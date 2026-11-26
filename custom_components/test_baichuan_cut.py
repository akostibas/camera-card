# /// script
# requires-python = ">=3.13"
# dependencies = ["reolink-aio==0.21.18"]  # match manifest.json
# ///
"""Check which NVR recording file a cut picks. Free: no NVR is contacted.

  uv run custom_components/test_baichuan_cut.py
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "reolink"))  # the module alone: the package needs Home Assistant
from baichuan_cut import find_file  # noqa: E402


def _t(tag, t):
    return f"<{tag}>" + "".join(f"<{k}>{getattr(t, k)}</{k}>" for k in ("year", "month", "day", "hour", "minute", "second")) + f"</{tag}>"


class FakeNvr:
    def __init__(self, *files):
        self.files = files

    async def send(self, cmd_id, channel, body, **_):
        if cmd_id == 14:
            return "<handle>7</handle>"
        return "".join(f"<FileInfo><name>{n}</name><Id>id-{n}</Id>{_t('startTime', s)}{_t('endTime', e)}</FileInfo>"
                       for n, s, e in self.files) if cmd_id == 15 else ""


def at(hms):
    return datetime.fromisoformat(f"2026-11-26T{hms}")


def find(nvr, start, end):
    return asyncio.run(find_file(nvr, "uid", 1, "main", at(start), at(end)))


def test_file_contains_start():
    nvr = FakeNvr(("a", at("11:40:00"), at("11:43:50")), ("b", at("11:43:52"), at("11:44:30")))
    assert find(nvr, "11:43:34", "11:43:54") == ("a", "id-a", at("11:43:34"), at("11:43:50"))


def test_file_starts_inside_range():
    nvr = FakeNvr(("a", at("11:20:00"), at("11:21:00")), ("b", at("11:43:37"), at("11:43:59")),
                  ("c", at("11:43:50"), at("11:44:30")))
    assert find(nvr, "11:43:34", "11:43:54") == ("b", "id-b", at("11:43:37"), at("11:43:54"))


def test_no_overlap_raises():
    nvr = FakeNvr(("a", at("11:20:00"), at("11:21:00")), ("b", at("11:43:54"), at("11:44:30")))
    try:
        find(nvr, "11:43:34", "11:43:54")
    except LookupError as e:
        assert "11:20:00-11:21:00, 11:43:54-11:44:30" in str(e), e
    else:
        raise AssertionError("expected LookupError")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
