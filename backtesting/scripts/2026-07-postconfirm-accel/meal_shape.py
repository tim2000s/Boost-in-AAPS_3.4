"""
Meal-SHAPE-at-confirm prediction test.

Question: at the CONFIRMED cycle, can we predict the meal's eventual SHAPE — which need
opposite handling — from features available AT confirm? Identification-clean (keep observed
BG, ask what follows). GroupKFold by USER (no cross-user leakage). Bootstrap CIs.

Shapes (from the forward trajectory, anchor t0 = CONFIRMED cycle):
  peak     = max BG in (0, 120] min ; t_peak = its time
  CRASH    = min BG in (t_peak, 180] < 70            -> needs RESTRAINT
  TAIL     = not crash AND median BG in (120, 210] > 150  -> under-recovery, needs SUSTAIN/plateau-nudge
  CLEAN    = otherwise (resolved to range, no crash)

Confirm-time features (all strictly <= t0):
  bg0, delta0 (5min), rise15 (15min), accel0 (delta_acceleration), score0 (boostv5_score),
  iob0, evoff0 (eventualBG-target), uamoff0, mlmeal0, budget0, tod_hour(sin/cos)

If shape is separable OOS (per-class AUC > 0.5, CI clear of 0.5) -> it can ROUTE meals to the
right existing lever at confirm. If not -> shape is only discoverable reactively (Fix 7 is right).
"""
import psycopg2, numpy as np, pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
import lightgbm as lgb

np.random.seed(20260720)
con = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql("""
  select user_id, ts_epoch, cgm_mgdl, boostv5_state, delta_acceleration, boostv5_score,
         iob_iob, sug_eventualbg, sug_current_target, reason_uampredbg, ml_meal_likely, boostv5_budget
  from boost_decisions where boostv5_state is not null and cgm_mgdl is not null
""", con)
con.close()

rows = []
for uid, g in df.groupby('user_id'):
    g = g.sort_values('ts_epoch').reset_index(drop=True)
    t = g['ts_epoch'].values.astype(float)
    bg = g['cgm_mgdl'].values.astype(float)
    st = g['boostv5_state'].values
    def at(arr, i):
        v = arr[i]; return float(v) if v is not None and not (isinstance(v,float) and np.isnan(v)) else np.nan
    conf = np.where(st == 'CONFIRMED')[0]
    last_anchor_t = -1e18
    for i in conf:
        t0 = t[i]
        if t0 - last_anchor_t < 20*60:   # dedupe re-invokes within same meal
            continue
        # --- forward label windows ---
        pk = (t > t0) & (t <= t0 + 120*60)
        late = (t > t0 + 120*60) & (t <= t0 + 210*60)
        if pk.sum() < 3 or late.sum() < 3:   # need forward coverage
            continue
        peak = np.nanmax(bg[pk]); tpk = t[pk][np.nanargmax(bg[pk])]
        crashw = (t > tpk) & (t <= t0 + 180*60)
        minpost = np.nanmin(bg[crashw]) if crashw.sum() else np.nan
        late_med = np.nanmedian(bg[late])
        if np.isnan(minpost): continue
        if minpost < 70: shape = 'CRASH'
        elif late_med > 150: shape = 'TAIL'
        else: shape = 'CLEAN'
        last_anchor_t = t0
        # --- confirm-time features (<= t0) ---
        b5  = bg[max(0,i-1)]; b15 = bg[max(0,i-3)]
        hr = (t0 % 86400) / 3600.0
        rows.append(dict(
            user=uid, shape=shape,
            bg0=bg[i], delta0=bg[i]-b5, rise15=bg[i]-b15,
            accel0=at(g['delta_acceleration'].values,i), score0=at(g['boostv5_score'].values,i),
            iob0=at(g['iob_iob'].values,i),
            evoff0=at(g['sug_eventualbg'].values,i)-at(g['sug_current_target'].values,i),
            uamoff0=at(g['reason_uampredbg'].values,i)-bg[i],
            mlmeal0=at(g['ml_meal_likely'].values,i), budget0=at(g['boostv5_budget'].values,i),
            tod_sin=np.sin(2*np.pi*hr/24), tod_cos=np.cos(2*np.pi*hr/24),
        ))
r = pd.DataFrame(rows)
FEATS = ['bg0','delta0','rise15','accel0','score0','iob0','evoff0','uamoff0','mlmeal0','budget0','tod_sin','tod_cos']
print(f"anchors: {len(r)}   base rates: " + ", ".join(f"{k} {v:.1%}" for k,v in r['shape'].value_counts(normalize=True).items()))
print("per-user shape mix:")
print((r.groupby('user')['shape'].value_counts(normalize=True).unstack().fillna(0)*100).round(0).astype(int).to_string())

# OOS multiclass via GroupKFold; collect out-of-fold probabilities
classes = ['CRASH','TAIL','CLEAN']
y = r['shape'].values
X = r[FEATS].values
groups = r['user'].values
oof = np.zeros((len(r), len(classes)))
imp = np.zeros(len(FEATS))
gkf = GroupKFold(n_splits=min(8, r['user'].nunique()))
for tr, te in gkf.split(X, y, groups):
    ytr = pd.Categorical(y[tr], categories=classes).codes
    m = lgb.LGBMClassifier(n_estimators=250, num_leaves=31, learning_rate=0.03,
                           min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
                           class_weight='balanced', verbose=-1)
    m.fit(X[tr], ytr)
    oof[te] = m.predict_proba(X[te])
    imp += m.feature_importances_
def boot_auc(yb, pb, nb=2000):
    idx = np.arange(len(yb)); a=[]
    for _ in range(nb):
        s = np.random.choice(idx, len(idx), replace=True)
        if len(np.unique(yb[s]))<2: continue
        a.append(roc_auc_score(yb[s], pb[s]))
    return np.percentile(a,[2.5,50,97.5])
print("\n=== OOS one-vs-rest AUC (GroupKFold by user, bootstrap 95% CI) ===")
for c in classes:
    yb = (y==c).astype(int); pb = oof[:, classes.index(c)]
    lo,md,hi = boot_auc(yb,pb)
    verdict = "SEPARABLE" if lo>0.5 else "not distinguishable from chance"
    print(f"  {c:6} (base {yb.mean():5.1%})  AUC {md:.3f} [{lo:.3f}, {hi:.3f}]  -> {verdict}")
print("\n=== feature importance (gain-split, summed over folds) ===")
for f,v in sorted(zip(FEATS, imp), key=lambda z:-z[1]):
    print(f"  {f:9} {v:6.0f}")
