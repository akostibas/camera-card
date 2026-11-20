# /// script
# requires-python = ">=3.13"
# dependencies = ["jinja2", "pyyaml"]
# ///
"""Check the alert wording.

  uv run test_message.py                       assert the wording rules against example.yaml
  uv run test_message.py compare AUTOMATIONS   same text as the Home Assistant automations it replaces?
"""
import random
import shlex
import sys
from pathlib import Path

import yaml

from message import message, questions

EXAMPLE = yaml.safe_load((Path(__file__).parent / "example.yaml").read_text())
T, CAMERAS = EXAMPLE["thresholds"], EXAMPLE["cameras"]


def render(camera, answers, trigger="Person"):
    return message(CAMERAS[camera], T, answers, trigger)


def q(value, confidence):
    return {"answer": value, "choice": value, "confidence": confidence}


def doing(camera, **yes):
    """Activity answers: 'no' to everything except the named ones, e.g. doing("side_yard", going_into_the_shed=0.9)."""
    want = {k.replace("_", " "): c for k, c in yes.items()}
    acts = CAMERAS[camera]["actions_list"]
    assert set(want) <= set(acts), set(want) - set(acts)
    return {f"act{i}": q("yes", want[act]) if act in want else q("no", 0.9) for i, act in enumerate(acts, 1)}


def demo():
    garage, yard, crawl, door = "garage", "side_yard", "crawl_space", "doorbell"
    quiet = {"person": q("no", 0.9), "count": q("0", 0.9), "ages": q("nobody", 0.9),
             "animal": q("no", 0.9), "kind": q("other", 0.5), "door": q("no", 0.9)}
    no_car = {"first": q("no", 0.8), "last": q("no", 0.8), "move": q("no car there", 0.8), "shade": q("no car there", 0.9)}
    adult = {"person": q("yes", 0.97), "count": q("1", 0.9), "ages": q("adults", 0.9),
             "men": q("cannot tell", 0.6), "women": q("cannot tell", 0.6)}
    parked = {"first": q("yes", 0.9), "last": q("yes", 0.9), "move": q("stays still", 0.9), "shade": q("light", 0.8)}

    # Garage empty, a car parked on the street, traffic passing.
    empty = {**quiet, **doing(garage), **no_car}
    assert render(garage, empty, "Vehicle") == "Vehicle detected, but it looks like a false alarm."
    # Before and after disagree with the direction of travel: say nothing about a car.
    odd = {**empty, "first": q("no", 0.7), "last": q("yes", 0.6), "door": q("yes", 0.8)}
    assert render(garage, odd, "Vehicle") == "Vehicle detected, but it looks like a false alarm. The garage door is open."
    # A parked car on its own is not news, but is worth a line next to other news.
    assert render(garage, {**empty, **parked}, "Vehicle") == "Vehicle detected, but it looks like a false alarm."
    walked_out = {**quiet, **adult, **doing(garage, walking_out=0.8, closing_the_garage_door=0.7), **parked}
    assert render(garage, walked_out) == "An adult is walking out and closing the garage door. A car is parked inside."

    arriving = {**quiet, **adult, **doing(garage, walking_in=0.7), "door": q("yes", 0.8),
                "first": q("no", 0.63), "last": q("yes", 0.88), "move": q("gets closer to the camera", 0.86), "shade": q("light", 0.72)}
    assert render(garage, arriving) == "An adult is walking in. The hatchback is pulling into the garage. The garage door is open."
    leaving = {**empty, "first": q("yes", 0.93), "last": q("no", 0.91), "move": q("gets farther from the camera", 0.93), "shade": q("dark", 0.85)}
    assert render(garage, leaving, "Vehicle") == "The wagon is pulling out of the garage."
    unsure = {**leaving, "last": q("no", 0.55), "shade": q("dark", 0.5)}
    assert render(garage, unsure, "Vehicle") == "A car may be pulling out of the garage."

    # Two things at once, said in the order they happen, not the order of confidence.
    both = {**adult, **doing(yard, leaving_through_the_gate=0.91, coming_out_of_the_shed=0.65)}
    assert render(yard, both) == "An adult is coming out of the shed and leaving through the gate."
    # At most two, the most confident ones.
    three = {**adult, **doing(yard, leaving_through_the_gate=0.9, coming_out_of_the_shed=0.8, walking_from_the_house=0.7)}
    assert render(yard, three) == "An adult is coming out of the shed and leaving through the gate."
    assert render(yard, {**adult, **doing(yard, leaving_through_the_gate=0.55)}) == "An adult is maybe leaving through the gate."
    # Only the generic fallback is true, then not even that.
    assert render(yard, {**adult, **doing(yard, standing_or_working_in_the_yard=0.9)}) == "An adult is standing or working in the yard."
    assert render(yard, {**adult, **doing(yard)}) == "An adult was spotted."
    # Men and women are named only when both counts are sure and add up to the headcount.
    leave = doing(yard, leaving_through_the_gate=0.9)

    def sexes(men, women, count="1", c=0.9):
        return {**adult, "count": q(count, 0.9), "men": q(men, c), "women": q(women, c), **leave}
    assert render(yard, sexes("1", "0")) == "A man is leaving through the gate."
    assert render(yard, sexes("0", "1")) == "A woman is leaving through the gate."
    assert render(yard, sexes("0", "1", c=0.65)) == "An adult is leaving through the gate."
    assert render(yard, sexes("1", "1", "2")) == "A man and a woman are leaving through the gate."
    assert render(yard, sexes("2", "0", "2")) == "2 men are leaving through the gate."
    assert render(yard, sexes("2", "1", "3")) == "2 men and a woman are leaving through the gate."
    assert render(yard, sexes("1", "0", "2")) == "2 adults are leaving through the gate."
    assert render(yard, sexes("3 or more", "0", "3")) == "3 adults are leaving through the gate."
    assert render(yard, sexes("0", "0", "5 or more")) == "5 or more adults are leaving through the gate."
    family = {"person": q("yes", 0.9), "count": q("2", 0.8), "ages": q("adults and kids", 0.8),
              "men": q("1", 0.9), "women": q("0", 0.9), **doing(yard, leaving_through_the_gate=0.75)}
    assert render(yard, family) == "2 people, adults and kids, are leaving through the gate."
    assert render(yard, {**family, "count": q("2", 0.4), "ages": q("adults", 0.4)}) == "Someone is leaving through the gate."

    tech = {**quiet, **adult, **doing(crawl, working_on_equipment_or_wiring=0.8)}
    assert render(crawl, tech) == "An adult is working on equipment or wiring."
    pest = {**quiet, **doing(crawl), "animal": q("yes", 0.9)}
    assert render(crawl, {**pest, "kind": q("rat", 0.8)}, "Animal") == "There is a rat."
    assert render(crawl, {**pest, "kind": q("opossum", 0.4)}, "Animal") == "There is an animal, maybe an opossum."
    assert render(crawl, {**pest, "kind": q("other", 0.9)}, "Animal") == "There is an animal."

    # Doorbell: one activity only, and a delivery needs more than a lukewarm yes.
    visit = {**adult, **doing(door, delivering_a_package=0.69, here_for_maintenance_or_repair_work=0.62, waiting_at_the_door=0.86)}
    assert render(door, visit) == "An adult is here for maintenance or repair work."
    courier = {**adult, **doing(door, delivering_a_package=0.9, here_for_maintenance_or_repair_work=0.62)}
    assert render(door, courier) == "An adult is delivering a package."

    # Model down: plain wording.
    assert render(door, None) == "Someone is at the door."
    assert render(crawl, None) == "Person detected."
    print("ok")


def random_answers(args, rng):
    """A made-up answer to every question in args, with confidences that land on and around the thresholds."""
    conf = [0.25, 0.29, 0.3, 0.45, 0.5, 0.55, 0.59, 0.6, 0.65, 0.69, 0.7, 0.75, 0.79, 0.8, 0.9, 0.97]
    out = {}
    for flag, spec in zip(args, args[1:]):
        if flag not in ("--yesno", "--choice"):
            continue
        key, _, rest = spec.partition("=")
        options = rest.rpartition(":")[2].split(",") if flag == "--choice" else ["yes", "no"]
        out[key] = q(rng.choice(options), rng.choice(conf))
    return out


# COMPAT: remove after 2026-12-20, once the alerts run from this code and the automations are gone.
def compare(path, rounds=3000):
    """Same questions and, for made-up answers, the same text as the Home Assistant automations in path."""
    import jinja2
    env, rng = jinja2.Environment(), random.Random(1)
    files = ["/a.jpg", "/b.jpg"]
    for auto in yaml.safe_load(Path(path).read_text()):
        steps = auto["actions"]
        ask = next(s["then"][0]["data"]["args"] for s in steps if "then" in s and "ask_gemini" in str(s))
        say = next(s["variables"] for s in steps if "message" in s.get("variables", {}))
        cfg = auto["variables"]
        t = {**{k: v for k, v in say.items() if isinstance(v, float)}, "car_sure": 0.6, "false_alarm": 0.8}
        args = questions(cfg, files)
        assert args == shlex.split(env.from_string(ask).render({**cfg, "files": files})), auto["id"]
        template = env.from_string(say["message"])
        for i in range(rounds):
            a = None if i == 0 else random_answers(args, rng)
            trigger = rng.choice(["Person", "Vehicle", "Animal"])
            old = template.render({**cfg, **t, "a": a, "trigger": {"id": trigger}}).strip()
            if old.startswith(("are ", "were ")):
                continue  # the automations drop the subject for "5 or more" adults with no men or women counted
            assert message(cfg, t, a, trigger) == old, (auto["id"], a, old, message(cfg, t, a, trigger))
        print(f"{auto['id']}: questions match, {rounds} made-up alerts read the same")


if __name__ == "__main__":
    if sys.argv[1:2] == ["compare"]:
        compare(sys.argv[2])
    else:
        demo()
