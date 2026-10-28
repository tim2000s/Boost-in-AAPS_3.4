#!/usr/bin/env python3
"""Bring the Boost cohort up to date in the local database.

Reads the private site registry, works out how stale each user is from the database rather than
from a note, and pulls only the missing window. Long gaps are fetched in chunks of at most seven
days because the upstream site returns 502 on longer windows.

Nothing about a site is written here or printed. The registry path is a parameter and its contents
stay in the registry.

Usage:
  python3 refresh_cohort.py [--registry ~/.config/boost_backtest/sites.json] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
DSN = "dbname=oref host=127.0.0.1 port=5432"
EXTRACTOR = os.path.expanduser("~/StudioProjects/Boost-AAPS-core/backtesting/scripts/extractor")

# The registry tags a site by role; the database keys by participant. Only one differs.
TAG_TO_USER = {"self": "tim"}

CHUNK_DAYS = 7
OVERLAP_DAYS = 1          # re-fetch a day either side of the boundary; upserts make this free


def load_sites(path):
    r = json.load(open(os.path.expanduser(path)))
    return r["sites"] if isinstance(r, dict) else r


def last_seen(cur, table, user):
    cur.execute(f"SELECT max(ts_utc) FROM {table} WHERE user_id = %s", (user,))
    return cur.fetchone()[0]


def row_count(cur, table, user):
    cur.execute(f"SELECT count(*) FROM {table} WHERE user_id = %s", (user,))
    return cur.fetchone()[0]


def windows(since: dt.date, until: dt.date):
    """Chunk a date range so no single request covers more than CHUNK_DAYS."""
    out = []
    a = since
    while a < until:
        b = min(a + dt.timedelta(days=CHUNK_DAYS), until)
        out.append((a, b))
        a = b
    return out


def run(script, args, retries=1):
    """Run the extractor, retrying on failure with a widening pause.

    The upstream site returns 503 and 502 intermittently, and on the first cohort run that cost one
    participant their entire update for want of a second attempt.
    """
    out = ""
    for attempt in range(max(1, retries)):
        r = subprocess.run([sys.executable, os.path.join(EXTRACTOR, script)] + args,
                           capture_output=True, text=True, cwd=EXTRACTOR)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            return 0, out
        if attempt + 1 < max(1, retries):
            time.sleep(10 * (attempt + 1))
    return r.returncode, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="~/.config/boost_backtest/sites.json")
    ap.add_argument("--max-backfill-days", type=int, default=120,
                    help="cap on how far back to go for a user absent from the database")
    ap.add_argument("--only", default="",
                    help="comma separated users, for retrying one site after a transient failure "
                         "without re-pulling the rest")
    ap.add_argument("--retries", type=int, default=3,
                    help="attempts per window; the upstream site returns 503 intermittently")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()

    sites = load_sites(a.registry)
    today = dt.date.today()
    # AUTOCOMMIT MATTERS HERE. psycopg2 opens a transaction on the first statement and holds it
    # until commit, so a plain SELECT leaves an ACCESS SHARE lock on boost_decisions open. The
    # extractor this script then shells out to begins with CREATE TABLE IF NOT EXISTS, which wants
    # ACCESS EXCLUSIVE, and blocks behind that lock forever. The first run deadlocked itself this
    # way: 36 minutes idle in transaction, the extractor waiting on Lock/relation, and not one row
    # fetched. Reads elsewhere queued behind the CREATE TABLE and appeared to hang too.
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()

    L, P = [], None
    P = L.append
    P("# Boost cohort refresh\n")
    P(f"\nRegistry holds {len(sites)} sites. Database checked for staleness per user; only the "
      f"missing window is fetched, in chunks of at most {CHUNK_DAYS} days.\n")
    P("\n| user | decisions before | last seen | days stale | windows | decisions after | gained | treatments gained | result |")
    P("|---|---|---|---|---|---|---|---|---|")

    only = {u.strip() for u in a.only.split(",") if u.strip()}
    for s in sites:
        tag = s.get("tag")
        user = TAG_TO_USER.get(tag, tag)
        if only and user not in only:
            continue
        if not s.get("token") or not s.get("base"):
            P(f"| {user} | | | | | | | | no credentials in registry, skipped |")
            continue

        before = row_count(cur, "boost_decisions", user)
        t_before = row_count(cur, "boost_treatments", user)
        last = last_seen(cur, "boost_decisions", user)
        if last is None:
            since = today - dt.timedelta(days=a.max_backfill_days)
            stale = None
        else:
            since = last.date() - dt.timedelta(days=OVERLAP_DAYS)
            stale = (today - last.date()).days

        wins = windows(since, today + dt.timedelta(days=1))
        if a.dry_run:
            P(f"| {user} | {before:,} | {last.date() if last else 'never'} | "
              f"{stale if stale is not None else 'n/a'} | {len(wins)} | | | | dry run |")
            continue

        ok = True
        detail = ""
        for (w0, w1) in wins:
            rc, out = run("boost_extractor.py",
                          ["--url", s["base"], "--token", s["token"], "--user-id", user,
                           "--since", f"{w0.isoformat()}T00:00:00Z",
                           "--until", f"{w1.isoformat()}T00:00:00Z"], retries=a.retries)
            if rc != 0:
                ok = False
                tail = [ln for ln in out.strip().splitlines() if ln.strip()]
                detail = tail[-1][:70] if tail else f"exit {rc}"
                break
        if ok:
            rc, out = run("boost_treatments.py",
                          ["--user-id", user, "--url", s["base"], "--token", s["token"],
                           "--since", since.isoformat()], retries=a.retries)
            if rc != 0:
                ok = False
                tail = [ln for ln in out.strip().splitlines() if ln.strip()]
                detail = "treatments: " + (tail[-1][:60] if tail else f"exit {rc}")

        after = row_count(cur, "boost_decisions", user)
        t_after = row_count(cur, "boost_treatments", user)
        new_last = last_seen(cur, "boost_decisions", user)
        P(f"| {user} | {before:,} | {last.date() if last else 'never'} | "
          f"{stale if stale is not None else 'n/a'} | {len(wins)} | {after:,} | "
          f"+{after - before:,} | +{t_after - t_before:,} | "
          f"{'ok, now ' + str(new_last.date()) if ok else detail} |")
        print(f"  [{user}] {'ok' if ok else 'FAILED'} +{after - before} decisions", flush=True)

    P("\nA user that gains nothing is already current rather than broken; the days-stale column "
      "shows which was the case. A user with no credentials in the registry cannot be refreshed "
      "from here and is listed so the omission is visible rather than silent.\n")

    conn.close()
    open(a.out or os.path.join(HERE, "REFRESH.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
