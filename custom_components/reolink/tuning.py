"""Auto-tune: lower a camera's detection sensitivity until Gemini stops calling its alerts false alarms.

Not part of upstream HA: added by camera-card (#3). Each chosen kind (person, vehicle, animal) starts at
`start`. False alarms fill a bucket that drains `per_week` a week (and a little per real detection); a
bucket over `allow` lowers sensitivity by `step`, never below `floor`. False alarms within `burst`
minutes of an incident's first are part of it. Done after `days` with no step down, so it lives through
nights. Detections that don't alert cost an extra Gemini call each, so those get at most `cap` a day in
all and `cap_each` per camera kind; a day out of calls doesn't count toward `days`. False alarms are not
pushed while tuning. Settings: `tuning:` in /config/camera_alerts.yaml.
"""
from datetime import datetime, timedelta

# HA is imported inside async_setup_tuning so the self-check at the bottom runs without it.

MODES = ("person", "vehicle", "animal")
DEFAULTS = {"start": 100, "step": 5, "floor": 30, "allow": 1, "per_week": 1, "real_credit": 0.05,
            "burst": 15, "days": 2, "cap": 150, "cap_each": 25}
SETTINGS_FILE = "camera_alerts.yaml"
STORE_KEY = "reolink_tuning"
AI_TYPE = {"person": "people", "vehicle": "vehicle", "animal": "dog_cat"}  # reolink_aio's names
CALLS = "_calls"  # state key for the day's extra Gemini calls, all cameras


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s)


def start(state: dict, ch: int, mode: str, before: int, cfg: dict, now: str) -> int:
    """Begin tuning; `before` is the camera's own value, restored on cancel. Returns the percent to set."""
    s = {**DEFAULTS, **cfg}
    state.setdefault(str(ch), {})[mode] = {
        "status": "tuning", "value": s["start"], "before": before, "cfg": s, "bucket": 0.0, "at": now,
        "incident": None, "step_at": now, "lost": 0, "paused": None, "calls": [now[:10], 0],
        "real": 0, "empty": 0, "since": now, "ended": None,
    }
    return s["start"]


def cancel(state: dict, ch: int, mode: str) -> int | None:
    """Forget the mode; returns the camera's own value to put back, if it was still tuning."""
    m = state.get(str(ch), {}).pop(mode, None)
    return m["before"] if m and m["status"] == "tuning" else None


def _tuning(state: dict, ch: int, mode: str) -> dict | None:
    m = state.get(str(ch), {}).get(mode)
    return m if m and m["status"] == "tuning" else None


def tuning(state: dict, ch: int) -> bool:
    return any(_tuning(state, ch, k) for k in MODES)


def _leak(m: dict, now: str) -> None:
    days = (_t(now) - _t(m["at"])).total_seconds() / 86400
    m["bucket"], m["at"] = max(0.0, m["bucket"] - days * m["cfg"]["per_week"] / 7), now


def _resume(m: dict, now: str) -> None:
    """A day out of calls doesn't count as quiet: add it to `lost`."""
    if m["paused"] and m["paused"][:10] < now[:10]:
        p = _t(m["paused"])
        midnight = datetime.combine(p.date() + timedelta(days=1), datetime.min.time(), p.tzinfo)
        m["lost"] += (midnight - p).total_seconds()
        m["paused"] = None


def judge(state: dict, ch: int, mode: str, now: str) -> bool:
    """Whether to spend a Gemini call on a detection that doesn't alert; counts it if so."""
    m = _tuning(state, ch, mode)
    if not m:
        return False
    _resume(m, now)
    c = m["cfg"]
    if m["incident"] and _t(now) - _t(m["incident"]) < timedelta(minutes=c["burst"]):
        return False  # part of an incident already counted
    day = now[:10]
    total = state.setdefault(CALLS, [day, 0])
    if total[0] != day:
        total[:] = [day, 0]
    if m["calls"][0] != day:
        m["calls"] = [day, 0]
    if total[1] >= c["cap"] or m["calls"][1] >= c["cap_each"]:
        m["paused"] = m["paused"] or now
        return False
    total[1] += 1
    m["calls"][1] += 1
    return True


def record(state: dict, ch: int, mode: str, verdict: str | None, now: str) -> tuple[int | None, bool]:
    """Count one detection's verdict ('real', 'false', or anything else for unsure).

    Returns (new percent to set or None, whether to push the alert).
    """
    m = _tuning(state, ch, mode)
    if not m:
        return None, True
    c = m["cfg"]
    _leak(m, now)
    if verdict == "real":
        m["real"] += 1
        m["bucket"] = max(0.0, m["bucket"] - c["real_credit"])
        return None, True
    if verdict != "false":
        return None, True  # unsure: counts for nothing, and might be someone
    m["empty"] += 1
    if m["incident"] and _t(now) - _t(m["incident"]) < timedelta(minutes=c["burst"]):
        return None, False
    m["incident"] = now
    m["bucket"] += 1
    if m["bucket"] <= c["allow"]:
        return None, False
    m["value"] = max(c["floor"], m["value"] - c["step"])
    m["bucket"], m["step_at"], m["lost"] = 0.0, now, 0
    if m["value"] <= c["floor"]:
        m["status"], m["ended"] = "floor", now
    return m["value"], False


def due(m: dict) -> str:
    """When the mode finishes if it stays under budget."""
    return (_t(m["step_at"]) + timedelta(days=m["cfg"]["days"], seconds=m["lost"])).isoformat()


def settle(state: dict, now: str) -> bool:
    """Finish every mode that has gone `days` without a step down; True if any did. Run hourly."""
    changed = False
    for ch, modes in state.items():
        if ch == CALLS:
            continue
        for m in modes.values():
            if m["status"] != "tuning" or m["paused"]:
                continue
            _leak(m, now)
            if now >= due(m):
                m["status"], m["ended"], changed = "done", now, True
    return changed


def verdict_for(mode: str, seen: dict) -> str | None:
    """'real', 'false' or None from what Gemini saw: {'person'|'vehicle'|'animal': 'yes'|'no'|None}."""
    return {"yes": "real", "no": "false"}.get(seen.get(mode))


def async_setup_tuning(hass) -> None:
    import asyncio
    import logging

    import probatio
    import yaml
    from aiohttp import web

    from homeassistant.components.http import HomeAssistantView
    from homeassistant.core import SupportsResponse
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.event import async_track_time_interval
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
            for ch, modes in state.items():  # COMPAT: remove after 2026-12-27 (pre-bucket test runs)
                if ch != CALLS:
                    state[ch] = {k: m for k, m in modes.items() if k in MODES and "bucket" in m}
        return state

    def _host():
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise web.HTTPServiceUnavailable(text="Reolink integration not loaded")
        return get_host(hass, entries[0].entry_id)  # one NVR, as card_api

    def _supported(api, ch: int, mode: str) -> bool:
        return api.supported(ch, "ai_sensitivity") and api.ai_supported(ch, AI_TYPE[mode])

    def _current(api, ch: int, mode: str) -> int:
        return api.ai_sensitivity(ch, AI_TYPE[mode])

    async def _set(api, ch: int, mode: str, pct: int) -> None:
        await api.set_ai_sensitivity(ch, int(pct), AI_TYPE[mode])

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
        """Before describing (`judge` for detections that don't alert) and after, with what Gemini saw."""
        ch, mode = call.data["channel"], call.data["trigger"].lower()
        mode = {"pet": "animal"}.get(mode, mode)
        seen = {k: v if (v := call.data.get(k)) in ("yes", "no") else None for k in MODES}
        async with lock:
            st = await _state()
            was = tuning(st, ch)
            this = bool(_tuning(st, ch, mode))
            pct, push, spend = None, True, False
            if this and any(seen.values()):
                pct, push = record(st, ch, mode, verdict_for(mode, seen), _now())
            elif this and call.data.get("judge"):
                spend = judge(st, ch, mode, _now())
            if this:
                await store.async_save(st)
        if pct is not None:
            try:
                await _set(_host().api, ch, mode, pct)
                log.info("Tuning ch %s %s: sensitivity now %s%%", ch, mode, pct)
            except Exception as err:  # noqa: BLE001 - a failed step still counts; the next one retries
                log.warning("Tuning ch %s %s: could not set %s%%: %s", ch, mode, pct, err)
        # tuning: the camera is tuning anything ([TUNING] prefix); judge: worth a Gemini call
        return {"tuning": was, "tuning_mode": this, "judge": spend, "push": push}

    hass.services.async_register(
        DOMAIN,
        "tuning_verdict",
        _async_verdict,
        schema=probatio.Schema({
            probatio.Required("channel"): cv.positive_int,
            probatio.Required("trigger"): cv.string,
            probatio.Optional("judge"): cv.boolean,
            probatio.Optional("person"): cv.string,
            probatio.Optional("vehicle"): cv.string,
            probatio.Optional("animal"): cv.string,
        }),
        supports_response=SupportsResponse.ONLY,
    )

    async def _settle(_now_dt=None) -> None:
        async with lock:
            st = await _state()
            if settle(st, _now()):
                await store.async_save(st)

    async_track_time_interval(hass, _settle, timedelta(hours=1))

    class TuningView(HomeAssistantView):
        """GET: each camera's kinds and how tuning them is going. POST {action, picks}: admins only."""

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
                    modes[mode] = {"now": _current(api, ch, mode)} | (
                        {k: m[k] for k in ("status", "value", "real", "empty", "since", "ended", "paused")}
                        | {"due": due(m), "floor": m["cfg"]["floor"]} if m else {})
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
                                old = _tuning(st, ch, mode)
                                before = old["before"] if old else _current(api, ch, mode)
                                await _set(api, ch, mode, start(st, ch, mode, before, cfg, _now()))
                            elif (back := cancel(st, ch, mode)) is not None:
                                await _set(api, ch, mode, back)
                        except Exception as err:  # noqa: BLE001 - report it, carry on with the others
                            failed.append(f"{api.camera_name(ch)} {mode}: {err}")
                await store.async_save(st)
            return self.json({"failed": failed})

    hass.http.register_view(TuningView())


if __name__ == "__main__":  # python3 tuning.py
    T = "2026-11-27T{}:00-08:00"
    st: dict = {}
    assert start(st, 3, "person", 60, {}, T.format("09:00")) == 100
    assert tuning(st, 3) and not tuning(st, 0)
    assert record(st, 3, "person", "false", T.format("09:10")) == (None, False), "first incident: silent"
    assert record(st, 3, "person", "false", T.format("09:20")) == (None, False), "same burst: not counted"
    assert st["3"]["person"]["bucket"] < 1.01
    assert record(st, 3, "person", None, T.format("09:30")) == (None, True), "unsure: pushed, uncounted"
    assert record(st, 3, "person", "false", T.format("10:00")) == (95, False), "second incident: one step"
    assert record(st, 3, "person", "real", T.format("10:10")) == (None, True)
    assert not settle(st, "2026-11-28T10:00:00-08:00"), "one day isn't two nights"
    assert settle(st, "2026-11-29T10:01:00-08:00") and not tuning(st, 3), "two quiet days: done"
    assert record(st, 3, "person", "false", T.format("11:00")) == (None, True), "done: back to normal alerts"
    assert cancel(st, 3, "person") is None, "a finished mode keeps its tuned value"

    # a slow trickle drains away: 1 a week never steps down
    start(st, 2, "animal", 40, {}, "2026-11-01T00:00:00-08:00")
    for d in ("02", "10", "18"):
        assert record(st, 2, "animal", "false", f"2026-11-{d}T00:00:00-08:00")[0] is None
    assert st["2"]["animal"]["value"] == 100

    start(st, 1, "vehicle", 50, {"start": 40, "allow": 0, "burst": 0}, T.format("09:00"))
    assert [record(st, 1, "vehicle", "false", T.format(f"09:0{i}"))[0] for i in (1, 2, 3)] == [35, 30, None]
    assert st["1"]["vehicle"]["status"] == "floor"

    # extra calls: capped per kind, and a day out of calls doesn't count toward finishing
    start(st, 5, "vehicle", 60, {"cap_each": 2}, T.format("09:00"))
    assert [judge(st, 5, "vehicle", T.format(f"09:0{i}")) for i in (1, 2, 3)] == [True, True, False]
    assert st["5"]["vehicle"]["paused"] == T.format("09:03")
    assert judge(st, 5, "vehicle", "2026-11-28T08:00:00-08:00")
    assert st["5"]["vehicle"]["lost"] == (24 * 60 - 9 * 60 - 3) * 60
    record(st, 5, "vehicle", "false", "2026-11-28T08:00:00-08:00")
    assert not judge(st, 5, "vehicle", "2026-11-28T08:05:00-08:00"), "inside a burst: no call"

    assert verdict_for("person", {"person": "yes"}) == "real"
    assert verdict_for("person", {"person": "no", "vehicle": "yes"}) == "false"
    assert verdict_for("animal", {"person": "yes"}) is None
    print("ok")
