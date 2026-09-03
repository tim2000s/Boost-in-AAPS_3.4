#!/usr/bin/env python3
"""Can a person's own hypoglycaemia clock add anything the shared model cannot?

The shared `hour` feature asks whether people in general go low at this time. It is worth about
+0.0015 AUC once the model has glucose, insulin on board and the rest, which is nothing. But a
cross-user model cannot express "this particular person goes low at 03:00", because participant is
the grouping unit and every split is fitted across people.

That hypothesis needs a different design. A per-user prior cannot be validated under GroupKFold,
since the participant is wholly in train or wholly in test and the prior would either leak or be
unavailable. So the split here is temporal within each participant: the prior is estimated on the
person's earlier rows and scored on their later ones, which is also how it would work in the field.

The prior is a smoothed hypoglycaemia rate by hour for that person, shrunk towards their own
overall rate so an hour with few observations does not swing it. Shrinkage strength is fixed in
advance rather than tuned, because tuning it on the same split would manufacture the result.

Three arms on identical later-half rows:
  pooled       the model as shipped, trained across participants
  +shared      the same plus the population's hour-of-day rate
  +personal    the same plus that person's own hour-of-day rate
"""
import json
import os
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import c1_hypo_scale as c1

HERE = os.path.dirname(os.path.abspath(__file__))
PRIOR_SHRINK = 50.0   # observations before an hour's own rate outweighs the person's mean
MIN_TRAIN_ROWS = 400  # a participant needs enough early history to form a prior at all


def main():
    out = {}
    for tag, path in (("4h", "c1_table_4h.parquet"), ("1h", "c1_table_1h.parquet")):
        df = pd.read_parquet(os.path.join(HERE, "cache", path)).reset_index(drop=True)
        feats = c1.feature_names()

        # Three temporal parts inside each participant. The prior is estimated on the first,
        # the model is trained on the second and scored on the third, so the prior feature is
        # never derived from the labels the model is fitted against.
        df["rank"] = df.groupby("user_id").cumcount()
        df["n_rows"] = df.groupby("user_id")["rank"].transform("max") + 1
        df = df[df.n_rows >= MIN_TRAIN_ROWS].copy()
        r = df["rank"] / df["n_rows"]
        df["part"] = np.where(r < 1 / 3, "prior", np.where(r < 2 / 3, "train", "test"))

        pri_src = df[df.part == "prior"]
        train = df[df.part == "train"].copy()
        test = df[df.part == "test"].copy()

        g = pri_src.groupby(["user_id", "hour"])["y"].agg(["sum", "count"])
        person_mean = pri_src.groupby("user_id")["y"].mean()
        personal = ((g["sum"] + PRIOR_SHRINK * person_mean.reindex(
            g.index.get_level_values(0)).to_numpy()) / (g["count"] + PRIOR_SHRINK))
        personal.name = "personal_clock"
        shared = pri_src.groupby("hour")["y"].mean().rename("shared_clock")
        overall = float(pri_src.y.mean())

        def attach(x):
            x = x.join(personal, on=["user_id", "hour"]).join(shared, on="hour")
            x["personal_clock"] = x["personal_clock"].fillna(
                x.user_id.map(person_mean)).fillna(overall)
            x["shared_clock"] = x["shared_clock"].fillna(overall)
            return x

        train, test = attach(train), attach(test)

        print(f"\n=== {tag}: prior {len(pri_src):,} / train {len(train):,} / test {len(test):,} rows, "
              f"{test.user_id.nunique()} participants, test base rate {test.y.mean():.3f} ===",
              flush=True)
        spread = test.groupby("user_id")["personal_clock"].agg(lambda x: x.max() - x.min())
        print(f"  within-person spread of the personal prior: median {spread.median():.3f}, "
              f"p90 {spread.quantile(0.9):.3f} (base rate {test.y.mean():.3f})")

        arms = {"pooled": feats,
                "shared": feats + ["shared_clock"],
                "personal": feats + ["personal_clock"],
                "both": feats + ["shared_clock", "personal_clock"]}
        sc = {}
        for name, f in arms.items():
            m = lgb.LGBMClassifier(random_state=0, **c1.PARAMS)
            m.fit(train[f], train["y"].to_numpy())
            sc[name] = m.predict_proba(test[f])[:, 1]
            used = dict(zip(f, m.booster_.feature_importance("split")))
            extra = {k: int(v) for k, v in used.items() if "clock" in k}
            print(f"  {name:>9} AUC {common.auc(test.y.to_numpy(), sc[name]):.4f}"
                  + (f"   splits on {extra}" if extra else ""), flush=True)

        late = test
        cmp = {}
        pid, y = late.user_id.to_numpy(), late.y.to_numpy()
        for a, b in [("personal", "pooled"), ("shared", "pooled"),
                     ("personal", "shared"), ("both", "pooled")]:
            d = common.paired_participant_bootstrap(pid, y, sc[a], sc[b], n_boot=4000)
            v = "distinguishable" if (d.lo > 0 or d.hi < 0) else "UNPROVEN"
            cmp[f"{a}_vs_{b}"] = [d.delta, d.lo, d.hi, v, d.n_ahead, d.n_part]
            print(f"  {a:>9} vs {b:<9} {d.delta:+.4f} ({d.lo:+.4f} to {d.hi:+.4f})  {v}"
                  f"  better on {d.n_ahead}/{d.n_part}")
        out[tag] = {"auc": {k: common.auc(y, v) for k, v in sc.items()}, "comparisons": cmp,
                    "n_late": int(len(late)), "n_participants": int(late.user_id.nunique()),
                    "personal_prior_spread_median": float(spread.median())}

    with open(os.path.join(HERE, "out", "c6_personal_clock.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote out/c6_personal_clock.json")


if __name__ == "__main__":
    main()
