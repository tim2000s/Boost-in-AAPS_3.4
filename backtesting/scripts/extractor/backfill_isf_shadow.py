#!/usr/bin/env python3
"""Backfill the ISF shadow from the console text already stored.

The shadow has computed an alternative sensitivity ratio on every cycle since February and written
it into the console block the app uploads:

    IsfShadow: tdd24=41.2 tdd7=38.9 | raw=1.059 | warmup=1.00 (days=14.0/14) | warmed=1.059
               | ema(t=3h)=1.021 | bounded=1.021

None of it was ever parsed, so a component with 370,000 cycles of output has never been scored.
Nothing is re-pulled: the parse runs over the stored text in place.
"""
import argparse
import re

import psycopg2
from psycopg2.extras import execute_batch

DSN = "dbname=oref host=127.0.0.1 port=5432"

DDL = """
alter table boost_decisions add column if not exists isf_shadow_raw double precision;
alter table boost_decisions add column if not exists isf_shadow_ema double precision;
alter table boost_decisions add column if not exists isf_shadow_bounded double precision;
alter table boost_decisions add column if not exists isf_shadow_warmup double precision;
"""

# The app formats these with the device's locale, so a participant on a European locale writes
# "raw=0,890" where an English one writes "raw=0.890". Two things follow. Matching [0-9.]+ stops at
# the comma and silently reads 0, which is what a first pass did on 61 per cent of rows. And
# Postgres's own regex would not carry the comma through a bracket expression the way Python's
# does, so the parse runs here rather than in SQL.
FIELDS = {
    "isf_shadow_raw":     re.compile(r"IsfShadow:.*?raw=(-?[0-9][0-9.,]*)"),
    "isf_shadow_ema":     re.compile(r"IsfShadow:.*?ema\([^)]*\)=(-?[0-9][0-9.,]*)"),
    "isf_shadow_bounded": re.compile(r"IsfShadow:.*?bounded=(-?[0-9][0-9.,]*)"),
    "isf_shadow_warmup":  re.compile(r"IsfShadow:.*?warmup=(-?[0-9][0-9.,]*)"),
}


def num(m):
    if not m:
        return None
    v = m.group(1).replace(",", ".")
    # a European format writes 1.234,5; after the swap that is 1.234.5, which is not a number
    if v.count(".") > 1:
        return None
    try:
        return float(v)
    except ValueError:
        return None


VALIDATE = """
select count(isf_shadow_bounded) n,
       round(percentile_cont(0.05) within group (order by isf_shadow_bounded)::numeric,3) p5,
       round(percentile_cont(0.50) within group (order by isf_shadow_bounded)::numeric,3) p50,
       round(percentile_cont(0.95) within group (order by isf_shadow_bounded)::numeric,3) p95,
       count(distinct user_id) filter (where isf_shadow_bounded is not null) users
from boost_decisions
"""


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--redo", action="store_true", help="re-derive rows that already carry a value")
    o = a.parse_args()
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(DDL)
    where = "" if o.redo else "and isf_shadow_bounded is null"
    cur.execute(f"select user_id, ts_utc, console_error from boost_decisions "
                f"where console_error like '%%IsfShadow:%%' {where}")
    rows = cur.fetchall()
    print(f"  {len(rows):,} candidate rows")
    upd = []
    for uid, ts, txt in rows:
        vals = {k: num(rx.search(txt)) for k, rx in FIELDS.items()}
        if vals["isf_shadow_bounded"] is None:
            continue
        upd.append((vals["isf_shadow_raw"], vals["isf_shadow_ema"],
                    vals["isf_shadow_bounded"], vals["isf_shadow_warmup"], uid, ts))
    execute_batch(cur, "update boost_decisions set isf_shadow_raw=%s, isf_shadow_ema=%s, "
                       "isf_shadow_bounded=%s, isf_shadow_warmup=%s "
                       "where user_id=%s and ts_utc=%s", upd, page_size=2000)
    print(f"  {len(upd):,} rows written")
    cur.execute(VALIDATE)
    n, p5, p50, p95, users = cur.fetchone()
    print(f"  {n:,} rows carry a bounded ratio, {users} participants")
    print(f"  5th centile {p5}, median {p50}, 95th {p95}")
    print("  A sensitivity ratio outside roughly 0.5 to 2.0 would mean the parse is wrong.")


if __name__ == "__main__":
    main()
