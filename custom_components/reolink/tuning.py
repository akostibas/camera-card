"""Auto-tune: lower a camera's detection sensitivity until Gemini stops calling its alerts false alarms.

Not part of upstream HA: added by camera-card (#3). Each chosen mode starts at full sensitivity. Every
`every` false alarms lowers it by `step`; `need` real ones in a row finishes it; it never goes below
`floor`. A false alarm while tuning is not pushed. Settings: `tuning:` in /config/camera_alerts.yaml.
"""
import datetime as dt

# HA is imported inside async_setup_tuning so the self-check at the bottom runs without it.

MODES = ("person", "vehicle", "animal", "motion")
DEFAULTS = {"start": 100, "step": 3, "every": 2, "need": 4, "floor": 30}
SETTINGS_FILE = "camera_alerts.yaml"
STORE_KEY = "reolink_tuning"
# reolink_aio's names; higher is more sensitive in both scales
AI_TYPE = {"person": "people", "vehicle": "vehicle", "animal": "dog_cat"}
MOTION_MAX = 50


def to_native(mode: str, pct: int) -> int:
    return max(1, round(pct * MOTION_MAX / 100)) if mode == "motion" else pct


def to_pct(mode: str, native: int) -> int:
    return round(native * 100 / MOTION_MAX) if mode == "motion" else native


def start(state: dict, ch: int, mode: str, before: int, cfg: dict, now: str) -> int:
    """Begin tuning; `before` is the camera's own value, restored on cancel. Returns the percent to set."""
    s = {**DEFAULTS, **cfg}
    state.setdefault(str(ch), {})[mode] = {
        "status": "tuning", "value": s["start"], "before": before, "cfg": s,
        "false": 0, "streak": 0, "real": 0, "empty": 0, "since": now, "ended": None,
    }
    return s["start"]


def cancel(state: dict, ch: int, mode: str) -> int | None:
    """Forget the mode; returns the camera's own value to put back, if it was still tuning."""
    m = state.get(str(ch), {}).pop(mode, None)
    return m["before"] if m and m["status"] == "tuning" else None


def tuning(state: dict, ch: int) -> bool:
    return any(m["status"] == "tuning" for m in state.get(str(ch), {}).values())


def record(state: dict, ch: int, mode: str, verdict: str | None, now: str) -> tuple[int | None, bool]:
    """Count one alert's verdict ('real', 'false', or anything else for unsure).

    Returns (new percent to set or None, whether to push the alert).
    """
    m = state.get(str(ch), {}).get(mode)
    if not m or m["status"] != "tuning":
        return None, True
    c = m["cfg"]
    if verdict == "real":
        m["real"] += 1
        m["streak"] += 1
        if m["streak"] >= c["need"]:
            m["status"], m["ended"] = "done", now
        return None, True
    if verdict != "false":
        return None, True  # unsure: counts for nothing, and might be someone
    m["empty"] += 1
    m["streak"] = 0
    m["false"] += 1
    if m["false"] < c["every"]:
        return None, False
    m["false"] = 0
    m["value"] = max(c["floor"], m["value"] - c["step"])
    if m["value"] <= c["floor"]:
        m["status"], m["ended"] = "floor", now
    return m["value"], False


def verdict_for(mode: str, seen: dict) -> str | None:
    """'real', 'false' or None from what Gemini saw: {'person'|'vehicle'|'animal': 'yes'|'no'|None}.

    Motion is a false alarm when none of the three is there, and real when any is.
    """
    kinds = ("person", "vehicle", "animal") if mode == "motion" else (mode,)
    said = [seen.get(k) for k in kinds]
    if "yes" in said:
        return "real"
    if said and all(s == "no" for s in said):
        return "false"
    return None


def async_setup_tuning(hass) -> None:
    import asyncio
    import logging

    import probatio
    import yaml
    from aiohttp import web

    from homeassistant.components.http import HomeAssistantView
    from homeassistant.core import SupportsResponse
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.storage import Store
    from homeassistant.util import dt as dt_util

    from .const import DOMAIN
    from .util import get_host

    log = logging.getLogger(__name__)
    store = Store(hass, 1, STORE_KEY)
    lock = asyncio.Lock()
    state: dict = {}
    loaded = False

    async def _state() -> dict:
        nonlocal state, loaded
        if not loaded:
            state, loaded = (await store.async_load()) or {}, True
        return state

    def _host():
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise web.HTTPServiceUnavailable(text="Reolink integration not loaded")
        return get_host(hass, entries[0].entry_id)  # one NVR, as card_api

    def _supported(api, ch: int, mode: str) -> bool:
        if mode == "motion":
            return api.supported(ch, "md_sensitivity")
        return api.supported(ch, "ai_sensitivity") and api.ai_supported(ch, AI_TYPE[mode])

    def _current(api, ch: int, mode: str) -> int:
        return api.md_sensitivity(ch) if mode == "motion" else api.ai_sensitivity(ch, AI_TYPE[mode])

    async def _set(api, ch: int, mode: str, native: int) -> None:
        if mode == "motion":
            await api.set_md_sensitivity(ch, int(native))
        else:
            await api.set_ai_sensitivity(ch, int(native), AI_TYPE[mode])

    def _read_cfg() -> dict:
        try:
            with open(hass.config.path(SETTINGS_FILE)) as f:
                return (yaml.safe_load(f) or {}).get("tuning") or {}
        except FileNotFoundError:
            return {}

    async def _cfg() -> dict:
        return await hass.async_add_executor_job(_read_cfg)

    def _now() -> str:
        return dt_util.now().isoformat(timespec="seconds")

    async def _async_verdict(call):
        """Called twice per alert: before describing (no answers) and after, with what Gemini saw."""
        ch, mode = call.data["channel"], call.data["trigger"].lower()
        seen = {k: v if (v := call.data.get(k)) in ("yes", "no") else None for k in ("person", "vehicle", "animal")}
        async with lock:
            st = await _state()
            was = tuning(st, ch)
            m = st.get(str(ch), {}).get(mode)
            this = bool(m and m["status"] == "tuning")
            pct, push = None, True
            if this and any(seen.values()):
                pct, push = record(st, ch, mode, verdict_for(mode, seen), _now())
                await store.async_save(st)
        if pct is not None:
            try:
                await _set(_host().api, ch, mode, to_native(mode, pct))
                log.info("Tuning ch %s %s: sensitivity now %s%%", ch, mode, pct)
            except Exception as err:  # noqa: BLE001 - a failed step still counts; the next one retries
                log.warning("Tuning ch %s %s: could not set %s%%: %s", ch, mode, pct, err)
        # tuning: the camera is tuning anything ([TUNING] prefix); tuning_mode: this trigger's kind is
        return {"tuning": was, "tuning_mode": this, "push": push}

    hass.services.async_register(
        DOMAIN,
        "tuning_verdict",
        _async_verdict,
        schema=probatio.Schema({
            probatio.Required("channel"): cv.positive_int,
            probatio.Required("trigger"): cv.string,
            probatio.Optional("person"): cv.string,
            probatio.Optional("vehicle"): cv.string,
            probatio.Optional("animal"): cv.string,
        }),
        supports_response=SupportsResponse.ONLY,
    )

    class TuningView(HomeAssistantView):
        """GET: each camera's modes and how tuning them is going. POST {action, channel?, modes?}: admins only."""

        requires_auth = True
        url = "/api/reolink/tuning"
        name = "api:reolink_tuning"

        async def get(self, request: web.Request) -> web.Response:
            if not request["hass_user"].is_admin:
                raise web.HTTPForbidden(text="admins only")
            api = _host().api
            st = await _state()
            cams = []
            for ch in api.channels:
                modes = {}
                for mode in MODES:
                    if not _supported(api, ch, mode):
                        continue
                    m = st.get(str(ch), {}).get(mode)
                    modes[mode] = {"now": to_pct(mode, _current(api, ch, mode))} | (
                        {k: m[k] for k in ("status", "value", "streak", "real", "empty", "since", "ended")}
                        | {"need": m["cfg"]["need"], "floor": m["cfg"]["floor"]} if m else {})
                if modes:
                    cams.append({"ch": ch, "name": api.camera_name(ch), "modes": modes})
            return self.json({"cameras": cams, "settings": {**DEFAULTS, **await _cfg()}})

        async def post(self, request: web.Request) -> web.Response:
            if not request["hass_user"].is_admin:
                raise web.HTTPForbidden(text="admins only")
            try:
                body = await request.json()
                action, picks = body["action"], body["picks"]  # picks: {channel: [mode, ...]}
                picks = {int(ch): [m for m in modes if m in MODES] for ch, modes in picks.items()}
            except (ValueError, KeyError, TypeError, AttributeError) as err:
                return web.Response(status=400, text=f"bad request: {err}")
            if action not in ("start", "cancel"):
                return web.Response(status=400, text="action must be start or cancel")
            api = _host().api
            failed = []
            async with lock:
                st = await _state()
                cfg = await _cfg()
                for ch, modes in picks.items():
                    for mode in modes:
                        if ch not in api.channels or not _supported(api, ch, mode):
                            continue
                        try:
                            if action == "start":
                                # restarting keeps the value from before the first start
                                old = st.get(str(ch), {}).get(mode)
                                before = old["before"] if old and old["status"] == "tuning" else _current(api, ch, mode)
                                await _set(api, ch, mode, to_native(mode, start(st, ch, mode, before, cfg, _now())))
                            elif (back := cancel(st, ch, mode)) is not None:
                                await _set(api, ch, mode, back)
                        except Exception as err:  # noqa: BLE001 - report it, carry on with the others
                            failed.append(f"{api.camera_name(ch)} {mode}: {err}")
                await store.async_save(st)
            return self.json({"failed": failed})

    hass.http.register_view(TuningView())


if __name__ == "__main__":  # python3 tuning.py
    st: dict = {}
    assert start(st, 3, "person", 60, {"need": 2}, "t0") == 100
    assert tuning(st, 3) and not tuning(st, 0)
    assert record(st, 3, "person", "false", "t1") == (None, False), "first false alarm: silent, no step yet"
    assert record(st, 3, "person", "false", "t2") == (97, False), "second: one step down"
    assert record(st, 3, "person", None, "t3") == (None, True), "unsure: pushed, uncounted"
    assert record(st, 3, "person", "real", "t4") == (None, True)
    assert record(st, 3, "person", "false", "t5") == (None, False), "breaks the streak"
    assert st["3"]["person"]["streak"] == 0
    record(st, 3, "person", "real", "t6")
    record(st, 3, "person", "real", "t7")
    assert st["3"]["person"]["status"] == "done" and not tuning(st, 3)
    assert record(st, 3, "person", "false", "t8") == (None, True), "done: back to normal alerts"
    assert cancel(st, 3, "person") is None, "a finished mode keeps its tuned value"

    start(st, 1, "vehicle", 50, {"start": 36, "step": 3, "every": 1, "floor": 30}, "t0")
    assert [record(st, 1, "vehicle", "false", "t")[0] for _ in range(3)] == [33, 30, None]
    assert st["1"]["vehicle"]["status"] == "floor"
    start(st, 1, "motion", 20, {}, "t0")
    assert cancel(st, 1, "motion") == 20 and "motion" not in st["1"]

    assert verdict_for("person", {"person": "yes"}) == "real"
    assert verdict_for("person", {"person": "no", "vehicle": "yes"}) == "false"
    assert verdict_for("animal", {"person": "yes"}) is None, "the animal question wasn't answered"
    assert verdict_for("motion", {"person": "no", "vehicle": "no", "animal": "no"}) == "false"
    assert verdict_for("motion", {"person": "no", "vehicle": None, "animal": "yes"}) == "real"
    assert verdict_for("motion", {"person": "no", "vehicle": None, "animal": "no"}) is None
    assert to_native("motion", 100) == 50 and to_native("motion", 1) == 1 and to_pct("motion", 25) == 50
    print("ok")
