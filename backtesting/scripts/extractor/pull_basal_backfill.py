#!/usr/bin/env python3
"""Backfill the basal stream that the treatments extractor was discarding.

The extractor kept a record only if it carried insulin or carbohydrate, or matched a short
list of zero-insulin event types. A temporary basal carries a rate and a duration and neither
of the first two, and it was not on the list, so the treatment table has held boluses alone.
Anything reading it for total daily dose has been seeing half its subject.

The extractor now keeps the basal stream, and this pulls it for the analysis cohort. Only
treatments are fetched; the decision stream is untouched. Insertion is idempotent on the
Nightscout identifier, so existing bolus rows are left as they are and only the missing basal
records land.

Site credentials are read from the private registry at runtime and never printed.

  python3 pull_basal_backfill.py --days 180
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.expanduser("~/.config/boost_backtest/sites.json")
COHORT = ("tim", "A", "B", "C", "D", "E", "F", "G", "H", "I")
# The registry tags the first participant's own site "self" while every table keys them by
# name, so a filter on the cohort names silently skips them. Map it rather than leave a
# participant out of a cohort backfill without saying so.
TAG_TO_USER = {"self": "tim"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--users", help="comma-separated subset")
    a = ap.parse_args()
    want = set(a.users.split(",")) if a.users else set(COHORT)

    reg = json.load(open(REG))
    def user_of(site):
        return TAG_TO_USER.get(site.get("tag"), site.get("tag"))

    sites = [s for s in reg["sites"] if user_of(s) in want]
    missing = want - {user_of(s) for s in sites}
    if missing:
        print(f"no registry entry for: {', '.join(sorted(missing))}\n")
    if not sites:
        raise SystemExit("no cohort sites in the registry")

    since = (dt.date.today() - dt.timedelta(days=a.days)).isoformat()
    print(f"{len(sites)} sites, treatments only, since {since}\n")
    print(f"{'user':<6}{'rows added':>12}  status")

    total = 0
    for s in sites:
        tag = user_of(s)
        cmd = [sys.executable, os.path.join(HERE, "boost_treatments.py"),
               "--user-id", tag, "--url", s["base"], "--token", s["token"],
               "--since", since]
        p = subprocess.run(cmd, capture_output=True, text=True)
        added = 0
        for line in p.stdout.splitlines():
            if "total " in line:
                try:
                    added = int(line.rsplit("total ", 1)[1].rstrip(")"))
                except ValueError:
                    pass
        total += added
        status = "ok" if p.returncode == 0 else (
            p.stderr.strip().splitlines()[-1][:50] if p.stderr.strip() else f"exit {p.returncode}")
        print(f"{tag:<6}{added:>12,}  {status}", flush=True)

    print(f"\n{total:,} treatment rows seen across the cohort")


if __name__ == "__main__":
    main()
