"""Boost's own record, put on the same footing as the two research sources.

This is the cohort any of these models would actually be deployed on, so a prior that
survives transfer from the research corpora to the OpenAPS Data Commons still has to be
shown to survive transfer to here. The engine telemetry is far richer than either corpus,
but only the fields with a counterpart in the Commons are read, so the arms stay
comparable.

Records are deduplicated to one per participant per five-minute slot, keeping the last,
which is the row the following interval's glucose actually followed.

The clock matters to every model here and Boost stores time in UTC, so each participant's
timestamps are shifted by the offset held in the private site registry. Participants the
registry has no offset for are left out rather than scored against the wrong hour; that
removes the imported phase-two sites and keeps the participants Boost is actually deployed
on.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

import common
from c2_fall_consequence import LOOP_COLS, _onsets, attach_loop
from c3_post_low_rebound import _episodes

SITES = os.path.expanduser("~/.config/boost_backtest/sites_all.json")

# Boost's field names differ from the Commons; the map keeps the feature vector identical.
FIELD_MAP = {
    "iob_iob": "iob_iob",
    "iob_activity": "iob_activity",
    "iob_basaliob": "iob_basaliob",
    "sug_cob": "sug_cob",
    "sug_insulinreq": "sug_insulinreq",
    "sug_isf": "variable_sens",
    "sug_current_target": "sug_current_target",
    "sug_eventualbg": "sug_eventualbg",
}


def tz_offsets() -> dict[str, float]:
    """Hours east of UTC per participant, read from the registry, never hardcoded."""
    with open(SITES) as f:
        d = json.load(f)
    sites = d["sites"] if isinstance(d, dict) and "sites" in d else d
    if isinstance(sites, dict):
        sites = list(sites.values())
    out = {}
    for s in sites:
        tag = s.get("tag") or s.get("user_id")
        off = s.get("tz_offset_hours")
        if tag is None or off is None:
            continue
        out[tag] = float(off)
    # The registry tags the developer device "self" while the decision table keys it by the
    # device's own identifier. The alias is read from the environment rather than written
    # here, so no participant identifier appears in a file that lives in a public repository.
    # With the variable unset that participant is simply left out.
    alias = os.environ.get("BOOST_SELF_USER_ID")
    if "self" in out:
        if alias:
            out[alias] = out.pop("self")
        else:
            out.pop("self")
    return out


def load_boost() -> pd.DataFrame:
    def build():
        offs = tz_offsets()
        sel = ", ".join(f"{v} as {k}" for k, v in FIELD_MAP.items())
        df = common.query(
            "select user_id, ts_epoch, cgm_mgdl, " + sel + " from public.boost_decisions "
            "where cgm_mgdl between 39 and 401 order by user_id, ts_epoch"
        )
        df = df[df["user_id"].isin(offs)].copy()
        # ts_epoch is already seconds since the epoch, which sidesteps the microsecond
        # conversion trap entirely; the assertion below is the same guard applied to it.
        sec = df["ts_epoch"].to_numpy(dtype="float64")
        assert np.nanmax(sec) > 1.6e9, f"ts_epoch looks wrong: {np.nanmax(sec)}"
        local = sec + df["user_id"].map(offs).to_numpy() * 3600.0
        df["slot"] = (local // common.GRID_S).astype("int64")
        df = df.drop_duplicates(["user_id", "slot"], keep="last")
        for c in ["cgm_mgdl"] + list(FIELD_MAP):
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
        return df.drop(columns=["ts_epoch"]).reset_index(drop=True)

    return common.cached("boost_grid", build)


def _walk(fn, cache_name, horizons=True):
    def build():
        df = load_boost()
        out = []
        for pid, g in df.groupby("user_id", sort=False):
            g = g.sort_values("slot")
            ts = (g["slot"].to_numpy() * common.GRID_S).astype(float)
            bg = g["cgm_mgdl"].to_numpy(dtype=float)
            if len(ts) < 500:
                continue
            rows = fn(ts, bg, dict(pid=f"boost:{pid}", study="boost"))
            if not rows:
                continue
            r = pd.DataFrame(rows)
            if horizons:
                r = attach_loop(r, ts, g)
            else:
                pos = r["idx"].to_numpy()
                for c in LOOP_COLS:
                    r[c] = g[c].to_numpy(dtype=float)[pos]
            out.append(r)
        return pd.concat(out, ignore_index=True)

    return common.cached(cache_name, build)


def boost_fall_onsets() -> pd.DataFrame:
    return _walk(_onsets, "boost_fall_onsets")


def boost_low_recoveries() -> pd.DataFrame:
    return _walk(_episodes, "boost_low_recoveries", horizons=False)


if __name__ == "__main__":
    f = boost_fall_onsets()
    print(f"fall onsets: {len(f):,} across {f.pid.nunique()} participants; "
          f"low rate {f.y_low.mean():.3f}, severe {f.y_severe.mean():.3f}")
    e = boost_low_recoveries()
    print(f"low recoveries: {len(e):,} across {e.pid.nunique()} participants; "
          f"rebound>180 {e.y_high.mean():.3f}, relow {e.y_relow.mean():.3f}")
