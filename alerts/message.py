"""What to ask the model about a camera's pictures, and the sentence its answers become.

cfg is one camera's settings and t the thresholds, both from the household's settings file
(see example.yaml). Answers are {question key: {answer, choice, confidence}}.
"""


def questions(cfg, files):
    """Arguments for `ask-gemini decide`: the pictures, one question each, then the scene."""
    args = [x for f in files for x in ("--file", f)]
    args += ["--yesno", "person=Is a person visible in any image?"]
    acts = cfg.get("actions_list")
    if acts:
        for i, act in enumerate(acts, 1):
            args += ["--yesno", f"act{i}=Is anyone {act} at any point in these images?"]
        args += [
            "--choice", "count=How many different people appear across the images?:0,1,2,3,4,5 or more",
            "--choice", "ages=Who is visible?:adults,kids,adults and kids,nobody",
            "--choice", "men=How many different adult men appear across the images?:0,1,2,3 or more,cannot tell",
            "--choice", "women=How many different adult women appear across the images?:0,1,2,3 or more,cannot tell",
        ]
    if cfg.get("animals_list"):
        args += ["--yesno", "animal=Is an animal visible in any image?",
                 "--choice", "kind=What kind of animal is it?:" + ",".join(cfg["animals_list"])]
    if cfg.get("vehicles_list"):
        vacts = cfg.get("vehicle_actions_list", [])
        # the last activity is what ordinary traffic does: the kind is asked of the vehicle that stands out
        which = f"is doing something other than {vacts[-1]}" if vacts else "moves"
        args += ["--yesno", "vmove=Is a vehicle of any kind moving at any point in these images?",
                 "--choice", f"vkind=What kind of vehicle {which}?:" + ",".join(cfg["vehicles_list"]) + ",other,no such vehicle"]
        for i, act in enumerate(vacts, 1):
            # "that moves": asked about "a vehicle", cars already parked count as parking at the curb
            args += ["--yesno", f"vact{i}=Is a vehicle that moves {act} at any point in these images?"]
    if cfg.get("car_names"):
        args += [
            "--yesno", "first=In the first image, is a car inside the garage itself, under its roof?",
            "--yesno", "last=In the last image, is a car inside the garage itself, under its roof?",
            "--choice", "move=Over the images, a car in the garage or on its driveway:"
                        "gets closer to the camera,gets farther from the camera,stays still,no car there",
            "--choice", "shade=What colour is the car that is in the garage or driveway?:dark,light,no car there",
        ]
    if cfg.get("door_check"):
        args += ["--yesno", "door=In the last image, is the garage door open?"]
    # auto-tuning (camera-card#3) judges every kind of trigger, whatever the camera reports on
    if not cfg.get("animals_list"):
        args += ["--yesno", "animal=Is an animal visible in any image?"]
    if not cfg.get("vehicles_list"):
        args += ["--yesno", "vmove=Is a vehicle of any kind moving at any point in these images?"]
    return args + [cfg["scene"] + (" Images are in time order." if len(files) > 1 else "")]


def _int(s, default):
    try:
        return int(s)
    except ValueError:
        return default


def _who(a, t):
    """('An adult', one) and the like: as specific as the answers are sure, and whether to say 'is'."""
    n = a["count"]["choice"] if a["count"]["confidence"] >= t["sure"] and a["count"]["choice"] != "0" else ""
    one = n in ("", "1")
    kind = a["ages"]["choice"] if a["ages"]["confidence"] >= t["sure"] else ""
    # men and women are said only when both counts are sure and add up to the headcount
    m = _int(a["men"]["choice"], -1) if a["men"]["confidence"] >= t["sex_sure"] else -1
    w = _int(a["women"]["choice"], -1) if a["women"]["confidence"] >= t["sex_sure"] else -1
    if kind == "adults" and m >= 0 and w >= 0 and 0 < m + w == (_int(n, 0) if n else 1):
        parts = [("a man" if m == 1 else f"{m} men") if m > 0 else "",
                 ("a woman" if w == 1 else f"{w} women") if w > 0 else ""]
        return " and ".join(p for p in parts if p).capitalize(), one
    if kind == "adults":
        return ("An adult" if one else f"{n} adults"), one
    if kind == "kids":
        return ("A kid" if one else f"{n} kids"), one
    if kind == "adults and kids" and not one:
        return f"{n} people, adults and kids,", one
    return ("Someone" if one else f"{n} people"), one


def _doing(cfg, acts, key, a, t, most, generic=True):
    """What they are doing (at most `most` things), as it reads after 'is'; '' when nothing is worth saying.

    The last entry is the generic fallback, said (if `generic`) when nothing more specific is true.
    """
    floor = cfg.get("action_min", {})
    # each activity is its own yes/no, so two can be true at once; the last entry is the generic fallback
    seen = [(a[f"{key}{i}"]["confidence"], i, act) for i, act in enumerate(acts[:-1], 1)
            if a[f"{key}{i}"]["answer"] == "yes" and a[f"{key}{i}"]["confidence"] >= floor.get(act, 0)]
    top = sorted(seen, key=lambda s: s[0], reverse=True)
    # the most confident ones, said in the order they'd happen
    plain = sorted([s for s in top if s[0] >= t["act_sure"]][:most], key=lambda s: s[1])
    if plain:
        return " and ".join(s[2] for s in plain)
    if top:
        return f"maybe {top[0][2]}"
    return acts[-1] if generic and a[f"{key}{len(acts)}"]["answer"] == "yes" else ""


def _people(cfg, a, t):
    who, one = _who(a, t)
    doing = _doing(cfg, cfg["actions_list"], "act", a, t, cfg.get("max_actions", 2))
    if doing:
        return f"{who} {'is' if one else 'are'} {doing}."
    return f"{who} {'was' if one else 'were'} spotted."


def _vehicle(cfg, a, t):
    """'A van is parking at the near curb.', or '' for ordinary traffic and for vehicles that never move."""
    if a["vmove"]["answer"] != "yes" or a["vmove"]["confidence"] < t["sure"]:
        return ""
    k = a["vkind"]
    kind = k["choice"] if k["choice"] in cfg["vehicles_list"] and k["confidence"] >= t["sure"] else "vehicle"
    lead = f"{'An' if kind[0] in 'aeio' else 'A'} {kind}"
    acts = cfg.get("vehicle_actions_list")
    if not acts:
        return f"{lead} was spotted."
    # one vehicle does one thing, and the generic last entry (traffic going past) is not news
    doing = _doing(cfg, acts, "vact", a, t, 1, generic=False)
    return f"{lead} is {doing}." if doing else ""


def _animal(a, t):
    k = a["kind"]["choice"] if a["kind"]["choice"] != "other" and a["kind"]["confidence"] >= t["maybe"] else "animal"
    lead = "There is " if k == "animal" or a["kind"]["confidence"] >= t["sure"] else "There is an animal, maybe "
    return f"{lead}{'an' if k[0] in 'aeio' else 'a'} {k}."


def _car(cfg, a, t, other_news):
    first, last, move, shade = a["first"], a["last"], a["move"], a["shade"]
    # before, after and direction must all agree; street traffic past an open door fails this
    if first["answer"] == "no" and last["answer"] == "yes" and move["choice"] == "gets closer to the camera":
        way = "pulling into"
    elif first["answer"] == "yes" and last["answer"] == "no" and move["choice"] == "gets farther from the camera":
        way = "pulling out of"
    else:
        # only alongside other news; unnamed because a parked car's roof looks dark in infrared whatever its color
        parked = (other_news and first["answer"] == "yes" and last["answer"] == "yes"
                  and min(first["confidence"], last["confidence"]) >= t["car_sure"])
        return "A car is parked inside." if parked else ""
    names = cfg["car_names"]
    car = f"The {names[shade['choice']]}" if shade["choice"] in names and shade["confidence"] >= t["car_sure"] else "A car"
    sure = min(first["confidence"], last["confidence"], move["confidence"]) >= t["car_sure"]
    return f"{car} {'is' if sure else 'may be'} {way} the garage."


def seen(answers, t):
    """{'person'|'vehicle'|'animal': 'yes', 'no' or None (unsure)}, for auto-tuning (camera-card#3)."""
    out = {}
    for kind, key in (("person", "person"), ("vehicle", "vmove"), ("animal", "animal")):
        a = (answers or {}).get(key) or {}
        if a.get("answer") == "yes" and a["confidence"] >= t["sure"]:
            out[kind] = "yes"
        elif a.get("answer") == "no" and a["confidence"] >= t["false_alarm"]:
            out[kind] = "no"
        else:
            out[kind] = None
    return out


def message(cfg, t, answers, trigger):
    """The alert text. answers is None when the model could not be asked; trigger is what the camera detected."""
    a = answers
    fb = cfg["fallback"] if "fallback" in cfg else f"{trigger} detected"
    parts, door = [], ""
    if a is not None:
        if cfg.get("actions_list") and a["person"]["answer"] == "yes":
            parts.append(_people(cfg, a, t))
        if cfg.get("animals_list") and a["animal"]["answer"] == "yes" and a["animal"]["confidence"] >= t["sure"]:
            parts.append(_animal(a, t))
        if cfg.get("vehicles_list"):
            vehicle = _vehicle(cfg, a, t)
            if vehicle:
                parts.append(vehicle)
        if cfg.get("car_names"):
            car = _car(cfg, a, t, bool(parts))
            if car:
                parts.append(car)
        if cfg.get("door_check") and a["door"]["answer"] == "yes" and a["door"]["confidence"] >= t["sure"]:
            door = " The garage door is open."
    if parts:
        return " ".join(parts) + door
    if a is not None and a["person"]["answer"] == "no" and a["person"]["confidence"] >= t["false_alarm"]:
        return f"{fb}, but it looks like a false alarm.{door}"
    return f"{fb}.{door}"
