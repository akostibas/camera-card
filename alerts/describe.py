"""Print the alert text for what a camera saw.

  python3 describe.py SETTINGS.yaml CAMERA TRIGGER [PICTURE...]

TRIGGER is what the camera detected ("Person"). With pictures this makes ONE PAID model call
(ask-gemini on PATH, GEMINI_API_KEY set) and lists the answers on stderr. With no pictures, or
if the model fails or is slow, it prints the plain wording and costs nothing.
"""
import json
import subprocess
import sys

import yaml

from message import message, questions


def ask(cfg, files):
    """The model's answers about these pictures, keyed by question. Paid."""
    out = subprocess.run(["ask-gemini", "decide", *questions(cfg, files)],
                         capture_output=True, text=True, check=True, timeout=15).stdout
    return {k: v for k, v in json.loads(out).items() if isinstance(v, dict)}


def named(cfg, answers):
    """Answers as (readable question, answer, confidence), e.g. ('leaving through the gate', 'yes', 0.9)."""
    names = {f"act{i}": act for i, act in enumerate(cfg.get("actions_list", []), 1)}
    return [(names.get(k, k), v.get("answer") or v.get("choice"), v["confidence"]) for k, v in answers.items()]


def describe(settings, camera, trigger, files, ask=ask):
    cfg, t = settings["cameras"][camera], settings["thresholds"]
    # at most 16 pictures, evenly spaced: keyframes come every 1-2s, so a minute of footage has up to 75
    files = files[::(len(files) + 15) // 16 or 1]
    try:
        answers = ask(cfg, files) if files else None
        for name, answer, confidence in named(cfg, answers or {}):
            print(f"  {name}: {answer} {confidence:.0%}", file=sys.stderr)
        return message(cfg, t, answers, trigger)
    except Exception as err:  # whatever went wrong, the alert still goes out
        print(f"describe: {err!r}", file=sys.stderr)
        return message(cfg, t, None, trigger)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    with open(sys.argv[1]) as f:
        print(describe(yaml.safe_load(f), sys.argv[2], sys.argv[3], sys.argv[4:]))
