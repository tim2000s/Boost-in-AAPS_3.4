#!/usr/bin/env python3
"""
Full-cohort analysis of the cold-IDLE fast-path branch (decision input for the 2026-06-26 fix).

For every fresh CONFIRMED transition, split by ORIGIN state (IDLE vs OBSERVING), classify the BG
outcome, and compute the COUNTERFACTUAL cost of removing the IDLE->CONFIRMED branch: under the fix a
cold IDLE enters OBSERVING and can fast-confirm on the NEXT cycle, so a "real" IDLE catch is only
LOST if the rise wasn't still sharp next cycle.

Crucial caveat baked into the report: only `self` (tim) is V5-ACTIVE (dosing real). A-F are
V5-SHADOW (V5 computes, V1 doses), so their post-fire BG is driven by V1, not by the V5 fire -- their
"undershoot" is NOT attributable to the V5 fire, and their "sustained" only shows the fast-path
correctly spotted a real fast carb (hypothetical benefit).
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay

WINDOW = 30
# shipped fast-path gate (MealHypothesis): delta>=8, accl>=15, score>=0.60, awake
FCT_DELTA, FCT_ACCL, FCT_SCORE = 8.0, 15.0, 0.60
ACTIVE = {"self"}  # V5-ACTIVE (real dosing); everyone else is V5-shadow

def outcome(cyc, j):
    bg = cyc[j]["bg"]
    if bg is None: return None
    fwd6 = [cyc[k]["bg"] for k in range(j+1, min(j+7, len(cyc))) if cyc[k]["bg"]]
    if not fwd6: return None
    fwd12 = [cyc[k]["bg"] for k in range(j+1, min(j+13, len(cyc))) if cyc[k]["bg"]]
    near = [cyc[k]["bg"] for k in range(j+1, min(j+5, len(cyc))) if cyc[k]["bg"]]
    peak = max(fwd6); trough = min(fwd12) if fwd12 else bg
    return {"bg": bg,
            "sustained": (peak - bg) >= 15,
            "reversed": bool(near) and min(near) <= bg-5 and (peak-bg) < 15,
            "undershoot": trough <= 80}

def fastpath_fires(c):
    return (c.get("delta") is not None and c.get("accl") is not None and not c["sleep"]
            and c["delta"] >= FCT_DELTA and c["accl"] >= FCT_ACCL
            and (c["score"] is None or c["score"] >= FCT_SCORE))

def counterfactual(cyc, j):
    """Under the fix (IDLE->OBSERVING this cycle): does it fast-confirm next cycle?"""
    if j+1 >= len(cyc): return "edge"
    return "delayed_1cycle" if fastpath_fires(cyc[j+1]) else "not_recovered_next_cycle"

cfg = json.load(open(replay.CONFIG_PATH))
rows = {"IDLE": [], "OBSERVING": [], "other": []}
per_user = {}
for site in cfg["sites"]:
    tag = site["tag"]
    try: cyc = replay.load(site, WINDOW, use_cache=True)["cyc"]
    except Exception as e: print(f"[{tag}] load failed: {e}"); continue
    u = {"IDLE":0,"OBS":0,"idle_sustained":0,"idle_undershoot":0,"idle_recovered":0,"idle_lost":0}
    for j in range(len(cyc)):
        if cyc[j]["state"]=="CONFIRMED" and (j==0 or cyc[j-1]["state"]!="CONFIRMED"):
            origin = cyc[j-1]["state"] if j>0 else "?"
            o = origin if origin in ("IDLE","OBSERVING") else "other"
            oc = outcome(cyc, j)
            if oc is None: continue
            rec = {"tag":tag,"active":tag in ACTIVE, **oc}
            if o=="IDLE":
                rec["cf"] = counterfactual(cyc, j)
                u["IDLE"]+=1
                u["idle_sustained"]+=oc["sustained"]; u["idle_undershoot"]+=oc["undershoot"]
                if rec["cf"]=="delayed_1cycle": u["idle_recovered"]+=1
                elif oc["sustained"]: u["idle_lost"]+=1   # real catch NOT recovered next cycle
            elif o=="OBSERVING": u["OBS"]+=1
            rows[o].append(rec)
    per_user[tag]=u

def pct(a,b): return f"{a*100//b}%" if b else "-"
print(f"=== Cold-IDLE fast-path — full cohort, {WINDOW}d ===\n")
print(f"{'user':5} {'mode':7} {'IDLE→C':7} {'OBS→C':6} {'idle:sustained':14} {'idle:undershoot':15} {'idle recovered@+1':17} {'idle lost':9}")
for tag,u in per_user.items():
    mode = "ACTIVE" if tag in ACTIVE else "shadow"
    print(f"{tag:5} {mode:7} {u['IDLE']:<7} {u['OBS']:<6} {u['idle_sustained']:<14} {u['idle_undershoot']:<15} {u['idle_recovered']:<17} {u['idle_lost']:<9}")

I = rows["IDLE"]; n=len(I)
print(f"\n=== POOLED IDLE-origin (n={n}) ===")
print(f"  sustained real-rise : {sum(x['sustained'] for x in I)} ({pct(sum(x['sustained'] for x in I),n)})")
print(f"  reversed transient  : {sum(x['reversed'] for x in I)} ({pct(sum(x['reversed'] for x in I),n)})")
print(f"  led to undershoot   : {sum(x['undershoot'] for x in I)} ({pct(sum(x['undershoot'] for x in I),n)})")
print(f"  recovered @ +1 cycle: {sum(x['cf']=='delayed_1cycle' for x in I)} ({pct(sum(x['cf']=='delayed_1cycle' for x in I),n)})  <- caught anyway, 5min later")
print(f"  NOT recovered @ +1  : {sum(x['cf']!='delayed_1cycle' for x in I)}  (of which sustained/real = {sum(x['cf']!='delayed_1cycle' and x['sustained'] for x in I)} = genuinely lost early-catch)")
print(f"\n  V5-ACTIVE (tim) IDLE fires: {sum(x['active'] for x in I)} | their undershoots: {sum(x['active'] and x['undershoot'] for x in I)}  <- the only REAL dosing harm")
print(f"  V5-shadow IDLE fires: {sum(not x['active'] for x in I)} | sustained: {sum(not x['active'] and x['sustained'] for x in I)}  <- hypothetical benefit (V1 dosed, not V5)")
O=rows["OBSERVING"]; m=len(O)
print(f"\n=== OBSERVING-origin baseline (n={m}) ===  sustained {pct(sum(x['sustained'] for x in O),m)} | undershoot {pct(sum(x['undershoot'] for x in O),m)}  (untouched by the fix)")
