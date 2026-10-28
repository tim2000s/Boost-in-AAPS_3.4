"""Shared machinery for the meal anticipation questions, across the whole cohort at 5 min."""
import os, json, numpy as np, psycopg2, datetime as dt
DSN = "dbname=oref host=127.0.0.1 port=5432"
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
SINCE = "2025-08-01"
RISE_MGDL, CLIMB_WINDOW, TROUGH_LOOKBACK = 40.0, 90, 20

def users():
    with psycopg2.connect(DSN) as c, c.cursor() as cur:
        cur.execute("select user_id, count(*) from boost_cgm where cgm_mgdl is not null "
                    "and ts_utc >= %s group by 1 having count(*) > 20000 order by 1", (SINCE,))
        return [r[0] for r in cur.fetchall()]

def load_user(u):
    with psycopg2.connect(DSN) as c, c.cursor() as cur:
        cur.execute("select extract(epoch from ts_utc)*1000, cgm_mgdl from boost_cgm "
                    "where user_id=%s and cgm_mgdl is not null and ts_utc>=%s order by ts_utc",
                    (u, SINCE))
        r = cur.fetchall()
        ts = np.array([int(x[0]) for x in r], np.int64)
        bg = np.array([float(x[1]) for x in r], float)
        cur.execute("select extract(epoch from ts_utc)*1000, steps_5m, steps_30m, steps_60m "
                    "from boost_decisions where user_id=%s and ts_utc>=%s and steps_30m is not null "
                    "order by ts_utc", (u, SINCE))
        s = cur.fetchall()
    st_ts = np.array([int(x[0]) for x in s], np.int64) if s else np.zeros(0, np.int64)
    st = np.array([[float(x[1] or 0), float(x[2] or 0), float(x[3] or 0)] for x in s], float) \
         if s else np.zeros((0, 3))
    day = np.array([dt.datetime.fromtimestamp(t/1000, dt.UTC).date() for t in ts])
    tod = np.array([dt.datetime.fromtimestamp(t/1000, dt.UTC).hour +
                    dt.datetime.fromtimestamp(t/1000, dt.UTC).minute/60.0 for t in ts])
    return dict(user=u, ts=ts, bg=bg, day=day, tod=tod, st_ts=st_ts, st=st)

def align_steps(ts, st_ts, st, max_gap_min=7.5):
    """Nearest steps record within max_gap; NaN elsewhere."""
    out = np.full((len(ts), st.shape[1] if st.size else 3), np.nan)
    if not len(st_ts): return out
    j = np.clip(np.searchsorted(st_ts, ts), 0, len(st_ts)-1)
    jm = np.clip(j-1, 0, len(st_ts)-1)
    pick = np.where(np.abs(st_ts[j]-ts) <= np.abs(st_ts[jm]-ts), j, jm)
    gap = np.abs(st_ts[pick]-ts)/60_000.0
    ok = gap <= max_gap_min
    out[ok] = st[pick[ok]]
    return out

def nominal_interval(ts):
    return float(np.median(np.diff(ts))/60_000.0)

def causal_slope(ts, bg, window_min, nominal):
    k = max(int(round(window_min/nominal)), 2)
    x = np.arange(k+1, dtype=float)*nominal
    w = (x - x.mean())/((x - x.mean())**2).sum()*5.0
    out = np.full(len(bg), np.nan)
    conv = np.convolve(bg, w[::-1], mode="valid")
    out[k:] = conv[:len(out)-k]
    span = np.full(len(bg), np.inf); span[k:] = (ts[k:] - ts[:-k])/60_000.0
    out[np.abs(span - k*nominal) > 0.3*k*nominal] = np.nan
    return out

def causal_delta(ts, bg, back_min, nominal):
    k = max(int(round(back_min/nominal)), 1)
    out = np.full(len(bg), np.nan); out[k:] = bg[k:] - bg[:-k]
    span = np.full(len(bg), np.inf); span[k:] = (ts[k:] - ts[:-k])/60_000.0
    out[np.abs(span - k*nominal) > 0.3*k*nominal] = np.nan
    return out

def glucose_features(ts, bg, nominal):
    cols = [bg]
    for b in (5, 10, 15, 30, 45): cols.append(causal_delta(ts, bg, b, nominal))
    for w in (15, 30, 45): cols.append(causal_slope(ts, bg, w, nominal))
    return np.column_stack(cols)

def climb_episodes(ts, bg, nominal):
    n = len(ts); k_w = max(int(round(CLIMB_WINDOW/nominal)), 2)
    k_b = max(int(round(TROUGH_LOOKBACK/nominal)), 1)
    eps, i = [], k_b
    while i < n-2:
        j = min(i+k_w, n-1)
        if (ts[j]-ts[i])/60_000.0 > CLIMB_WINDOW*1.4: i += 1; continue
        seg = bg[i:j+1]
        if seg.max()-bg[i] < RISE_MGDL: i += 1; continue
        if bg[i] > bg[max(i-k_b, 0):i+1].min()+5.0: i += 1; continue
        pk = i+int(np.argmax(seg)); eps.append((i, pk)); i = pk+1
    return eps

def habit_prior(tod_train, onset_flag_train, tod_eval, n_slots=48, smooth=1.5):
    """Rate of climb onsets by time of day, estimated on training rows only."""
    slot_t = (tod_train/(24.0/n_slots)).astype(int) % n_slots
    num = np.bincount(slot_t, weights=onset_flag_train, minlength=n_slots)
    den = np.bincount(slot_t, minlength=n_slots).astype(float)
    # circular smoothing
    k = np.exp(-0.5*(np.arange(-4, 5)/smooth)**2); k /= k.sum()
    num = np.convolve(np.r_[num[-4:], num, num[:4]], k, mode="same")[4:-4]
    den = np.convolve(np.r_[den[-4:], den, den[:4]], k, mode="same")[4:-4]
    rate = num/np.maximum(den, 1.0)
    slot_e = (tod_eval/(24.0/n_slots)).astype(int) % n_slots
    return rate[slot_e]

def day_bootstrap(stat_fn, groups, n_boot=400, seed=20260731):
    rng = np.random.default_rng(seed)
    du = np.unique(groups); idx = {d: np.nonzero(groups == d)[0] for d in du}
    bs = []
    for _ in range(n_boot):
        pick = rng.choice(du, size=len(du), replace=True)
        sel = np.concatenate([idx[d] for d in pick])
        try:
            v = stat_fn(sel)
            if np.isfinite(v): bs.append(float(v))
        except Exception: pass
    if not bs: return (float("nan"), float("nan"))
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))

def save(name, obj):
    os.makedirs(RESULTS, exist_ok=True)
    p = os.path.join(RESULTS, name)
    with open(p, "w") as f: json.dump(obj, f, indent=1, default=float)
    print(f"  -> {p}")

def read(name):
    with open(os.path.join(RESULTS, name)) as f: return json.load(f)
