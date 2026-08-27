#!/usr/bin/env python3
"""Fill shadow-telemetry columns that were written by the extractor without the parsers.

Two extractors write `boost_decisions`. One carries the parsers for the shadow tags and the other
does not, so a run by the wrong one leaves the tag sitting in `reason_text` with its columns null.
An empty column here has always meant the extractor rather than the device.

Nothing needs re-fetching. `reason_text` is retained in full on every row, so the fix is to re-parse
what is already stored. This touches no external service and cannot lose data: it only writes
columns that are currently null, and only where the corresponding tag is present.

Run with --dry-run first. It reports what it would fill and changes nothing.
"""

import argparse
import sys

import psycopg2
import psycopg2.extras

from boost_extractor import _accelmeal, _antb, _anticip, _conseq, _plat, _prtrial, _tranche

TABLE = "public.boost_decisions"

# tag marker -> (column, parser, index, cast)
GROUPS = {
    "accelMeal=": [
        ("accelmeal_trig", _accelmeal, 0, int), ("accelmeal_accel", _accelmeal, 1, float),
        ("accelmeal_shortavgdelta", _accelmeal, 2, float),
        ("accelmeal_longavgdelta", _accelmeal, 3, float),
        ("accelmeal_bg", _accelmeal, 4, int), ("accelmeal_state", _accelmeal, 5, str),
    ],
    "antBackout=": [
        ("antbackout_state", _antb, 0, str), ("antbackout_ra0", _antb, 1, float),
        ("antbackout_ranow", _antb, 2, float), ("antbackout_bg0", _antb, 3, int),
        ("antbackout_bgnow", _antb, 4, int), ("antbackout_confirmed", _antb, 5, int),
        ("antbackout_backedout", _antb, 6, int), ("antbackout_trip", _antb, 7, int),
        ("antbackout_meallikely", _antb, 8, float), ("antbackout_armsrc", _antb, 9, str),
    ],
    "anticip=": [
        ("anticip_p_ex", _anticip, 0, float), ("anticip_p_meal", _anticip, 1, float),
        ("anticip_src_ex", _anticip, 2, str), ("anticip_src_meal", _anticip, 3, str),
        ("anticip_ex_arm", _anticip, 4, int), ("anticip_ex_conf", _anticip, 5, int),
        ("anticip_ex_bo", _anticip, 6, int), ("anticip_meal_arm", _anticip, 7, int),
        ("anticip_meal_conf", _anticip, 8, int), ("anticip_meal_bo", _anticip, 9, int),
        ("anticip_mins_ex", _anticip, 10, int), ("anticip_mins_meal", _anticip, 11, int),
        ("anticip_n_ex", _anticip, 12, int), ("anticip_n_meal", _anticip, 13, int),
    ],
    "plateau=": [
        ("boostv5_plateau_trig", _plat, 0, int), ("boostv5_plateau_wouldnudge", _plat, 1, float),
        ("boostv5_plateau_bg", _plat, 2, float), ("boostv5_plateau_trend", _plat, 3, float),
        ("boostv5_plateau_iob", _plat, 4, float), ("boostv5_plateau_floor", _plat, 6, str),
    ],
    "tranche=": [
        ("tranche_sized_u", _tranche, 0, float), ("tranche_delivered_u", _tranche, 1, float),
        ("tranche_held_u", _tranche, 2, float), ("tranche_release_p", _tranche, 3, float),
        ("tranche_state", _tranche, 4, str),
    ],
    "conseq=": [
        ("conseq_p_high", _conseq, 0, float), ("conseq_p_rise", _conseq, 1, float),
        ("conseq_onset_bg", _conseq, 2, int), ("conseq_mins", _conseq, 3, int),
        ("conseq_rise", _conseq, 4, int),
    ],
    "prTrial=": [
        ("prtrial_enrolled", _prtrial, 0, int), ("prtrial_arm", _prtrial, 1, str),
        ("prtrial_cap", _prtrial, 2, float),
    ],
}
# the column whose nullness marks a row as unparsed for that tag
SENTINEL = {"accelMeal=": "accelmeal_trig", "antBackout=": "antbackout_state",
            "anticip=": "anticip_p_meal", "plateau=": "boostv5_plateau_trig",
            "prTrial=": "prtrial_arm", "conseq=": "conseq_p_high", "tranche=": "tranche_sized_u"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default="dbname=oref")
    ap.add_argument("--tags", default=",".join(GROUPS))
    ap.add_argument("--batch", type=int, default=20000)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(args.dsn)
    conn.autocommit = False
    total = 0
    for tag in args.tags.split(","):
        if tag not in GROUPS:
            print(f"unknown tag {tag}", file=sys.stderr)
            continue
        cols = GROUPS[tag]
        sent = SENTINEL[tag]
        with conn.cursor() as cur:
            cur.execute(f"select count(*) from {TABLE} "
                        f"where reason_text like %s and {sent} is null", (f"%{tag}%",))
            n = cur.fetchone()[0]
        print(f"{tag:<13} {n:>8,} rows with the tag and no columns", flush=True)
        if args.dry_run or n == 0:
            continue

        filled = 0
        while True:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    f"select user_id, ts_utc, reason_text from {TABLE} "
                    f"where reason_text like %s and {sent} is null limit %s",
                    (f"%{tag}%", args.batch))
                rows = cur.fetchall()
            if not rows:
                break
            payload = []
            for r in rows:
                vals = [p(r["reason_text"], i, c) for (_, p, i, c) in cols]
                if all(v is None for v in vals):
                    continue                       # tag present but unparseable; leave it alone
                payload.append(tuple(vals) + (r["user_id"], r["ts_utc"]))
            if not payload:
                print(f"  {tag} halted: {len(rows)} rows matched but none parsed", flush=True)
                break
            sets = ", ".join(f"{c} = %s" for (c, _, _, _) in cols)
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur, f"update {TABLE} set {sets} where user_id = %s and ts_utc = %s",
                    payload, page_size=1000)
            conn.commit()
            filled += len(payload)
            print(f"  {tag} filled {filled:,}/{n:,}", flush=True)
            if len(rows) < args.batch:
                break
        total += filled
    print(f"\n{'would fill' if args.dry_run else 'filled'} {total:,} rows")
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
