#!/usr/bin/env python3
"""Recompute the reason-derived shadow columns in place, from reason_text already in the database.

A shadow that logs into the [reason] string only reaches an analysis if the extractor parsed it
into a column. When a shadow ships after rows have been written, or the extractor gains a parser
after the fact, the raw string is present and the column is null, and every query over that column
silently reports the shadow as absent. On 2026-09-07 that had hypo4 reading 38 cycles when the
device had logged 4,468 in three days.

Re-pulling from Nightscout would fix it and costs a long chunked download. The raw material is
already local, so this re-parses it in place instead, using the extractor's own functions so the
backfilled values cannot drift from the ones a fresh pull would produce.

Only columns derived purely from the reason string are touched. Nothing is deleted, and a row
whose reason_text is null is skipped.

Usage:
    python3 reparse_shadows.py [--user USER] [--days N] [--dry-run]
"""
import argparse
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boost_extractor as bx  # noqa: E402

# column -> callable(reason) -> value. Every one of these is a pure function of the reason string.
COLUMNS = {
    "hypo4_sustained": lambda r: bx._hypo4(r, 0),
    "hypo4_near": lambda r: bx._hypo4(r, 1),
    "hypo4_skip": lambda r: (lambda m: m.group(1) if m else None)(bx.HYPO4SKIP_RE.search(r or "")),
    "fallcon_score": lambda r: bx._fallcon(r, 0),
    "fallcon_onset_age_min": lambda r: bx._fallcon(r, 1, int),
    "fallcon_onset_bg": lambda r: bx._fallcon(r, 2),
    "fallcon_fall_mgdl": lambda r: bx._fallcon(r, 3),
    "fallcon_still_falling": lambda r: bx._fallcon(r, 4, int),
    "fallcon_skip": lambda r: (lambda m: m.group(1) if m else None)(bx.FALLCONSKIP_RE.search(r or "")),
    "fallcon_n_readings": lambda r: (lambda m: int(m.group(2)) if m else None)(bx.FALLCONSKIP_RE.search(r or "")),
    "ml_hypo_risk_shadow": lambda r: bx._hyposhadow(r),
    "accelmeal_trig": lambda r: bx._accelmeal(r, 0, int),
    "accelmeal_accel": lambda r: bx._accelmeal(r, 1),
    "accelmeal_shortavgdelta": lambda r: bx._accelmeal(r, 2),
    "accelmeal_longavgdelta": lambda r: bx._accelmeal(r, 3),
    "accelmeal_bg": lambda r: bx._accelmeal(r, 4, float),
    "accelmeal_state": lambda r: bx._accelmeal(r, 5, str),
    "tranche_sized_u": lambda r: bx._tranche(r, 0),
    "tranche_delivered_u": lambda r: bx._tranche(r, 1),
    "tranche_held_u": lambda r: bx._tranche(r, 2),
    "tranche_release_p": lambda r: bx._tranche(r, 3),
    "tranche_state": lambda r: bx._tranche(r, 4, str),
    "primer_kind": lambda r: bx._primer(r, "kind"),
    "primer_u": lambda r: bx._primer(r, "u"),
    "primer_detail": lambda r: bx._primer(r, "detail"),
    "primer_route": lambda r: bx._primer(r, "route"),
    "primer_delta": lambda r: bx._primer(r, "d"),
    "primer_f_rise": lambda r: bx._primer(r, "fR"),
    "primer_f_bg": lambda r: bx._primer(r, "fB"),
    "primer_f_iob": lambda r: bx._primer(r, "fI"),
    "primer_target": lambda r: bx._primer(r, "tgt"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=None, help="restrict to one user_id")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    c = psycopg2.connect("dbname=oref host=127.0.0.1 port=5432")
    cur = c.cursor()
    where = ["reason_text is not null",
             "ts_epoch > extract(epoch from now()) - %s * 86400"]
    params = [args.days]
    if args.user:
        where.append("user_id = %s")
        params.append(args.user)
    sel = f"""select user_id, ts_epoch, reason_text, {', '.join(COLUMNS)}
              from public.boost_decisions where {' and '.join(where)}"""
    cur.execute(sel, params)
    rows = cur.fetchall()
    print(f"examined {len(rows):,} rows")

    names = list(COLUMNS)
    changed, per_col = [], {n: 0 for n in names}
    for r in rows:
        uid, ts, reason, *current = r
        new = [COLUMNS[n](reason) for n in names]
        if new != list(current):
            for n, a, b in zip(names, current, new):
                if a != b:
                    per_col[n] += 1
            changed.append((uid, ts, new))

    print(f"rows needing update: {len(changed):,}")
    for n, k in per_col.items():
        if k:
            print(f"    {n:<24} {k:,}")
    if not changed or args.dry_run:
        print("dry run, nothing written" if args.dry_run else "nothing to do")
        return

    sets = ", ".join(f"{n} = %s" for n in names)
    upd = f"update public.boost_decisions set {sets} where user_id = %s and ts_epoch = %s"
    for uid, ts, new in changed:
        cur.execute(upd, (*new, uid, ts))
    c.commit()
    print(f"updated {len(changed):,} rows")


if __name__ == "__main__":
    main()
