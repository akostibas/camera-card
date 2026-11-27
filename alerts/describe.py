"""Print the alert text for what a camera saw.

  python3 describe.py [--unpushed] [--json] SETTINGS.yaml CAMERA TRIGGER [PICTURE...]

TRIGGER is what the camera detected ("Person"). With pictures this makes ONE PAID model call
(ask-gemini on PATH, GEMINI_API_KEY set) and lists the answers on stderr. With no pictures, or
if the model fails or is slow, it prints the plain wording and costs nothing.

--json prints {"text": ..., "seen": {"person"|"vehicle"|"animal": "yes"|"no"|null}} instead, so
auto-tuning (camera-card#3) can tell a false alarm. seen is all null when the model wasn't asked.

--unpushed is for an event nobody is being alerted about, described only so it can be shown
later. It prints nothing unless the camera's `describe` setting covers the event and the model
had something to say.

Paid calls are counted in SETTINGS.yaml.count and stop for the day at the settings' daily_limit.
The first call refused says so: on the end of a pushed alert, or alone with exit status 3 when
--unpushed.
"""
import fcntl
import json
import subprocess
import sys
from datetime import date

import yaml

from message import message, questions, seen

LEVELS = ("push", "event", "motion")  # each describes everything the one before it does


def ask(cfg, files):
    """The model's answers about these pictures, keyed by question. Paid."""
    out = subprocess.run(["ask-gemini", "decide", *questions(cfg, files)],
                         capture_output=True, text=True, check=True, timeout=15).stdout
    return {k: v for k, v in json.loads(out).items() if isinstance(v, dict)}


def named(cfg, answers):
    """Answers as (readable question, answer, confidence), e.g. ('leaving through the gate', 'yes', 0.9)."""
    names = {f"act{i}": act for i, act in enumerate(cfg.get("actions_list", []), 1)}
    names |= {f"vact{i}": f"vehicle {act}" for i, act in enumerate(cfg.get("vehicle_actions_list", []), 1)}
    return [(names.get(k, k), v.get("answer") or v.get("choice"), v["confidence"]) for k, v in answers.items()]


def budget(path, limit, today):
    """A check to run before each paid call: budget(...)(camera) -> (go ahead, warning to pass on)."""
    def spend(camera):
        with open(path, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)  # cameras are described at the same time
            f.seek(0)
            try:
                s = json.loads(f.read())
            except ValueError:
                s = {}
            if s.get("day") != today:
                s = {"day": today, "by": {}, "warned": False}
            ok, warning = sum(s["by"].values()) < limit, ""
            if ok:
                s["by"][camera] = s["by"].get(camera, 0) + 1
            elif not s["warned"]:
                top = max(s["by"], key=s["by"].get, default=camera)
                warning = (f"Descriptions have stopped until tomorrow: today's limit of {limit} is used up. "
                           f"{top.replace('_', ' ').capitalize()} used the most ({s['by'].get(top, 0)}).")
                s["warned"] = True
            f.seek(0)
            f.truncate()
            json.dump(s, f)
        return ok, warning
    return spend


def _describe(settings, camera, trigger, files, ask, spend):
    """(the text, a warning that the day's limit was just reached or '', the model's answers or None)."""
    cfg, t = settings["cameras"][camera], settings["thresholds"]
    # at most 16 pictures, evenly spaced: keyframes come every 1-2s, so a minute of footage has up to 75
    files = files[::(len(files) + 15) // 16 or 1]
    warning = ""
    try:
        if files and spend:
            try:
                ok, warning = spend(camera)
            except OSError as err:  # a broken count must not cost the household its descriptions
                print(f"describe: not counted: {err!r}", file=sys.stderr)
                ok = True
            files = files if ok else []
        answers = ask(cfg, files) if files else None
        for name, answer, confidence in named(cfg, answers or {}):
            print(f"  {name}: {answer} {confidence:.0%}", file=sys.stderr)
        return message(cfg, t, answers, trigger), warning, answers
    except Exception as err:  # whatever went wrong, the alert still goes out
        print(f"describe: {err!r}", file=sys.stderr)
        return message(cfg, t, None, trigger), warning, None


def describe(settings, camera, trigger, files, ask=ask, spend=None):
    """(the text of a pushed alert, what the model saw)."""
    text, warning, answers = _describe(settings, camera, trigger, files, ask, spend)
    return " ".join(filter(None, (text, warning))), seen(answers, settings["thresholds"])


def describe_unpushed(settings, camera, trigger, files, ask=ask, spend=None):
    """(text, exit status, what the model saw) for an event nobody is alerted about: text '' when there is nothing to keep."""
    cfg = settings["cameras"][camera]
    level = cfg.get("describe", "push")
    if level not in LEVELS:
        raise ValueError(f"{camera}: describe must be one of {', '.join(LEVELS)}, not {level!r}")
    if level == "push" or (level == "event" and trigger == "Motion") or not files:
        return "", 0, seen(None, settings["thresholds"])
    # the fallback is worded for the push ("Someone is at the door"); here the plain wording is never shown
    quiet = {**settings, "cameras": {camera: {k: v for k, v in cfg.items() if k != "fallback"}}}
    text, warning, answers = _describe(quiet, camera, trigger, files, ask, spend)
    saw = seen(answers, settings["thresholds"])
    if warning:
        return warning, 3, saw
    plain = message(quiet["cameras"][camera], settings["thresholds"], None, trigger)
    return ("" if text == plain else text), 0, saw


if __name__ == "__main__":
    args = sys.argv[1:]
    unpushed, as_json = "--unpushed" in args[:2], "--json" in args[:2]
    args = [a for a in args[:2] if a not in ("--unpushed", "--json")] + args[2:]
    if len(args) < 3:
        sys.exit(__doc__)
    with open(args[0]) as f:
        settings = yaml.safe_load(f)
    spend = budget(args[0] + ".count", settings.get("daily_limit", 500), date.today().isoformat())
    if unpushed:
        text, status, saw = describe_unpushed(settings, args[1], args[2], args[3:], spend=spend)
    else:
        (text, saw), status = describe(settings, args[1], args[2], args[3:], spend=spend), 0
    print(json.dumps({"text": text, "seen": saw}) if as_json else text)
    sys.exit(status)
