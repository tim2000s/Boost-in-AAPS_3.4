#!/usr/bin/env python3
"""
Boost V6 — cohort performance + dosing-mechanism analysis for the V6 article (2026-07-19).

Honest by construction (see CLAUDE.md + RELATIONSHIPS_REGISTER):
  - OUTCOMES (TIR/TING/TBR) are DESCRIPTIVE of the V6-active era. They are NOT a causal V6 effect:
    no glucose simulator ⇒ no counterfactual vs the previous generation; the cohort is small +
    self-selected; the within-user RCT has not been run. Reported per-user, then summarised as the
    MEDIAN across users (within-subject > between).
  - MECHANISM (V6 finalDose vs `v1_units`, the would-dose computed the SAME cycle) IS clean: a within-
    cycle shadow comparison, no counterfactual needed. NOTE: `v1_units` is the PREVIOUS BOOST
    generation (`DetermineBasalBoost`, the V1-gen Boost algorithm with its own UAM-Boost tiers), NOT
    stock oref (CLAUDE.md: "V1 is Boost"). So it shows what V6 adds ON TOP OF an already-aggressive
    predecessor — where it restrains, where it front-loads — not a gain over passive oref.

Aggregates only; no raw traces leave the DB. Anonymised user tags (self→'tim', others A–H).
"""
import numpy as np, psycopg2

conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
cur = conn.cursor()
USERS = ['tim', 'F', 'H', 'B', 'E', 'A', 'C']


def q(sql, args=()):
    cur.execute(sql, args); return cur.fetchall()


def pct(a, lo, hi):
    a = a[~np.isnan(a)]; return 100.0 * np.mean((a >= lo) & (a <= hi)) if len(a) else np.nan


def below(a, thr):
    a = a[~np.isnan(a)]; return 100.0 * np.mean(a < thr) if len(a) else np.nan


def above(a, thr):
    a = a[~np.isnan(a)]; return 100.0 * np.mean(a > thr) if len(a) else np.nan


print("=" * 92)
print("BOOST V6 — COHORT GLYCAEMIC OUTCOMES over the V6-active era (DESCRIPTIVE, not a causal effect)")
print("=" * 92)
hdr = f"{'user':<5}{'days':>5}{'nCGM':>7}{'mean':>6}{'CV%':>6}{'TIR%':>6}{'TING%':>7}{'TAR%':>6}{'<70%':>6}{'<54%':>6}"
print(hdr)
rows = {}
span = q("""select user_id, min(ts_utc)::date, max(ts_utc)::date from boost_decisions
            where boostv5_active group by user_id""")
spand = {u: (a, b) for u, a, b in span}
for u in USERS:
    r = q("""select cgm_mgdl from boost_decisions where user_id=%s and boostv5_active
             and cgm_mgdl is not null order by ts_epoch""", (u,))
    g = np.array([x[0] for x in r], float)
    days = (spand[u][1] - spand[u][0]).days + 1 if u in spand else 0
    mean = np.nanmean(g); cv = 100.0 * np.nanstd(g) / mean
    rows[u] = dict(days=days, n=len(g), mean=mean, cv=cv,
                   tir=pct(g, 70, 180), ting=pct(g, 63, 140), tar=above(g, 180),
                   b70=below(g, 70), b54=below(g, 54))
    d = rows[u]
    print(f"{u:<5}{days:>5}{d['n']:>7}{d['mean']:>6.0f}{d['cv']:>6.1f}{d['tir']:>6.0f}{d['ting']:>7.0f}"
          f"{d['tar']:>6.0f}{d['b70']:>6.1f}{d['b54']:>6.1f}")


def med(k): return np.median([rows[u][k] for u in USERS])
def iqr(k):
    v = sorted(rows[u][k] for u in USERS); return np.percentile(v, 25), np.percentile(v, 75)
print("-" * 92)
for k, lab in [('tir', 'TIR 70-180'), ('ting', 'TING 63-140'), ('tar', 'TAR>180'), ('b70', 'TBR<70'), ('b54', 'TBR<54'), ('cv', 'CV')]:
    lo, hi = iqr(k)
    print(f"  median {lab:<12}: {med(k):5.1f}%   (IQR {lo:.1f}–{hi:.1f})")

print("\n" + "=" * 92)
print("V6 vs V1 DOSING MECHANISM — same-cycle shadow (boostv5_finaldose vs v1_units). CLEAN, no counterfactual.")
print("=" * 92)
print(f"{'user':<5}{'V6 U/d':>8}{'V1 U/d':>8}{'net%':>7}{'amp%':>7}{'restr%':>8}{'same%':>7}  (amp=V6>V1, restr=V6<V1)")
agg = {}
for u in USERS:
    r = q("""select boostv5_finaldose, v1_units, boostv5_state, extract(hour from ts_utc at time zone 'Europe/London'),
                    cgm_mgdl, iob_iob
             from boost_decisions where user_id=%s and boostv5_active
             and boostv5_finaldose is not null and v1_units is not null""", (u,))
    v6 = np.array([x[0] for x in r], float); v1 = np.array([x[1] for x in r], float)
    days = rows[u]['days']
    amp = 100.0 * np.mean(v6 > v1 + 1e-6); restr = 100.0 * np.mean(v6 < v1 - 1e-6); same = 100.0 * np.mean(np.abs(v6 - v1) <= 1e-6)
    net = 100.0 * (v6.sum() - v1.sum()) / max(v1.sum(), 1e-9)
    agg[u] = dict(v6d=v6.sum() / days, v1d=v1.sum() / days, net=net, amp=amp, restr=restr, same=same,
                  rows=r)
    a = agg[u]
    print(f"{u:<5}{a['v6d']:>8.1f}{a['v1d']:>8.1f}{net:>+7.0f}{amp:>7.1f}{restr:>8.1f}{same:>7.1f}")
print("-" * 92)
print(f"  median net vs V1: {np.median([agg[u]['net'] for u in USERS]):+.0f}%   "
      f"amplify {np.median([agg[u]['amp'] for u in USERS]):.1f}%   restrain {np.median([agg[u]['restr'] for u in USERS]):.1f}%   "
      f"same {np.median([agg[u]['same'] for u in USERS]):.1f}%")

print("\n" + "=" * 92)
print("WHERE V6 DIFFERS FROM V1 — pooled net insulin delta (V6−V1, U/1000 cycles) by context")
print("=" * 92)
# by state
print("\n  by V6 state:")
for st in ('IDLE', 'OBSERVING', 'CONFIRMED'):
    d6 = d1 = n = 0.0
    for u in USERS:
        for fd, v1u, state, hr, bg, iob in agg[u]['rows']:
            if state == st:
                d6 += fd; d1 += v1u; n += 1
    if n: print(f"    {st:<10} n={int(n):>6}  V6−V1 = {1000*(d6-d1)/n:+7.1f} U/1000cyc  ({'front-loads' if d6>d1 else 'restrains'})")
# by time of day
print("\n  by time of day:")
for lab, h0, h1 in [('overnight 00-06', 0, 6), ('morning 06-12', 6, 12), ('afternoon 12-18', 12, 18), ('evening 18-24', 18, 24)]:
    d6 = d1 = n = 0.0
    for u in USERS:
        for fd, v1u, state, hr, bg, iob in agg[u]['rows']:
            if hr is not None and h0 <= hr < h1:
                d6 += fd; d1 += v1u; n += 1
    if n: print(f"    {lab:<16} n={int(n):>6}  V6−V1 = {1000*(d6-d1)/n:+7.1f} U/1000cyc")
# by BG band
print("\n  by glucose band:")
for lab, lo, hi in [('low <90', 0, 90), ('in-band 90-140', 90, 140), ('mild-high 140-180', 140, 180), ('high >180', 180, 999)]:
    d6 = d1 = n = 0.0
    for u in USERS:
        for fd, v1u, state, hr, bg, iob in agg[u]['rows']:
            if bg is not None and lo <= bg < hi:
                d6 += fd; d1 += v1u; n += 1
    if n: print(f"    {lab:<18} n={int(n):>6}  V6−V1 = {1000*(d6-d1)/n:+7.1f} U/1000cyc")

print("\n" + "=" * 92)
print("TIME-OF-DAY OUTCOMES (descriptive) — median across users")
print("=" * 92)
for lab, h0, h1 in [('overnight 00-06', 0, 6), ('daytime 06-24', 6, 24)]:
    tirs = []; tings = []
    for u in USERS:
        r = q("""select cgm_mgdl from boost_decisions where user_id=%s and boostv5_active
                 and cgm_mgdl is not null and extract(hour from ts_utc at time zone 'Europe/London') >= %s
                 and extract(hour from ts_utc at time zone 'Europe/London') < %s""", (u, h0, h1))
        g = np.array([x[0] for x in r], float)
        if len(g) > 100: tirs.append(pct(g, 70, 180)); tings.append(pct(g, 63, 140))
    print(f"  {lab:<16}: median TIR {np.median(tirs):.0f}%   median TING {np.median(tings):.0f}%   (n={len(tirs)} users)")

maxts = q("select max(ts_utc) from boost_decisions where boostv5_active")[0][0]
print(f"\n[data through {maxts}]  cohort n={len(USERS)} users, V6-active era.")
conn.close()
