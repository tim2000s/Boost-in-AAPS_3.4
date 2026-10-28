"""The confirm-tranche threshold derivation, step for step as the device runs it.

This mirrors plugins/aps/.../openAPSBoostV5/TrancheThresholdDeriver.kt and the apply rule in
BoostV5AutoConfigApply.resolveTrancheThreshold. The method is that of
backtesting/scripts/2026-08-meal-size-readability/tranche_rule_derive.py, scored with the shipped
coefficients (ConfirmTrancheController) rather than held-out refits. Times are integer milliseconds,
as on the device. make_fixture.py writes a shared fixture that the Kotlin test checks against.
"""
import bisect
import math

OFFSET_MS = 10 * 60_000
FORWARD_MS = 180 * 60_000
LARGE, SMALL = 75.0, 30.0
MIN_LABELLED, MIN_PER_CLASS = 15, 5
MIN_LABELLED_TO_LOWER = 30
WELL_CONTROLLED_MAX_TBR70, WELL_CONTROLLED_MAX_SEV54 = 1.5, 0.3
FACTORY = 0.48
GRID = [round(0.20 + 0.05 * i, 2) for i in range(13)]

# ConfirmTrancheController companion, fitted 2026-08-27.
B0 = 2.48631
BG_CONFIRM = -0.014480
RISE_SINCE = -0.003822
MAX_RISE_SINCE = 0.138821
SLOPE_NOW = 0.072499
BG_NOW = -0.018302


def release_probability(bg_confirm, rise, max_rise, slope, bg_now):
    # Same summation order as the Kotlin, so the two agree to the last bit.
    z = B0 + BG_CONFIRM * bg_confirm + RISE_SINCE * rise + MAX_RISE_SINCE * max_rise + SLOPE_NOW * slope + BG_NOW * bg_now
    return 1.0 / (1.0 + math.exp(-z))


def confirm_onsets(cycles):
    """cycles: iterable of (ms, state). The first CONFIRMED after a non-CONFIRMED cycle."""
    c = sorted(cycles, key=lambda r: r[0])
    return [c[i][0] for i in range(1, len(c)) if c[i][1] == "CONFIRMED" and c[i - 1][1] != "CONFIRMED"]


def episodes(confirm_ms, glucose):
    """glucose: iterable of (ms, mg/dL)."""
    g = sorted(((int(t), float(v)) for t, v in glucose if v is not None and math.isfinite(v) and v > 0),
               key=lambda r: r[0])
    ts = [t for t, _ in g]
    bg = [v for _, v in g]
    out = []
    for t0 in confirm_ms:
        j = bisect.bisect_right(ts, t0) - 1
        m = bisect.bisect_right(ts, t0 + OFFSET_MS) - 1
        if j < 1 or m <= j or m >= len(ts) - 12:
            continue
        b = bisect.bisect_right(ts, t0 + FORWARD_MS)
        if b - j < 14:
            continue
        seg_max = max(bg[j:b])
        win_max = max(bg[j:m + 1])
        bgc, bgn = bg[j], bg[m]
        rise, max_rise, slope, peak = bgn - bgc, win_max - bgc, bgn - bg[m - 1], seg_max - bgc
        p = release_probability(bgc, rise, max_rise, slope, bgn)
        label = "LARGE" if peak >= LARGE else ("SMALL" if peak < SMALL else None)
        out.append(dict(confirm_ms=int(t0), bg_confirm=bgc, bg_now=bgn, rise_since=rise,
                        max_rise_since=max_rise, slope_now=slope, peak=peak, p=p, label=label))
    return out


def youden(eps, t):
    small = [e for e in eps if e["label"] == "SMALL"]
    large = [e for e in eps if e["label"] == "LARGE"]
    ws = sum(e["p"] <= t for e in small) / max(len(small), 1)
    wl = sum(e["p"] <= t for e in large) / max(len(large), 1)
    return ws - wl


def derive_from_episodes(eps):
    ns = sum(e["label"] == "SMALL" for e in eps)
    nl = sum(e["label"] == "LARGE" for e in eps)
    if ns + nl < MIN_LABELLED:
        return dict(n_small=ns, n_large=nl, threshold=None, j=None, shortfall="TOO_FEW_LABELLED")
    if ns < MIN_PER_CLASS or nl < MIN_PER_CLASS:
        return dict(n_small=ns, n_large=nl, threshold=None, j=None, shortfall="CLASS_TOO_SMALL")
    best_t, best_j = GRID[0], -math.inf
    for t in GRID:
        jv = youden(eps, t)
        if jv > best_j:          # strict: ties keep the lower value, as in the August derivation
            best_t, best_j = t, jv
    return dict(n_small=ns, n_large=nl, threshold=best_t, j=best_j, shortfall="NONE")


def derive(confirm_ms, glucose):
    eps = episodes(confirm_ms, glucose)
    d = derive_from_episodes(eps)
    d["episodes"] = eps
    return d


def resolve(derived, n_labelled, stored, last_written, tbr70, sev54):
    """The apply rule. Returns (outcome, operative value after, reason)."""
    current = FACTORY if stored is None else stored
    hand_set = (stored is not None and abs(stored - FACTORY) > 1e-4
                and (last_written is None or abs(stored - last_written) > 1e-4))
    if hand_set:
        return "KEPT_USER_TUNED", current, "user-set"
    if derived is None:
        return "INSUFFICIENT_EVIDENCE", current, "evidence"
    target = round(min(max(derived, 0.20), 0.80), 2)
    if abs(target - current) <= 1e-4:
        return "INSIDE_DEADBAND", current, "unchanged"
    if target < current:
        why = []
        if not (tbr70 < WELL_CONTROLLED_MAX_TBR70 and sev54 < WELL_CONTROLLED_MAX_SEV54):
            why.append("not-well-controlled")
        if n_labelled < MIN_LABELLED_TO_LOWER:
            why.append(f"n<{MIN_LABELLED_TO_LOWER}")
        if why:
            return "LOOSENING_HELD", current, "+".join(why)
    return "APPLIED", target, "raise" if target > current else "lower"
