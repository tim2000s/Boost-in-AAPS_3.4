#!/usr/bin/env python3
"""
Field audit of the two pre-trained LightGBM models that ship inside the Boost engine.

Both models were trained in early 2026 on a 28-user Nightscout cohort and exported to
JSON for pure-Kotlin inference (app/src/main/assets/boost/{hypo_risk,meal_likelihood}_model.json).
They have never been re-validated against the telemetry of the people actually running them.

This script asks three questions of the live record:

  1. Coverage and distribution. On what fraction of cycles does each model produce a score,
     and what does the score distribution look like?

  2. Do the consumption thresholds ever bite? riskScale engages above 0.30, tier downgrade
     above 0.60, the G3 hold releases above 0.50 on the meal model.

  3. Does the score still discriminate in the field? AUC against the model's own training
     target, per user and pooled, with a cluster bootstrap over users.

The discrimination figure is measured ON POLICY: a high hypo score causes the loop to dose
less, which suppresses some of the very events being predicted. The field AUC is therefore a
lower bound on the model's discrimination, not a clean out-of-sample estimate, and the
direction of the bias is toward zero. This is stated in the report rather than corrected for,
because correcting for it needs the counterfactual the programme does not have.

Targets, taken from each model's own metadata asset rather than from its documentation:
  hypo model  : CGM below 70 mg/dL sustained for >= 15 min, beginning within the next 90 min
  meal model  : max CGM within the next 90 minutes >= current CGM + 50 mg/dL

The hypo model is additionally scored against the target its KDoc claims (2 readings below 70
within 4 hours), which is the target of the model it replaced. The two differ enough to matter.

Usage:  python3 ml_field_audit.py [--days N] [--json out.json]
"""

import argparse
import json
import sys

import numpy as np
import psycopg2

BOOST_USERS = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "tim")

# Consumption thresholds, read from the engine source:
#   DetermineBasalBoostV3MLG3.kt:1206  riskScale engages when mlHypoRisk > 0.30
#   DetermineBasalBoostV3MLG3.kt:1217  tier downgrade when mlHypoRisk > 0.60
#   DetermineBasalBoostV3MLG3.kt:1295  G3 hold releases when mlMealLikely > 0.50
RISK_SCALE_THRESHOLD = 0.30
TIER_DOWNGRADE_THRESHOLD = 0.60
MEAL_RELEASE_THRESHOLD = 0.50

# The shipped hypo model's own provenance file, app/src/main/assets/boost/hypo_risk_meta.json,
# records label "sustained_hypo (<70 for >=15min)" and horizon_min 90. Three separate documents
# (the BoostRiskModel KDoc, the V3ML reader, the ML branch README) still describe the model it
# replaced: 2+ consecutive readings below 70 within 4 hours. Both are scored below, because the
# gap between what the model predicts and what its consumers believe it predicts is itself a
# finding.
HYPO_MGDL = 70.0
HYPO_HORIZON_MIN = 90       # v12 meta
HYPO_MIN_SPAN_MIN = 15      # v12 meta: sustained
LEGACY_HORIZON_MIN = 240    # what the KDoc claims
LEGACY_MIN_SPAN_MIN = 5     # 2 consecutive 5-minute readings
MEAL_RISE_MGDL = 50.0
MEAL_HORIZON_MIN = 90

BUCKET_MIN = 5  # de-duplicate decision rows to one per 5-minute bucket


ERA = {"since": None, "until": None}   # set from --since/--until; the model generation window


def _era(col):
    """Restrict to one model generation. The ml_hypo_risk column pools the outputs of three
    generations with different targets and different output scales, so any figure computed
    across the boundary is a mixture rather than a measurement."""
    c = []
    if ERA["since"]: c.append(f"AND {col} >= '{ERA['since']}'")
    if ERA["until"]: c.append(f"AND {col} < '{ERA['until']}'")
    return " ".join(c)


def fetch(conn, days):
    """One row per user per 5-minute bucket, carrying both model scores and the CGM value."""
    where_days = ("AND d.ts_utc >= now() - interval '%d days'" % days if days else "") + " " + _era("d.ts_utc")
    sql = f"""
        SELECT DISTINCT ON (d.user_id, to_timestamp(floor(extract(epoch FROM d.ts_utc) / {BUCKET_MIN * 60}) * {BUCKET_MIN * 60}))
               d.user_id,
               extract(epoch FROM d.ts_utc) AS ts,
               d.cgm_mgdl,
               d.ml_hypo_risk,
               d.ml_meal_likely,
               d.sug_iob,
               d.sug_eventualbg
        FROM boost_decisions d
        WHERE d.user_id = ANY(%s)
          AND d.cgm_mgdl IS NOT NULL
          {where_days}
        ORDER BY d.user_id,
                 to_timestamp(floor(extract(epoch FROM d.ts_utc) / {BUCKET_MIN * 60}) * {BUCKET_MIN * 60}),
                 d.ts_utc
    """
    cur = conn.cursor()
    cur.execute(sql, (list(BOOST_USERS),))
    rows = cur.fetchall()
    out = {}
    f = lambda x: None if x is None else float(x)
    for uid, ts, cgm, risk, meal, iob, ebg in rows:
        out.setdefault(uid, []).append((float(ts), float(cgm), f(risk), f(meal), f(iob), f(ebg)))
    for uid in out:
        out[uid].sort(key=lambda r: r[0])
    return out


def cgm_series(conn, days):
    """Sensor record, used for the forward outcome so the label does not depend on the loop running."""
    # the outcome window must extend past the era end, or labels truncate at the boundary
    where_days = ("AND ts_utc >= now() - interval '%d days'" % days if days else "") + (
        f" AND ts_utc >= '{ERA['since']}'" if ERA["since"] else "")
    cur = conn.cursor()
    cur.execute(f"""
        SELECT user_id, extract(epoch FROM ts_utc), cgm_mgdl
        FROM boost_cgm
        WHERE user_id = ANY(%s) AND cgm_mgdl IS NOT NULL {where_days}
        ORDER BY user_id, ts_utc
    """, (list(BOOST_USERS),))
    out = {}
    for uid, ts, cgm in cur.fetchall():
        out.setdefault(uid, []).append((float(ts), float(cgm)))
    return {u: (np.array([r[0] for r in v]), np.array([r[1] for r in v])) for u, v in out.items()}


def hypo_onsets(cgm_ts, cgm_val, min_span_min):
    """Start times of runs below 70 that persist for at least min_span_min minutes.

    Spans are measured in wall-clock time rather than in readings, so the definition
    means the same thing on a one-minute feed as on a five-minute one.
    """
    below = cgm_val < HYPO_MGDL
    onsets = []
    i, n = 0, len(below)
    while i < n:
        if not below[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and below[j + 1] and (cgm_ts[j + 1] - cgm_ts[j]) <= 15 * 60:
            j += 1
        if (cgm_ts[j] - cgm_ts[i]) >= (min_span_min - 1e-9) * 60:
            onsets.append(cgm_ts[i])
        i = j + 1
    return np.array(onsets, dtype=float)


def label_hypo(ts_arr, onset_ts, horizon_min):
    """1 if a qualifying hypo onset falls within the horizon."""
    if onset_ts.size == 0:
        return np.zeros(len(ts_arr), dtype=int)
    lo = np.searchsorted(onset_ts, ts_arr, side="right")
    hi = np.searchsorted(onset_ts, ts_arr + horizon_min * 60, side="right")
    return (hi > lo).astype(int)


def label_meal(ts_arr, cgm_now, cgm_ts, cgm_val):
    """1 if the max CGM in the next 90 minutes is at least current + 50 mg/dL."""
    lo = np.searchsorted(cgm_ts, ts_arr, side="right")
    hi = np.searchsorted(cgm_ts, ts_arr + MEAL_HORIZON_MIN * 60, side="right")
    out = np.zeros(len(ts_arr), dtype=int)
    valid = np.zeros(len(ts_arr), dtype=bool)
    for i in range(len(ts_arr)):
        a, b = lo[i], hi[i]
        if b <= a:
            continue
        valid[i] = True
        if cgm_val[a:b].max() >= cgm_now[i] + MEAL_RISE_MGDL:
            out[i] = 1
    return out, valid


def auc(scores, labels):
    """Mann-Whitney AUC with tie handling. None when a class is absent."""
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    n_pos = int(labels.sum())
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = np.argsort(scores, kind="mergesort")
    s = scores[order]
    ranks = np.empty(len(s), dtype=float)
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    r = np.empty(len(s), dtype=float)
    r[order] = ranks
    return (r[labels == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def cluster_bootstrap_auc(per_user, n_boot=2000, seed=20260813):
    """Resample USERS, not observations: the question is about people, not cycles."""
    users = [u for u in per_user if per_user[u][0].size and per_user[u][1].sum() > 0
             and per_user[u][1].sum() < per_user[u][1].size]
    if len(users) < 2:
        return None, None, None, users
    rng = np.random.default_rng(seed)
    point = auc(np.concatenate([per_user[u][0] for u in users]),
                np.concatenate([per_user[u][1] for u in users]))
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(len(users), size=len(users), replace=True)
        s = np.concatenate([per_user[users[k]][0] for k in pick])
        l = np.concatenate([per_user[users[k]][1] for k in pick])
        a = auc(s, l)
        if a is not None:
            boots.append(a)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return point, lo, hi, users


def calibration(scores, labels, n_bins=10):
    """Observed event rate by predicted decile, to see whether the probability means anything."""
    if len(scores) == 0:
        return []
    edges = np.quantile(scores, np.linspace(0, 1, n_bins + 1))
    edges = np.unique(edges)
    if len(edges) < 3:
        return []
    idx = np.clip(np.digitize(scores, edges[1:-1], right=True), 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        m = idx == b
        if m.sum() == 0:
            continue
        rows.append(dict(bin=b, n=int(m.sum()),
                         pred_mean=float(scores[m].mean()),
                         obs_rate=float(labels[m].mean()),
                         lo=float(edges[b]), hi=float(edges[b + 1])))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="0 = all history")
    ap.add_argument("--since", default=None, help="model-generation window start, YYYY-MM-DD")
    ap.add_argument("--until", default=None, help="model-generation window end, YYYY-MM-DD")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    ERA["since"], ERA["until"] = args.since, args.until
    if args.since or args.until:
        print(f"era: {args.since or 'start'} to {args.until or 'now'}\n")

    conn = psycopg2.connect("dbname=oref")
    conn.autocommit = True

    decisions = fetch(conn, args.days)
    cgm = cgm_series(conn, args.days)

    result = {"users": {}, "thresholds": {
        "risk_scale": RISK_SCALE_THRESHOLD,
        "tier_downgrade": TIER_DOWNGRADE_THRESHOLD,
        "meal_release": MEAL_RELEASE_THRESHOLD}}

    risk_by_user, meal_by_user, legacy_by_user = {}, {}, {}
    all_risk_scores, all_risk_labels = [], []
    all_meal_scores, all_meal_labels = [], []
    # Matched baselines the model has to beat to earn its place in the dose path.
    # A 53-feature gradient-boosted model that cannot outrank the single number it was
    # given as its first feature is not adding anything.
    base_risk = {"low glucose (-BG)": {}, "eventualBG (-)": {}, "IOB": {}}
    base_meal = {"glucose (BG)": {}, "eventualBG": {}}

    print("=" * 78)
    print("COVERAGE AND THRESHOLD CROSSING")
    print("=" * 78)
    print(f"{'user':6s} {'cycles':>8s} {'scored':>8s} {'cov%':>6s} "
          f"{'risk>.30':>9s} {'risk>.60':>9s} {'meal>.50':>9s}")

    for uid in sorted(decisions):
        rows = decisions[uid]
        ts = np.array([r[0] for r in rows])
        bg = np.array([r[1] for r in rows])
        risk = np.array([np.nan if r[2] is None else r[2] for r in rows])
        meal = np.array([np.nan if r[3] is None else r[3] for r in rows])
        iob = np.array([np.nan if r[4] is None else r[4] for r in rows])
        ebg = np.array([np.nan if r[5] is None else r[5] for r in rows])
        has_risk = ~np.isnan(risk)
        has_meal = ~np.isnan(meal)
        n, ns = len(rows), int(has_risk.sum())
        if ns == 0:
            continue
        r = risk[has_risk]
        m = meal[has_meal]
        pct = lambda x: 100.0 * float(np.mean(x)) if len(x) else float("nan")
        print(f"{uid:6s} {n:8d} {ns:8d} {100.0*ns/n:6.1f} "
              f"{pct(r > RISK_SCALE_THRESHOLD):8.2f}% {pct(r > TIER_DOWNGRADE_THRESHOLD):8.2f}% "
              f"{pct(m > MEAL_RELEASE_THRESHOLD):8.2f}%")

        u = {"cycles": n, "scored": ns, "coverage_pct": 100.0 * ns / n,
             "risk_q": [float(x) for x in np.quantile(r, [0.5, 0.9, 0.99, 1.0])],
             "meal_q": [float(x) for x in np.quantile(m, [0.5, 0.9, 0.99, 1.0])] if len(m) else None,
             "pct_risk_over_scale": pct(r > RISK_SCALE_THRESHOLD),
             "pct_risk_over_tier": pct(r > TIER_DOWNGRADE_THRESHOLD),
             "pct_meal_over_release": pct(m > MEAL_RELEASE_THRESHOLD)}

        if uid in cgm:
            c_ts, c_bg = cgm[uid]
            # hypo model
            onsets_v12 = hypo_onsets(c_ts, c_bg, HYPO_MIN_SPAN_MIN)
            onsets_legacy = hypo_onsets(c_ts, c_bg, LEGACY_MIN_SPAN_MIN)
            y = label_hypo(ts[has_risk], onsets_v12, HYPO_HORIZON_MIN)
            y_legacy = label_hypo(ts[has_risk], onsets_legacy, LEGACY_HORIZON_MIN)
            legacy_by_user[uid] = (r, y_legacy)
            risk_by_user[uid] = (r, y)
            all_risk_scores.append(r); all_risk_labels.append(y)
            u["hypo_auc"] = auc(r, y)
            u["hypo_base_rate"] = float(y.mean())
            # baselines on exactly the same rows and the same label
            bg_r, iob_r, ebg_r = bg[has_risk], iob[has_risk], ebg[has_risk]
            base_risk["low glucose (-BG)"][uid] = (-bg_r, y)
            fin = ~np.isnan(ebg_r)
            if fin.sum():
                base_risk["eventualBG (-)"][uid] = (-ebg_r[fin], y[fin])
            fin = ~np.isnan(iob_r)
            if fin.sum():
                base_risk["IOB"][uid] = (iob_r[fin], y[fin])
            # meal model
            if has_meal.sum():
                ym, valid = label_meal(ts[has_meal], bg[has_meal], c_ts, c_bg)
                if valid.sum():
                    meal_by_user[uid] = (m[valid], ym[valid])
                    all_meal_scores.append(m[valid]); all_meal_labels.append(ym[valid])
                    u["meal_auc"] = auc(m[valid], ym[valid])
                    u["meal_base_rate"] = float(ym[valid].mean())
                    bg_m = bg[has_meal][valid]; ebg_m = ebg[has_meal][valid]
                    base_meal["glucose (BG)"][uid] = (bg_m, ym[valid])
                    fin = ~np.isnan(ebg_m)
                    if fin.sum():
                        base_meal["eventualBG"][uid] = (ebg_m[fin], ym[valid][fin])
        result["users"][uid] = u

    print()
    print("=" * 78)
    print("FIELD DISCRIMINATION (on policy — see the note in the docstring)")
    print("=" * 78)

    for name, per_user in (("hypo risk", risk_by_user), ("meal likelihood", meal_by_user)):
        print(f"\n### {name}")
        print(f"  {'user':6s} {'n':>8s} {'base':>7s} {'AUC':>7s}")
        for uid in sorted(per_user):
            s, y = per_user[uid]
            a = auc(s, y)
            print(f"  {uid:6s} {len(s):8d} {y.mean():7.3f} "
                  f"{'  n/a' if a is None else f'{a:7.3f}'}")
        point, lo, hi, used = cluster_bootstrap_auc(per_user)
        if point is None:
            print("  pooled: insufficient users")
            continue
        verdict = "distinguishable from chance" if lo > 0.5 else "NOT distinguishable from chance"
        print(f"  pooled AUC {point:.3f}  95% CI [{lo:.3f}, {hi:.3f}]  "
              f"({len(used)} users)  -> {verdict}")
        key = "hypo" if name.startswith("hypo") else "meal"
        result[f"{key}_pooled"] = {"auc": point, "ci_lo": lo, "ci_hi": hi,
                                   "n_users": len(used), "users": used}

    print()
    print("=" * 78)
    print("LABEL MISMATCH — the model's own target vs the one its documentation claims")
    print("=" * 78)
    for tag, pu in (("v12 meta: sustained >=15min within 90min", risk_by_user),
                    ("KDoc claim: 2 readings <70 within 4h", legacy_by_user)):
        p_, lo_, hi_, used_ = cluster_bootstrap_auc(pu)
        if p_ is None:
            continue
        br_ = float(np.concatenate([pu[u][1] for u in used_]).mean())
        print(f"  {tag:44s} base {br_:.3f}  AUC {p_:.3f} [{lo_:.3f}, {hi_:.3f}]")
        result[("hypo_v12" if tag.startswith("v12") else "hypo_legacy") + "_pooled"] = {
            "auc": p_, "ci_lo": lo_, "ci_hi": hi_, "base_rate": br_}
    print()
    print("=" * 78)
    print("MATCHED BASELINES — same rows, same label, trivial predictors")
    print("=" * 78)
    for title, model_pu, baselines in (("hypo risk", risk_by_user, base_risk),
                                       ("meal likelihood", meal_by_user, base_meal)):
        print(f"\n### {title}")
        p, lo, hi, used = cluster_bootstrap_auc(model_pu)
        print(f"  {'the shipped model':22s} {p:6.3f}  [{lo:.3f}, {hi:.3f}]")
        result.setdefault("baselines", {})[title] = {}
        for bname, pu in baselines.items():
            bp, blo, bhi, bused = cluster_bootstrap_auc(pu)
            if bp is None:
                continue
            print(f"  {bname:22s} {bp:6.3f}  [{blo:.3f}, {bhi:.3f}]")
            result["baselines"][title][bname] = {"auc": bp, "ci_lo": blo, "ci_hi": bhi}
        # paired difference, model minus best baseline, resampling users
        best = max(baselines.items(),
                   key=lambda kv: (cluster_bootstrap_auc(kv[1])[0] or 0))
        bname, bpu = best
        common = [u for u in model_pu if u in bpu]
        if len(common) >= 2:
            rng = np.random.default_rng(20260813)
            diffs = []
            for _ in range(2000):
                pick = rng.choice(len(common), size=len(common), replace=True)
                ms = np.concatenate([model_pu[common[k]][0] for k in pick])
                ml_ = np.concatenate([model_pu[common[k]][1] for k in pick])
                bs = np.concatenate([bpu[common[k]][0] for k in pick])
                bl = np.concatenate([bpu[common[k]][1] for k in pick])
                a1, a2 = auc(ms, ml_), auc(bs, bl)
                if a1 is not None and a2 is not None:
                    diffs.append(a1 - a2)
            dlo, dhi = np.percentile(diffs, [2.5, 97.5])
            dpt = float(np.mean(diffs))
            sign = "beats" if dlo > 0 else ("LOSES TO" if dhi < 0 else "is indistinguishable from")
            print(f"  -> model minus '{bname}': {dpt:+.3f} [{dlo:+.3f}, {dhi:+.3f}] "
                  f"— the model {sign} the baseline")
            result["baselines"][title]["model_minus_best"] = {
                "baseline": bname, "delta": dpt, "ci_lo": float(dlo), "ci_hi": float(dhi)}

    print()
    print("=" * 78)
    print("HORIZON SWEEP — is the null about the model or about how far ahead it looks?")
    print("=" * 78)
    print("  The shipped model is trained and scored at +4h. Re-scoring the SAME scores")
    print("  against nearer horizons separates 'the model is weak' from '4h is too far'.")
    print("  The -BG column is the baseline at the same horizon: at short range 'glucose is")
    print("  already low' predicts a low trivially, and the model has to beat that to count.")
    print(f"\n  {'horizon':>8s} {'base':>7s} {'model':>7s} {'95% CI':>17s} "
          f"{'-BG':>7s} {'model - (-BG)':>22s}")
    sweep = {}
    for horizon in (30, 60, 90, 120, 180, 240):
        pu, pb = {}, {}
        for uid in sorted(decisions):
            rows = decisions[uid]
            if uid not in cgm:
                continue
            ts = np.array([r[0] for r in rows])
            bgv = np.array([r[1] for r in rows])
            risk = np.array([np.nan if r[2] is None else r[2] for r in rows])
            has = ~np.isnan(risk)
            if not has.sum():
                continue
            c_ts, c_bg = cgm[uid]
            y = label_hypo(ts[has], hypo_onsets(c_ts, c_bg, HYPO_MIN_SPAN_MIN), horizon)
            pu[uid] = (risk[has], y)
            pb[uid] = (-bgv[has], y)
        p, lo, hi, used = cluster_bootstrap_auc(pu)
        bp, blo, bhi, _ = cluster_bootstrap_auc(pb)
        br = float(np.concatenate([pu[u][1] for u in used]).mean()) if used else float("nan")
        if p is None:
            continue
        rng = np.random.default_rng(20260813)
        diffs = []
        for _ in range(2000):
            pick = rng.choice(len(used), size=len(used), replace=True)
            a1 = auc(np.concatenate([pu[used[k]][0] for k in pick]),
                     np.concatenate([pu[used[k]][1] for k in pick]))
            a2 = auc(np.concatenate([pb[used[k]][0] for k in pick]),
                     np.concatenate([pb[used[k]][1] for k in pick]))
            if a1 is not None and a2 is not None:
                diffs.append(a1 - a2)
        dlo, dhi = np.percentile(diffs, [2.5, 97.5])
        mark = "" if dlo <= 0 <= dhi else ("  (adds)" if dlo > 0 else "  (worse)")
        print(f"  {horizon:6d}m {br:7.3f} {p:7.3f}  [{lo:6.3f},{hi:6.3f}] {bp:7.3f} "
              f"  {np.mean(diffs):+.3f} [{dlo:+.3f},{dhi:+.3f}]{mark}")
        sweep[horizon] = {"auc": p, "ci_lo": lo, "ci_hi": hi, "base_rate": br,
                          "bg_baseline_auc": bp,
                          "delta_vs_bg": float(np.mean(diffs)),
                          "delta_lo": float(dlo), "delta_hi": float(dhi)}
    result["hypo_horizon_sweep"] = sweep

    print()
    print("=" * 78)
    print("CALIBRATION — observed rate by predicted decile")
    print("=" * 78)
    for name, scores, labels, key in (
            ("hypo risk", all_risk_scores, all_risk_labels, "hypo"),
            ("meal likelihood", all_meal_scores, all_meal_labels, "meal")):
        if not scores:
            continue
        s = np.concatenate(scores); y = np.concatenate(labels)
        rows = calibration(s, y)
        print(f"\n### {name}   (n={len(s)}, base rate {y.mean():.3f})")
        if key == "hypo":
            # AggressionBudget.kt: mlHypoRiskScale is 1.0 below risk 0.30 and falls linearly
            # to ML_HYPO_RISK_FLOOR (0.50 at the default knob) at risk 1.0. Printing it beside
            # the observed rate prices the on-policy confound instead of merely conceding it:
            # a decile where the damper never engaged cannot have had its events suppressed.
            print(f"  {'decile':>6s} {'n':>8s} {'pred':>7s} {'observed':>9s} {'damper':>8s}")
            for rr in rows:
                p_ = rr['pred_mean']
                scale = 1.0 if p_ <= 0.30 else max(0.50, 1.0 - 0.5 * (p_ - 0.30) / 0.70)
                rr['implied_damper'] = scale
                print(f"  {rr['bin']:6d} {rr['n']:8d} {p_:7.3f} {rr['obs_rate']:9.3f} {scale:8.3f}")
        else:
            print(f"  {'decile':>6s} {'n':>8s} {'pred':>7s} {'observed':>9s}")
            for rr in rows:
                print(f"  {rr['bin']:6d} {rr['n']:8d} {rr['pred_mean']:7.3f} {rr['obs_rate']:9.3f}")
        result[f"{key}_calibration"] = rows

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(result, fh, indent=2, default=float)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
