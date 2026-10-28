#!/usr/bin/env python3
"""Within-user V5/V6-era vs pre-era outcomes, with a never-migrated control.

Design
------
`boostv5_active` is an era flag (verified ~100% of cycles once a user migrates,
dipping only where the loop was off). For each migrated user we take:

  post = [first_v5 + 1 day, last CGM day]
  pre  = the equal-length calendar window immediately before first_v5

and compare CGM outcomes. Uncertainty is a day-level bootstrap (resample whole
days with replacement, 2000 draws) because CGM points within a day are heavily
autocorrelated and a per-point CI would be far too narrow.

User G never migrated, so G is run over the pooled post-window calendar dates
against its own matched pre-window as a never-treated control: if G moves by the
same amount, the shift is calendar/season, not the engine.

This is observational and within-subject. It is NOT a counterfactual: nothing
here rules out that the users who migrated also changed something else.
"""
import numpy as np, psycopg2, json, os

DSN = "dbname=oref host=127.0.0.1 port=5432"
HERE = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(20260729)
NBOOT = 2000


def q(sql, args=()):
    with psycopg2.connect(DSN) as c, c.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def era_bounds():
    """user -> (first_v5_date, last_cgm_date) for users with a migration."""
    rows = q("""
        select d.user_id,
               min(d.ts_utc) filter (where d.boostv5_active)::date,
               (select max(ts_utc)::date from boost_cgm g where g.user_id = d.user_id)
        from boost_decisions d group by 1 order by 1""")
    return {u: (f, l) for u, f, l in rows if f is not None}


def cgm_days(user, d0, d1):
    """[(date, np.array of mg/dL)] for a user over [d0, d1)."""
    rows = q("""
        select ts_utc::date, cgm_mgdl from boost_cgm
        where user_id=%s and ts_utc >= %s and ts_utc < %s and cgm_mgdl is not null
        order by ts_utc""", (user, d0, d1))
    by = {}
    for d, v in rows:
        by.setdefault(d, []).append(v)
    return [(d, np.asarray(v, float)) for d, v in sorted(by.items())]


def metrics(vals):
    v = vals
    return dict(
        tir=100 * np.mean((v >= 70) & (v <= 180)),
        ting=100 * np.mean((v >= 63) & (v <= 140)),
        tbr70=100 * np.mean(v < 70),
        tbr54=100 * np.mean(v < 54),
        tar180=100 * np.mean(v > 180),
        mean=float(np.mean(v)),
        cv=100 * np.std(v) / np.mean(v),
    )


def boot_diff(pre_days, post_days):
    """Day-level bootstrap of post-minus-pre for each metric -> (point, lo, hi)."""
    keys = ["tir", "ting", "tbr70", "tbr54", "tar180", "mean", "cv"]
    pre_arrs = [a for _, a in pre_days]
    post_arrs = [a for _, a in post_days]
    point = {k: metrics(np.concatenate(post_arrs))[k] - metrics(np.concatenate(pre_arrs))[k]
             for k in keys}
    draws = {k: [] for k in keys}
    npre, npost = len(pre_arrs), len(post_arrs)
    for _ in range(NBOOT):
        a = np.concatenate([pre_arrs[i] for i in RNG.integers(0, npre, npre)])
        b = np.concatenate([post_arrs[i] for i in RNG.integers(0, npost, npost)])
        ma, mb = metrics(a), metrics(b)
        for k in keys:
            draws[k].append(mb[k] - ma[k])
    out = {}
    for k in keys:
        lo, hi = np.percentile(draws[k], [2.5, 97.5])
        out[k] = (point[k], float(lo), float(hi))
    return out


def main():
    bounds = era_bounds()
    results, spans = {}, {}

    for user, (first, last) in sorted(bounds.items()):
        post0 = first + np.timedelta64(1, "D").astype("timedelta64[D]").item() if False else first
        # post starts the day AFTER migration begins (migration day is partial)
        import datetime as dt
        post0 = first + dt.timedelta(days=1)
        post1 = last + dt.timedelta(days=1)
        ndays = (post1 - post0).days
        if ndays < 14:
            spans[user] = dict(skipped=f"only {ndays} post-days")
            continue
        pre1, pre0 = first, first - dt.timedelta(days=ndays)
        pre_days = cgm_days(user, pre0, pre1)
        post_days = cgm_days(user, post0, post1)
        if len(pre_days) < 10 or len(post_days) < 10:
            spans[user] = dict(skipped=f"pre {len(pre_days)}d / post {len(post_days)}d")
            continue
        spans[user] = dict(first_v5=str(first), pre=f"{pre0}..{pre1}", post=f"{post0}..{post1}",
                           pre_days=len(pre_days), post_days=len(post_days))
        results[user] = dict(
            pre=metrics(np.concatenate([a for _, a in pre_days])),
            post=metrics(np.concatenate([a for _, a in post_days])),
            diff=boot_diff(pre_days, post_days))

    # never-migrated control: G, over the pooled median post window
    import datetime as dt
    firsts = [f for f, _ in bounds.values()]
    ref = sorted(firsts)[len(firsts) // 2]
    glast = q("select max(ts_utc)::date from boost_cgm where user_id='G'")[0][0]
    gpost0, gpost1 = ref + dt.timedelta(days=1), glast + dt.timedelta(days=1)
    gn = (gpost1 - gpost0).days
    gpre0, gpre1 = ref - dt.timedelta(days=gn), ref
    gpre, gpost = cgm_days("G", gpre0, gpre1), cgm_days("G", gpost0, gpost1)
    control = None
    if len(gpre) >= 10 and len(gpost) >= 10:
        spans["G(control)"] = dict(ref=str(ref), pre=f"{gpre0}..{gpre1}", post=f"{gpost0}..{gpost1}",
                                   pre_days=len(gpre), post_days=len(gpost))
        control = dict(pre=metrics(np.concatenate([a for _, a in gpre])),
                       post=metrics(np.concatenate([a for _, a in gpost])),
                       diff=boot_diff(gpre, gpost))

    out = dict(spans=spans, users=results, control_G=control, nboot=NBOOT)
    with open(os.path.join(HERE, "era_within_user.json"), "w") as f:
        json.dump(out, f, indent=1, default=float)

    # ---- print
    print("Windows")
    for u, s in spans.items():
        print(f"  {u:12s} {s}")
    hdr = f"\n{'user':6s} {'TIR Δ':>22s} {'TING Δ':>22s} {'TBR<70 Δ':>22s} {'TBR<54 Δ':>22s}"
    print(hdr)
    def cell(t):
        p, lo, hi = t
        return f"{p:+6.2f} [{lo:+6.2f},{hi:+6.2f}]"
    for u, r in results.items():
        d = r["diff"]
        print(f"{u:6s} {cell(d['tir']):>22s} {cell(d['ting']):>22s} "
              f"{cell(d['tbr70']):>22s} {cell(d['tbr54']):>22s}")
    if control:
        d = control["diff"]
        print(f"{'G*':6s} {cell(d['tir']):>22s} {cell(d['ting']):>22s} "
              f"{cell(d['tbr70']):>22s} {cell(d['tbr54']):>22s}   <- never migrated (control)")

    print("\nLevels (pre -> post): TIR / TING / TBR<70 / TBR<54 / mean / CV")
    for u, r in list(results.items()) + ([("G*", control)] if control else []):
        a, b = r["pre"], r["post"]
        print(f"  {u:6s} TIR {a['tir']:5.1f}->{b['tir']:5.1f}  TING {a['ting']:5.1f}->{b['ting']:5.1f}  "
              f"TBR70 {a['tbr70']:4.2f}->{b['tbr70']:4.2f}  TBR54 {a['tbr54']:4.2f}->{b['tbr54']:4.2f}  "
              f"mean {a['mean']:5.1f}->{b['mean']:5.1f}  CV {a['cv']:4.1f}->{b['cv']:4.1f}")


if __name__ == "__main__":
    main()
