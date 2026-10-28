#!/usr/bin/env python3
"""
DESCENT 2 (pivotal) — does the KAIROS Twin lo30 separate STUCK plateaus (safe to dose) from
SLOW-DECLINE plateaus (a low is coming) where V6's own minGuard can't?

Replay the calibrated Twin EnKF offline over each user's V6 era (insulin reconstructed from the DB:
finaldose SMB + basal from sug_rate), capture lo30 at every cycle. On the plateau cells (dr1: BG>140,
flat/falling, +90..210min post-meal), test which forecast better predicts the GROUND-TRUTH forward low
(nadir<70 in 3h): the Twin lo30, or minGuard. Better = lower false-alarm at matched sensitivity, so a
gate on it would dose the stuck plateaus while withholding on the ones that go low. Per user, parallel.
Usage: python3 dr2_twin_gate.py <user>  (writes dr2_<user>.json)
"""
import sys, json, numpy as np, psycopg2
U = sys.argv[1]
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch,cgm_mgdl,boostv5_finaldose,sug_rate,iob_iob,reason_minguardbg
   from boost_decisions where user_id=%s and variant='boost-other' and cgm_mgdl is not null order by ts_epoch""", (U,))
r = cur.fetchall()
EP = np.array([x[0] for x in r], float); G = np.array([x[1] for x in r], float)
INS = np.array([(x[2] or 0.0) + (x[3] or 0.0) / 12.0 for x in r], float)   # SMB + basal(U/hr → per 5min)
MG = np.array([x[5] if x[5] is not None else np.nan for x in r], float)
if np.nanmedian(MG) < 30: MG *= 18.0
N = len(G)

# ---- calibrated Twin EnKF (faithful to twin_model.py) ----
P = dict(ka1=.03, ka2=.022, p2=.028, SI=.00055, SG=.021, Gb=float(np.nanmedian(G)), taui=12., kra=.02)
M = 120; Qsd = np.array([.02, .02, 1e-4, .55, 2., .6]); Qf = np.array([0, 0, 0, .95, 2.2, 0]); Rsd = 6.
INFLATE0, MEAL_P, MEAL_RA = 28., .03, 5.; rng = np.random.default_rng(1)
def fwd5(x, u):
    for _ in range(5):
        I1, I2, X, Ra, g, Gi = x
        I1 = I1 + (-P['ka1'] * I1) + u / 5; I2 = I2 + (P['ka1'] * I1 - P['ka2'] * I2)
        X = X + (-P['p2'] * X + P['p2'] * P['SI'] * I2); Ra = Ra + (-P['kra'] * Ra)
        g = g + (-P['SG'] * (g - P['Gb']) - X * max(g, 1) + Ra); Gi = Gi + (g - Gi) / P['taui']
        x = np.array([I1, I2, max(X, 0), Ra, max(g, 10), max(Gi, 10)])
    return x
def fwd5v(x, u):
    for _ in range(5):
        I1, I2, X, Ra, g, Gi = x
        I1 = I1 + (-P['ka1'] * I1) + u / 5; I2 = I2 + (P['ka1'] * I1 - P['ka2'] * I2)
        X = X + (-P['p2'] * X + P['p2'] * P['SI'] * I2); Ra = Ra + (-P['kra'] * Ra)
        g = g + (-P['SG'] * (g - P['Gb']) - X * np.maximum(g, 1) + Ra); Gi = Gi + (g - Gi) / P['taui']
        x = np.array([I1, I2, np.maximum(X, 0), Ra, np.maximum(g, 10), np.maximum(Gi, 10)])
    return x
g0 = np.nanmedian(G[:200]); g0 = 120. if np.isnan(g0) else g0
x = np.zeros((6, M)); x[4] = g0 + rng.normal(0, 8, M); x[5] = g0 + rng.normal(0, 8, M); x[3] = rng.normal(0, 2, M)
LO30 = np.full(N, np.nan)
for i in range(N):
    if i + 6 < N:
        xf = x.copy(); xf[4] += rng.standard_normal(M) * INFLATE0; xf[5] += rng.standard_normal(M) * INFLATE0
        for j in range(6):
            xf = fwd5v(xf, INS[i + j]) + Qf[:, None] * rng.standard_normal((6, M))
            meal = rng.random(M) < MEAL_P; xf[3] += meal * np.abs(rng.standard_normal(M)) * MEAL_RA; xf[4] = np.maximum(xf[4], 10)
        gi = xf[5] + rng.normal(0, Rsd, M); LO30[i] = np.percentile(gi, 5)
    x = fwd5v(x, INS[i]) + Qsd[:, None] * rng.standard_normal((6, M))
    x[4] = np.maximum(x[4], 10); x[5] = np.maximum(x[5], 10); x[2] = np.maximum(x[2], 0)
    if not np.isnan(G[i]):
        hx = x[5]; hm = hx.mean(); xm = x.mean(1, keepdims=True)
        Pxy = ((x - xm) * (hx - hm)).mean(1); Pyy = ((hx - hm) ** 2).mean() + Rsd ** 2; K = Pxy / Pyy
        x = x + K[:, None] * (G[i] + rng.normal(0, Rsd, M) - hx)[None, :]
        x[4] = np.maximum(x[4], 10); x[5] = np.maximum(x[5], 10); x[2] = np.maximum(x[2], 0)

def bg(e, tol=400):
    i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < N and abs(EP[j] - e) < tol]
    return G[min(c, key=lambda j: abs(EP[j] - e))] if c else np.nan
# plateau cells (dr1 logic) + attach lo30, minGuard, forward nadir
onsets = []; last = -1e9
for i in range(6, N):
    if EP[i] - EP[i - 1] > 400: continue
    if G[i] > 140 and G[i - 1] <= 140 and np.nanmin(G[max(0, i - 6):i + 1]) <= 130 and (EP[i] - last) > 5400:
        onsets.append(EP[i]); last = EP[i]
cells = []
for e0 in onsets:
    for m in range(90, 211, 5):
        i = np.searchsorted(EP, e0 + m * 60)
        if not (0 <= i < N) or abs(EP[i] - (e0 + m * 60)) > 300 or G[i] <= 140: continue
        d15 = G[i] - bg(EP[i] - 900)
        if np.isnan(d15) or d15 > 8 or np.isnan(LO30[i]): continue
        na = np.nanmin([bg(EP[i] + k * 60) for k in range(10, 181, 5)])
        if np.isnan(na): continue
        cells.append(dict(lo30=float(LO30[i]), mg=float(MG[i]) if not np.isnan(MG[i]) else -1,
                          fwd_nadir=float(na), goes_low=int(na < 70)))
json.dump(dict(user=U, n=len(cells), cells=cells), open(f"dr2_{U}.json", "w"))
print(f"{U}: {len(cells)} plateau cells with Twin lo30")
conn.close()
