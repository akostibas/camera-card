# /// script
# requires-python = ">=3.13"
# dependencies = ["pyyaml"]
# ///
"""Street activity question experiments. PAID: one decide call per (variant, recording).

  uv run alerts/experiments/street_questions.py SETTINGS.yaml VARIANT[,VARIANT...]
  uv run alerts/experiments/street_questions.py SETTINGS.yaml EVAL_RESULTS.json   score eval.py's saved answers

Results are appended to results.jsonl in the test library. TRUTH is from the street recordings' notes.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "custom_components/reolink"))
from keyframe_pick import pick  # noqa: E402

MAIN = Path(subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()).parent
LIB = MAIN / "testdata/street"
HERE = LIB  # results and crops stay in the gitignored library
SCENE = yaml.safe_load(Path(sys.argv[1]).read_text())["cameras"]["street"]["scene"] + " Images are in time order."

# canonical activities; required must be claimed, allowed may be, anything else claimed is invented
TRUTH = {
    "2026-11-26T09-54-08": ({"car"}, {"walk"}),
    "2026-11-26T12-07-19": ({"car"}, {"walk"}),
    "2026-11-26T14-39-05": ({"walk"}, set()),
    "2026-11-26T15-16-21": ({"trolley"}, {"walk"}),
    "2026-11-26T16-33-03": ({"walk"}, set()),
    "2026-11-26T17-00-49": ({"walk"}, set()),
}
SURE = 0.6

BASE_ACTS = {  # today's actions_list -> canonical
    "getting out of the Leaf": "car", "getting out of the Bolt": "car", "getting out of another car": "car",
    "walking a dog": "dog", "jogging": "jog", "pushing a stroller": "stroller",
    "riding a bicycle or scooter": "bike", "smoking": "smoke", "delivering mail or a package": "delivery",
    "putting out or bringing in trash cans": "trash", "looking into parked cars": "car",
    "getting into the Leaf": "car", "getting into the Bolt": "car", "getting into another car": "car",
    "walking up to the house": "porch", "walking by": "walk",
}

MAIN = {"walking by": "walk", "walking a dog": "dog", "pushing a stroller": "stroller",
        "pulling a cart, trolley or luggage": "trolley", "moving trash bins": "trash", "delivering a package": "delivery",
        "jogging or running": "jog", "riding a bike or scooter": "bike", "getting into or out of a car": "car",
        "walking up to the house": "porch", "standing around or talking": "stand"}

OBJECT_Q = ("obj=Look strictly at what the people on the sidewalk or street are holding, pulling, or pushing. "
            "Which single option best matches the clearest visual evidence?:"
            "a dog on a leash,a baby stroller,a wheeled shopping bag or trolley or luggage,a wheeled trash or recycling bin,"
            "a delivery box or package,nothing or empty-handed or unclear in shadow")
OBJ_MAP = {"a dog on a leash": "dog", "a baby stroller": "stroller", "a wheeled shopping bag or trolley or luggage": "trolley",
           "a wheeled trash or recycling bin": "trash", "a delivery box or package": "delivery"}
WHERE_Q = ("where=Where do the people in these images go?:they stay on the public sidewalk or street passing by,"
           "at least one walks up the front steps toward the house,at least one goes to or gets into or out of a parked car,"
           "at least one moves trash bins between the house and the curb")
WHERE_MAP = {"they stay on the public sidewalk or street passing by": "walk",
             "at least one walks up the front steps toward the house": "porch",
             "at least one goes to or gets into or out of a parked car": "car",
             "at least one moves trash bins between the house and the curb": "trash"}
PACE_Q = ("pace=Compare body posture and how far people move between consecutive images. Are they:"
          "walking at a normal pace,jogging or running,standing still,riding a bike or scooter")
PACE_MAP = {"walking at a normal pace": "walk", "jogging or running": "jog", "riding a bike or scooter": "bike"}
SMOKE_Q = ("smoke=Is there enough light and detail on people's hands and faces to see a small held object, and is anyone smoking?:"
           "yes a cigarette or vape or smoke is clearly visible,hands and faces are clear and nobody is smoking,"
           "too backlit or distant or dark to tell")


def combo_args():
    return ["--choice", OBJECT_Q, "--choice", WHERE_Q, "--choice", PACE_Q, "--choice", SMOKE_Q]


def combo_claims(a):
    out = set()
    for key, m in (("obj", OBJ_MAP), ("where", WHERE_MAP), ("pace", PACE_MAP)):
        if a[key]["confidence"] >= SURE and a[key]["choice"] in m:
            out.add(m[a[key]["choice"]])
    if a["smoke"]["choice"].startswith("yes") and a["smoke"]["confidence"] >= SURE:
        out.add("smoke")
    return out


EVIDENCE = {  # object-presence yes/no with an explicit veto for shadow
    "dog": "Ignore posture and arm position. Is a live dog (a recognisable head, body or legs) clearly visible in any image? Answer no if near the person there is only a dark shadow or an object.",
    "stroller": "Is a baby stroller or pram (a seat on wheels with a canopy or handle) clearly visible in any image?",
    "trolley": "Is a wheeled shopping trolley, cart, or rolling suitcase clearly visible being pulled or pushed in any image?",
    "trash": "Is a wheeled trash or recycling bin being moved by a person in any image (not just standing at the curb)?",
    "delivery": "Is anyone clearly carrying a package or mail toward the house in any image?",
    "smoke": "Is a cigarette, vape, or smoke clearly visible at someone's hand or mouth in any image? Answer no if hands and faces are too dark or small to see.",
    "jog": "Comparing consecutive images, does anyone cover distance clearly faster than walking, with a running stride?",
    "car": "Does anyone get into, get out of, or load or unload a parked car in any image?",
    "walk": "Does anyone simply walk along the sidewalk or street past the house?",
}

PERSON_OPTS = list(MAIN) + ["there is no such person"]


def person_args():
    args = []
    for i, nth in enumerate(("first", "second", "third"), 1):
        args += ["--choice", f"p{i}=What is the main thing the {nth} different person to appear in the images is doing?:" + ",".join(PERSON_OPTS)]
    return args


def person_claims(a):
    return {MAIN[a[k]["choice"]] for k in ("p1", "p2", "p3") if a[k]["choice"] in MAIN and a[k]["confidence"] >= SURE}


VARIANTS = {
    # name: (args builder, claims, decide extra flags, crop)
    "base_hi": (lambda: [x for i, act in enumerate(BASE_ACTS, 1) for x in ("--yesno", f"act{i}=Is anyone {act} at any point in these images?")],
                lambda a: {BASE_ACTS[act] for i, act in enumerate(BASE_ACTS, 1) if a[f"act{i}"]["answer"] == "yes" and a[f"act{i}"]["confidence"] >= SURE},
                ["--resolution", "high"], False),
    "main": (lambda: ["--choice", "main=What were the people in these images mainly doing?:" + ",".join(MAIN),
                      "--choice", "also=What else did anyone do, besides that?:" + ",".join(MAIN) + ",nothing else"],
             lambda a: {MAIN[a[k]["choice"]] for k in ("main", "also") if a[k]["choice"] in MAIN and a[k]["confidence"] >= SURE},
             [], False),
    "combo": (combo_args, combo_claims, [], False),
    "combo_crop": (combo_args, combo_claims, [], True),
    "combo2": (combo_args, combo_claims, [], False),
    "combo_hi": (combo_args, combo_claims, ["--resolution", "high"], False),
    "combo_ultra": (combo_args, combo_claims, ["--resolution", "ultra_high"], False),
    "evidence": (lambda: [x for k, q in EVIDENCE.items() for x in ("--yesno", f"{k}={q}")],
                 lambda a: {k for k in EVIDENCE if a[k]["answer"] == "yes" and a[k]["confidence"] >= SURE},
                 [], False),
    "person": (person_args, person_claims, [], False),
}


def frames(rec, crop):
    clip = yaml.safe_load((rec / "clip.yaml").read_text())
    pics = sorted(rec.glob("k*.jpg"))
    times = [yaml.safe_load(p.with_suffix(".yaml").read_text())["time"] for p in pics]
    files = [pics[i] for i in pick(times, [tuple(w) for w in clip["seen"]], 16)]
    if not crop:
        return [str(f) for f in files]
    out = HERE / "crops" / rec.name
    out.mkdir(parents=True, exist_ok=True)
    for f in files:  # the sidewalk and steps: lower-left, without sky and door frame
        if not (out / f.name).exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(f), "-vf", "crop=iw*0.6:ih*0.55:iw*0.15:ih*0.45",
                            str(out / f.name)], check=True)
    return [str(out / f.name) for f in files]


def run(variant, rec):
    build, claims, extra, crop = VARIANTS[variant]
    files = frames(rec, crop)
    args = ["ask-gemini", "decide", *extra, *[x for f in files for x in ("--file", f)], *build(), SCENE]
    r = subprocess.run(args, capture_output=True, text=True, timeout=180)
    if r.returncode:
        return {"variant": variant, "rec": rec.name, "error": r.stderr[-300:]}
    a = {k: v for k, v in json.loads(r.stdout).items() if isinstance(v, dict)}
    need, ok = TRUTH[rec.name]
    got = claims(a)
    return {"variant": variant, "rec": rec.name, "claims": sorted(got), "missed": sorted(need - got),
            "invented": sorted(got - need - ok), "answers": a}


def score_saved(path):
    """Today's street questions, from eval.py's saved answers: free."""
    for r in json.loads(Path(path).read_text()):
        a, need = r["answers"], TRUTH[r["recording"]]
        got = {BASE_ACTS[act] for i, act in enumerate(BASE_ACTS, 1) if a[f"act{i}"]["answer"] == "yes" and a[f"act{i}"]["confidence"] >= SURE}
        print(f"  {r['recording'][11:16]}  claims {sorted(got)}  missed {sorted(need[0] - got)}  invented {sorted(got - need[0] - need[1])}")


def main():
    if sys.argv[2].endswith(".json"):
        return score_saved(sys.argv[2])
    jobs = [(v, LIB / r) for v in sys.argv[2].split(",") for r in TRUTH]
    with ThreadPoolExecutor(8) as pool:
        res = list(pool.map(lambda j: run(*j), jobs))
    with open(HERE / "results.jsonl", "a") as f:
        for r in res:
            f.write(json.dumps(r) + "\n")
    for v in sys.argv[2].split(","):
        rows = [r for r in res if r["variant"] == v]
        miss = sum(len(r.get("missed", [])) for r in rows)
        inv = sum(len(r.get("invented", [])) for r in rows)
        errs = sum("error" in r for r in rows)
        print(f"\n## {v}: missed {miss}, invented {inv}" + (f", ERRORS {errs}" if errs else ""))
        for r in rows:
            print(f"  {r['rec'][11:16]}  " + (r["error"].strip()[-120:] if "error" in r else
                  f"claims {r['claims']}  missed {r['missed']}  invented {r['invented']}"))


if __name__ == "__main__":
    main()
