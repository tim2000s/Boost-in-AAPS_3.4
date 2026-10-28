# Boost research papers

What was investigated during the development of the V6 and V7 generations of the Boost algorithm,
what the investigations found, and what was built or abandoned as a result. Each document takes one
topic through abstract, introduction, methods, results and discussion, and names the analysis folder
its figures come from.

Several documents report nulls, and they are written at the same length as the positive results,
because the point of the record is to stop questions being asked twice and that only works if the
negative answers are as findable as the positive ones.

Rendered PDFs of these papers are published in the separate research-papers repository, alongside
the simulator series. This folder holds the sources.


### The papers

**[00 The programme](00_the_programme.md)**. The frame the rest work under. The identification constraint and how it divides questions into those the record can answer and those it can only price, the three conditions imposed on every effect size, and the separation between what is learned offline and what the dose path consumes.

**[01 Dose timing and dose size at meals](01_dose_timing_and_sizing.md)**. Whether insulin moved earlier within a meal differs from insulin added to one. Movement is harm-neutral; addition carries about fifteen percentage points of additional lows. Also the commitment gate, and a retired acceleration detector at 98 per cent recall and 15 per cent precision.

**[02 The committed state and subsequent hypoglycaemia](02_the_confirm_state.md)**. Three attempts to predict which commitments end in hypoglycaemia, all at chance, and a matched-control comparison of the post-commitment low rate itself. Against controls matched within participant on glucose, insulin on board and hour of day, the rate below 70 mg/dL is 22.8 per cent against 14.0.

**[03 Attribution of time outside range to proximate mechanism](03_where_the_loss_comes_from.md)**. Every episode outside range assigned to the mechanism that started it, with a layer scoring how foreseeable each was forty five minutes earlier. Includes the effect of taking a rescue antecedent from a forward-looking window rather than a backward-looking one.

**[04 The composed brake, the caps and the floor beneath them](04_restraint.md)**. A brake ranked first among mechanisms behind time above range, priced by what followed each suppressed cycle. Under a strict definition the set is 675 minutes over six weeks, of which 3 per cent was recoverable and 13 per cent preceded a low that did not occur. One participant contributes half of it.

**[05 A per-person state estimator as forecaster and as controller substrate](05_prediction_and_the_twin.md)**. An ensemble Kalman filter fitted per person, assessed as a forecaster, as a detector of falls and rises, and as a controller substrate. Insulin sensitivity varies eightfold inside the filter without changing its accuracy, which is why the planner it feeds is degenerate.

**[06 Rebound after treated hypoglycaemia, and where restraint has to be applied](06_post_rescue.md)**. Why demoting a response tier does not restrain the delivered quantity, and the graduated scale on the final microbolus that does. Priced at 34 per cent of removed insulin sitting before a low, with a leave-one-participant-out floor of 27.

**[07 Activity, hypoglycaemia, and exercise taken soon after a meal](07_exercise_and_activity.md)**. The dose-response between recent steps and forward hypoglycaemia, and whether it transfers between people. Also the insulin carried at the onset of exercise taken soon after a meal, where two constructions of the same question disagree in direction and the question is left open.

**[08 Overnight performance, the night gate, and sleep detection](08_overnight_and_sleep.md)**. Where the advantage over the preceding generation sits in the day, what the night gate suppresses, and whether a learned bedtime carries information a clock does not.

**[09 Insulin sensitivity estimation and the shape of absorption](09_sensitivity_and_absorption.md)**. Two estimators of insulin sensitivity, one computed from the algorithm's own residuals and one anchored to consumption, and a proposed equivalence between the shipped ratio and a separate overlay tested at clinical tolerance. Includes the insulin-context contrast that underpins most of the restraint in the controller.

**[10 Anticipation of meals and exercise, and retractable action](10_anticipation.md)**. Where habitual timing transfers between people and where it does not, exercise and meals running in opposite directions, and the state machine that makes a 0.63-precision detector safe to act on by making the action retractable.

**[11 Per-participant configuration, derived offline and adjusted online](11_per_user_configuration.md)**. A per-participant configuration derived once from a person's history, against four controllers that adjust the same parameters online. All four fail in both directions and for both caps and sliders, with revert rate as the diagnostic.

**[12 Sensor cadence, smoothing, and the ingestion path](12_the_cgm_signal.md)**. What a one-minute sensor carries against a five-minute one, measured by variogram across two real eras. Also the smoothing filter and its tuning, and the ingestion path that reduces any feed to a five-minute grid before the algorithm sees it.

**[13 Cohort outcomes across a change of algorithm generation](13_cohort_outcomes.md)**. Three approaches to the same migration comparison, and the two measurement choices that change the answer: establishing era membership from telemetry rather than dates, and taking glucose from the sensor series rather than from decision cycles.

**[14 Simulator fidelity and the analysis harness](14_methods_and_tooling.md)**. A published simulator assessed against signatures measured on real data and graded across six levels, and a harness that runs the shipped engine components from analysis code. Includes what happens to an evaluation that drops the runs in which the virtual participant died.

**[15 The two pre-trained models on the dose path](15_learned_components_in_the_dose_path.md)**. The two gradient-boosted models whose output reaches the dose: how the model class, feature count and deployment format were chosen, what the pre-deployment validation showed, and a field audit against the cohort now running them. Locates a top-decile calibration failure in a lag feature imputed one way in training and another at inference.

**[16 Short-horizon glucose forecasting and its feature set](16_forecasting_and_the_information_ceiling.md)**. What each block of available features adds to a thirty-minute glucose forecast, where the residual error concentrates, and what dose response the resulting model implies.

**[17 Negative results in prediction and detection](17_what_could_not_be_learned.md)**. Four searches for a signal distinguishing the dosing decisions that go wrong, all returning chance, together with a fourteen-point improvement that was participant leakage and two transfer tests that locate where personalisation belongs.

### Citations and provenance, Boost

Each paper names the analysis folder its figures come from, in the form
`backtesting/scripts/2026-07-residency/` and similar. Those folders hold the scripts, the raw
reports and the intermediate tables, and they live in a separate private repository alongside the
algorithm source. They are not reproduced here.

A reader of this repository therefore cannot follow a citation through to the code, and that is a
real limitation rather than an oversight. The citations are given so that anyone with access to the
analysis repository can find the exact script that produced a figure and re-run it, and so that the
provenance of every number in this series is recorded even where it cannot be followed from here.

The underlying data cannot be published in any case. It is the continuous glucose and insulin record
of a small number of identifiable people who consented to their data being used for this work and
not to its release.
