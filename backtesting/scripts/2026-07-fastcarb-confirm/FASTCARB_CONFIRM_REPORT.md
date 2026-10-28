# Fast-carb CONFIRMED-shot crash analysis

_Data: oref.boost_decisions, V6, span 2026-05-07→2026-07-10. From Tim's 48h review (3 fast-carb rise-then-crash events). `fastcarb_confirm_crash.py`._

## Confirmed: CONFIRMED shots crash a lot (per-user)

| user | shots | crash% (nadir<70 in 3h) |
|---|---|---|
| tim | 193 | 29% |
| A | 153 | 8% |
| B | 179 | 19% |
| C | 136 | 21% |
| D | 88 | 39% |
| E | 11 | 18% |
| F | 116 | 9% |
| H | 27 | 11% |

Tim 29%, D 39% — a real over-treatment rate, not a bad day. So the 48h review generalises.

## But my hypothesis (trim when DECELERATING + modest) does NOT generalise

- CRASH events (n=181): only **10%** fired decelerating+modest.

- NEEDED events (n=393): 3%.

- The trim guard flags 77 shots, crash:needed = **18:12** — a poor ratio and it catches only ~10% of crashes. **Do NOT build the decelerating guard** — Tim's 3 events happened to be decelerating, but most crashes are not.

## The real discriminator is confirm-context (BG + IOB), and it's actionable

- CRASH shots fire at a LOWER current BG (**120** vs needed 137) and LOWER IOB (**0.6** vs needed 1.2).

- Reading: crashes come from **confirming a meal shot EAGERLY on a modest rise at a still-low BG with little IOB** — the 'meal' turns out small (crash peaks 143 vs needed 186) and self-limits, so the ~1U shot overshoots → crash to ~58. It is NOT 'late confirm on a big fast carb'; it's eager confirm before the rise proves itself.

- BUT the separation (120 vs 137, 0.6 vs 1.2) is modest/overlapping — a hard guard would be imperfect. Needs a priced confirm_bg×IOB threshold sweep (or conditioning the SHOT SIZE on the confirm context) before any change, and it interacts with the existing confirm-gate/age-gate.

## Caveat
Counterfactual BG under a trimmed/delayed shot is unsimulable — this prices context, it does not prove a non-crash. There's a real tension with the early-dosing lever (dose early to catch real meals) — so any confirm-context guard must be shadow-logged + live-checked, not shipped blind.
