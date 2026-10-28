#!/usr/bin/env python3
"""
g7_cohort_peruser.py -- per-user breakdown of the G7/One+ cohort smoothing quality.

The pooled Mode-B table in benchmark.py sums lag/jitter/reversals across all G7
users, so the biggest series (one user holds ~1/3 of the rows) can dominate the
headline. This script runs the SAME metrics (imported verbatim from benchmark.py)
PER USER, so the question is the honest cross-user one: does the v4 UKF beat the
shipped exponential on noise-removal and lag for EVERY user, or only on average?

No new methodology -- it reuses smooth_series / accumulate_stable_and_lag /
accumulate_onestep / rmse from benchmark.py. Deduped 5-min buckets via
load_db_sensor('G7'). Anonymous tags U1..Un only; no personal identifiers.

Run:  python3 g7_cohort_peruser.py
"""
import benchmark as B

SENSOR = "G7"


def per_user_metrics(ts, vals):
    """Return {smoother: dict(jit, lag, rev, onestep, nstable)} for one user."""
    out = {}
    for name in B.SMOOTHERS:
        acc = B.Acc()
        sm = B.smooth_series(name, ts, vals)
        B.accumulate_onestep(acc, ts, vals, sm)
        B.accumulate_stable_and_lag(acc, ts, vals, sm)   # ref = raw (Mode B)
        out[name] = dict(
            jit=B._mean(acc.jit_var),
            lag=B._mean(acc.lag),
            rev=acc.reversals,
            onestep=B.rmse(acc.onestep),
            nstable=len(acc.jit_var),
        )
    return out


def main():
    series = B.load_db_sensor(SENSOR)
    print(f"# G7/One+ cohort -- per-user smoothing quality ({len(series)} users)\n")
    print("Deduped 5-min buckets. Metrics identical to benchmark.py Mode B "
          "(ref=raw). Jitter = within-window variance on stable (|slope|<0.3) "
          "windows (mg/dL^2, lower=smoother); lag = signed offset on fast "
          "(|slope|>2) windows (mg/dL, +=trails); reversals = direction flips "
          "in stable windows (lower=less chatter).\n")

    rows = []
    for (label, ts, vals) in series:
        m = per_user_metrics(ts, vals)
        rows.append((label, len(ts), m))

    # ---- per-user jitter (variance) ----
    print("## Jitter variance per user (mg/dL^2) -- lower is smoother\n")
    print("| user | n(5-min) | raw/persist | exponential | tsunami | v4 | v4 vs raw | v4 vs exp |")
    print("|---|---|---|---|---|---|---|---|")
    v4_beats_exp_jit = 0
    for (label, n, m) in rows:
        raw = m['persistence']['jit']; exp = m['exponential']['jit']
        tsu = m['tsunami']['jit']; v4 = m['v4']['jit']
        red_raw = 100.0 * (raw - v4) / raw if raw else 0.0
        red_exp = 100.0 * (exp - v4) / exp if exp else 0.0
        if v4 < exp:
            v4_beats_exp_jit += 1
        print(f"| {label} | {n} | {raw:.2f} | {exp:.2f} | {tsu:.2f} | {v4:.2f} "
              f"| -{red_raw:.0f}% | -{red_exp:.0f}% |")

    # ---- per-user lag ----
    print("\n## Lag per user (mg/dL, + = trails the move) -- nearer 0 is better\n")
    print("| user | persist | exponential | tsunami | v4 |")
    print("|---|---|---|---|---|")
    v4_beats_exp_lag = 0
    for (label, n, m) in rows:
        p = m['persistence']['lag']; exp = m['exponential']['lag']
        tsu = m['tsunami']['lag']; v4 = m['v4']['lag']
        if abs(v4) < abs(exp):
            v4_beats_exp_lag += 1
        print(f"| {label} | {p:+.2f} | {exp:+.2f} | {tsu:+.2f} | {v4:+.2f} |")

    # ---- per-user reversals ----
    print("\n## Reversals per user (direction flips in stable windows) -- lower is less chatter\n")
    print("| user | persist(raw) | exponential | tsunami | v4 |")
    print("|---|---|---|---|---|")
    for (label, n, m) in rows:
        print(f"| {label} | {m['persistence']['rev']} | {m['exponential']['rev']} "
              f"| {m['tsunami']['rev']} | {m['v4']['rev']} |")

    # ---- consistency verdict ----
    N = len(rows)
    print(f"\n## Cross-user consistency\n")
    print(f"- v4 has **lower jitter than exponential in {v4_beats_exp_jit}/{N}** users.")
    print(f"- v4 has **smaller |lag| than exponential in {v4_beats_exp_lag}/{N}** users.")
    all_win = v4_beats_exp_jit == N and v4_beats_exp_lag == N
    print(f"- Verdict: {'UNANIMOUS -- the pooled win is not a single-user artefact.' if all_win else 'NOT unanimous -- see the per-user rows.'}")


if __name__ == "__main__":
    main()
