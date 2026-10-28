#!/usr/bin/env python3
"""Generate the schema reference for the local analysis database.

The extractor's table has grown to a hundred and fifty odd columns across four generations of the
engine, and the column list alone does not say which generation wrote what or which columns are
populated for whom. This reads the live database and reports both: the declared schema, and how much
of each column is actually filled, which is usually the question being asked.

Grouping is by column prefix, because that is how the extractor names things and it corresponds to
where the value came from: sug_ from the oref suggestion, boostv5_ from the V5/V6 engine, boosttwin_
from the shadow forecaster, and so on.

Usage:
  python3 schema_doc.py [--out SCHEMA.md]
"""
from __future__ import annotations

import argparse
import os
import warnings

import pandas as pd
import psycopg2

DSN = "dbname=oref host=127.0.0.1 port=5432"
HERE = os.path.dirname(os.path.abspath(__file__))
warnings.filterwarnings("ignore", message=".*SQLAlchemy connectable.*")

# Prefix to section. Order is the order they appear in the document.
GROUPS = [
    ("",            "Identity and time"),
    ("cgm_",        "Glucose"),
    ("sug_",        "The oref suggestion"),
    ("reason_",     "Parsed from the reason string"),
    ("iob_",        "Insulin on board"),
    ("boost_",      "Boost, engine-agnostic"),
    ("boostv5_",    "V5/V6 engine state"),
    ("boosttwin_",  "Twin shadow forecaster"),
    ("v7_",         "V7 shadow"),
    ("boostv7_",    "V7 shadow"),
    ("ml",          "Machine-learning inputs"),
    ("plateau_",    "Plateau nudge shadow"),
    ("accel_",      "Acceleration meal detector shadow"),
    ("primer_",     "Acceleration primer"),
    ("prtrial_",    "Post-rescue ramp trial"),
    ("accelmeal_",  "Acceleration meal detector shadow"),
    ("antbackout_", "Anticipatory back-out controller shadow"),
    ("anticip_",    "Anticipation predictor shadow"),
    ("sleep_",      "Sleep detection"),
    ("isf_",        "ISF"),
    ("hr_",         "Heart rate and activity"),
    ("steps_",      "Heart rate and activity"),
    ("tdd",         "Total daily dose"),
    ("pump_",       "Pump and device"),
]

# Columns whose name carries no usable prefix. Assigned explicitly rather than left in a bucket
# called Other, since every one of them is read by something in backtesting/.
EXPLICIT = {
    "hrr_pct": "Heart rate and activity",
    "delta_acceleration": "Glucose",
    "variable_sens": "ISF", "dynamic_isf": "ISF", "running_dynamic_isf": "ISF",
    "prediction_isf": "ISF", "sens_normal_target": "ISF",
    "fast_carb_protection": "Boost, engine-agnostic",
    "console_error": "Identity and time",
    "v1_units": "Boost, engine-agnostic",
}

IDENTITY = {"user_id", "ts_utc", "ts_epoch", "variant"}


def connect():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def group_of(col):
    if col in IDENTITY:
        return "Identity and time"
    if col in EXPLICIT:
        return EXPLICIT[col]
    best = None
    for prefix, name in GROUPS:
        if prefix and col.startswith(prefix):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, name)
    return best[1] if best else "Other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="SCHEMA.md")
    ap.add_argument("--table", default="boost_decisions")
    a = ap.parse_args()
    conn = connect()

    tables = pd.read_sql(
        """SELECT table_name FROM information_schema.tables
           WHERE table_schema='public' AND table_name LIKE 'boost%' ORDER BY 1""", conn)

    L = []
    P = L.append
    P("# The local analysis database\n")
    P("\nPostgreSQL with TimescaleDB, database `oref`, tables in `public`. Written by the extractor "
      "from each participant's Nightscout site and read by everything in `backtesting/`. Generated "
      "from the live database rather than maintained by hand, so it reports what is there rather "
      "than what was intended.\n")

    P("\n## Tables\n")
    P("\n| table | columns | rows | participants | earliest | latest |")
    P("|---|---|---|---|---|---|")
    for t in tables.table_name:
        n = pd.read_sql(f"SELECT count(*) n, count(DISTINCT user_id) u, min(ts_utc) a, max(ts_utc) b "
                        f"FROM {t}", conn).iloc[0]
        cols = pd.read_sql("SELECT count(*) c FROM information_schema.columns "
                           "WHERE table_name=%(t)s", conn, params={"t": t}).c.iloc[0]
        P(f"| `{t}` | {cols} | {int(n.n):,} | {int(n.u)} | {str(n.a)[:10]} | {str(n.b)[:10]} |")

    P("\n## Keys and indexes\n")
    idx = pd.read_sql(
        """SELECT tablename, indexname, indexdef FROM pg_indexes
           WHERE schemaname='public' AND tablename LIKE 'boost%' ORDER BY tablename, indexname""",
        conn)
    P("\n| table | index | definition |")
    P("|---|---|---|")
    for _, r in idx.iterrows():
        d = r.indexdef.split(" USING ")[-1]
        P(f"| `{r.tablename}` | `{r.indexname}` | `{d}` |")

    try:
        hyp = pd.read_sql("SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables",
                          conn)
        boost_hyp = [r for _, r in hyp.iterrows() if r.hypertable_name.startswith("boost")]
        if boost_hyp:
            P("\nTimescaleDB hypertables: " +
              ", ".join(f"`{r.hypertable_name}` ({int(r.num_chunks)} chunks)" for r in boost_hyp) + ".\n")
        elif not hyp.empty:
            P("\nNone of the `boost_` tables is a hypertable. They are ordinary PostgreSQL tables, "
              "indexed on participant and time, in a database that also holds older TimescaleDB "
              "hypertables from earlier work: "
              + ", ".join(f"`{r.hypertable_name}`" for _, r in hyp.iterrows())
              + ". Nothing in the current analysis depends on TimescaleDB features, so the tables "
                "can be read with plain PostgreSQL.\n")
        else:
            P("\nNo hypertables are declared; the tables are ordinary PostgreSQL tables in a database "
              "that has the TimescaleDB extension available.\n")
    except Exception:
        P("\nHypertable status could not be read.\n")

    # ---- the wide table, by group, with fill rates
    P(f"\n## `{a.table}`\n")
    total = pd.read_sql(f"SELECT count(*) n FROM {a.table}", conn).n.iloc[0]
    cols = pd.read_sql(
        """SELECT column_name, data_type FROM information_schema.columns
           WHERE table_name=%(t)s ORDER BY ordinal_position""", conn, params={"t": a.table})
    P(f"\n{len(cols)} columns over {total:,} rows. The fill column is the share of rows where the "
      f"value is not null, which is the quickest way to see whether a field belongs to an engine "
      f"generation or a shadow layer that only some participants ran.\n")

    counts = pd.read_sql(
        "SELECT " + ", ".join(f'count("{c}") AS "{c}"' for c in cols.column_name) +
        f" FROM {a.table}", conn).iloc[0]

    cols["group"] = cols.column_name.map(group_of)
    order = [n for _, n in GROUPS] + ["Other"]
    seen = set()
    for gname in order:
        if gname in seen:
            continue
        seen.add(gname)
        g = cols[cols.group == gname]
        if g.empty:
            continue
        P(f"\n### {gname}\n")
        P("\n| column | type | fill |")
        P("|---|---|---|")
        for _, r in g.iterrows():
            filled = int(counts[r.column_name])
            pct = 100.0 * filled / total if total else 0
            P(f"| `{r.column_name}` | {r.data_type.replace('double precision','float')} | "
              f"{pct:.0f}% |")

    # The narrow tables, in full: they are small enough to list outright and are read as often as
    # the wide one.
    for t in [x for x in tables.table_name if x != a.table]:
        P(f"\n## `{t}`\n")
        n = pd.read_sql(f"SELECT count(*) n FROM {t}", conn).n.iloc[0]
        c2 = pd.read_sql("""SELECT column_name, data_type, is_nullable FROM information_schema.columns
                            WHERE table_name=%(t)s ORDER BY ordinal_position""",
                         conn, params={"t": t})
        P(f"\n{len(c2)} columns over {n:,} rows.\n")
        P("\n| column | type | nullable |")
        P("|---|---|---|")
        for _, r in c2.iterrows():
            P(f"| `{r.column_name}` | {r.data_type.replace('double precision','float')} | "
              f"{'yes' if r.is_nullable=='YES' else 'no'} |")

    text = "\n".join(L) + "\n"
    open(os.path.join(HERE, a.out), "w").write(text)
    print(f"wrote {a.out}  ({len(text):,} chars, {len(cols)} columns)")


if __name__ == "__main__":
    main()
