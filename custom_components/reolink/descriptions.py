"""reolink.keep_description: what an alert said about a moment on a camera, so the card says it too.

Not part of upstream HA: added by camera-card. One JSON line
per description in /config/reolink_descriptions.jsonl; card_api attaches them to recordings.
"""
import bisect
import json
import threading
from pathlib import Path

# HA is imported inside async_setup_descriptions so the self-check at the bottom runs without it.

FILE = "reolink_descriptions.jsonl"
LEAD = 5  # seconds a description may precede its recording: NVR and HA clocks differ slightly

_lock = threading.Lock()
_by_ch: dict[int, list[tuple[float, str]]] | None = None  # per channel, sorted by time


def _load(path: Path) -> dict[int, list[tuple[float, str]]]:
    """Caller holds _lock."""
    global _by_ch
    if _by_ch is None:
        _by_ch = {}
        for line in path.read_text().splitlines() if path.exists() else []:
            try:
                d = json.loads(line)
                bisect.insort(_by_ch.setdefault(int(d["ch"]), []), (float(d["t"]), str(d["text"])))
            except (ValueError, KeyError, TypeError):
                continue  # a torn last line after a crash
    return _by_ch


def keep(path: Path, ch: int, t: float, text: str) -> None:
    # ponytail: the file only grows (~50 KB a day at 500 descriptions); prune by oldest recording if it ever matters
    with _lock:
        by_ch = _load(path)
        with path.open("a") as f:
            f.write(json.dumps({"ch": ch, "t": t, "text": text}) + "\n")
        bisect.insort(by_ch.setdefault(ch, []), (t, text))


def said(path: Path, ch: int, start: float, end: float) -> list[str]:
    """What was said about channel ch between start and end (epoch seconds), oldest first."""
    with _lock:
        rows = _load(path).get(ch, [])
        i = bisect.bisect_left(rows, (start - LEAD,))
        j = bisect.bisect_left(rows, (end,))
        return [text for _, text in rows[i:j]]


def async_setup_descriptions(hass) -> None:
    import probatio

    from homeassistant.helpers import config_validation as cv
    from homeassistant.util import dt as dt_util

    from .const import DOMAIN

    async def _async_keep(call) -> None:
        t = dt_util.as_utc(call.data["time"]).timestamp()
        await hass.async_add_executor_job(keep, Path(hass.config.path(FILE)), call.data["channel"], t, call.data["text"])

    hass.services.async_register(
        DOMAIN,
        "keep_description",
        _async_keep,
        schema=probatio.Schema({
            probatio.Required("channel"): cv.positive_int,
            probatio.Required("time"): cv.datetime,
            probatio.Required("text"): cv.string,
        }),
    )


if __name__ == "__main__":  # python3 descriptions.py
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / FILE
        keep(p, 3, 1000.0, "A man is leaving through the gate.")
        keep(p, 3, 1300.0, "Someone was spotted.")
        keep(p, 0, 1000.0, "The Leaf is pulling into the garage.")
        with p.open("a") as f:
            f.write('{"ch": 3, "t"')  # torn line
        _by_ch = None  # as after a restart
        assert said(p, 3, 990.0, 1290.0) == ["A man is leaving through the gate."]
        assert said(p, 3, 1004.0, 1290.0) == ["A man is leaving through the gate."], "within LEAD of the start"
        assert said(p, 3, 1006.0, 1300.0) == [], "end is exclusive: the next recording owns it"
        assert said(p, 3, 900.0, 2000.0) == ["A man is leaving through the gate.", "Someone was spotted."]
        assert said(p, 5, 0.0, 9e9) == []
    print("ok")
