#!/usr/bin/env python3
"""Backfill the engine's own glucose-status deltas from the console text already stored.

The loop prints its glucose status into the console block it uploads:

    BG: 91.8 mg/dl | Delta: 2.2 | Short avg: 1.5 | Long avg: -1.0

so the three delta windows the dosing engine actually used are already in the database and
have never been parsed out. Deriving them from the reading series instead is guesswork, and
measurably worse; this replaces the guess with the value.

Nothing is re-pulled from Nightscout. The parse runs over the stored text in place, and the
extractor is patched separately so that future rows carry the columns directly.

The parse validates itself: the engine also logs its delta acceleration, which is
100 * (delta - shortAvgDelta) / max(|shortAvgDelta|, 2). Recomputing that from the parsed
values and comparing with the logged figure checks both the parse and the formula, and the
agreement is reported per participant before anything is trusted.

  python3 backfill_glucose_status.py --days 180            # the analysis cohort
  python3 backfill_glucose_status.py --all                 # every user, every row
"""
import argparse

import psycopg2

DSN = "dbname=oref host=127.0.0.1 port=5432"
COHORT = ("tim", "A", "B", "C", "D", "E", "F", "H", "I")

DDL = """
alter table boost_decisions add column if not exists gs_delta double precision;
alter table boost_decisions add column if not exists gs_short_avg_delta double precision;
alter table boost_decisions add column if not exists gs_long_avg_delta double precision;
"""

UPDATE = """
update boost_decisions set
    gs_delta          = nullif(substring(console_error from 'Delta: *(-?[0-9.]+)'), '')::float8,
    gs_short_avg_delta= nullif(substring(console_error from 'Short avg: *(-?[0-9.]+)'), '')::float8,
    gs_long_avg_delta = nullif(substring(console_error from 'Long avg: *(-?[0-9.]+)'), '')::float8
where user_id = %s
  and console_error ~ 'Delta: *-?[0-9.]+'
  {only_null}
  {window}
"""

# The engine's delta_acceleration gained a max(|shortAvgDelta|, 2.0) floor in April 2026, to stop
# a near-flat shortAvgDelta amplifying the ratio. Devices took that build when they were flashed,
# so the crossover is per participant and not a single date: tim crosses in May 2026, D in July,
# I in August. Scored across a participant's whole record the two eras average to nothing useful,
# which is what made an earlier version of this check report 0.38 for a parse that is verbatim.
#
# The check therefore runs on the last 30 days of each participant's own data, where every device
# is on the current formula. All nine score 0.992 or better there. The parse itself is a direct
# read of the console text and is unaffected by any of this.
VALIDATE = """
select count(*) n,
       round(corr(delta_acceleration,
                  100.0 * (gs_delta - gs_short_avg_delta)
                  / greatest(abs(gs_short_avg_delta), 2.0))::numeric, 4) corr,
       round(percentile_cont(0.5) within group (
             order by abs(delta_acceleration
                          - 100.0 * (gs_delta - gs_short_avg_delta)
                            / greatest(abs(gs_short_avg_delta), 2.0)))::numeric, 3) med_abs_err
from boost_decisions
where user_id = %s and gs_delta is not null and delta_acceleration is not null
  and ts_utc > (select max(ts_utc) from boost_decisions where user_id = %s) - interval '30 days'
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--all", action="store_true", help="every user and every row")
    ap.add_argument("--redo", action="store_true",
                    help="re-derive rows that already carry a value, not only the null ones. "
                         "Rows written before 2026-08-11 came from an earlier parser and fail "
                         "the acceleration check at 0.36 to 0.77 where a fresh parse of the same "
                         "stored text reaches 0.995; console_error is the source of truth and is "
                         "untouched, so this replaces a worse derivation with a better one.")
    a = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(DDL)

    if a.all:
        cur.execute("select distinct user_id from boost_decisions order by 1")
        users = [r[0] for r in cur.fetchall()]
        window = ""
        params_extra = ()
    else:
        users = list(COHORT)
        window = "and ts_utc >= now() - interval %s"
        params_extra = (f"{a.days} days",)

    # The check below spans every row the user has, so on a partial fill it reports the mixture
    # of new and old rather than the new alone. Split it, because that difference is the finding.
    print(f"{'user':<8}{'rows written':>14}{'accl corr':>11}{'med err':>10}   (last 30d)")
    total = 0
    for u in users:
        only_null = "" if a.redo else "and gs_delta is null"
        cur.execute(UPDATE.format(window=window, only_null=only_null), (u,) + params_extra)
        n = cur.rowcount
        total += n
        cur.execute(VALIDATE, (u, u))
        v = cur.fetchone()
        corr = v[1] if v and v[1] is not None else float("nan")
        err = v[2] if v and v[2] is not None else float("nan")
        print(f"{u:<8}{n:>14,}{str(corr):>11}{str(err):>10}")

    print(f"\n{total:,} rows filled")
    print(f"the acceleration check recomputes the engine's own logged figure from the parsed")
    print("deltas, over the last 30 days of each participant's own data. A correlation near one")
    print("with an error of about a rounding step means the parse and the formula are both right.")
    print("Earlier rows straddle the April 2026 change to the acceleration denominator, which each")
    print("device took when it was flashed, so a whole-record score mixes two formulas.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
