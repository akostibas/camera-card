"""Which keyframes to describe when only a few can be sent: the ones from while the camera saw something."""

PAD = 2.0  # seconds either side of a detection: the sensor turns on a beat late and off a beat early
SPREAD = 4  # pictures kept for the rest of the recording, in case the sensor missed something


def windows(changes: list[tuple[float, bool]], length: float) -> list[tuple[float, float]]:
    """(start, end) offsets the sensor was on, from its (offset, is on) changes over a recording `length` long."""
    out, since = [], None
    for t, on in sorted(changes):
        if on and since is None:
            since = t
        elif not on and since is not None:
            out.append((since, t))
            since = None
    if since is not None:
        out.append((since, length))
    return out


def _even(seq: list[int], k: int) -> list[int]:
    return [seq[int((j + 0.5) * len(seq) / k)] for j in range(min(k, len(seq)))]


def pick(times: list[float], seen: list[tuple[float, float]], n: int) -> list[int]:
    """Indexes of at most n keyframes (at `times` offsets), favouring those within PAD of a `seen` window."""
    if len(times) <= n:
        return list(range(len(times)))
    merged: list[list[float]] = []
    for a, b in sorted(seen):
        if merged and a - PAD <= merged[-1][1] + PAD:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    groups = [g for a, b in merged if (g := [i for i, t in enumerate(times) if a - PAD <= t <= b + PAD])]
    # round-robin, so a passerby's few seconds aren't outvoted by someone lingering for a minute
    share, left = [0] * len(groups), max(n - SPREAD, 0)
    while left and any(s < len(g) for s, g in zip(share, groups)):
        for j, g in enumerate(groups):
            if left and share[j] < len(g):
                share[j] += 1
                left -= 1
    chosen = {i for g, s in zip(groups, share) for i in _even(g, s)}
    rest = [i for i in range(len(times)) if i not in chosen]
    return sorted(chosen | set(_even(rest, n - len(chosen))))
