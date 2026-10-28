#!/usr/bin/env python3
"""Writes the shared fixture that ties the Kotlin derivation to this one.

The fixture is synthetic, seeded, and carries no participant data. It holds a cycle stream with
states and a glucose series, half on a five-minute cadence and half on one-minute, with rises of
assorted size, CGM gaps and a confirm too close to the end of the series. The expected episodes,
probabilities, counts, threshold and J are computed here with tranche_derive.py and written beside
the inputs; TrancheThresholdDeriverTest reads the file and checks the Kotlin reproduces them.

Output: plugins/aps/src/test/resources/tranche_fixture.json
"""
import json
import os
import random
import sys

import tranche_derive as td

SEED = 20261008
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "..", "plugins", "aps", "src", "test", "resources", "tranche_fixture.json")


def build():
    rng = random.Random(SEED)
    t = 1_790_000_000_000
    cycles, glucose = [], []
    for k in range(70):
        step = 300_000 if k < 35 else 60_000
        base = rng.uniform(90, 200)
        size = rng.choice([rng.uniform(0, 25), rng.uniform(30, 70), rng.uniform(80, 160)])
        rate = rng.uniform(0.5, 3.0)        # mg/dL per minute while rising
        n = int(4.5 * 3600_000 / step)
        onset = int(60 * 60_000 / step)
        conf = onset + int(rng.uniform(10, 30) * 60_000 / step)
        gap = rng.random() < 0.08
        conf_len = int(rng.choice([1, 2, 6]) * 300_000 / step)
        for i in range(n):
            ts = t + i * step
            mins = (i - onset) * step / 60_000
            rise = 0.0 if mins < 0 else min(size, rate * mins) - max(0.0, (mins - size / rate - 40) * 0.6)
            v = round(base + rise + rng.gauss(0, 1.5), 1)
            if gap and conf + 3 < i < conf + 3 + int(40 * 60_000 / step):
                pass                             # CGM gap after the confirm
            else:
                glucose.append([ts, v])
            if i < onset - 2:
                state = "IDLE"
            elif i < conf:
                state = "OBSERVING"
            elif i < conf + conf_len:
                state = "CONFIRMED"
            else:
                state = "COMMITTED" if i < conf + 12 else "RECOVERING"
            cycles.append([ts, state])
            if step == 60_000 and rng.random() < 0.15:
                cycles.append([ts + 20_000, state])   # an extra cycle within the minute
        t += n * step + 30 * 60_000
    # A confirm near the end of the series, which must be skipped for want of forward readings.
    cycles.append([t - 20 * 60_000, "OBSERVING"])
    cycles.append([t - 15 * 60_000, "CONFIRMED"])
    return cycles, glucose


def main():
    cycles, glucose = build()
    onsets = td.confirm_onsets([tuple(c) for c in cycles])
    d = td.derive(onsets, [tuple(g) for g in glucose])
    fixture = dict(
        note="Synthetic; written by backtesting/scripts/2026-10-tranche-autoconfig/make_fixture.py",
        cycles=cycles, glucose=glucose,
        expected=dict(onsets=onsets, n_small=d["n_small"], n_large=d["n_large"],
                      threshold=d["threshold"], j=d["j"], shortfall=d["shortfall"],
                      episodes=[dict(confirm_ms=e["confirm_ms"], p=e["p"], peak=e["peak"], label=e["label"])
                                for e in d["episodes"]]))
    with open(OUT, "w") as f:
        json.dump(fixture, f, separators=(",", ":"))
    print(f"{len(onsets)} onsets, {len(d['episodes'])} episodes, {d['n_small']} small, {d['n_large']} large, "
          f"threshold {d['threshold']}, J {d['j']}")
    print(f"wrote {os.path.relpath(OUT, HERE)}")


if __name__ == "__main__":
    sys.exit(main())
