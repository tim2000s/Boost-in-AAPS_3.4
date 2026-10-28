#!/usr/bin/env python3
"""Q2. Can the remaining rise be bounded well enough to size a dose?

Flagging that a peak is near is not what a dose decision needs. The quantity needed is how much
further glucose will rise, because that is what determines how much insulin is still required.

For every point inside a climb the target is peak glucose minus current glucose. Models are per
user, validated with GroupKFold over whole days, and use glucose history together with time of
day. Results are reported three ways:

  as normalised error, where 1.0 means no better than predicting the user's mean remaining rise
  as the width of the central 90% of the residual, in mg/dL
  as that width converted to insulin units at the user's own insulin sensitivity factor

The third is the one that answers the question. If the residual spans a large fraction of a
meal bolus then the prediction cannot size a dose, however good its correlation looks.
"""
import sys, os, numpy as np, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anticip_lib as A
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

def user_isf_and_bolus(u):
    with psycopg2.connect(A.DSN) as c, c.cursor() as cur:
        cur.execute("select percentile_cont(0.5) within group (order by isf_mgdl_for_carbs) "
                    "from boost_decisions where user_id=%s and ts_utc>=%s "
                    "and isf_mgdl_for_carbs is not null and isf_mgdl_for_carbs between 5 and 400",
                    (u, A.SINCE))
        isf = cur.fetchone()[0]
        cur.execute("select percentile_cont(0.5) within group (order by sug_cob) "
                    "from boost_decisions where user_id=%s and ts_utc>=%s and sug_cob > 5", (u, A.SINCE))
        cob = cur.fetchone()[0]
    return (float(isf) if isf else None), (float(cob) if cob else None)

print("03. CAN THE REMAINING RISE BE BOUNDED?\n")
print(f"  {'user':>4s} {'n':>7s} {'SD of target':>13s} {'nRMSE':>7s} {'resid SD':>9s} "
      f"{'90% width':>10s} {'ISF':>6s} {'90% width in U':>15s}")
rows = []
for u in A.users():
    d = A.load_user(u)
    ts, bg, day, tod = d["ts"], d["bg"], d["day"], d["tod"]
    nom = A.nominal_interval(ts); nom = 5.0 if nom > 3.0 else nom
    n = len(ts)
    G = A.glucose_features(ts, bg, nom)
    tcyc = np.column_stack([np.sin(2*np.pi*tod/24), np.cos(2*np.pi*tod/24),
                            np.sin(4*np.pi*tod/24), np.cos(4*np.pi*tod/24)])
    X = np.column_stack([G, tcyc])
    eps = A.climb_episodes(ts, bg, nom)
    tgt = np.full(n, np.nan)
    for a, pk in eps: tgt[a:pk] = bg[pk] - bg[a:pk]
    m = np.isfinite(X).all(1) & np.isfinite(tgt)
    if m.sum() < 1500: continue
    y = tgt[m]; g = day[m]; Xm = X[m]
    p = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=5).split(Xm, y, groups=g):
        sc = StandardScaler().fit(Xm[tr])
        p[te] = LinearRegression().fit(sc.transform(Xm[tr]), y[tr]).predict(sc.transform(Xm[te]))
    resid = y - p
    nrmse = float(np.sqrt(np.mean(resid**2))/y.std())
    w90 = float(np.percentile(resid, 95) - np.percentile(resid, 5))
    isf, cob = user_isf_and_bolus(u)
    u90 = w90/isf if isf else None
    rows.append(dict(user=u, n=int(m.sum()), target_sd=float(y.std()), target_mean=float(y.mean()),
                     nrmse=nrmse, resid_sd=float(resid.std()), width90=w90, isf=isf,
                     width90_units=u90, median_cob=cob))
    print(f"  {u:>4s} {int(m.sum()):7,d} {y.std():13.1f} {nrmse:7.3f} {resid.std():9.1f} "
          f"{w90:10.1f} {isf if isf else float('nan'):6.1f} "
          f"{u90 if u90 else float('nan'):15.2f}")

print(f"\n  Cohort medians: nRMSE {np.median([r['nrmse'] for r in rows]):.3f}, "
      f"90% residual width {np.median([r['width90'] for r in rows]):.1f} mg/dL, "
      f"{np.median([r['width90_units'] for r in rows if r['width90_units']]):.2f} U")
cobs = [r['median_cob'] for r in rows if r['median_cob']]
if cobs:
    print(f"  For scale, the median announced carbohydrate load when one is entered is "
          f"{np.median(cobs):.0f} g.")
    for r in rows:
        if r['median_cob'] and r['isf']:
            r['typical_meal_units'] = r['median_cob']/10.0   # rough, 10 g per unit
    tu = [r.get('typical_meal_units') for r in rows if r.get('typical_meal_units')]
    if tu:
        print(f"  At a nominal 10 g per unit that is about {np.median(tu):.1f} U for a typical meal.")
        ratio = [r['width90_units']/r['typical_meal_units'] for r in rows
                 if r.get('typical_meal_units') and r.get('width90_units')]
        print(f"  The 90% residual spans {np.median(ratio):.2f} times a typical meal dose "
              f"(range {np.min(ratio):.2f} to {np.max(ratio):.2f}).")
A.save("03_remaining_rise.json", rows)
