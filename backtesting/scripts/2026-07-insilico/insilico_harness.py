#!/usr/bin/env python3
"""In-silico harness — run dosing controllers side-by-side on the UVA/Padova virtual patients
in accelerated time (2026-07-10).

Purpose (from the counterfactual-BG research): we cannot get a trustworthy counterfactual BG on
our REAL users (unannounced meals break individualized replay). What we CAN do is run a controller
against the 30 FDA virtual patients and get a real BG trajectory — a safety / behaviour A/B
(oscillation, stacking, hypo induction) that our shadow telemetry can't surface. This is NOT an
A/B on Tim's data; it's a virtual-patient stress test.

Runs on simglucose (open-source UVA/Padova 2008 reimpl). Requires the dedicated venv:
    ~/.venvs/boost-insilico/bin/python insilico_harness.py

A controller is any object with policy(observation, reward, done, **info) -> Action(basal, bolus)
(the simglucose Controller interface). Add Boost V6/V7 as controllers via CONTROLLERS below.
"""
import argparse
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from simglucose.simulation.env import T1DSimEnv
from simglucose.patient.t1dpatient import T1DPatient
from simglucose.sensor.cgm import CGMSensor
from simglucose.actuator.pump import InsulinPump
from simglucose.simulation.scenario import CustomScenario
from simglucose.controller.base import Action
from simglucose.controller.basal_bolus_ctrller import BBController
from datetime import datetime

# A fixed announced-meal day (hour, grams) — same for every patient/run for reproducibility.
MEAL_DAY = [(7, 45), (12, 70), (18, 80), (22, 15)]


def default_patients(n_adult=10, n_adol=0, n_child=0):
    pats = [f"adult#{i:03d}" for i in range(1, n_adult + 1)]
    pats += [f"adolescent#{i:03d}" for i in range(1, n_adol + 1)]
    pats += [f"child#{i:03d}" for i in range(1, n_child + 1)]
    return pats


def build_scenario(days):
    start = datetime(2026, 1, 1, 0, 0, 0)
    meals = [(d * 24 + h, g) for d in range(days) for h, g in MEAL_DAY]
    return start, CustomScenario(start_time=start, scenario=meals)


def run_one(patient_name, controller, days, seed):
    """Run one patient for `days` days; return the CGM series (mg/dL) at sensor cadence."""
    start, scen = build_scenario(days)
    patient = T1DPatient.withName(patient_name)
    sensor = CGMSensor.withName("Dexcom", seed=seed)
    pump = InsulinPump.withName("Insulet")
    env = T1DSimEnv(patient, sensor, pump, scen)
    env.reset()
    if hasattr(controller, "reset"):
        controller.reset()
    obs, reward, done, info = env.step(Action(basal=0, bolus=0))
    cgm = []
    n_steps = int(days * 24 * 60 / env.sample_time)
    for _ in range(n_steps):
        action = controller.policy(obs, reward, done, **info)
        obs, reward, done, info = env.step(action)
        cgm.append(env.CGM_hist[-1] if env.CGM_hist else obs.CGM)
        if done:
            break
    return np.array([c for c in cgm if c is not None and c > 0], dtype=float)


def metrics(cgm):
    n = len(cgm) or 1
    m = lambda lo, hi: 100 * np.mean((cgm >= lo) & (cgm < hi))
    # hypo events = runs that cross below 70 (count of distinct excursions)
    below = cgm < 70
    events = int(np.sum(below[1:] & ~below[:-1]) + (1 if len(below) and below[0] else 0))
    return dict(
        mean=round(float(np.mean(cgm)), 0), cv=round(100 * np.std(cgm) / np.mean(cgm), 0),
        TIR=round(m(70, 180), 1), TING=round(m(63, 140), 1),
        TBR70=round(100 * np.mean(cgm < 70), 1), TBR54=round(100 * np.mean(cgm < 54), 2),
        TAR180=round(100 * np.mean(cgm > 180), 1), TAR250=round(100 * np.mean(cgm > 250), 1),
        hypo_events=events,
    )


# ── Controller registry — add Boost V6/V7 here (see boost_controller.py) ──
def make_bb():
    return BBController()


CONTROLLERS = {"basal_bolus": make_bb}
try:
    from boost_controller import BoostV6Controller  # noqa
    CONTROLLERS["boost_v6"] = lambda: BoostV6Controller()
except Exception:
    pass


def run_cohort(ctrl_name, patients, days, seed):
    factory = CONTROLLERS[ctrl_name]
    rows = []
    for p in patients:
        cgm = run_one(p, factory(), days, seed)
        r = {"patient": p}
        r.update(metrics(cgm))
        rows.append(r)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="basal_bolus")
    ap.add_argument("--b", default=None, help="second controller for an A/B; omit for single run")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--adults", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    patients = default_patients(n_adult=args.adults)

    print(f"=== in-silico run: {args.a}" + (f" vs {args.b}" if args.b else "") +
          f" | {len(patients)} patients × {args.days}d ===")
    A = run_cohort(args.a, patients, args.days, args.seed)
    print(f"\n--- {args.a} (per-patient) ---")
    print(A.to_string(index=False))
    print(f"\n{args.a} cohort median: " +
          ", ".join(f"{k} {A[k].median()}" for k in ["TIR", "TBR70", "TBR54", "TAR180", "hypo_events"]))

    if args.b:
        B = run_cohort(args.b, patients, days=args.days, seed=args.seed)
        print(f"\n=== A/B cohort medians (paired, same patients+seed) ===")
        print(f"{'metric':>12} {args.a:>14} {args.b:>14} {'Δ(b−a)':>10}")
        for k in ["TIR", "TING", "TBR70", "TBR54", "TAR180", "hypo_events", "cv"]:
            a, b = A[k].median(), B[k].median()
            print(f"{k:>12} {a:>14} {b:>14} {b - a:>+10.1f}")


if __name__ == "__main__":
    main()
