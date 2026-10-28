"""Regenerate the G7/One+ point-by-point trace figure used in the report.

Reads the sensor-labelled oref_phase2_sites_v2 table, dedupes to one reading per
5-min bucket (the raw export interleaves upload streams), runs exponential + the UKF
on a clean continuous window, and saves ../g7_pointwise_trace.png.

Run:  python g7_pointwise_plot.py      (needs psycopg2 + matplotlib + local DB)
"""
import os, numpy as np, psycopg2
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from smoothers import smooth_series  # same directory

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "g7_pointwise_trace.png")

def load_g7_dedup(uid):
    conn = psycopg2.connect("dbname=oref"); cur = conn.cursor()
    cur.execute("SELECT DISTINCT ON (floor(ts_utc_ms/300000)) ts_utc_ms, cgm_mgdl FROM oref_phase2_sites_v2 "
                "WHERE user_id=%s AND sensor_type='G7' AND cgm_mgdl IS NOT NULL "
                "ORDER BY floor(ts_utc_ms/300000), ts_utc_ms DESC", (uid,))
    rows = sorted(cur.fetchall(), key=lambda r: r[0]); cur.close(); conn.close()
    return np.array([float(r[0]) for r in rows]), np.array([float(r[1]) for r in rows])

def busiest_g7_user():
    conn = psycopg2.connect("dbname=oref"); cur = conn.cursor()
    cur.execute("SELECT user_id FROM oref_phase2_sites_v2 WHERE sensor_type='G7' "
                "GROUP BY user_id ORDER BY count(*) DESC LIMIT 1")
    u = cur.fetchone()[0]; cur.close(); conn.close(); return u

ts, vals = load_g7_dedup(busiest_g7_user())
gaps = np.diff(ts)/60000.0
W = 60
i = 0
for k in range(len(ts)-W):
    seg = gaps[k:k+W-1]
    if np.all((seg > 3) & (seg < 7)) and (vals[k:k+W].max()-vals[k:k+W].min()) > 60:
        i = k; break
t = ts[i:i+W]; v = vals[i:i+W]
ex = smooth_series("exponential", list(t), list(v))["level_online"]
u = smooth_series("v4", list(t), list(v))
mins = (t - t[0])/60000.0

fig, ax = plt.subplots(figsize=(11, 5))
ax.plot(mins, v, 'o-', color='#bbb', ms=3, lw=0.8, label='raw G7 (deduped 5-min)')
ax.plot(mins, ex, '-', color='#d55e00', lw=1.6, label='exponential (AAPS today)')
ax.plot(mins, u['level_online'], '-', color='#0072b2', lw=1.6, label='UKF (online)')
ax.plot(mins, u['level_offline'], '--', color='#009e73', lw=1.6, label='UKF (RTS)')
ax.set_xlabel('minutes'); ax.set_ylabel('mg/dL')
ax.set_title('G7/One+ real CGM, point-by-point: exponential lags; UKF tracks with ~0 lag')
ax.legend(loc='best', fontsize=9); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(OUT, dpi=130)
print("wrote", os.path.normpath(OUT))
