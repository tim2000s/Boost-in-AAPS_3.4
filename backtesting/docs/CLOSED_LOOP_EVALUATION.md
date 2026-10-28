# Evaluating a closed-loop system in different contexts

Written from what worked and what failed while answering one question, sampling cadence, end to
end. Every rule below is here because breaking it produced a wrong answer first.

## The shape of it

Four layers, separable, each with its own failure mode.

    controller   the real engine, unmodified
    context      everything you vary, declared per arm
    substrate    where glucose comes from, and how it responds
    verdict      the gate, the null, and the validity monitor

## 1. Controller: run the shipped code, never a port

The Boost V5 package imports only `kotlin.math` and the Dagger annotations. It compiles and
runs on a desktop JVM with two annotation stubs, and `DetermineBasalBoostV5.decide()` is a pure
function over inputs and prior state. Wrapping it as a per-cycle stdin/stdout server
(`2026-07-cadence-sim/src/EngineServer.kt`) lets any driver in any language run the genuine
engine with state carried between cycles.

This retires a blocker that had stood since the in-silico harness was written, which said a
Python port would first have to reproduce logged doses within tolerance before any A/B could be
trusted. There is no port, so there is nothing to validate. Any engine generation can be
wrapped the same way, which makes V1 against V6 against V7 a matter of starting a different
server rather than of maintaining three ports.

The rule: if the controller can be run rather than reimplemented, run it. A port is a second
system that must be proved equal to the first, and the proof costs more than the port.

## 2. Context: declare every parameter per arm, and check which ones bind

The context is everything the study varies or holds: sensor cadence, sensor noise, quantisation,
dropouts, SMB interval, maximum IOB, pump granularity, auto-config values, meal announcement,
exercise.

The failure to avoid is subtle and cost a whole run here. A shared parameter can bind
asymmetrically. A three-minute minimum interval between microboluses is not binding at a
five-minute cadence, because cycles are already further apart than that, but it is binding at a
one-minute cadence, where it throttles the loop to every third cycle. Applying the same number
to both arms silently did the equalising, and the study reported no difference where the honest
comparison showed eight per cent.

The rule: for every parameter, ask whether it binds equally in both arms. If it does not, it is
part of the treatment and must be declared per arm. State explicitly which contexts are being
compared, in the form "the user changes X and leaves Y alone", because that is the decision a
reader will make.

## 3. Substrate: three options, each with a validity domain

**Real-trace counterfactual.** Take the real record, run the controller, apply only the
difference in insulin through an action curve. Retains all real variability, including the
roughness, the unannounced meals and the sensor artefacts that synthetic patients lack.

Its limit is that a linear perturbation carries no counter-regulation, so it accumulates
without bound. Applied continuously over 9.5 days it drove the counterfactual to a mean of 36
mg/dl on 0.75 U of insulin, which is a statement about the model and not about the treatment.
The fix is to cut the replay into independent episodes of about one insulin duration, each
starting fresh from the real trace. Valid for small perturbations over short horizons.

**Virtual patient.** simglucose and the UVA/Padova cohort. Arbitrary perturbations, arbitrary
duration, real feedback, no identification problem.

Its limit is fidelity, and the limit is question-specific. For the cadence question the
simulated feed had six times too little variance at a one-minute lag, three times too little at
thirty minutes, a roughness exponent of 1.64 against 1.35 in reality, and no excursion below
139 mg/dl in five days. A study of short-timescale behaviour on that substrate would have been
an artefact.

**Hybrid.** A virtual patient whose disturbance inputs are calibrated so its output matches the
real signal statistics. Not built here. It is the only route to large perturbations over long
horizons with credible short-lag behaviour, and it is the obvious next investment if that class
of question keeps arising.

Choose by the question:

| Question | Substrate |
|---|---|
| Small change, short horizon, realism matters | real-trace counterfactual, episodic |
| Large change, long horizon, safety screening | virtual patient, with a gate |
| Anything turning on short-timescale structure | neither, until the hybrid exists |
| Does the engine decide differently given identical state | open-loop replay, no substrate needed |

## 4. Verdict: a gate, a null, and a monitor

**The gate is question-specific.** A general fidelity suite tells you the simulator is broadly
reasonable. It does not tell you whether it is adequate for the thing your study turns on.
Declare the signature the question depends on and test that. Cadence turns on short-lag
structure, so the gate was the variogram at one to thirty minutes. A hypoglycaemia study would
gate on the low tail, which the same simulator would also fail, for a different reason.

**The null comes from a duplicate arm.** Run the same context twice, differing only in seed or
in unit. Any treatment effect must exceed that. In the four-sensor design this is what the
second sensor of each cadence buys, and it is why that design measures its own power rather
than needing one estimated in advance.

**The monitor invalidates rather than averages.** Report perturbation size against the range
where the model holds. Exclude episodes that leave a plausible physiological range and say how
many: ten of thirty-seven here, and the count rose with the perturbation, which is itself a
signal that the model was being pushed.

## 5. What this cannot do

None of it produces a counterfactual outcome for a real person under a policy change. That is
the identification wall, and it does not move. What the layers above give is a way to ask
narrower questions honestly: whether the engine decides differently given identical state, how
much of a rate effect survives feedback, whether behaviour is pathological under a stress the
real data never contained.

A dosing change still needs the two-test bar and a pre-registered within-user trial. This
framework tells you which changes are worth taking that far.

## 6. Worked example

The cadence question, run through all four layers, gave three numbers that are all correct and
answer different questions:

    51%  more insulin, open loop, IOB frozen           the arithmetic of a per-cycle dose
     8%  more insulin, closed loop, natural intervals   what feedback leaves of it
     1%  more insulin, closed loop, matched intervals   what the throttle removes

Reporting any one alone would have misled. The open-loop figure is what the engine asks for,
the middle figure is what a user would experience, and the last is a measurement of the
limiter rather than of the cadence.
