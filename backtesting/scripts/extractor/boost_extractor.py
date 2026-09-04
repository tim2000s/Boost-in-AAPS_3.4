#!/usr/bin/env python3
"""
Boost data extractor — pulls all devicestatus + cgm entries from a Nightscout
site and stores them as a per-decision table in TimescaleDB.

Designed for the Boost analysis (v1 / V2 / V3 variants), so it captures every
field the existing oref extractor did, plus the Boost-specific top-level
suggested fields (boostActive, deltaAcceleration, tdd, tddRatio, sensNormalTarget,
variable_sens, dynamicISF, predictionISF, runningDynamicIsf, isfMgdlForCarbs,
boostProfileSwitch), plus parsed-from-consoleError fields (boostTier, the
algorithm-variant tag, the V3 HR/Karvonen line, fastCarbProtection state).

Output table: boost_decisions (created if missing). One row per devicestatus
suggested record. CGM joined via backward-merge with 10-minute tolerance.
"""
import argparse
import json
import re
import sys
import time
import warnings
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import requests

warnings.filterwarnings("ignore")

DB_NAME = "oref"  # reuse existing local TimescaleDB
TABLE = "boost_decisions"

# Mapping from variant header signature -> normalised tag
VARIANT_PATTERNS = [
    (re.compile(r"Boost V3"), "v3"),
    (re.compile(r"Boost V2"), "v2"),
    (re.compile(r"v4\.1\.5"), "v1"),
    (re.compile(r"Boost"), "boost-other"),
]

# Trio (iOS Boost port, shipped 2026-06-24, branch Boost-in-Trio-v0.1): its Boost
# shadow telemetry is NOT structured suggested fields — it's a compact tag appended
# to the oref determination reason by BoostV5Adapter.reasonTag, e.g.
#   boostV5[shadow]: state=IDLE score=0.35 wouldSMB=0.00U; ml(hypo=0.12 meal=n/a) postEx asleep
# mode ∈ {off, shadow, active} (BoostMode rawValues); state ∈ MealHypothesis rawValues
# (IDLE/OBSERVING/CONFIRMED/COMMITTED/RECOVERING); ml values are "%.2f" or "n/a".
# Active mode appends MORE text after the tag (e.g. " V6 suppressed (...);"), so the
# regex must not be end-anchored. Trio devicestatus has no consoleError, so these
# records would otherwise be misfiled "v1-silent".
TRIO_TAG_RE = re.compile(
    r"boostV5\[(?P<mode>off|shadow|active)\]:\s*state=(?P<state>[A-Z]+)\s+"
    r"score=(?P<score>-?[\d.]+)\s+wouldSMB=(?P<smb>-?[\d.]+)U;\s*"
    r"ml\(hypo=(?P<hypo>-?[\d.]+|n/a)\s+meal=(?P<meal>-?[\d.]+|n/a)\)"
)


TWIN_RE = re.compile(r"twin=([-\d.,]+)")
HYPOSHADOW_RE = re.compile(r"hyposhadow=([-\d.]+)")
FALLCON_RE = re.compile(r"fallcon=([-\d.,]+)")
FALLCONSKIP_RE = re.compile(r"fallconskip=([a-z0-9]+),(\d+)")
PLATEAU_RE = re.compile(r"plateau=([^;]+);")
# 2026-08-03 auto-config breadcrumbs, both replayed EVERY cycle so the DB always carries the
# CURRENT state rather than the single cycle on which the derivation ran.
#   autocfg=  onboarding derivation outcome
#   autordv=  last periodic re-derivation: @ISO,win=28d,ev=N,ch=M[,<knob>:<value>][,held-…][,retired-…]
AUTOCFG_RE = re.compile(r"autocfg=([^;]+);")
AUTORDV_RE = re.compile(r"autordv=([^;]+);")
# 2026-08-03 post-rescue tight-ramp TRIAL: "prTrial=<enrolled 0|1>,<control|tight>,<cap>;"
# emitted every cycle (not only when the guard fired), so exposure is countable on days the
# guard never engaged. Pre-reg: backtesting/protocols/2026-08_postrescue_tight_ramp_PREREG.md
PRTRIAL_RE = re.compile(r"prTrial=([^;]+);")
ANTBACKOUT_RE = re.compile(r"antBackout=([^;]+);")
ANTICIP_RE = re.compile(r"anticip=([^;]+);")


def _anticip(reason: str, i: int, cast=float):
    """Per-user ANTICIPATION SHADOW tag (2026-07-27), READ-ONLY: doses nothing.
    "anticip=pEx,pMeal,srcEx,srcMeal,exArm,exConf,exBO,mealArm,mealConf,mealBO,minsEx,minsMeal,nEx,nMeal;"
    pEx/pMeal = p(onset within 45min) or '-' (unfitted); srcEx/srcMeal = peruser|blend|prior; the
    arm/confirm/backout edge flags per lever (0/1); minutes since last onset; banked onset counts.
    Field 0/1 may be '-' → None. Mixed text+numeric → split on ','."""
    m = ANTICIP_RE.search(reason or "")
    if not m:
        return None
    parts = m.group(1).split(",")
    if i >= len(parts):
        return None
    try:
        return cast(parts[i])
    except (ValueError, TypeError):
        return None


def _antb(reason: str, i: int, cast=float):
    """Anticipatory back-out controller SHADOW tag (2026-07-20), READ-ONLY: doses nothing.
    "antBackout=state,ra0,raNow,bg0,bgNow,confirmed,backedout,trip,mealLikely,armSrc;" — state(IDLE|ARMED),
    the Ra/BG at ARM vs now, the confirm/back-out/low-trip flags, and armSrc(accel|ml|-) = which trigger
    armed this run (2026-07-20 ACCELMEAL_ARM: accelMeal onset detector OR the mlMealLikely placeholder;
    field 9, absent in pre-accelArm data → None). Mixed text+numeric → split on ','."""
    m = ANTBACKOUT_RE.search(reason or "")
    if not m:
        return None
    parts = m.group(1).split(",")
    if i >= len(parts):
        return None
    try:
        return cast(parts[i])
    except (ValueError, TypeError):
        return None


def _plat(reason: str, i: int, cast=float):
    """Post-meal plateau-nudge SHADOW tag (2026-07-19), READ-ONLY: doses nothing.
    "plateau=trig,wouldNudgeU,bg,trend,iob,state,floor;" — trig(0/1), the would-nudge U, and the
    trigger context; floor = why it did/didn't fire ('ok'|'n/a'|recent-low|post-rescue|cum-cap|
    minguard|not-active|no-headroom). Mixed numeric+text, so match to ';' then split."""
    m = PLATEAU_RE.search(reason or "")
    if not m:
        return None
    parts = m.group(1).split(",")
    if i >= len(parts):
        return None
    try:
        return cast(parts[i])
    except (ValueError, TypeError):
        return None


def _prtrial(reason: str, i: int, cast=float):
    """Post-rescue tight-ramp trial tag: enrolled(0/1), arm(control|tight), cap(U)."""
    m = PRTRIAL_RE.search(reason or "")
    if not m:
        return None
    parts = m.group(1).split(",")
    if i >= len(parts):
        return None
    try:
        return cast(parts[i])
    except (ValueError, TypeError):
        return None


def _autordv(reason: str, field: str):
    """Pull one field out of the periodic re-derivation breadcrumb.

    field: 'raw' | 'at' | 'window_d' | 'evaluated' | 'changed' | 'changes'
    'changes' returns the comma-joined knob:value list, i.e. what actually moved.
    """
    m = AUTORDV_RE.search(reason or "")
    if not m:
        return None
    raw = m.group(1)
    if field == "raw":
        return raw
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    try:
        if field == "at":
            return parts[0].lstrip("@") if parts and parts[0].startswith("@") else None
        if field == "window_d":
            v = next((p for p in parts if p.startswith("win=")), None)
            return int(v[4:].rstrip("d")) if v else None
        if field == "evaluated":
            v = next((p for p in parts if p.startswith("ev=")), None)
            return int(v[3:]) if v else None
        if field == "changed":
            v = next((p for p in parts if p.startswith("ch=")), None)
            return int(v[3:]) if v else None
        if field == "changes":
            # the leading @ISO timestamp also contains colons — exclude it and the
            # held-/retired- markers, leaving only knob:value pairs that actually moved
            ch = [p for p in parts
                  if ":" in p and not p.startswith(("@", "held-", "retired-", "win=", "ev=", "ch="))]
            return ",".join(ch) or None
    except (ValueError, IndexError):
        return None
    return None


def _fallcon(reason: str, i: int, cast=float):
    """Fall-consequence shadow, "fallcon=score,ageMin,onsetBg,fall,stillFalling;".

    Absent on most cycles by design: the anchor is a fall onset, which happens a few times a day,
    not every five minutes. A null means no qualifying onset, never a score of zero.
    """
    m = FALLCON_RE.search(reason or "")
    if not m:
        return None
    parts = m.group(1).split(",")
    if i >= len(parts):
        return None
    try:
        return cast(parts[i])
    except ValueError:
        return None


def _hyposhadow(reason: str) -> Optional[float]:
    """Shadow hypo-risk score, emitted as "hyposhadow=<0..1>;" once per cycle.

    Absent where the shadow asset failed to load or the feature vector was short, both of
    which return null rather than a score, so a null here is "no shadow" and never zero.
    """
    m = HYPOSHADOW_RE.search(reason or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _twin(reason: str, i: int) -> Optional[float]:
    """Split the KAIROS Twin reason tag into its i-th float. Tag (2026-07-18, 9 fields):
    "twin=fc30,fc60,lo60,hi60,ra,gi,insU,lo30,floorbreach;" — lo30/floorbreach appended at the
    END so existing index positions are unchanged (idea-4 descent-side shadow). It rides in
    `reason` (not its own RT field) to avoid the legacy V3MLG3 ART verifier crash; index-safe for
    old rows that carry only the first 7 fields (returns None past the split length)."""
    m = TWIN_RE.search(reason or "")
    if not m:
        return None
    parts = m.group(1).split(",")
    if i >= len(parts):
        return None
    try:
        return float(parts[i])
    except (ValueError, TypeError):
        return None


def parse_trio_tag(reason: str) -> Optional[dict]:
    """Parse the Trio boostV5 reason tag into the existing boostv5_*/ml_* fields."""
    m = TRIO_TAG_RE.search(reason or "")
    if not m:
        return None

    def num(s):
        try:
            return float(s)
        except (TypeError, ValueError):
            return None  # "n/a"

    return {
        "mode": m.group("mode"),
        "state": m.group("state"),
        "score": num(m.group("score")),
        "smb": num(m.group("smb")),
        "hypo": num(m.group("hypo")),
        "meal": num(m.group("meal")),
    }


AIMI_MARKERS = (
    "MPC predictive model", "PI physiological model", "Autodrive",
    "PKPD: DIA=", "UAM model:", "Final SMB",
)


def looks_like_aimi(sug: dict, reason: str) -> bool:
    """True when this decision came from the AIMI fork rather than Boost/oref.

    AIMI sets suggested.algorithm == "AIMI" on most records, but not all (it flips
    to null on a subset), so fall back to its distinctive reason-string markers and
    its trajectory* field family. Detection must be POSITIVE-only: a Boost record
    must never match, or the whole cohort gets re-tagged.
    """
    if (sug.get("algorithm") or "").upper() == "AIMI":
        return True
    if any(k.startswith("trajectory") for k in sug):
        return True
    r = reason or ""
    return sum(1 for m in AIMI_MARKERS if m in r) >= 2


def detect_variant(console_error: str, reason: str = "") -> str:
    """Identify which Boost variant produced this decision.

    Important: the absence of a "Boost vX" header line in consoleError does
    NOT mean the user wasn't running Boost. Older Boost builds emit oref-style
    consoleError without any Boost branding line, but the algorithm running
    is still Boost. We tag those records "v1-silent" rather than "no-boost"
    so the analysis pipeline knows the records belong to the Boost v1
    population, just with limited field emission.

    Trio records are detected from the reason string (they carry no
    consoleError); the tag literal "boostV5[" never occurs in AAPS reason
    strings (verified against the full boost_decisions table, 0/332k rows),
    so AAPS classification is unchanged.
    """
    m = TRIO_TAG_RE.search(reason or "")
    if m:
        return f"trio-{m.group('mode')}"
    if not console_error:
        return "v1-silent"
    head = "\n".join(console_error.split("\n")[:8])
    for pat, tag in VARIANT_PATTERNS:
        if pat.search(head):
            return tag
    return "v1-silent"


def parse_boost_tier(console_error: str, top_level: Optional[str]) -> Optional[str]:
    """V3 exposes boostTier at the top level. V1/V2 only log it in consoleError."""
    if top_level:
        return top_level
    if not console_error:
        return None
    m = re.search(r"TIER \d+: ([A-Za-z0-9_ ]+?)\s*<<<", console_error)
    if not m:
        return None
    label = m.group(1).strip().upper().replace(" ", "_")
    return label


def parse_hr_features(console_error: str) -> dict:
    """V3 logs an HR line: 'HR: avg=90.0 bpm | HRR=22.4% | zone=zone1 | steps15m=0 => INACTIVE (HIGH)'"""
    out = {"hr_avg": None, "hrr_pct": None, "hr_zone": None}
    if not console_error:
        return out
    m = re.search(r"HR:\s*avg=([\d.]+)\s*bpm\s*\|\s*HRR=([\d.]+)%\s*\|\s*zone=(\w+)", console_error)
    if m:
        out["hr_avg"] = float(m.group(1))
        out["hrr_pct"] = float(m.group(2))
        out["hr_zone"] = m.group(3)
    return out


def parse_glucose_status(console_error: str) -> dict:
    """The engine's own delta windows, which it prints into the glucose block:
    'BG: 91.8 mg/dl | Delta: 2.2 | Short avg: 1.5 | Long avg: -1.0'

    These are the values the dosing engine actually used. Reconstructing them from the reading
    series is measurably worse, so any replay wants them read rather than derived.
    """
    out = {"gs_delta": None, "gs_short_avg_delta": None, "gs_long_avg_delta": None}
    if not console_error:
        return out
    m = re.search(r"Delta:\s*(-?[\d.]+)\s*\|\s*Short avg:\s*(-?[\d.]+)\s*\|\s*"
                  r"Long avg:\s*(-?[\d.]+)", console_error)
    if m:
        out["gs_delta"] = float(m.group(1))
        out["gs_short_avg_delta"] = float(m.group(2))
        out["gs_long_avg_delta"] = float(m.group(3))
    return out


def parse_steps(console_error: str) -> dict:
    out = {"steps_5m": None, "steps_15m": None, "steps_30m": None, "steps_60m": None}
    if not console_error:
        return out
    m = re.search(r"Steps:\s*5m=(\d+)\s+15m=(\d+)\s+30m=(\d+)\s+60m=(\d+)", console_error)
    if m:
        out["steps_5m"] = int(m.group(1))
        out["steps_15m"] = int(m.group(2))
        out["steps_30m"] = int(m.group(3))
        out["steps_60m"] = int(m.group(4))
    return out


def parse_boost_active(console_error: str) -> Optional[bool]:
    if not console_error:
        return None
    if "✓ BOOST ACTIVE" in console_error:
        return True
    if "BOOST INACTIVE" in console_error or "Boost OFF" in console_error:
        return False
    return None


def parse_shadow_lines(console_error: str) -> dict:
    """The ISF and volume-weighted dose shadows, parsed from the console block they write into.

    Both print a single line per cycle and neither was ever extracted, so seven months of one and
    none of the other sat unparsed. Numbers are formatted with the device's locale, so a European
    participant writes "raw=0,890" where an English one writes "raw=0.890"; matching digits and
    full stops alone stops at the comma and reads zero.
    """
    out = {k: None for k in
           ("isf_shadow_raw", "isf_shadow_ema", "isf_shadow_bounded", "isf_shadow_warmup",
            "vwa_blend", "vwa_projection", "vwa_expected", "vwa_delivered",
            "vwa_day_fraction", "vwa_curve_days", "vwa_used_prev_day")}
    if not console_error:
        return out

    def num(m, cast=float):
        if not m:
            return None
        v = m.group(1).replace(",", ".")
        if v.count(".") > 1:
            return None
        try:
            return cast(float(v))
        except ValueError:
            return None

    n = r"(-?[0-9][0-9.,]*)"
    if "IsfShadow:" in console_error:
        out["isf_shadow_raw"] = num(re.search(rf"IsfShadow:.*?raw={n}", console_error))
        out["isf_shadow_ema"] = num(re.search(rf"IsfShadow:.*?\)={n}", console_error))
        out["isf_shadow_bounded"] = num(re.search(rf"IsfShadow:.*?bounded={n}", console_error))
        out["isf_shadow_warmup"] = num(re.search(rf"IsfShadow:.*?warmup={n}", console_error))
    if "VwaTdd:" in console_error:
        out["vwa_day_fraction"] = num(re.search(rf"VwaTdd: day={n}", console_error))
        out["vwa_delivered"] = num(re.search(rf"VwaTdd:.*?deliv={n}", console_error))
        out["vwa_projection"] = num(re.search(rf"VwaTdd:.*?proj={n}", console_error))
        out["vwa_expected"] = num(re.search(rf"VwaTdd:.*?expected={n}", console_error))
        out["vwa_blend"] = num(re.search(rf"VwaTdd:.*?blend={n}", console_error))
        out["vwa_curve_days"] = num(re.search(rf"VwaTdd:.*?curveDays={n}", console_error), int)
        out["vwa_used_prev_day"] = "(prev)" in console_error
    return out


def parse_isf_blend(console_error: str) -> dict:
    """Pull TDD blend components."""
    out = {"tdd_7d": None, "tdd_1d": None, "tdd_24h": None, "tdd_4h": None,
           "tdd_8to4h": None, "tdd_weighted8h": None, "tdd_blended": None,
           "tdd_adj_factor": None}
    if not console_error:
        return out
    m = re.search(r"TDD data:\s*7D=([\d.]+)\s*\|\s*1D=([\d.]+)\s*\|\s*24H=([\d.]+)\s*\|\s*4H=([\d.]+)\s*\|\s*8-4H=([\d.]+)", console_error)
    if m:
        out["tdd_7d"] = float(m.group(1))
        out["tdd_1d"] = float(m.group(2))
        out["tdd_24h"] = float(m.group(3))
        out["tdd_4h"] = float(m.group(4))
        out["tdd_8to4h"] = float(m.group(5))
    m = re.search(r"Weighted8H=([\d.]+)", console_error)
    if m: out["tdd_weighted8h"] = float(m.group(1))
    m = re.search(r"Blended TDD=([\d.]+)", console_error)
    if m: out["tdd_blended"] = float(m.group(1))
    m = re.search(r"adj factor (\d+)%", console_error)
    if m: out["tdd_adj_factor"] = float(m.group(1)) / 100.0
    return out


def parse_reason(reason: str) -> dict:
    """Parse oref-style reason string for embedded numeric fields (BGI, Dev, ISF, CR, etc)
    and the Boost sleep state + learned sleep window, when present."""
    out = {"reason_Dev": None, "reason_BGI": None, "reason_minPredBG": None,
           "reason_minGuardBG": None, "reason_IOBpredBG": None, "reason_UAMpredBG": None,
           "sleep_state": None, "sleep_learned_onset": None,
           "sleep_learned_wake": None, "sleep_learned_days": None}
    if not reason:
        return out
    for k, key in [("Dev", "reason_Dev"), ("BGI", "reason_BGI"),
                   ("minPredBG", "reason_minPredBG"), ("minGuardBG", "reason_minGuardBG"),
                   ("IOBpredBG", "reason_IOBpredBG"), ("UAMpredBG", "reason_UAMpredBG")]:
        m = re.search(rf"\b{k}\s*[:=]?\s*(-?[\d.]+)", reason)
        if m:
            try:
                out[key] = float(m.group(1))
            except ValueError:
                pass
    # Boost sleep state (collected when present): "sleep=SLEEPING learned=01:35→06:18/42d"
    m = re.search(r"sleep=([A-Za-z_]+)", reason)
    if m:
        out["sleep_state"] = m.group(1)
    lm = re.search(r"learned=(\d{1,2}:\d{2})\D+?(\d{1,2}:\d{2})/(\d+)\s*d", reason)
    if lm:
        out["sleep_learned_onset"] = lm.group(1)
        out["sleep_learned_wake"] = lm.group(2)
        try:
            out["sleep_learned_days"] = int(lm.group(3))
        except ValueError:
            pass
    return out


# ───────────────────────────────────────────────────────────────────────────
# Nightscout fetcher
# ───────────────────────────────────────────────────────────────────────────

def fetch_devicestatus(url: str, token: str, since: str, until: str) -> list:
    """Page backward through devicestatus from `until` to `since`."""
    out = []
    end = until
    while True:
        params = {
            "token": token,
            "count": 5000,
            "find[created_at][$lt]": end,
            "find[created_at][$gte]": since,
        }
        r = requests.get(f"{url}/api/v1/devicestatus.json", params=params, timeout=120)
        r.raise_for_status()
        page = r.json()
        if not page:
            break
        out.extend(page)
        if len(page) < 5000:
            break
        end = min(rec["created_at"] for rec in page)
        print(f"  devicestatus: fetched {len(out):,} so far, oldest now {end[:10]}")
    return out


def fetch_entries(url: str, token: str, since: str, until: str) -> list:
    """Page entries by `date` (epoch ms). The `created_at` filter on this
    Nightscout instance appears to be capped at ~1000 records regardless of
    the requested count, but `date` filtering paginates correctly. Walk
    backward in time, deduping on _id."""
    since_ms = int(pd.to_datetime(since).timestamp() * 1000)
    until_ms = int(pd.to_datetime(until).timestamp() * 1000)
    out = []
    seen = set()
    end_ms = until_ms
    while True:
        params = {
            "token": token,
            "count": 10000,
            "find[date][$lt]": end_ms,
            "find[date][$gte]": since_ms,
            "find[type]": "sgv",
        }
        r = requests.get(f"{url}/api/v1/entries.json", params=params, timeout=120)
        r.raise_for_status()
        page = r.json()
        if not page:
            break
        new_in_page = 0
        for rec in page:
            rid = rec.get("_id")
            if rid and rid in seen:
                continue
            if rid:
                seen.add(rid)
            new_in_page += 1
            out.append(rec)
        if new_in_page == 0:
            break
        new_end = min(rec.get("date", end_ms) for rec in page if rec.get("date"))
        if new_end >= end_ms:  # no progress
            break
        end_ms = new_end
        print(f"  entries: fetched {len(out):,} so far, oldest now {pd.to_datetime(end_ms, unit='ms').strftime('%Y-%m-%d')}")
    return out


# ───────────────────────────────────────────────────────────────────────────
# Row builder
# ───────────────────────────────────────────────────────────────────────────

def to_mgdl(v):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    # Heuristic: anything below 35 is mmol/L; multiply
    if 0 < v < 35:
        return v * 18.0
    return v


def build_row(rec: dict, user_id: str) -> Optional[dict]:
    sug = rec.get("openaps", {}).get("suggested", {})
    if not sug:
        return None
    iob = rec.get("openaps", {}).get("iob", {})
    if isinstance(iob, list):
        iob = iob[0] if iob else {}

    ce = sug.get("consoleError", "") or ""
    if isinstance(ce, list):
        ce = "\n".join(ce)
    reason = sug.get("reason", "") or ""

    is_aimi = looks_like_aimi(sug, reason)
    variant = "aimi" if is_aimi else detect_variant(ce, reason)

    ts_str = rec.get("created_at") or sug.get("timestamp") or sug.get("deliverAt")
    if not ts_str:
        return None
    try:
        ts = pd.to_datetime(ts_str, utc=True)
    except Exception:
        return None

    bg_raw = sug.get("bg")
    bg_mgdl = to_mgdl(bg_raw)
    if bg_mgdl is None and is_aimi:
        # AIMI emits NO suggested.bg — the reason carries "BG=110" (and "BG=110 D2,4"),
        # and predBGs.* arrays start at the current value. Try the reason first (it is the
        # value AIMI actually reasoned from), then the first IOB prediction point.
        m = re.search(r"\bBG=(\d+(?:[.,]\d+)?)", reason)
        if m:
            bg_mgdl = to_mgdl(float(m.group(1).replace(",", ".")))
        else:
            pred = sug.get("predBGs") or {}
            arr = pred.get("IOB") or pred.get("ZT") or pred.get("UAM") or []
            if isinstance(arr, list) and arr:
                bg_mgdl = to_mgdl(arr[0])
    if bg_mgdl is None:
        return None

    target_mgdl = to_mgdl(sug.get("targetBG"))

    row = {
        "user_id": user_id,
        "ts_utc": ts.to_pydatetime(),
        "ts_epoch": int(ts.timestamp()),
        "variant": variant,
        # Standard suggested fields
        "cgm_mgdl": bg_mgdl,
        "sug_current_target": target_mgdl,
        "sug_eventualBG": to_mgdl(sug.get("eventualBG")),
        "sug_insulinReq": sug.get("insulinReq"),
        "sug_rate": sug.get("rate"),
        "sug_duration": sug.get("duration"),
        "sug_COB": sug.get("COB"),
        # AIMI's suggested.IOB disagrees with its own iob block (observed -0.008 vs 2.313),
        # so for AIMI take the iob block, which is the value its dosing used.
        "sug_IOB": (iob.get("iob") if is_aimi and iob.get("iob") is not None else sug.get("IOB")),
        # Boost top-level
        "tdd": sug.get("tdd"),
        "tdd_ratio": sug.get("tddRatio"),
        "delta_acceleration": sug.get("deltaAcceleration"),
        # Volume-weighted dose shadow: the blend it proposes and the working behind it. Read-only
        # telemetry, so a within-person trial has the paired estimates from the first cycle.
        "vwa_blend": sug.get("boostVwa_blend"),
        "vwa_projection": sug.get("boostVwa_projection"),
        "vwa_expected": sug.get("boostVwa_expected"),
        "vwa_delivered": sug.get("boostVwa_delivered"),
        "vwa_day_fraction": sug.get("boostVwa_dayFraction"),
        "vwa_calibrated_tdd": sug.get("boostVwa_calibratedTdd"),
        "vwa_curve_days": sug.get("boostVwa_curveDays"),
        "vwa_used_prev_day": sug.get("boostVwa_usedPrevDay"),
        "sens_normal_target": sug.get("sensNormalTarget"),
        "variable_sens": sug.get("variable_sens"),
        "dynamic_isf": sug.get("dynamicISF"),
        "running_dynamic_isf": sug.get("runningDynamicIsf"),
        "prediction_isf": sug.get("predictionISF"),
        "isf_mgdl_for_carbs": sug.get("isfMgdlForCarbs"),
        "boost_active_top": sug.get("boostActive"),
        "boost_profile_switch": sug.get("boostProfileSwitch"),
        "boost_tier_top": sug.get("boostTier"),
        "fast_carb_protection": sug.get("fastCarbProtection"),
        # V5/V6 shadow override (Boost-ML-Beta logs these every cycle; NULL on
        # original-Boost users). boostV5_finalDose = the V6 would-be SMB, paired
        # against `units` (V1's actual SMB) from identical inputs.
        "boostv5_active": sug.get("boostV5_active"),
        "boostv5_state": sug.get("boostV5_state"),
        "boostv5_finaldose": sug.get("boostV5_finalDose"),
        "boostv5_budget": sug.get("boostV5_budget"),
        "boostv5_actionmult": sug.get("boostV5_actionMult"),
        "boostv5_score": sug.get("boostV5_score"),
        "boostv5_age": sug.get("boostV5_age"),
        "boostv5_gatereduction": sug.get("boostV5_gateReduction"),
        "boostv5_committedcap": sug.get("boostV5_committedCap"),
        "boostv5_confirmedcap": sug.get("boostV5_confirmedCap"),
        # 2026-07-03 confirm-gate telemetry (for the 2026-07-10 live gate review):
        # confirmGate = "pass" | "blocked" | "n/a"; prospectiveShot = velocity-scaled prospective
        # confirm shot (U) the gate compares to the floor; aggressionKnob = user's Aggression knob.
        "boostv5_confirmgate": sug.get("boostV5_confirmGate"),
        "boostv5_prospectiveshot": sug.get("boostV5_prospectiveShot"),
        "boostv5_aggressionknob": sug.get("boostV5_aggressionKnob"),
        # 2026-07-04 post-rescue meal-state cap telemetry (for the 2026-07-10 live review):
        # true when the app's recentLowBG45Min < 75 mg/dL — V1's tiers are hypo-restrained AND the
        # V6 meal-state exemption is suppressed (CONFIRMED/COMMITTED capped at V1's would-dose).
        "boostv5_postrescuewindow": sug.get("boostV5_postRescueWindow"),
        # 2026-07-06 composed-floor SHADOW: extra U the Phase-3 composed floor (F=0.25) would have
        # added this cycle (null = floor conditions unmet). Validates the multiplicative-brake-stack
        # fix (median composed mult 0.037 on meal-session high cycles) before activation.
        "boostv5_floorwouldadd": sug.get("boostV5_floorWouldAdd"),
        # 2026-07-06 cumulative-cap telemetry: the operative rolling-60-min anti-stacking SMB cap
        # (0 = disabled) and the trailing-60-min SMB volume it compares against — a cap suppression
        # was previously indistinguishable from a zero-dose decision.
        "boostv5_cumulativecapu": sug.get("boostV5_cumulativeCapU"),
        "boostv5_smbvol60min": sug.get("boostV5_smbVol60Min"),
        # 2026-07 V7 SHADOW telemetry (read-only would-dose instrument on the Boost-V7-shadow
        # build; see Boost-AAPS-core plugins/aps/.../openAPSBoostV7/V7_SHADOW.md and the
        # foundation report's NO-GO lineage). wouldDoseR4/R7/R10 = the revised distributional
        # sizer at low:high cost ratio 4/7/10 — identical values in the field means acceptance
        # criterion (a) is still failing; q50drift = active regime pool's median 30-min residual
        # (criterion (b): quiet_flat must read ≈0 once debiased); pool = "regime(n=…)" |
        # "regime(warming n=…)" | "excluded"; plow90 = display-only left-shoulder p(BG<70 in 90m);
        # innovsensfrozen = rolling 30-min innovation SUM with sens frozen at profile ISF.
        "boostv7_woulddoser4": sug.get("boostV7_wouldDoseR4"),
        "boostv7_woulddoser7": sug.get("boostV7_wouldDoseR7"),
        "boostv7_woulddoser10": sug.get("boostV7_wouldDoseR10"),
        "boostv7_plow90": sug.get("boostV7_pLow90"),
        "boostv7_q50drift": sug.get("boostV7_q50Drift"),
        "boostv7_pool": sug.get("boostV7_pool"),
        "boostv7_innovsensfrozen": sug.get("boostV7_innovSensFrozen"),
        # 2026-07-18 KAIROS Twin shadow — physiological EnKF forecaster telemetry (read-only; the Twin
        # doses nothing). Packed by the app into ONE csv field "fc30,fc60,lo60,hi60,ra,gi,insU" (the
        # legacy V3MLG3 ART verifier limit forbids 7 separate RT fields). Split back into columns here.
        # fc30/fc60 = forecast CGM at 30/60 min; lo60/hi60 = 60-min 90% band; ra = inferred glucose
        # appearance (meal signal); gi = filtered glucose; insu = insulin the Twin assimilated (fidelity watch).
        "boosttwin_fc30": _twin(reason, 0),
        "boosttwin_fc60": _twin(reason, 1),
        "boosttwin_lo60": _twin(reason, 2),
        "boosttwin_hi60": _twin(reason, 3),
        "boosttwin_ra": _twin(reason, 4),
        "boosttwin_gi": _twin(reason, 5),
        "boosttwin_insu": _twin(reason, 6),
        "boosttwin_lo30": _twin(reason, 7),
        "boosttwin_floorbreach": _twin(reason, 8),
        # 2026-07-19 post-meal plateau-nudge SHADOW (read-only; PLATEAU_NUDGE_SPEC.md). trig=would-fire
        # this cycle; wouldnudge=U it would deliver; floor=why (ok/n/a/veto). Price on-device before active.
        "boostv5_plateau_trig": _plat(reason, 0, int),
        "boostv5_plateau_wouldnudge": _plat(reason, 1),
        "boostv5_plateau_bg": _plat(reason, 2),
        "boostv5_plateau_trend": _plat(reason, 3),
        "boostv5_plateau_iob": _plat(reason, 4),
        "boostv5_plateau_floor": _plat(reason, 6, str),
        "autocfg_summary": (lambda m: m.group(1) if m else None)(AUTOCFG_RE.search(reason or "")),
        "autordv_at": _autordv(reason, "at"),
        "autordv_window_d": _autordv(reason, "window_d"),
        "autordv_evaluated": _autordv(reason, "evaluated"),
        "autordv_changed": _autordv(reason, "changed"),
        "autordv_changes": _autordv(reason, "changes"),
        "prtrial_enrolled": _prtrial(reason, 0, int),
        "prtrial_arm": _prtrial(reason, 1, str),
        "prtrial_cap": _prtrial(reason, 2),
        # 2026-07-20 anticipatory back-out controller SHADOW (read-only; BACKOUT_CONTROLLER_SPEC.md).
        "antbackout_state": _antb(reason, 0, str),
        "antbackout_ra0": _antb(reason, 1), "antbackout_ranow": _antb(reason, 2),
        "antbackout_bg0": _antb(reason, 3, int), "antbackout_bgnow": _antb(reason, 4, int),
        "antbackout_confirmed": _antb(reason, 5, int), "antbackout_backedout": _antb(reason, 6, int),
        "antbackout_trip": _antb(reason, 7, int), "antbackout_meallikely": _antb(reason, 8),
        "antbackout_armsrc": _antb(reason, 9, str),
        # 2026-07-27 per-user ANTICIPATION SHADOW (read-only; ANTICIPATION_ARCHITECTURE_SPEC.md).
        "anticip_p_ex": _anticip(reason, 0), "anticip_p_meal": _anticip(reason, 1),
        "anticip_src_ex": _anticip(reason, 2, str), "anticip_src_meal": _anticip(reason, 3, str),
        "anticip_ex_arm": _anticip(reason, 4, int), "anticip_ex_conf": _anticip(reason, 5, int),
        "anticip_ex_bo": _anticip(reason, 6, int), "anticip_meal_arm": _anticip(reason, 7, int),
        "anticip_meal_conf": _anticip(reason, 8, int), "anticip_meal_bo": _anticip(reason, 9, int),
        "anticip_mins_ex": _anticip(reason, 10, int), "anticip_mins_meal": _anticip(reason, 11, int),
        "anticip_n_ex": _anticip(reason, 12, int), "anticip_n_meal": _anticip(reason, 13, int),
        "ml_hypo_risk": sug.get("mlHypoRisk"),
        # 2026-09 refit, logged and never dosed on. NOT comparable to ml_hypo_risk by
        # level: different base-rate calibration, so it reads higher for the same risk.
        # Read from a [reason] tag, not an RT field: RT cannot take another field without
        # tripping the ART method verifier in the legacy V3MLG3 engine (see RT.kt).
        "ml_hypo_risk_shadow": _hyposhadow(reason),
        # Fall-consequence shadow (2026-09-03). P(reaching 70 mg/dL within 2 h of a fall onset),
        # calibrated to a 0.221 base rate. NOT comparable to ml_hypo_risk: different question,
        # different horizon, and no threshold transfers between them.
        "fallcon_score": _fallcon(reason, 0),
        "fallcon_onset_age_min": _fallcon(reason, 1, int),
        "fallcon_onset_bg": _fallcon(reason, 2),
        "fallcon_fall_mgdl": _fallcon(reason, 3),
        "fallcon_still_falling": _fallcon(reason, 4, int),
        # Why no score this cycle: nomodel, norows, rows<n>, noanchor, below70, fall<n>,
        # shortwin, schema<n>. A silent shadow and a quiet day look identical without this.
        "fallcon_skip": (lambda m: m.group(1) if m else None)(FALLCONSKIP_RE.search(reason or "")),
        "fallcon_n_readings": (lambda m: int(m.group(2)) if m else None)(FALLCONSKIP_RE.search(reason or "")),
        "ml_meal_likely": sug.get("mlMealLikely"),
        # 2026-07-07 sensing hardening: which step feeds were live this cycle
        # ("phone+wear"|"phone"|"wear"|"none" — "none" = INACTIVE + sleep-in suppressed), and the
        # 5-min HR extremes (15-min averaging blunts hypo-tachycardia: +1.5 vs +13.6 bpm,
        # 2026-07-06 analysis).
        "boost_steps_feed": sug.get("boostSteps_feed"),
        "hr_bpm_max5m": sug.get("hrBpmMax5m"),
        "hr_bpm_min5m": sug.get("hrBpmMin5m"),
        # 2026-07-10 dose-chain intermediates — make boostv5_finaldose reconstructible stage-by-stage
        # (raw→×velocity&cap=doseaftercaps→brakes=doseafterbrakes→floor=finaldose) so an offline V6
        # port can be fidelity-validated per stage.
        "boostv5_velocityfactor": sug.get("boostV5_velocityFactor"),
        "boostv5_doseaftercaps": sug.get("boostV5_doseAfterCaps"),
        "boostv5_doseafterbrakes": sug.get("boostV5_doseAfterBrakes"),
        # 2026-07-10 MISSING-DATA FIX: structured HR (hrBpmAvg15m is DENSER than the console-parsed
        # hr_avg the DB had — the DB HR sparsity was partly this gap) + learned baselines + source.
        "hr_bpm_latest": sug.get("hrBpmLatest"),
        "hr_bpm_avg5m": sug.get("hrBpmAvg5m"),
        "hr_bpm_avg15m": sug.get("hrBpmAvg15m"),
        "hr_learned_resting_bpm": sug.get("hrLearnedRestingBpm"),
        "hr_learned_daytime_bpm": sug.get("hrLearnedDaytimeBpm"),
        "hr_source_resolved": sug.get("hrSource_resolved"),
        "hr_source_states": (lambda v: None if v is None else str(v))(sug.get("hrSource_states")),
        # 2026-07-10 MISSING-DATA FIX: activity-load telemetry (intraday ISF bump, step bank, source).
        "boost_activity_load_steps_today": sug.get("boostActivityLoad_stepsToday"),
        "boost_activity_load_last_day_steps": sug.get("boostActivityLoad_lastDaySteps"),
        "boost_activity_load_baseline_steps": sug.get("boostActivityLoad_baselineSteps"),
        "boost_activity_load_ratio": sug.get("boostActivityLoad_ratio"),
        "boost_activity_load_intraday_ratio": sug.get("boostActivityLoad_intradayRatio"),
        "boost_activity_load_intraday_delta_isf_pct": sug.get("boostActivityLoad_intradayDeltaIsfPct"),
        "boost_activity_load_would_delta_isf_pct": sug.get("boostActivityLoad_wouldDeltaIsfPct"),
        "boost_activity_load_source": (lambda v: None if v is None else str(v))(sug.get("boostActivityLoad_source")),
        "boost_activity_load_steps_source": (lambda v: None if v is None else str(v))(sug.get("boostActivityLoad_stepsSource")),
        # On AAPS variants: V1's actual SMB (paired against boostV5_finalDose).
        # On trio variants: the ACTING engine is stock trio-oref, so v1_units =
        # trio-oref's actual suggested/enacted SMB units for the cycle — same
        # paired-comparison semantics (acting-engine dose vs Boost would-dose).
        "v1_units": sug.get("units"),
        # IOB block
        "iob_iob": iob.get("iob"),
        "iob_activity": iob.get("activity"),
        "iob_basaliob": iob.get("basaliob"),
        "iob_bolusiob": iob.get("bolusiob"),
        "iob_netbasalinsulin": iob.get("netbasalinsulin"),
        # Pump
        "pump_battery": (rec.get("pump") or {}).get("battery", {}).get("percent") if isinstance((rec.get("pump") or {}).get("battery"), dict) else None,
    }

    # Trio: fill the V5-shadow columns from the reason tag (Trio has no
    # structured boostV5_* suggested fields — sug.get() above yields None).
    if variant.startswith("trio"):
        trio = parse_trio_tag(reason)
        if trio:
            row["boostv5_active"] = trio["mode"] == "active"
            row["boostv5_state"] = trio["state"]
            row["boostv5_score"] = trio["score"]
            row["boostv5_finaldose"] = trio["smb"]
            row["ml_hypo_risk"] = trio["hypo"]
            row["ml_meal_likely"] = trio["meal"]

    # Parsed-from-consoleError fields
    row["boost_active_console"] = parse_boost_active(ce)
    row["boost_tier"] = parse_boost_tier(ce, sug.get("boostTier"))
    row.update(parse_steps(ce))
    row.update(parse_glucose_status(ce))
    row.update(parse_hr_features(ce))
    row.update(parse_isf_blend(ce))
    row.update(parse_shadow_lines(ce))
    row.update(parse_reason(reason))

    # Keep raw consoleError so re-parses are possible without re-fetching
    row["console_error"] = ce[:8000]  # cap to avoid runaway rows
    row["reason_text"] = reason[:2000]
    return row


# ───────────────────────────────────────────────────────────────────────────
# Database
# ───────────────────────────────────────────────────────────────────────────

def migrate_columns(cur, table, ddl):
    """Add any column the DDL declares for `table` that the live table lacks.

    CREATE TABLE IF NOT EXISTS does nothing to a table that already exists, so a column added to
    the DDL never reaches a database built before it. The failure is silent where it matters: the
    refresh runner reports FAILED in a truncated cell and the only visible symptom is that no new
    rows arrive. That happened on 2026-09-03, when five fallcon_ columns were declared and the live
    table was not altered, and every refresh failed for a day before anyone looked.

    The DDL string defines more than one table, so the block for this one is isolated first. An
    earlier version of this function did not, and added boost_cgm's `direction` column to
    boost_decisions.
    """
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table}\s*\((.*?)\n\);", ddl, re.S | re.I)
    if not m:
        return
    declared = []
    for line in m.group(1).splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY", "UNIQUE", "CONSTRAINT", "FOREIGN")):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and re.fullmatch(r"[a-z_][a-z0-9_]*", parts[0]):
            declared.append((parts[0], parts[1]))

    cur.execute("select column_name from information_schema.columns where table_name = %s", (table,))
    have = {r[0] for r in cur.fetchall()}
    added = []
    for name, typ in declared:
        if name in have:
            continue
        cur.execute(f'alter table {table} add column if not exists "{name}" {typ}')
        added.append(name)
    if added:
        print(f"[db] added {len(added)} missing column(s) to {table}: {', '.join(added)}")


DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    user_id              text NOT NULL,
    ts_utc               timestamptz NOT NULL,
    ts_epoch             bigint,
    variant              text,
    cgm_mgdl             double precision,
    sug_current_target   double precision,
    sug_eventualBG       double precision,
    sug_insulinReq       double precision,
    sug_rate             double precision,
    sug_duration         double precision,
    sug_COB              double precision,
    sug_IOB              double precision,
    tdd                  double precision,
    tdd_ratio            double precision,
    delta_acceleration   double precision,
    gs_delta             double precision,
    gs_short_avg_delta   double precision,
    gs_long_avg_delta    double precision,
    sens_normal_target   double precision,
    variable_sens        double precision,
    dynamic_isf          double precision,
    running_dynamic_isf  boolean,
    prediction_isf       double precision,
    isf_mgdl_for_carbs   double precision,
    boost_active_top     boolean,
    boost_profile_switch double precision,
    boost_tier_top       text,
    fast_carb_protection text,
    boostv5_active        boolean,
    boostv5_state         text,
    boostv5_finaldose     double precision,
    boostv5_budget        double precision,
    boostv5_actionmult    double precision,
    boostv5_score         double precision,
    boostv5_age           double precision,
    boostv5_gatereduction text,
    ml_hypo_risk          double precision,
    ml_hypo_risk_shadow   double precision,
    fallcon_score         double precision,
    fallcon_onset_age_min integer,
    fallcon_onset_bg      double precision,
    fallcon_fall_mgdl     double precision,
    fallcon_still_falling integer,
    fallcon_skip          text,
    fallcon_n_readings    integer,
    ml_meal_likely        double precision,
    v1_units              double precision,
    iob_iob              double precision,
    iob_activity         double precision,
    iob_basaliob         double precision,
    iob_bolusiob         double precision,
    iob_netbasalinsulin  double precision,
    pump_battery         double precision,
    boost_active_console boolean,
    boost_tier           text,
    steps_5m             integer,
    steps_15m            integer,
    steps_30m            integer,
    steps_60m            integer,
    hr_avg               double precision,
    hrr_pct              double precision,
    hr_zone              text,
    isf_shadow_raw       double precision,
    isf_shadow_ema       double precision,
    isf_shadow_bounded   double precision,
    isf_shadow_warmup    double precision,
    tdd_7d               double precision,
    tdd_1d               double precision,
    tdd_24h              double precision,
    tdd_4h               double precision,
    tdd_8to4h            double precision,
    tdd_weighted8h       double precision,
    tdd_blended          double precision,
    tdd_adj_factor       double precision,
    reason_Dev           double precision,
    reason_BGI           double precision,
    reason_minPredBG     double precision,
    reason_minGuardBG    double precision,
    reason_IOBpredBG     double precision,
    reason_UAMpredBG     double precision,
    console_error        text,
    reason_text          text,
    PRIMARY KEY (user_id, ts_utc)
);
CREATE INDEX IF NOT EXISTS {TABLE}_user_variant_idx ON {TABLE} (user_id, variant);
CREATE INDEX IF NOT EXISTS {TABLE}_ts_idx ON {TABLE} (ts_utc);

-- Self-migrate existing tables to the V5/V6 shadow columns (idempotent).
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_active        boolean;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_state         text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_finaldose     double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_budget        double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_actionmult    double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_score         double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_age           double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_gatereduction text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_committedcap  double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_confirmedcap  double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_confirmgate     text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_prospectiveshot double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_aggressionknob  double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_postrescuewindow boolean;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_floorwouldadd   double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_cumulativecapu  double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_smbvol60min     double precision;
-- 2026-07-10 dose-chain intermediates (offline V6-port fidelity validation)
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_velocityfactor  double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_doseaftercaps   double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_doseafterbrakes double precision;
-- 2026-07-10 MISSING-DATA FIX: structured HR (denser than console hr_avg) + learned baselines + source
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS hr_bpm_latest           double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS hr_bpm_avg5m            double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS hr_bpm_avg15m           double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS hr_learned_resting_bpm  double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS hr_learned_daytime_bpm  double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS hr_source_resolved      text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS hr_source_states        text;
-- 2026-07-10 MISSING-DATA FIX: activity-load telemetry (intraday ISF bump, step bank, source)
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boost_activity_load_steps_today            double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boost_activity_load_last_day_steps         double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boost_activity_load_baseline_steps         double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boost_activity_load_ratio                  double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boost_activity_load_intraday_ratio         double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boost_activity_load_intraday_delta_isf_pct double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boost_activity_load_would_delta_isf_pct    double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boost_activity_load_source                 text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boost_activity_load_steps_source           text;
-- 2026-07 V7 SHADOW telemetry (Boost-V7-shadow build; NULL on every other variant).
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv7_woulddoser4     double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv7_woulddoser7     double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv7_woulddoser10    double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv7_plow90          double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv7_q50drift        double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv7_pool            text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv7_innovsensfrozen double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boosttwin_fc30          double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boosttwin_fc60          double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boosttwin_lo60          double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boosttwin_hi60          double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boosttwin_ra            double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boosttwin_gi            double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boosttwin_insu          double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boosttwin_lo30          double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boosttwin_floorbreach   double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_plateau_trig       double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_plateau_wouldnudge double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_plateau_bg         double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_plateau_trend      double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_plateau_iob        double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boostv5_plateau_floor      text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS autocfg_summary            text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS autordv_at                 text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS autordv_window_d           integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS autordv_evaluated          integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS autordv_changed            integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS autordv_changes            text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS prtrial_enrolled           integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS prtrial_arm                text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS prtrial_cap                double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS antbackout_state           text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS antbackout_ra0             double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS antbackout_ranow           double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS antbackout_bg0             double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS antbackout_bgnow           double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS antbackout_confirmed       integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS antbackout_backedout       integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS antbackout_trip            integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS antbackout_meallikely      double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS antbackout_armsrc          text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_p_ex               double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_p_meal             double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_src_ex             text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_src_meal           text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_ex_arm             integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_ex_conf            integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_ex_bo              integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_meal_arm           integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_meal_conf          integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_meal_bo            integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_mins_ex            integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_mins_meal          integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_n_ex               integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS anticip_n_meal             integer;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS ml_hypo_risk          double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS ml_meal_likely        double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS v1_units              double precision;
-- 2026-07-07 sensing-hardening telemetry: step-feed availability (F1) + 5-min HR extremes (F5).
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS boost_steps_feed      text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS hr_bpm_max5m          double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS hr_bpm_min5m          double precision;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS sleep_state           text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS sleep_learned_onset   text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS sleep_learned_wake    text;
ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS sleep_learned_days    integer;

CREATE TABLE IF NOT EXISTS boost_cgm (
    user_id  text NOT NULL,
    ts_utc   timestamptz NOT NULL,
    cgm_mgdl double precision,
    direction text,
    PRIMARY KEY (user_id, ts_utc)
);
"""


def upsert(conn, rows: list, columns: list, table: str):
    if not rows:
        return 0
    # Dedupe on the conflict key (user_id, ts_utc) before the upsert: some uploaders double-post at
    # the same created_at timestamp, and ON CONFLICT DO UPDATE cannot affect the same key twice in a
    # single command (CardinalityViolation). Keep the last occurrence.
    deduped = {}
    for r in rows:
        deduped[(r.get("user_id"), r.get("ts_utc"))] = r
    rows = list(deduped.values())
    placeholders = ",".join(columns)
    update_set = ", ".join(f"{c}=EXCLUDED.{c}" for c in columns if c not in ("user_id", "ts_utc"))
    sql = (f"INSERT INTO {table} ({placeholders}) VALUES %s "
           f"ON CONFLICT (user_id, ts_utc) DO UPDATE SET {update_set}")
    values = [tuple(r.get(c) for c in columns) for r in rows]
    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=2000)
    conn.commit()
    return len(rows)


# ───────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--since", default="2026-02-01T00:00:00Z")
    ap.add_argument("--until", default=None)
    args = ap.parse_args()

    until = args.until or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[fetch] devicestatus {args.since} → {until}")
    ds = fetch_devicestatus(args.url, args.token, args.since, until)
    print(f"[fetch] devicestatus total: {len(ds):,}")

    print(f"[fetch] entries (CGM)")
    entries = fetch_entries(args.url, args.token, args.since, until)
    print(f"[fetch] entries total: {len(entries):,}")

    # Build decision rows
    rows = []
    for rec in ds:
        r = build_row(rec, args.user_id)
        if r:
            rows.append(r)
    print(f"[parse] decisions parsed: {len(rows):,}")

    variant_counts = {}
    for r in rows:
        variant_counts[r["variant"]] = variant_counts.get(r["variant"], 0) + 1
    print(f"[parse] variant breakdown: {variant_counts}")

    # Unit-normalise oref guard/pred BG to mg/dL. AAPS emits these in the user's DISPLAY unit —
    # mmol/L for mmol users (median ~5, can be negative), mg/dL for others (median ~100). Per-VALUE
    # detection is unsafe: oref projects genuine deep/negative mg/dL lows that overlap the mmol
    # range (a bare "8" is ambiguous). Decide PER-USER from the batch median (this script runs one
    # user per invocation) and scale the whole user's rows. Consistent for future + backfilled DBs.
    for fld in ("reason_minGuardBG", "reason_minPredBG"):
        vals = sorted(abs(r[fld]) for r in rows if r.get(fld) is not None)
        if vals:
            med = vals[len(vals) // 2]
            if med < 30:  # mmol/L → mg/dL
                for r in rows:
                    if r.get(fld) is not None:
                        r[fld] *= 18.0
                print(f"[units] {fld}: mmol/L (batch median {med:.1f}) → scaled ×18 to mg/dL")

    # CGM rows
    cgm_rows = []
    seen = set()
    for e in entries:
        ts_str = e.get("created_at") or e.get("dateString") or e.get("sysTime")
        if not ts_str and e.get("date"):
            # Fall back to epoch milliseconds
            ts_str = pd.to_datetime(int(e["date"]), unit="ms", utc=True).isoformat()
        if not ts_str:
            continue
        try:
            ts = pd.to_datetime(ts_str, utc=True).to_pydatetime()
        except Exception:
            continue
        sgv = e.get("sgv")
        if sgv is None:
            continue
        key = (args.user_id, ts)
        if key in seen:
            continue
        seen.add(key)
        cgm_rows.append({
            "user_id": args.user_id,
            "ts_utc": ts,
            "cgm_mgdl": float(sgv),
            "direction": e.get("direction"),
        })
    print(f"[parse] CGM points: {len(cgm_rows):,}")

    # DB insert
    print(f"[db] connecting to {DB_NAME}")
    conn = psycopg2.connect(f"dbname={DB_NAME}")
    with conn.cursor() as cur:
        cur.execute(DDL)
        migrate_columns(cur, TABLE, DDL)
    conn.commit()

    decision_columns = [k for k in rows[0].keys()] if rows else []
    n = upsert(conn, rows, decision_columns, TABLE)
    print(f"[db] upserted {n:,} decisions into {TABLE}")

    n2 = upsert(conn, cgm_rows, ["user_id", "ts_utc", "cgm_mgdl", "direction"], "boost_cgm")
    print(f"[db] upserted {n2:,} CGM points into boost_cgm")

    conn.close()
    print("[done]")


if __name__ == "__main__":
    main()
