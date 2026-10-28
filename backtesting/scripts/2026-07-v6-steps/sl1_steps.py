#!/usr/bin/env python3
"""Do POST-cell steps predict the lows glucose+insulin couldn't (dr3 AUC 0.55)? For confirm shots AND
plateau cells: forward_steps = sum steps_5m over (t, t+90min]; target = nadir<70 in 3h. Write per user."""
import sys, json, numpy as np, psycopg2
U = sys.argv[1]
conn = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432"); cur = conn.cursor()
cur.execute("""select ts_epoch,cgm_mgdl,steps_5m,boostv5_state,boostv5_finaldose,iob_iob from boost_decisions
   where user_id=%s and variant='boost-other' and cgm_mgdl is not null order by ts_epoch""", (U,))
r = cur.fetchall()
EP = np.array([x[0] for x in r], float); G = np.array([x[1] for x in r], float)
ST = np.array([x[2] if x[2] is not None else 0.0 for x in r], float)
STATE = [x[3] for x in r]; FD = np.array([x[4] or 0.0 for x in r], float); IOB = np.array([x[5] if x[5] is not None else np.nan for x in r], float)
N = len(G)
def bg(e, tol=400):
    i = np.searchsorted(EP, e); c = [j for j in (i - 1, i, i + 1) if 0 <= j < N and abs(EP[j] - e) < tol]
    return G[min(c, key=lambda j: abs(EP[j] - e))] if c else np.nan
def cur_steps(k): return float(ST[(EP<=EP[k])&(EP>EP[k]-60*60)].sum())
def fwd_steps(k):
    m = (EP > EP[k]) & (EP <= EP[k] + 90 * 60); return float(ST[m].sum())
def fwd_nadir(k): return np.nanmin([bg(EP[k] + m * 60) for m in range(10, 181, 5)])
cells = []
# confirm cells
for k in range(N):
    if STATE[k] == 'CONFIRMED' and FD[k] > 0.15:
        na = fwd_nadir(k)
        if not np.isnan(na): cells.append(dict(typ='confirm', fsteps=fwd_steps(k), csteps=cur_steps(k), low=int(na < 70)))
# plateau cells
last = -1e9; onsets = []
for i in range(6, N):
    if EP[i] - EP[i - 1] > 400: continue
    if G[i] > 140 and G[i - 1] <= 140 and np.nanmin(G[max(0, i - 6):i + 1]) <= 130 and (EP[i] - last) > 5400:
        onsets.append(EP[i]); last = EP[i]
for e0 in onsets:
    for mm in range(90, 211, 5):
        k = np.searchsorted(EP, e0 + mm * 60)
        if not (0 <= k < N) or abs(EP[k] - (e0 + mm * 60)) > 300 or G[k] <= 140: continue
        d15 = G[k] - bg(EP[k] - 900)
        if np.isnan(d15) or d15 > 8: continue
        na = fwd_nadir(k)
        if np.isnan(na): continue
        cells.append(dict(typ='plateau', fsteps=fwd_steps(k), csteps=cur_steps(k), low=int(na < 70)))
json.dump(dict(user=U, cells=cells), open(f"sl_{U}.json", "w"))
print(f"{U}: {sum(c['typ']=='confirm' for c in cells)} confirm, {sum(c['typ']=='plateau' for c in cells)} plateau cells")
conn.close()
