#!/usr/bin/env python3
"""Build a compressed hypertable copy of boost_decisions, leaving the original in place.

The original stays as the golden source. Nothing is migrated onto the copy until the copy has been
shown to return the same answers, which is what verify() is for. Two tables holding the same rows is
a deliberate cost for as long as it takes to trust the second one.

Why a hypertable is worth it here rather than in general. The table is 2.8 GB over 1.97 M rows and
154 columns, of which console_error is 717 MB and reason_text 611 MB: 73 per cent of it is two text
fields almost nothing reads. A routine 28-day query currently sequentially scans the lot to return
three columns. Compressed chunks are columnar, so the same query reads the columns it asked for, and
chunk exclusion means it reads four weeks of them rather than a year.

Usage:
  python3 make_hypertable.py --create      build it and copy the rows
  python3 make_hypertable.py --compress    compress chunks older than the threshold
  python3 make_hypertable.py --verify      compare the copy against the original
"""
from __future__ import annotations

import argparse
import time

import psycopg2

DSN = "dbname=oref host=127.0.0.1 port=5432"
SRC = "boost_decisions"
DST = "boost_decisions_ht"
CHUNK = "7 days"
COMPRESS_AFTER = "14 days"


def connect():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def create(cur):
    cur.execute(f"DROP TABLE IF EXISTS {DST}")
    # Same column types as the source, no constraints yet: the primary key has to include the
    # partitioning column, and adding it after the copy is faster than maintaining it during.
    cur.execute(f"CREATE TABLE {DST} (LIKE {SRC} INCLUDING DEFAULTS)")
    cur.execute(f"SELECT create_hypertable('{DST}', 'ts_utc', chunk_time_interval => INTERVAL '{CHUNK}')")
    print(f"  hypertable created, {CHUNK} chunks")
    t0 = time.time()
    cur.execute(f"INSERT INTO {DST} SELECT * FROM {SRC}")
    n = cur.rowcount
    print(f"  copied {n:,} rows in {time.time() - t0:.0f}s")
    cur.execute(f"ALTER TABLE {DST} ADD PRIMARY KEY (user_id, ts_utc)")
    cur.execute(f"CREATE INDEX ON {DST} (user_id, variant)")
    print("  primary key and variant index added")


def compress(cur):
    # Segment by participant because every analytical query filters on it, and order by time within
    # the segment so a range scan inside a chunk stays sequential.
    cur.execute(f"""ALTER TABLE {DST} SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'user_id',
        timescaledb.compress_orderby = 'ts_utc DESC')""")
    cur.execute(f"SELECT add_compression_policy('{DST}', INTERVAL '{COMPRESS_AFTER}')")
    print(f"  compression policy added: chunks older than {COMPRESS_AFTER}")
    cur.execute(f"""SELECT compress_chunk(c) FROM show_chunks(
        '{DST}', older_than => INTERVAL '{COMPRESS_AFTER}') c""")
    print(f"  compressed {cur.rowcount} existing chunks")


def verify(cur):
    ok = True

    def check(label, sql):
        nonlocal ok
        cur.execute(sql.format(t=SRC))
        a = cur.fetchall()
        cur.execute(sql.format(t=DST))
        b = cur.fetchall()
        same = a == b
        ok &= same
        print(f"  {'match  ' if same else 'DIFFER '} {label}")
        if not same:
            print(f"      original: {a[:3]}")
            print(f"      copy    : {b[:3]}")

    check("row count", "SELECT count(*) FROM {t}")
    check("participants and their row counts",
          "SELECT user_id, count(*) FROM {t} GROUP BY 1 ORDER BY 1")
    check("time span", "SELECT min(ts_utc), max(ts_utc) FROM {t}")
    check("null count on a sparse column", "SELECT count(boostv7_plow90) FROM {t}")
    check("28-day glucose aggregate per participant-day",
          """SELECT user_id, ts_utc::date, count(*), round(avg(cgm_mgdl)::numeric, 6)
             FROM {t} WHERE ts_utc > now() - interval '28 days'
               AND cgm_mgdl IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2""")
    check("checksum over every non-text column",
          """SELECT sum(hashtext(user_id || ts_utc::text || coalesce(cgm_mgdl::text,'')
                                || coalesce(sug_iob::text,'') || coalesce(boostv5_active::text,''))::bigint)
             FROM {t}""")
    print("\n  " + ("the copy is identical to the original" if ok
                    else "THE COPY DIFFERS — do not use it"))
    return ok


def sizes(cur):
    cur.execute("""SELECT relname, pg_size_pretty(pg_total_relation_size(c.oid))
                   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname='public' AND relname LIKE 'boost_decisions%' AND relkind='r'""")
    for r in cur.fetchall():
        print(f"    {r[1]:>10}  {r[0]}")
    cur.execute(f"""SELECT pg_size_pretty(hypertable_size('{DST}'))""")
    print(f"    {cur.fetchone()[0]:>10}  {DST} (hypertable_size, includes compressed chunks)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--compress", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--sizes", action="store_true")
    a = ap.parse_args()
    conn = connect()
    cur = conn.cursor()
    if a.create:
        create(cur)
    if a.compress:
        compress(cur)
    if a.verify:
        verify(cur)
    if a.sizes:
        sizes(cur)


if __name__ == "__main__":
    main()
