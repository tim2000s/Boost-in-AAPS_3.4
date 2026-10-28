#!/usr/bin/env python3
"""user H — early-insulin diagnosis. Dedupe per 5-min bucket, meal episodes,
confirm latency, cap-clip split, glycaemia, base-vs-V6 comparison."""
import re, json
import numpy as np, pandas as pd, psycopg2

conn = psycopg2.connect("dbname=oref")
TZ = "Etc/GMT-2"

dec = pd.read_sql("""
  SELECT ts_utc, variant, cgm_mgdl, sug_eventualbg, sug_insulinreq, sug_cob, sug_iob,
         v1_units, boostv5_state, boostv5_finaldose, boostv5_budget, boostv5_actionmult,
         boostv5_score, boostv5_age, boostv5_gatereduction, boostv5_committedcap,
         boostv5_confirmedcap, ml_hypo_risk, reason_text, tdd
  FROM boost_decisions WHERE user_id='H' ORDER BY ts_utc
""", conn)
cgm = pd.read_sql("SELECT ts_utc, cgm_mgdl FROM boost_cgm WHERE user_id='H' ORDER BY ts_utc", conn)

dec["ts_utc"] = pd.to_datetime(dec.ts_utc, utc=True)
cgm["ts_utc"] = pd.to_datetime(cgm.ts_utc, utc=True)

# ── dedupe decisions per 5-min bucket (keep last upload per bucket)
dec["bucket"] = dec.ts_utc.dt.floor("5min")
dec = dec.sort_values("ts_utc").groupby("bucket", as_index=False).last()
print(f"decisions after 5-min dedupe: {len(dec)}  ({dec.ts_utc.min()} -> {dec.ts_utc.max()})")

# base would-dose from reason (V6 era): "base would=0.0U" / "base SMB 0.05U"
def base_would(r):
    if not isinstance(r, str): return np.nan
    m = re.search(r"base would=([\d.]+)U", r)
    if m: return float(m.group(1))
    m = re.search(r"base SMB ([\d.]+)U", r)
    if m: return float(m.group(1))
    return np.nan
dec["base_would"] = dec.reason_text.apply(base_would)
dec["v6_active_cycle"] = dec.reason_text.str.contains("V6-ACTIVE", na=False)
dec["v6_suppressed"] = dec.reason_text.str.contains("V6 suppressed", na=False)

# CGM dedupe per 5 min
cgm["bucket"] = cgm.ts_utc.dt.floor("5min")
cgm = cgm.sort_values("ts_utc").groupby("bucket", as_index=False).last()
cgm = cgm.set_index("bucket").sort_index()

# ── glycaemia by era ─────────────────────────────────────────────
V6_START = pd.Timestamp("2026-06-29 22:00", tz="UTC")  # V6 era begins 06-30 local
def glyc(g, label):
    v = g.cgm_mgdl.dropna()
    if len(v) == 0: return
    print(f"{label:28s} n={len(v):6d} mean={v.mean():5.0f} TIR70-180={((v>=70)&(v<=180)).mean()*100:4.1f}% "
          f"TING63-140={((v>=63)&(v<=140)).mean()*100:4.1f}% >180={(v>180).mean()*100:4.1f}% "
          f">250={(v>250).mean()*100:4.1f}% <70={(v<70).mean()*100:4.2f}% <54={(v<54).mean()*100:4.2f}%")
print("\n=== GLYCAEMIA (deduped CGM) ===")
glyc(cgm, "ALL (05-04..07-05)")
glyc(cgm[cgm.index <  V6_START], "V1/V2-acting era (<06-30)")
glyc(cgm[cgm.index >= V6_START], "V6-ACTIVE era (>=06-30)")
# last 14d of V1 era for fair season comparison
glyc(cgm[(cgm.index >= V6_START - pd.Timedelta(days=14)) & (cgm.index < V6_START)], "V1 era last 14d")

# ── meal episode detection from CGM: rise >= 30 mg/dL over 35 min ──
c = cgm.cgm_mgdl.resample("5min").median().interpolate(limit=2)
rise35 = c - c.shift(7)
onset = (rise35 >= 30) & ((rise35.shift(1) < 30) | rise35.shift(1).isna())
# collapse onsets within 90 min of each other
onset_times = list(c.index[onset.fillna(False)])
episodes = []
for t in onset_times:
    if episodes and (t - episodes[-1]) < pd.Timedelta("90min"): continue
    episodes.append(t)
print(f"\nmeal-rise episodes (>=30mg/dL/35min, 90min collapse): {len(episodes)}")

# per-episode stats over following 3h
def episode_stats(t0, dec_era):
    w = c[t0 - pd.Timedelta("35min"): t0 + pd.Timedelta("3h")]
    if w.empty: return None
    start_bg = c.asof(t0 - pd.Timedelta("35min"))
    peak = w.max(); t_peak = (w.idxmax() - t0).total_seconds()/60
    over180 = (w[t0:] > 180).sum() * 5
    d = dec_era[(dec_era.bucket >= t0 - pd.Timedelta("10min")) & (dec_era.bucket <= t0 + pd.Timedelta("3h"))]
    return dict(t0=t0, start_bg=start_bg, peak=peak, t_peak_min=t_peak, min_over180=over180, dec=d)

v6dec = dec[dec.variant == "boost-other"]
v1dec = dec[dec.variant.isin(["v1","v2","v1-silent"])]

print("\n=== V6-ERA MEAL EPISODES (06-30 → 07-05) ===")
v6_eps = [e for t in episodes if t >= V6_START and (e:=episode_stats(t, v6dec)) and len(e["dec"])>0]
lat_rows = []
for e in v6_eps:
    d = e["dec"].sort_values("bucket")
    states = d.boostv5_state.tolist()
    # confirm latency: first CONFIRMED at/after onset
    conf = d[(d.boostv5_state=="CONFIRMED") & (d.bucket>=e["t0"])]
    committed = d[(d.boostv5_state=="COMMITTED") & (d.bucket>=e["t0"])]
    lat = (conf.bucket.iloc[0] - e["t0"]).total_seconds()/60 if len(conf) else np.nan
    lat_c = (committed.bucket.iloc[0] - e["t0"]).total_seconds()/60 if len(committed) else np.nan
    # doses in first 60 min from onset
    d60 = d[(d.bucket>=e["t0"]) & (d.bucket < e["t0"]+pd.Timedelta("60min"))]
    v6_u = d60.v1_units.fillna(0).sum()
    base_u = d60.base_would.fillna(0).sum()
    local = e["t0"].tz_convert(TZ)
    lat_rows.append(dict(t0=str(local)[:16], start=e["start_bg"], peak=e["peak"],
        t_peak=e["t_peak_min"], min180=e["min_over180"], lat_confirm=lat, lat_commit=lat_c,
        v6_u60=round(v6_u,2), base_u60=round(base_u,2),
        states="/".join(pd.Series(states).value_counts().index[:3])))
ep = pd.DataFrame(lat_rows)
pd.set_option("display.width", 250)
print(ep.to_string(index=False))
if len(ep):
    print(f"\nmedian peak={ep.peak.median():.0f} mg/dL; median min>180 per episode={ep.min180.median():.0f}")
    print(f"confirm latency: median={ep.lat_confirm.median():.0f}min reached-CONFIRMED {ep.lat_confirm.notna().sum()}/{len(ep)}")
    print(f"commit latency:  median={ep.lat_commit.median():.0f}min reached-COMMITTED {ep.lat_commit.notna().sum()}/{len(ep)}")
    print(f"V6 delivered first-60min: median={ep.v6_u60.median():.2f}U  base-would median={ep.base_u60.median():.2f}U")

# ── cap-clip analysis on V6-era dosing cycles ──────────────────────
print("\n=== CAP ANALYSIS (V6 era, deduped) ===")
CC, CF = 0.5, 2.5  # operative caps 06-30..07-04 era (2.5 pre-update; 4.0 from 07-05)
dv = v6dec[v6dec.boostv5_finaldose > 0].copy()
dv["cap"] = np.where(dv.bucket >= pd.Timestamp("2026-07-05", tz="UTC"),
                     np.where(dv.boostv5_state=="COMMITTED", 0.5, 4.0),
                     np.where(dv.boostv5_state=="COMMITTED", CC, CF))
for st in ["COMMITTED","CONFIRMED"]:
    g = dv[dv.boostv5_state==st]
    clip = (g.boostv5_finaldose >= g.cap - 0.011)
    print(f"{st}: dosing cycles={len(g)} at-cap={clip.sum()} ({clip.mean()*100:.0f}%)")

# meal-phase under-delivery split (HIM): within meal episodes, cycles where V6 delivered < base would
print("\n=== MEAL-PHASE UNDER-DELIVERY vs BASE ENGINE (V6 era, first 90min of episodes) ===")
rows = []
for e in v6_eps:
    d = e["dec"]
    d90 = d[(d.bucket>=e["t0"]) & (d.bucket < e["t0"]+pd.Timedelta("90min"))].copy()
    rows.append(d90)
md = pd.concat(rows) if rows else pd.DataFrame()
if len(md):
    md["v6u"] = md.v1_units.fillna(0); md["baseu"] = md.base_would.fillna(0)
    under = md[md.v6u < md.baseu - 0.01]
    md["cap"] = np.where(md.boostv5_state=="COMMITTED", CC, np.where(md.boostv5_state=="CONFIRMED", CF, np.inf))
    under_capped = under[under.v6u >= under.cap.loc[under.index] - 0.011] if len(under) else under
    tot_gap = (md.baseu - md.v6u).clip(lower=0).sum()
    print(f"meal-phase cycles={len(md)}  V6 total={md.v6u.sum():.1f}U  base-would total={md.baseu.sum():.1f}U")
    print(f"under-delivered cycles={len(under)} gap={tot_gap:.1f}U; of gap, on cap-clipped cycles: "
          f"{(md.baseu - md.v6u).clip(lower=0)[md.v6u >= md.cap - 0.011].sum():.1f}U")
    print("state mix on under-delivered cycles:", under.boostv5_state.value_counts().to_dict())
    print("state mix all meal-phase cycles:", md.boostv5_state.value_counts().to_dict())
conn.close()
