"""Print the alert text for what a camera saw.

  python3 describe.py [--unpushed] SETTINGS.yaml CAMERA TRIGGER [PICTURE...]

TRIGGER is what the camera detected ("Person"). With pictures this makes ONE PAID model call
(ask-gemini on PATH, GEMINI_API_KEY set) and lists the answers on stderr. With no pictures, or
if the model fails or is slow, it prints the plain wording and costs nothing.

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

from message import message, questions

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
    """(the text, a warning that the day's limit was just reached or '')."""
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
        return message(cfg, t, answers, trigger), warning
    except Exception as err:  # whatever went wrong, the alert still goes out
        print(f"describe: {err!r}", file=sys.stderr)
        return message(cfg, t, None, trigger), warning


def describe(settings, camera, trigger, files, ask=ask, spend=None):
    """The text of a pushed alert."""
    return " ".join(filter(None, _describe(settings, camera, trigger, files, ask, spend)))


def describe_unpushed(settings, camera, trigger, files, ask=ask, spend=None):
    """(text, exit status) for an event nobody is alerted about: ('', 0) when there is nothing to keep."""
    cfg = settings["cameras"][camera]
    level = cfg.get("describe", "push")
    if level not in LEVELS:
        raise ValueError(f"{camera}: describe must be one of {', '.join(LEVELS)}, not {level!r}")
    if level == "push" or (level == "event" and trigger == "Motion") or not files:
        return "", 0
    # the fallback is worded for the push ("Someone is at the door"); here the plain wording is never shown
    quiet = {**settings, "cameras": {camera: {k: v for k, v in cfg.items() if k != "fallback"}}}
    text, warning = _describe(quiet, camera, trigger, files, ask, spend)
    if warning:
        return warning, 3
    plain = message(quiet["cameras"][camera], settings["thresholds"], None, trigger)
    return ("" if text == plain else text), 0


if __name__ == "__main__":
    args = sys.argv[1:]
    unpushed = args[:1] == ["--unpushed"]
    args = args[unpushed:]
    if len(args) < 3:
        sys.exit(__doc__)
    with open(args[0]) as f:
        settings = yaml.safe_load(f)
    spend = budget(args[0] + ".count", settings.get("daily_limit", 500), date.today().isoformat())
    if unpushed:
        text, status = describe_unpushed(settings, args[1], args[2], args[3:], spend=spend)
        print(text)
        sys.exit(status)
    print(describe(settings, args[1], args[2], args[3:], spend=spend))
