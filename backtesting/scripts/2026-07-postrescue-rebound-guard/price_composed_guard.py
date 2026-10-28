#!/usr/bin/env python3
"""Price the composed post-rescue rebound guard (2026-07-23, user-H incident).

Proposal: apply the graduated fast-carb scale s(bg) to the FINAL SMB after tier
selection whenever the post-rescue window (45-min rolling min BG < 75) is active
and COB == 0 and bg < 170 — instead of only inside T3/T5/T6 and only while
delta_accl > 25. This closes the T7/T8 hole that delivered 3.55U at BG 97
25 min after a 67 mg/dL low (user H, 2026-07-23), which the V6 post-rescue cap
then inherited ("capped from 4.0U to V1's 3.55U").

s(bg) = 0.3 for bg < 120, linear 0.3 -> 1.0 over 120..170, 1.0 above.

Pricing mirrors postrescue_cap.py (2026-07-04, SHIP benchmark 27%):
  - universe: dosing cycles (delivered > 0) with min45 < 75, COB == 0, bg < 170
  - delivered basis: min(v6 finaldose, v1_units) in V6 meal-state rows
    (post-rescue cap already live), v1_units otherwise
  - cycles already scaled by the live guard (fast_carb_protection on AND tier in
    T3/T5/T6) are excluded — the change is a no-op there
  - removed = delivered * (1 - s)
  - episodes = consecutive affected cycles (gap <= 30 min)
  - benefit: % of removed insulin sitting ahead of a second low < 70 within 3h
  - cost: episodes that were genuine meals (>180 for > 60 min after window expiry)
  - velocity-override variant: keep the delta>10 & bg>target+20 escape (approx
    smoothed delta from CGM) and report how much benefit it gives back
"""
import numpy as np
import pandas as pd
import psycopg2

RNG = np.random.default_rng(20260723)

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
df = pd.read_sql(
    """
    SELECT DISTINCT ON (user_id, floor(ts_epoch/300.0))
      user_id, ts_epoch, ts_utc, cgm_mgdl, sug_cob, sug_current_target AS target,
      boostv5_state AS state, boostv5_finaldose AS fd, v1_units, boost_tier AS tier,
      fast_carb_protection AS fcp, iob_iob AS iob
    FROM boost_decisions
    WHERE cgm_mgdl IS NOT NULL
    ORDER BY user_id, floor(ts_epoch/300.0), ts_epoch DESC
    """,
    conn,
).sort_values(["user_id", "ts_epoch"]).reset_index(drop=True)

# normalise target to mg/dL per user (mmol users store display units)
for uid, g in df.groupby("user_id"):
    med = g.target.abs().median()
    if med is not np.nan and med < 30:
        df.loc[g.index, "target"] = g.target * 18.0

# rolling 45-min min BG, forward 3h low/high, approx smoothed delta
min45 = np.full(len(df), np.nan)
low3h = np.zeros(len(df), bool)
delta = np.full(len(df), np.nan)
for uid, g in df.groupby("user_id", sort=False):
    ts = g.ts_epoch.values
    bg = g.cgm_mgdl.values
    idx = g.index.values
    n = len(g)
    j = 0
    for i in range(n):
        while ts[i] - ts[j] > 2700:
            j += 1
        min45[idx[i]] = np.nanmin(bg[j : i + 1])
        # smoothed 5-min delta over the last ~15 min (shortAvgDelta analogue)
        k = i
        while k > 0 and ts[i] - ts[k - 1] <= 900:
            k -= 1
        if k < i and ts[i] > ts[k]:
            delta[idx[i]] = (bg[i] - bg[k]) / ((ts[i] - ts[k]) / 300.0)
    for i in range(n):
        k = i + 1
        while k < n and ts[k] - ts[i] <= 10800:
            k += 1
        low3h[idx[i]] = (bg[i + 1 : k] < 70).any()
df["min45"] = min45
df["low3h"] = low3h
df["delta"] = delta
df["in_window"] = df.min45 < 75

# delivered dose under the CURRENT pipeline
meal = df.state.isin(["CONFIRMED", "COMMITTED"])
v1 = df.v1_units.fillna(0).clip(lower=0)
fd = df.fd.fillna(0).clip(lower=0)
df["delivered"] = np.where(meal & df.fd.notna(), np.minimum(fd, v1), v1)

# graduated scale
bg = df.cgm_mgdl
df["s"] = np.where(bg < 120, 0.3, np.clip(0.3 + 0.7 * (bg - 120) / 50.0, 0.3, 1.0))
df.loc[bg >= 170, "s"] = 1.0

already_scaled = df.fcp.fillna("").str.lower().isin(["true", "t", "1"]) & df.tier.isin(
    ["UAM_BOOST", "PERCENT_SCALE", "ACCELERATION"]
)
df["affected"] = (
    df.in_window
    & (df.sug_cob.fillna(0) == 0)
    & (bg < 170)
    & (df.delivered > 0)
    & ~already_scaled
)
df["removed"] = np.where(df.affected, df.delivered * (1 - df.s), 0.0)
# velocity-override escape (current code): delta > 10 and bg > target + 20
df["vo_escape"] = (df.delta > 10) & (bg > df.target.fillna(90) + 20)

print("===== 1. EXPOSURE =====")
aff = df[df.affected]
dose_cycles = df[df.delivered > 0]
print(
    f"affected dosing cycles: {len(aff)} of {len(dose_cycles)} dosing cycles "
    f"({100 * len(aff) / len(dose_cycles):.1f}%)"
)
print("per user:", aff.groupby("user_id").size().to_dict())
print("tier split:", aff.tier.fillna("?").value_counts().head(8).to_dict())
print(
    f"insulin removed: {aff.removed.sum():.1f}U of {aff.delivered.sum():.1f}U delivered "
    f"in affected cycles ({100 * aff.removed.sum() / aff.delivered.sum():.0f}%)"
)
print("per-user removed U:", aff.groupby("user_id").removed.sum().round(1).to_dict())
print(
    f"cycles the velocity override would exempt: {aff.vo_escape.sum()} "
    f"({100 * aff.vo_escape.mean():.0f}%), holding {aff[aff.vo_escape].removed.sum():.1f}U "
    f"of the removed insulin"
)

# ===== episodes =====
eps = []
for uid, g in aff.groupby("user_id"):
    g = g.sort_values("ts_epoch")
    brk = (g.ts_epoch.diff() > 1800).cumsum()
    gu = df[df.user_id == uid]
    for _, ep in g.groupby(brk):
        end = ep.ts_epoch.iloc[-1]
        fw3 = gu[(gu.ts_epoch > end) & (gu.ts_epoch <= end + 10800)]
        after = gu[gu.ts_epoch >= ep.ts_epoch.iloc[0]]
        expi = after[~after.in_window]
        exp_ts = expi.ts_epoch.iloc[0] if len(expi) else end + 2700
        fwx = gu[(gu.ts_epoch > exp_ts) & (gu.ts_epoch <= exp_ts + 10800)]
        m180 = 5 * int((fwx.cgm_mgdl > 180).sum())
        eps.append(
            dict(
                user=uid,
                start=ep.ts_utc.iloc[0],
                n=len(ep),
                delivered=ep.delivered.sum(),
                removed=ep.removed.sum(),
                removed_no_vo=ep[~ep.vo_escape].removed.sum(),
                bg0=ep.cgm_mgdl.iloc[0],
                second_low=bool((fw3.cgm_mgdl < 70).any()) if len(fw3) else None,
                nadir3h=fw3.cgm_mgdl.min() if len(fw3) else np.nan,
                min180_after_expiry=m180,
                peak3h=fw3.cgm_mgdl.max() if len(fw3) else np.nan,
            )
        )
E = pd.DataFrame(eps)
v = E[E.second_low.notna()]

print(f"\n===== 2. BENEFIT (episodes: {len(E)}) =====")
sl = v[v.second_low]
frac_u = sl.removed.sum() / max(v.removed.sum(), 1e-9)
print(
    f"episodes followed by second low <70 within 3h: {len(sl)} ({100 * v.second_low.mean():.0f}%)"
)
print(
    f"removed insulin sitting ahead of a second low: {sl.removed.sum():.1f}U of "
    f"{v.removed.sum():.1f}U ({100 * frac_u:.0f}%)  [07-04 cap benchmark 27%; other levers 14-19%]"
)
# bootstrap CI over episodes for the headline fraction
boots = []
varr = v.reset_index(drop=True)
for _ in range(2000):
    idx = RNG.integers(0, len(varr), len(varr))
    b = varr.iloc[idx]
    boots.append(b[b.second_low].removed.sum() / max(b.removed.sum(), 1e-9))
lo, hi = np.percentile(boots, [2.5, 97.5])
print(f"bootstrap 95% CI on that fraction: [{100 * lo:.0f}%, {100 * hi:.0f}%]")
print("per-user second-low episodes:", sl.groupby("user").size().to_dict())
print(f"second-low nadir: med {sl.nadir3h.median():.0f} mg/dL")

print("\n===== 3. COST (genuine post-hypo meals) =====")
gm = v[v.min180_after_expiry > 60]
print(
    f"episodes that were genuine meals (>180 for >60min after expiry): {len(gm)} "
    f"({100 * len(gm) / len(v):.0f}%)"
)
print(
    f"under-delivery on them: total {gm.removed.sum():.1f}U, med {gm.removed.median():.2f}U, "
    f"max {gm.removed.max():.2f}U"
)
print(
    f"their outcome WITH full dosing today: peak3h med {gm.peak3h.median():.0f}, "
    f"second-low rate {100 * gm.second_low.mean():.0f}%"
)

print("\n===== 3b. SENSITIVITY: EXCLUDE G (Trio-shadow, doses hypothetical) =====")
vx = v[v.user != "G"]
slx = vx[vx.second_low]
fx = slx.removed.sum() / max(vx.removed.sum(), 1e-9)
bootsx = []
vxr = vx.reset_index(drop=True)
for _ in range(2000):
    idx = RNG.integers(0, len(vxr), len(vxr))
    b = vxr.iloc[idx]
    bootsx.append(b[b.second_low].removed.sum() / max(b.removed.sum(), 1e-9))
lox, hix = np.percentile(bootsx, [2.5, 97.5])
print(
    f"excl-G second-low share of removed insulin: {100 * fx:.0f}% "
    f"[{100 * lox:.0f}%, {100 * hix:.0f}%] over {len(vx)} episodes"
)

print("\n===== 4. VELOCITY-OVERRIDE VARIANT =====")
frac_vo = sl.removed_no_vo.sum() / max(v.removed_no_vo.sum(), 1e-9)
print(
    f"if the delta>10 escape is KEPT in-window: removed drops to {v.removed_no_vo.sum():.1f}U, "
    f"second-low share {100 * frac_vo:.0f}%"
)
gm_vo = gm.removed_no_vo
print(
    f"genuine-meal under-delivery with escape kept: total {gm_vo.sum():.1f}U, med {gm_vo.median():.2f}U"
)

print("\n===== 5. USER-H INCIDENT REPLAY (2026-07-23) =====")
df["ts_utc"] = pd.to_datetime(df.ts_utc, utc=True)
h = df[
    (df.user_id == "H")
    & (df.ts_utc >= pd.Timestamp("2026-07-23 08:30", tz="UTC"))
    & (df.ts_utc <= pd.Timestamp("2026-07-23 12:00", tz="UTC"))
]
h = h[h.delivered > 0]
if len(h):
    for _, r in h.iterrows():
        print(
            f"{r.ts_utc}  bg={r.cgm_mgdl:.0f} min45={r.min45:.0f} tier={r.tier} state={r.state} "
            f"delivered={r.delivered:.2f}U -> scaled={(r.delivered * (r.s if r.affected else 1)):.2f}U"
            f"{' [VO escape]' if r.vo_escape else ''}{' [unaffected]' if not r.affected else ''}"
        )
    print(
        f"episode total: delivered {h.delivered.sum():.2f}U -> "
        f"{(h.delivered * np.where(h.affected, h.s, 1)).sum():.2f}U under composed guard "
        f"(with VO escape: {(h.delivered * np.where(h.affected & ~h.vo_escape, h.s, 1)).sum():.2f}U)"
    )
else:
    print("no user-H rows in incident window — refresh DB first")
