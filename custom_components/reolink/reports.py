"""Reports of a wrong description, flagged from the card (#22), kept for the next tuning session.

Not part of upstream HA: added by camera-card. One JSON line per flag in /config/reolink_reports.jsonl;
a note added after the flag is a later line carrying the flag's ref. bin/testdata reports reads them.
"""
import json
import threading
import uuid
from pathlib import Path

# HA is imported inside async_setup_reports so bin/testdata and the self-check can import this without it.

FILE = "reolink_reports.jsonl"
NOTE_MAX = 500

_lock = threading.Lock()


def add(path: Path, row: dict) -> None:
    with _lock, path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def merged(lines) -> list[dict]:
    """Each flag with its notes joined in, oldest first."""
    flags: dict[str, dict] = {}
    for line in lines:
        try:
            d = json.loads(line)
            if "ch" in d:
                flags[d["ref"]] = {**d, "notes": [d["note"]] if d.get("note") else []}
            elif d.get("ref") in flags and d.get("note"):
                flags[d["ref"]]["notes"].append(d["note"])
        except (ValueError, KeyError, TypeError):
            continue  # a torn last line after a crash
    return list(flags.values())


def async_setup_reports(hass) -> None:
    import datetime as dt

    from aiohttp import web

    from homeassistant.components.http import HomeAssistantView
    from homeassistant.util import dt as dt_util

    from .const import DOMAIN
    from .util import get_host

    path = Path(hass.config.path(FILE))
    iso = lambda s: dt_util.as_local(dt.datetime.fromtimestamp(s, dt.UTC)).isoformat(timespec="seconds")  # noqa: E731

    class ReportView(HomeAssistantView):
        """POST {ch, start, end, said, at[, note]} (times in epoch ms, at in seconds) -> {ref}; or {ref, note}. Admins only."""

        requires_auth = True
        url = "/api/reolink/report"
        name = "api:reolink_report"

        async def post(self, request: web.Request) -> web.Response:
            user = request["hass_user"]
            if not user.is_admin:
                raise web.HTTPForbidden(text="admins only")
            try:
                b = await request.json()
                note = str(b.get("note") or "").strip()[:NOTE_MAX]
                if "ref" in b:
                    row = {"ref": str(b["ref"]), "note": note}
                else:
                    ch = int(b["ch"])
                    said = [str(s) for s in b["said"]]
                    if not said:
                        raise ValueError("nothing was said")
                    entries = hass.config_entries.async_loaded_entries(DOMAIN)
                    name = get_host(hass, entries[0].entry_id).api.camera_name(ch) if entries else str(ch)
                    row = {"ref": uuid.uuid4().hex[:12], "on": dt_util.now().isoformat(timespec="seconds"),
                           "by": user.name, "ch": ch, "camera": name,
                           "start": iso(float(b["start"]) / 1000), "end": iso(float(b["end"]) / 1000),
                           "at": round(float(b["at"]), 1), "said": said, "note": note}
            except (ValueError, KeyError, TypeError, AttributeError) as err:
                return web.Response(status=400, text=f"bad request: {err}")
            await hass.async_add_executor_job(add, path, row)
            return self.json({"ref": row["ref"]})

    hass.http.register_view(ReportView())


if __name__ == "__main__":  # python3 reports.py
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / FILE
        add(p, {"ref": "a", "ch": 5, "start": "S1", "said": ["2 people: walking a dog."], "note": ""})
        add(p, {"ref": "b", "ch": 0, "start": "S2", "said": ["A car."], "note": "no car"})
        add(p, {"ref": "a", "note": "no dog, it was a cart"})
        add(p, {"ref": "zzz", "note": "for a flag that isn't there"})
        with p.open("a") as f:
            f.write('{"ref": "a", "no')  # torn line
        m = merged(p.read_text().splitlines())
        assert [r["ref"] for r in m] == ["a", "b"]
        assert m[0]["notes"] == ["no dog, it was a cart"], "a flag without a note, then its note"
        assert m[1]["notes"] == ["no car"]
    print("ok")
