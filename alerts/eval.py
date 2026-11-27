# /// script
# requires-python = ">=3.13"
# dependencies = ["pyyaml"]
# ///
"""Describe every labeled recording of a camera and print it beside the truth. PAID: one call each.

  uv run alerts/eval.py SETTINGS.yaml CAMERA [RECORDING...] [--save RESULTS.json]

Recordings come from the test library (bin/testdata). Each sends the same 16 pictures production would
(custom_components/reolink/keyframe_pick.py). The truth is the latest recording note with a
people_count; a note by someone other than a model wins over a model's.
"""
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components/reolink"))  # the module alone: the package needs Home Assistant
from keyframe_pick import pick  # noqa: E402
from describe import ask, named  # noqa: E402
from message import message  # noqa: E402

MAIN = Path(subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()).parent
LIB = MAIN / "testdata"


def truth(rec):
    notes = [n for n in yaml.safe_load((rec / "clip.yaml").read_text()).get("notes", []) if "people_count" in n]
    human = [n for n in notes if not str(n["by"]).startswith("claude")]
    best = (human or notes or [{}])[-1]
    # a human's note may give only the count: take the people from the model note it corrects
    people = best.get("people") or next((n.get("people") for n in reversed(notes) if n.get("people")), [])
    return best.get("people_count"), best.get("by"), [f"{p.get('looks')}: {', '.join(p.get('doing', []))}" for p in people]


def main(argv):
    save = argv[argv.index("--save") + 1] if "--save" in argv else None
    argv = [a for i, a in enumerate(argv) if a != "--save" and (i == 0 or argv[i - 1] != "--save")]
    settings_path, camera, *only = argv
    settings = yaml.safe_load(Path(settings_path).read_text())
    cfg, t = settings["cameras"][camera], settings["thresholds"]
    out = []
    for rec in sorted((LIB / camera).iterdir()):
        if only and rec.name not in only or not (rec / "clip.yaml").exists():
            continue
        clip = yaml.safe_load((rec / "clip.yaml").read_text())
        pics = sorted(rec.glob("k*.jpg"))
        times = [yaml.safe_load(p.with_suffix(".yaml").read_text())["time"] for p in pics]
        files = [str(pics[i]) for i in pick(times, [tuple(w) for w in clip["seen"]], 16)]
        answers = ask(cfg, files, timeout=90)  # uploading from here is slower than from the host
        text = message(cfg, t, answers, "Person")
        count, by, people = truth(rec)
        print(f"\n== {rec.name}  truth: {count} people (by {by})")
        for p in people:
            print(f"   - {p}")
        print(f"   model: {text}")
        for name, ans, conf in named(cfg, answers):
            if ans not in ("no", "0") or name in ("count", "person"):
                print(f"     {name}: {ans} {conf:.0%}")
        out.append({"recording": rec.name, "truth": count, "text": text, "answers": answers})
    if save:
        Path(save).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
