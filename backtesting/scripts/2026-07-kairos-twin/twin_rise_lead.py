#!/usr/bin/env python3
"""
KAIROS Twin — does the forecast POINT lead real upward excursions earlier than the incumbent's
own forward predictor? The identifiable gate for the RISE-RETIMING brick (2026-07-18).

The mirror of the withdrawal gate (TWIN_HYPO_LEAD.md). There, the Twin's 30-min forecast FLOOR
(lo30) led real lows at ⅓–½ the false alarms of oref's hypo predictors → withdraw earlier on the
descent. Here we ask the up-side question: does the Twin's 30-min forecast POINT (fc30) lead real
RISES earlier than oref's own eventualBG (and the naive "BG already rising" reaction), at matched
false-alarm rate? If yes, a Twin-informed confirm could bring the dose the incumbent would give
ANYWAY one or two cycles earlier — moving insulin, not adding it (harm-neutral, register-proven),
shaving the 140–180 peak that is the addressable TING loss.

Ground truth = objective rise events from CGM alone: BG crosses >170 having been <=140 within the
prior 30 min (a genuine upward excursion needing a correction), deduped 60 min. Predictors swept
over their own threshold, compared AT MATCHED SENSITIVITY (sensitivity saturates → FA is the axis):
  Twin fc30   30-min calibrated forecast median (offline EnKF replay, the shipped scheme)
  Twin hi30   30-min upper band (expected to cry wolf, like lo60 did — the control)
  oref eventualBG   sug_eventualbg (the incumbent's own forward BG)
  trend       BG already rising: cgm[t]-cgm[t-3] (the naive reactive signal)
A predictor "leads" a rise if it fires in [t*-45min, t*-10min] (>=10 min lead to act). FA = firing
on a rising/flat cycle with NO excursion in the next 60 min. Cross-user then pooled. Aggregates only.
"""
import numpy as np, psycopg2
DT = 300; SUB = 5; M = 120; DAYS = 45
USERS = ['tim', 'F', 'H', 'B', 'E', 'A', 'C']
PRIOR = dict(ka1=0.030, ka2=0.022, p2=0.028, SI=0.00055, SG=0.021, Gb=118.0, taui=12.0, kra=0.020)
INFLATE0, MEAL_P, MEAL_RA = 28.0, 0.03, 5.0        # calibrated forecast scheme (twin_calibrate.py)
Qsd = np.array([0.02, 0.02, 1e-4, 0.55, 2.0, 0.6]); Qf = np.array([0.0, 0.0, 0.0, 0.95, 2.2, 0.0]); Rsd = 6.0


def step(x, u, P):
    Isc1, Isc2, X, Ra, G, Gi = x
    Isc1 = Isc1 + (-P['ka1'] * Isc1) + u; Isc2 = Isc2 + (P['ka1'] * Isc1 - P['ka2'] * Isc2)
    X = X + (-P['p2'] * X + P['p2'] * P['SI'] * Isc2); Ra = Ra + (-P['kra'] * Ra)
    G = G + (-P['SG'] * (G - P['Gb']) - X * np.maximum(G, 1.0) + Ra); Gi = Gi + (G - Gi) / P['taui']
    return np.array([Isc1, Isc2, np.maximum(X, 0), Ra, np.maximum(G, 10.0), np.maximum(Gi, 10.0)])


def forward5(x, u5, P):
    for _ in range(SUB):
        x = step(x, u5 / SUB, P)
    return x


def run_forecast(CGM, INS, P, h=6, seed=1):
    """Filtering EnKF + calibrated forecast at horizon h. Returns fc[N] (median) and hi[N] (95th)."""
    rng = np.random.default_rng(seed); N = len(CGM)
    g0 = np.nanmedian(CGM[:200]); g0 = 120.0 if np.isnan(g0) else g0
    x = np.zeros((6, M)); x[4] = g0 + rng.normal(0, 8, M); x[5] = g0 + rng.normal(0, 8, M); x[3] = rng.normal(0, 2, M)
    fc = np.full(N, np.nan); hi = np.full(N, np.nan)
    for i in range(N):
        xf = x.copy()
        xf[4] += rng.standard_normal(M) * INFLATE0; xf[5] += rng.standard_normal(M) * INFLATE0
        for j in range(h):
            fut = INS[i + j] if i + j < N else INS[min(i, N - 1)]
            xf = forward5(xf, fut, P) + Qf[:, None] * rng.standard_normal((6, M))
            meal = (rng.random(M) < MEAL_P); xf[3] += meal * np.abs(rng.standard_normal(M)) * MEAL_RA
            xf[4] = np.maximum(xf[4], 10)
        gi_obs = xf[5] + rng.normal(0, Rsd, M)
        fc[i] = np.median(xf[5]); hi[i] = np.percentile(gi_obs, 95)
        x = forward5(x, INS[i], P) + Qsd[:, None] * rng.standard_normal((6, M))
        x[4] = np.maximum(x[4], 10); x[5] = np.maximum(x[5], 10); x[2] = np.maximum(x[2], 0)
        if not np.isnan(CGM[i]):
            y = CGM[i]; hx = x[5]; hm = hx.mean(); xm = x.mean(1, keepdims=True)
            Pxy = ((x - xm) * (hx - hm)).mean(1); Pyy = ((hx - hm) ** 2).mean() + Rsd ** 2; K = Pxy / Pyy
            x = x + K[:, None] * (y + rng.normal(0, Rsd, M) - hx)[None, :]
            x[4] = np.maximum(x[4], 10); x[5] = np.maximum(x[5], 10); x[2] = np.maximum(x[2], 0)
    return fc, hi


def pull(cur, uid):
    cur.execute("""select ts_epoch,cgm_mgdl,boostv5_finaldose,sug_rate,sug_eventualbg
                   from boost_decisions where user_id=%s and cgm_mgdl is not null and boostv5_active
                     and ts_utc>now()-interval '%s days' order by ts_epoch""", (uid, DAYS))
    rows = cur.fetchall()
    if not rows: return None
    ep = np.array([r[0] for r in rows], float); t0 = int(ep.min() // DT * DT); t1 = int(ep.max() // DT * DT)
    grid = np.arange(t0, t1 + DT, DT); n = len(grid)
    cgm = np.full(n, np.nan); ins = np.zeros(n); ev = np.full(n, np.nan)
    for ts, g, fd, sr, evb in rows:
        k = int((ts // DT * DT - t0) // DT)
        if not (0 <= k < n): continue
        if g and g > 0: cgm[k] = g
        ins[k] = (fd or 0.0) + (sr or 0.0) / 12.0
        if evb is not None: ev[k] = evb
    med = np.nanmedian(ev)
    if not np.isnan(med) and med < 30: ev *= 18.0        # mmol/L -> mg/dL where needed
    return dict(cgm=cgm, ins=ins, ev=ev)


def rise_events(cgm):
    n = len(cgm); evs = []; last = -999
    for t in range(6, n):
        if np.isnan(cgm[t]): continue
        if cgm[t] > 170 and np.nanmin(cgm[max(0, t - 6):t + 1]) <= 140 and (t - last) > 12:
            # first crossing of 170 after being <=140 within 30 min
            if cgm[t - 1] <= 170 or last < 0:
                evs.append(t); last = t
    return evs


LEAD_MIN, LEAD_MAX = 2, 9    # fire window t*-45 .. t*-10 min
TH = {'fc30': [130, 140, 150, 160, 170, 180], 'hi30': [150, 170, 190, 210, 230],
      'eventual': [130, 140, 150, 160, 170, 180], 'trend': [4, 7, 10, 14, 18]}


def accumulate(fire, cgm, evs, n, agg_slot, lead_slot):
    ev_mask = np.zeros(n, bool)
    for t in evs: ev_mask[max(0, t - 6):min(n, t + 18)] = True     # peri-rise exclusion for FA
    hit = 0
    for t in evs:
        idx = [k for k in range(max(0, t - LEAD_MAX), max(0, t - LEAD_MIN + 1)) if fire[k]]
        if idx: hit += 1; lead_slot.append((t - idx[0]) * 5.0)
    elig = fa = 0
    for t in range(3, n - 12):
        if np.isnan(cgm[t]) or np.isnan(cgm[t - 1]) or cgm[t] < cgm[t - 1] or ev_mask[t]: continue   # rising/flat only
        if any(k in evs for k in range(t + 1, t + 13)): continue
        elig += 1; fa += 1 if fire[t] else 0
    agg_slot[0] += hit; agg_slot[1] += len(evs); agg_slot[2] += fa; agg_slot[3] += elig


def main():
    conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
    names = ['fc30', 'hi30', 'eventual', 'trend']
    agg = {nm: {th: [0, 0, 0, 0] for th in TH[nm]} for nm in names}
    leadp = {nm: {th: [] for th in TH[nm]} for nm in names}
    total_rise = 0
    for uid in USERS:
        d = pull(cur, uid)
        if d is None: print(f"{uid}: none"); continue
        cgm = d['cgm']; n = len(cgm); P = dict(PRIOR); P['Gb'] = float(np.nanmedian(cgm))
        fc, hi = run_forecast(cgm, d['ins'], P); evs = rise_events(cgm); total_rise += len(evs)
        trend = np.full(n, np.nan)
        for t in range(3, n):
            if not np.isnan(cgm[t]) and not np.isnan(cgm[t - 3]): trend[t] = cgm[t] - cgm[t - 3]
        vals = {'fc30': fc, 'hi30': hi, 'eventual': d['ev'], 'trend': trend}
        for nm in names:
            v = vals[nm]
            for th in TH[nm]:
                fire = np.array([(not np.isnan(v[t])) and v[t] > th for t in range(n)])
                accumulate(fire, cgm, evs, n, agg[nm][th], leadp[nm][th])
        print(f"{uid}: rises={len(evs)}  (n={n})")

    def roc(nm):
        out = []
        for th in TH[nm]:
            hit, nev, fa, elig = agg[nm][th]
            out.append(dict(thr=th, sens=hit / max(1, nev), fa=fa / max(1, elig),
                            lead=float(np.median(leadp[nm][th])) if leadp[nm][th] else None))
        return out
    rocs = {nm: roc(nm) for nm in names}
    print(f"\ntotal rise events: {total_rise}")
    for nm in names:
        print(f"\n{nm} ROC:")
        for r in rocs[nm]:
            print(f"  thr={r['thr']:>3}  sens={r['sens']:.2f}  fa={r['fa']:.3f}  lead={r['lead']}min")

    def best_at(nm, tgt):
        ok = [x for x in rocs[nm] if x['sens'] >= tgt]
        return min(ok, key=lambda x: x['fa']) if ok else None
    print("\n=== MATCHED-SENSITIVITY (lowest FA to catch >= target; fa / lead) ===")
    for tgt in (0.70, 0.80, 0.90):
        def fmt(nm):
            b = best_at(nm, tgt); return f"{nm}: fa={b['fa']:.3f} lead={b['lead']}m" if b else f"{nm}: n/a"
        print(f"  catch>={tgt:.2f}:  {fmt('fc30')}  |  {fmt('eventual')}  |  {fmt('trend')}  |  {fmt('hi30')}")
    print("\nGate: if fc30 catches real rises at LOWER FA and/or MORE lead than oref eventualBG and the")
    print("naive trend, the Twin can bring the incumbent's dose earlier safely (move, not add) → the")
    print("rise-retiming shadow is justified. This is a PREDICTION win only; the retiming ACTION is")
    print("policy (shadow-first, two-test bar). hi30 is expected to cry wolf (the control).")
    conn.close()


if __name__ == '__main__':
    main()
