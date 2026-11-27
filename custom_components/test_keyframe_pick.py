# /// script
# requires-python = ">=3.13"
# ///
"""Check which keyframes a street description sends. Free: nothing is contacted.

  uv run custom_components/test_keyframe_pick.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "reolink"))  # the module alone: the package needs Home Assistant
from keyframe_pick import pick, windows  # noqa: E402

TIMES = [i * 2.0 for i in range(65)]  # a 130s recording, a keyframe every 2s


def check(name, ok):
    print(("ok  " if ok else "FAIL") + "  " + name)
    return ok


results = []
# 11-26 3:16pm: people in view 15:16:23-27, 0s is 15:16:21 when the sensor turned on
one = pick(TIMES, [(0, 6)], 16)
results.append(check("a single passerby gets most of the pictures",
                     len(one) == 16 and sum(TIMES[i] <= 8 for i in one) >= 5))
results.append(check("some pictures still cover the rest of the recording", any(TIMES[i] > 60 for i in one)))

walks = [(5, 9), (40, 44), (70, 72), (100, 105), (120, 124)]
many = pick(TIMES, walks, 16)
results.append(check("each of five passersby is pictured at least twice",
                     all(sum(a - 2 <= TIMES[i] <= b + 2 for i in many) >= 2 for a, b in walks)))

linger = pick(TIMES, [(0, 100), (110, 113)], 16)
results.append(check("someone lingering doesn't crowd out a later passerby",
                     sum(109 <= TIMES[i] <= 115 for i in linger) >= 3))

results.append(check("no detection history: evenly spread as before", len(pick(TIMES, [], 16)) == 16))
results.append(check("a short clip sends every keyframe", pick(TIMES[:10], [(0, 3)], 16) == list(range(10))))
results.append(check("never more than asked for, never repeats",
                     all(len(p) == len(set(p)) <= 16 for p in (one, many, linger))))

results.append(check("sensor history becomes on-windows",
                     windows([(-3, True), (6, False), (40, True), (44, False), (120, True)], 130)
                     == [(-3, 6), (40, 44), (120, 130)]))
results.append(check("sensor off all recording: no windows", windows([(-50, False)], 130) == []))

sys.exit(0 if all(results) else 1)
