# /// script
# requires-python = ">=3.13"
# dependencies = ["pyyaml"]
# ///
"""Check the alert wording rules against example.yaml. Free: the model is never called.

  uv run test_message.py
"""
from pathlib import Path

import yaml

from describe import budget, describe, describe_unpushed
from message import message, questions

EXAMPLE = yaml.safe_load((Path(__file__).parent / "example.yaml").read_text())
T, CAMERAS = EXAMPLE["thresholds"], EXAMPLE["cameras"]


def render(camera, answers, trigger="Person"):
    return message(CAMERAS[camera], T, answers, trigger)


def q(value, confidence):
    return {"answer": value, "choice": value, "confidence": confidence}


def doing(camera, key="act", **yes):
    """Activity answers: 'no' to everything except the named ones, e.g. doing("side_yard", going_into_the_shed=0.9)."""
    want = {k.replace("_", " "): c for k, c in yes.items()}
    acts = CAMERAS[camera]["actions_list" if key == "act" else "vehicle_actions_list"]
    assert set(want) <= set(acts), set(want) - set(acts)
    return {f"{key}{i}": q("yes", want[act]) if act in want else q("no", 0.9) for i, act in enumerate(acts, 1)}


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

    # Street: only a vehicle that moves is news, named as far as the model is sure.
    street = "street"
    nobody = {"person": q("no", 0.9), **doing(street)}

    def traffic(kind, sure=0.9, moving=("yes", 0.9), **yes):
        return {**nobody, "vmove": q(*moving), "vkind": q(kind, sure), **doing(street, "vact", **yes)}
    assert render(street, traffic("pickup truck", passing_by=0.9), "Vehicle") == "A pickup truck is passing by."
    assert render(street, traffic("trash truck", collecting_the_trash=0.8, passing_by=0.9), "Vehicle") == "A trash truck is collecting the trash."
    assert render(street, traffic("van", 0.3, parking_at_the_near_curb=0.7), "Vehicle") == "A vehicle is parking at the near curb."
    assert render(street, traffic("other", pulling_away_from_the_far_curb=0.5), "Vehicle") == "A vehicle is maybe pulling away from the far curb."
    assert render(street, traffic("car"), "Vehicle") == "A car was spotted."
    # One vehicle does one thing: the surest, however many the model says yes to.
    both_curbs = traffic("car", parking_at_the_near_curb=0.76, parking_at_the_far_curb=0.69, passing_by=0.74)
    assert render(street, both_curbs, "Vehicle") == "A car is parking at the near curb."
    still = traffic("no vehicle moves", moving=("no", 0.9))
    assert render(street, still, "Vehicle") == "Vehicle detected, but it looks like a false alarm."
    # Smoking needs more than a lukewarm yes.
    walker = {**still, **adult, **doing(street, walking_a_dog=0.9, smoking=0.7)}
    assert render(street, walker) == "An adult is walking a dog."
    driver = {**traffic("car", pulling_away_from_the_near_curb=0.8), **adult, **doing(street, getting_into_a_car=0.8)}
    assert render(street, driver) == "An adult is getting into a car. A car is pulling away from the near curb."

    # Model down: plain wording.
    assert render(door, None) == "Someone is at the door."
    assert render(crawl, None) == "Person detected."

    # No pictures: the model is not asked. Model fails: plain wording. Model answers: its sentence.
    def fail(cfg, files):
        raise TimeoutError
    assert describe(EXAMPLE, crawl, "Animal", [], ask=None) == "Animal detected."
    assert describe(EXAMPLE, door, "0", ["a.jpg"], ask=fail) == "Someone is at the door."
    assert describe(EXAMPLE, crawl, "Person", ["a.jpg"], ask=lambda cfg, files: tech) == "An adult is working on equipment or wiring."
    seen = []
    describe(EXAMPLE, crawl, "Person", [f"{i}.jpg" for i in range(75)], ask=lambda cfg, files: seen.extend(files) or tech)
    assert len(seen) == 15 and seen[:2] == ["0.jpg", "5.jpg"]
    # Not pushed: described only at the camera's level, and only kept when there is something to say.
    passing = traffic("car", passing_by=0.9)

    def unpushed(camera, trigger, answers=passing, files=("a.jpg",), **kw):
        return describe_unpushed(EXAMPLE, camera, trigger, list(files), ask=lambda cfg, files: answers, **kw)
    assert unpushed(street, "Vehicle") == ("A car is passing by.", 0)
    assert unpushed(street, "Motion") == ("", 0), "event level leaves plain motion alone"
    assert unpushed(crawl, "Animal", pest) == ("", 0), "cameras describe on push unless told otherwise"
    assert unpushed(street, "Vehicle", files=()) == ("", 0)
    assert unpushed(street, "Vehicle", still) == ("Vehicle detected, but it looks like a false alarm.", 0)
    assert describe_unpushed(EXAMPLE, street, "Vehicle", ["a.jpg"], ask=fail) == ("", 0), "plain wording is not worth keeping"
    motion = {**EXAMPLE, "cameras": {street: {**CAMERAS[street], "describe": "motion"}}}
    assert describe_unpushed(motion, street, "Motion", ["a.jpg"], ask=lambda cfg, files: passing) == ("A car is passing by.", 0)

    # The day's limit: the first call refused carries the warning, later ones are just plain, tomorrow starts over.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        spend = budget(f"{d}/count", 2, "2026-11-20")
        assert unpushed(street, "Vehicle", spend=spend) == ("A car is passing by.", 0)
        assert describe(EXAMPLE, crawl, "Person", ["a.jpg"], ask=lambda cfg, files: tech, spend=spend) == "An adult is working on equipment or wiring."
        warning = "Descriptions have stopped until tomorrow: today's limit of 2 is used up. Street used the most (1)."
        assert describe(EXAMPLE, crawl, "Person", ["a.jpg"], ask=fail, spend=spend) == f"Person detected. {warning}"
        assert describe(EXAMPLE, crawl, "Person", ["a.jpg"], ask=fail, spend=spend) == "Person detected."
        assert unpushed(street, "Vehicle", spend=spend) == ("", 0)
        assert unpushed(street, "Vehicle", spend=budget(f"{d}/count", 2, "2026-11-21")) == ("A car is passing by.", 0)
        assert unpushed(street, "Vehicle", spend=budget(f"{d}/other", 0, "2026-11-20")) == (warning.replace("of 2", "of 0").replace("(1)", "(0)"), 3)

    # One picture is a snapshot; several are footage, and the model is told they are in order.
    assert questions(CAMERAS[door], ["a.jpg"])[-1] == CAMERAS[door]["scene"]
    assert questions(CAMERAS[crawl], ["a.jpg", "b.jpg"])[-1].endswith(" Images are in time order.")
    print("ok")


if __name__ == "__main__":
    demo()
