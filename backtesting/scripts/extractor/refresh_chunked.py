#!/usr/bin/env python3
"""Refresh one site in fixed time chunks, with retries.

The one-minute instances publish five times as many devicestatus records as a
five-minute one, and a Nightscout site fronted by a free tier times out (502/504)
long before the record count itself is a problem. refresh_all.py asks for the whole
outstanding window in one request and gives up when that happens, which leaves the
arm stalled at its last successful run.

This walks the same window in chunks, retrying each with backoff, so a single slow
response costs one chunk rather than the refresh. Site base URL and token are read at
runtime from the private registry and never printed.

  refresh_chunked.py CAD_D [--hours 6] [--since 2026-08-13T00:00:00Z]
"""
import argparse, datetime as dt, json, os, subprocess, sys, time
import psycopg2

REG = os.path.expanduser("~/.config/boost_backtest/sites.json")
DSN = "dbname=oref host=127.0.0.1 port=5432"
HERE = os.path.dirname(os.path.abspath(__file__))
OVERLAP_H = 6
FALLBACK_DAYS = 14
RETRIES = 4


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", help="site tag in the private registry, or 'self'")
    ap.add_argument("--hours", type=float, default=6.0, help="chunk width in hours")
    ap.add_argument("--since", default=None, help="ISO8601 Z; default = last DB row less an overlap")
    ap.add_argument("--until", default=None, help="ISO8601 Z; default = now")
    a = ap.parse_args()

    sites = json.load(open(REG))["sites"]
    site = next((s for s in sites if s["tag"] == a.tag), None)
    if site is None:
        print(f"no site tagged {a.tag} in the registry", file=sys.stderr)
        return 2
    uid = "tim" if a.tag == "self" else a.tag

    if a.since:
        since = dt.datetime.strptime(a.since, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
    else:
        with psycopg2.connect(DSN) as c, c.cursor() as cur:
            cur.execute("select max(ts_utc) from boost_decisions where user_id = %s", (uid,))
            last = cur.fetchone()[0]
        since = ((last - dt.timedelta(hours=OVERLAP_H)) if last
                 else dt.datetime.now(dt.UTC) - dt.timedelta(days=FALLBACK_DAYS)).astimezone(dt.UTC)
    until = (dt.datetime.strptime(a.until, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
             if a.until else dt.datetime.now(dt.UTC))

    width = dt.timedelta(hours=a.hours)
    ok = failed = 0
    t = since
    while t < until:
        t1 = min(t + width, until)
        s0, s1 = (x.strftime("%Y-%m-%dT%H:%M:%SZ") for x in (t, t1))
        for attempt in range(1, RETRIES + 1):
            r = subprocess.run(
                [sys.executable, os.path.join(HERE, "boost_extractor.py"),
                 "--url", site["base"], "--token", site.get("token", ""),
                 "--user-id", uid, "--since", s0, "--until", s1],
                capture_output=True, text=True)
            if r.returncode == 0:
                rows = [l for l in r.stdout.splitlines() if "upserted" in l]
                print(f"[{uid}] {s0} -> {s1}  " + ("; ".join(x.strip() for x in rows[-2:]) or "ok"),
                      flush=True)
                ok += 1
                break
            wait = 5 * attempt
            print(f"[{uid}] {s0} -> {s1}  attempt {attempt} failed, retrying in {wait}s", flush=True)
            time.sleep(wait)
        else:
            print(f"[{uid}] {s0} -> {s1}  GAVE UP after {RETRIES} attempts", flush=True)
            failed += 1
        t = t1
    print(f"[{uid}] {ok} chunk(s) loaded, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
