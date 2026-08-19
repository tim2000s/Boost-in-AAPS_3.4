#!/usr/bin/env python3
"""Boost treatments extractor — pulls Nightscout `treatments` into TimescaleDB.

Why this exists: `boost_decisions` carries the DECISION stream (what the engine
computed each cycle) but not the TREATMENT stream (what was actually delivered,
and in particular the user's own MANUAL boluses). The auto-config derivation reads
manual (BS.Type.NORMAL) boluses and SMBs as two separate lists, so any offline
replay of it needs both. This wires the missing field into the extractor rather
than re-pulling ad hoc (backtesting protocol).

Output table: boost_treatments, one row per Nightscout treatment record, keyed by
(user_id, ns_id) so re-runs are idempotent.

SMB classification: AAPS v3 uploads the bolus record's `type` verbatim — "SMB" or
"NORMAL" — which is exactly the `BS.Type` the on-device auto-config splits on. That
field is stored raw (`bolus_type`) alongside a derived `is_smb`, so a consumer can
re-classify. (`isSMB` is honoured as a fallback for older uploader versions; it is
absent on current records.)

Site base URL and token are read at RUNTIME from the private registry and are
never printed.

Usage:
    python3 boost_treatments.py --user-id tim --url <base> --token <tok> [--since ISO]
    python3 boost_treatments.py --all            # every registered site, incremental
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

import psycopg2
import requests
from psycopg2.extras import execute_values

DSN = "dbname=oref host=127.0.0.1 port=5432"
TABLE = "boost_treatments"
REG = os.path.expanduser("~/.config/boost_backtest/sites.json")
CHUNK_DAYS = 7          # the sites 502 on long windows

# Zero-insulin events kept as analysis covariates (see parse()).
EVENT_TYPES_KEPT = {
    "Site Change",          # cannula age -> absorption rate
    "Insulin Change",       # cartridge: brand, concentration, dilution
    "Sensor Change", "Sensor Start",   # CGM discontinuities and warm-up artefacts
    "Pump Battery Change",
    "Profile Switch", "Temporary Target",
    # The basal stream. These carry a rate and a duration rather than an insulin amount, so
    # without them the table holds boluses only and any total-daily-dose work is reconstructing
    # half its subject from the rate the engine suggested rather than reading what was set.
    "Temp Basal", "Temporary Basal", "Suspend Pump", "Resume Pump",
}
MAX_RETRY = 4
COUNT = 50000

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    user_id    text NOT NULL,
    ns_id      text NOT NULL,
    ts_utc     timestamptz NOT NULL,
    event_type text,
    bolus_type text,                -- AAPS BS.Type verbatim: SMB | NORMAL | ...
    insulin    double precision,
    rate       double precision,
    duration   double precision,
    carbs      double precision,
    is_smb     boolean,
    PRIMARY KEY (user_id, ns_id)
);
CREATE INDEX IF NOT EXISTS {TABLE}_user_ts ON {TABLE} (user_id, ts_utc);
"""


def fetch(base, token, start, end):
    """One 7-day window of treatments, with backoff. Returns a list of dicts."""
    url = base.rstrip("/") + "/api/v1/treatments.json"
    params = {
        "find[created_at][$gte]": start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "find[created_at][$lte]": end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "count": COUNT,
    }
    if token:
        params["token"] = token
    for attempt in range(MAX_RETRY):
        try:
            r = requests.get(url, params=params, timeout=120,
                             headers={"User-Agent": "boost-backtest/1.0"})
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except Exception as e:                                   # noqa: BLE001
            last = type(e).__name__
        time.sleep(2 ** attempt * 3)
    print(f"    window {start:%Y-%m-%d} failed ({last})", file=sys.stderr)
    return []


def parse(rec, uid):
    ts = rec.get("created_at") or rec.get("timestamp")
    if not ts:
        return None
    try:
        t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.UTC)
    ins = rec.get("insulin")
    carbs = rec.get("carbs")
    # A temp basal is uploaded as a rate in units per hour with a duration in minutes; some
    # uploaders send the absolute rate under a different key, and a suspend arrives as a zero
    # rate. Both are needed to integrate delivery over the interval.
    rate = rec.get("rate")
    if rate in (None, "") and rec.get("absolute") not in (None, ""):
        rate = rec.get("absolute")
    dur = rec.get("duration")
    # Keep zero-insulin EVENT records too. Site/cartridge/sensor changes carry neither insulin nor
    # carbs, but they are required covariates for anything touching insulin kinetics: subcutaneous
    # absorption differs markedly between a fresh cannula and a three-day-old one, so an analysis
    # that ignores site age confounds it with whatever else changed at the same moment. Cartridge
    # changes matter equally when the insulin itself is altered (concentration, dilution, brand).
    if ins in (None, "") and carbs in (None, "") and rate in (None, ""):
        if str(rec.get("eventType") or "") not in EVENT_TYPES_KEPT:
            return None
    btype = rec.get("type")
    is_smb = (str(btype).upper() == "SMB") or bool(rec.get("isSMB", False))
    return (uid, str(rec.get("_id") or f"{uid}-{ts}-{ins}"), t,
            rec.get("eventType"), btype,
            float(ins) if ins not in (None, "") else None,
            float(carbs) if carbs not in (None, "") else None,
            float(rate) if rate not in (None, "") else None,
            float(dur) if dur not in (None, "") else None,
            is_smb)


def pull(uid, base, token, since, until=None):
    until = until or dt.datetime.now(dt.UTC)
    conn = psycopg2.connect(DSN)
    with conn, conn.cursor() as cur:
        cur.execute(DDL)
    rows_total = 0
    cursor = since
    while cursor < until:
        end = min(cursor + dt.timedelta(days=CHUNK_DAYS), until)
        recs = fetch(base, token, cursor, end)
        rows = [p for p in (parse(r, uid) for r in recs) if p]
        if rows:
            with conn, conn.cursor() as cur:
                execute_values(cur, f"""
                    INSERT INTO {TABLE}
                      (user_id, ns_id, ts_utc, event_type, bolus_type, insulin, carbs, rate, duration, is_smb)
                    VALUES %s ON CONFLICT (user_id, ns_id) DO NOTHING""", rows)
        rows_total += len(rows)
        print(f"    [{uid}] {cursor:%Y-%m-%d} +{len(rows)} (total {rows_total})", flush=True)
        cursor = end
    conn.close()
    return rows_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id")
    ap.add_argument("--url")
    ap.add_argument("--token", default="")
    ap.add_argument("--since", help="ISO date; default = incremental from the DB")
    ap.add_argument("--days", type=int, default=400, help="fallback lookback when the table is empty")
    ap.add_argument("--all", action="store_true", help="every site in the private registry")
    a = ap.parse_args()

    conn = psycopg2.connect(DSN)
    with conn, conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute(f"select user_id, max(ts_utc) from {TABLE} group by 1")
        latest = dict(cur.fetchall())
    conn.close()

    def since_for(uid):
        if a.since:
            return dt.datetime.fromisoformat(a.since).replace(tzinfo=dt.UTC)
        last = latest.get(uid)
        if last:
            return last - dt.timedelta(hours=6)
        return dt.datetime.now(dt.UTC) - dt.timedelta(days=a.days)

    if a.all:
        for s in json.load(open(REG))["sites"]:
            uid = "tim" if s["tag"] == "self" else s["tag"]
            print(f"[{uid}] treatments from {since_for(uid):%Y-%m-%d}", flush=True)
            try:
                pull(uid, s["base"], s.get("token", ""), since_for(uid))
            except Exception as e:                                # noqa: BLE001
                print(f"    FAILED {type(e).__name__}", file=sys.stderr)
    else:
        pull(a.user_id, a.url, a.token, since_for(a.user_id))


if __name__ == "__main__":
    main()
