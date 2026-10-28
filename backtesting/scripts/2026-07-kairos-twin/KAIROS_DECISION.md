# KAIROS — the controller question, settled; and the frontier AID that is actually buildable

*2026-07-18. Closes the "KAIROS as a forecast-optimising controller / MPC" line and states the
automatic-unannounced-meal programme that survives the identification constraint. Read with
`TWIN_OFFPOLICY.md` (the evidence) and `TING_FRONTIER.md` (the objective).*

## The mandate

Build the most effective AID we can, especially for **automatic meal management with no user
intervention** (pure UAM — the user announces nothing). This note records what a full, honest
attempt at the controller found, and where the real frontier is.

## What was tested, and what it showed

1. **The Twin is a validated SENSOR** — a calibrated per-person forecaster (30-min band 85%,
   60-min 91% after `twin_calibrate.py`) whose 30-min floor beats oref's hypo predictors at ⅓–½
   the false-alarm rate (`TWIN_HYPO_LEAD.md`). This is real and shippable.

2. **The Twin is NOT a controller model — the insulin gain is unidentifiable from the data.**
   - In the EnKF, scaling insulin sensitivity across an **8× range** leaves the forecaster's
     calibration and RMSE unchanged: the latent meal state Ra silently absorbs any insulin gain
     (`TWIN_OFFPOLICY.md`, Leg B).
   - A direct, model-light identification from **clean insulin-driven falls** (`twin_identify.py`)
     did not rescue it: the estimate swings from −1.4× to 39× the prior depending on specification,
     with R² ≤ 0 throughout. The falls are not cleanly insulin-explained (activity, meal tails, ISF
     drift dominate). Direction is robust (the old prior was ~10–20× too low); the magnitude is not
     identifiable observationally.
   - You *can* anchor SI to the user's **clinical ISF** (external knowledge) — the forward
     counterfactual gain then becomes physiological (−4 mg/dL/U at 60 min) — but Leg A still shows
     calibration decays off the modal policy, and the band does **not** widen off-policy (no
     uncertainty self-limiting).

3. **The forecast-optimising planner is degenerate in every offline configuration** (`twin_ting.py`).
   Fed the Twin's calibrated forecast + floor, the TING planner respects the floor perfectly and is
   smoother than delivered — but would dose **135–202 U/day** (open-loop) or **65–70 U/day** with an
   anti-windup self-IOB fix, against **19 U/day** actually delivered. It chases an aim (112) below
   where the glucose physically sits, and open-loop the forecast never falls in response to its own
   doses. Characterising the dose correctly requires rolling the Twin forward under the planner's own
   3.5×-off-policy doses — **exactly the off-policy counterfactual finding (2) says the Twin cannot
   provide.**

## The decision

**Stop building KAIROS as a forecast-optimising controller / MPC.** The bottleneck is
identification, not modelling (CLAUDE.md). Any policy that **adds net insulin** to chase a lower
glucose needs a trajectory counterfactual to validate, and no trustworthy one exists — the Twin,
our best forecaster, is not trustworthy far off the delivered-insulin policy, and a controller that
improves TING necessarily operates there. This is a wall, not a tuning problem.

## The frontier AID that IS buildable — and validatable

The policies that do **not** need an off-policy counterfactual to bound their safety are exactly the
ones the register already proves are harm-neutral or harm-reducing. Both use the Twin as a **sensor**,
both are floor-pinned, both attack the TING variance lever from opposite sides of an excursion, and
**neither adds net insulin** — they *re-time* the insulin the incumbent would give anyway:

- **Descent — withdraw earlier (idea 4, already built + shadowed).** When the Twin's calibrated
  30-min floor predicts a low, cut insulin (zero-temp) ahead of oref. Net insulin **down** ⇒ the
  harm direction is bounded (removing insulin cannot cause a high-tail low), so it is validatable
  from observed outcomes. Removes the over-correction low where the recoverable variance lives.

- **Rise — move the same insulin earlier?** *Tested and REJECTED as a Twin signal
  (`TWIN_RISE_LEAD.md`, added 2026-07-18).* The Twin's forecast `fc30` predicts real rises **worse**
  than oref's own `eventualBG` and even the naive BG-trend (FA 0.24 vs 0.14 vs 0.10, less lead) — a
  rise is directly visible in the trend, there is no hidden state for the filter to add. The Twin's
  value is **asymmetric: descent-only.** Rise-timing, if pursued at all, belongs to the incumbent's
  existing confirm-timing levers (early-dosing audit), not to KAIROS.

The synthesis, corrected by the rise gate: **the Twin re-times the incumbent's insulin in ONE
direction — gone earlier on the predicted way down.** The up-side is already handled as well as it
can be by the visible trend; the Twin adds nothing there. That still attacks the TING variance lever
where the recoverable variance actually lives (the post-meal over-correction low), keeps the low-tail
as a hard floor, and is validatable (harm direction bounded). It is not a controller optimising a
forecast; it is a validated **descent** sensor letting a proven reactive core give back insulin
earlier on the way down. One brick, honestly — the ceiling identification permits.

## Next bricks

1. **Bank the withdrawal shadow** (idea 4, live on the now-calibrated band) ~1–2 weeks → price the
   would-withhold signal against actual subsequent lows (the identifiable leg is already clear).
   **This is the one Twin brick that survived both gates.**
2. ~~Rise-retiming shadow~~ — **REJECTED** (`TWIN_RISE_LEAD.md`): the Twin is dominated by the trend
   on rises. Do not ship.
3. **Federation prior** for the Twin (population-init per-person params) — cold-start a new user's
   sensor on the manifold of all metabolisms. Pure sensor work; safe.
4. **Do NOT** re-open the forecast-MPC controller unless the insulin channel becomes identifiable —
   which needs an intervention the observational data cannot supply (e.g. a within-user micro-bolus
   probe protocol), not another model.
