# Descent lever — is the post-meal plateau safely dosable? Per-user: SOMETIMES

*2026-07-19. `dr1_plateau.py`. The under-recovery is real (foundation ff1); this asks whether there's
HEADROOM to dose it, or whether V6 is correctly restrained (ff2-style anchor). Plateau cycles = BG>140,
flat/falling, +90..210min post-onset. For each: V6 dose, IOB, minGuardBG (V6's low forecast), and the
GROUND-TRUTH forward nadir over the next 3h. Per-user JSON gitignored.*

## Result — headroom is per-user, and does NOT align with who has the problem
Pooled (3266 plateau cycles): V6 doses ~0 in 77%; of those only 29% have minGuard≥80 (V6 sees no low).
On those "safe-looking" dosable cells (n=721): forward nadir goes **<70 14%, <80 28%, stays ≥90 60%.**
So even where V6's own forecast said safe, dosing would feed a low ~1-in-7 times — NOT clean headroom.

**But it splits sharply by user, and it splits the two worst under-recoverers OPPOSITE ways:**
| user | under-recovery | plateau→low <70 (safe cells) | verdict |
|---|---|---|---|
| **A** | severe (plat 148) | **0%** (n=45) | genuinely STUCK → dosable |
| **H** | mild | **3%** (n=91) | dosable |
| **F** | severe (plat 149) | **22%** (n=117) | slow-DECLINE → dosing crashes it |
| **B** | mod | 23% (n=94) | trap |
| tim | mod | 16% (n=249) | marginal/trap |

## Interpretation — TWO kinds of plateau
1. **Genuinely stuck** (A, H): glucose sits at 148 and won't come down on its own (forward nadir stays
   100-109) → real headroom, V6 truly under-doses. The descent lever WOULD help.
2. **Slow decline / insulin already catching up** (F, B, tim): glucose sits at 148 but is drifting
   down and will reach target — or overshoot low (22% <70). V6 is CORRECTLY holding; dosing overshoots.

**V6's minGuard cannot separate these** (14% lows even where it looked safe). So a blanket "dose the
descent" helps A and crashes F. The lever is real but needs a BETTER low-discriminator than minGuard —
which is exactly where the KAIROS Twin `lo30` floor (validated at ⅓–½ minGuard's false-alarm rate) is
the natural candidate. That is the one genuine place the sensor programme and the dosing programme meet.

## Next (dr2, proposed) — TEST it, don't assume
Does `lo30` (or the Twin's forecast slope) separate STUCK from SLOW-DECLINE plateaus where minGuard
can't? If it flags F's 22%-low cells while clearing A's 0%-low cells, the descent lever becomes
Twin-gated and viable; if not, the plateau is a per-user trait, not a dosable moment.

---

## dr2 — the Twin lo30 does NOT gate the descent (decisive negative)
Replayed the calibrated Twin EnKF offline over all users (insulin from DB: finaldose+basal), captured
lo30 at every plateau cell (2508 cells, 14% actually go <70 in 3h). Head-to-head vs minGuard at
predicting the ground-truth forward low:

| forecast | AUC (low<70) | mean on go-low vs safe |
|---|---|---|
| minGuard | 0.49 (chance) | 93 vs 90 (sep −3) |
| **Twin lo30** | **0.38 (WORSE than chance)** | 139 vs **124** — WRONG sign |

lo30 is *higher* on the plateaus that actually crash — anti-predictive. At matched catch its false-alarm
is worse than minGuard's (81% vs 71% at 70% catch). Reason: lo30 was validated for FAST descents into a
low (idea-4); the PLATEAU lows are a different phenomenon — slow-decline / delayed absorption / activity,
driven by factors OUTSIDE the glucose-insulin model. Also confounded by BG level (higher plateaus crash
harder AND have higher lo30). Neither forecast can see the plateau low coming.

## Verdict — the descent lever is NOT safely gateable
The plateau lows aren't forecastable from the signals V6 (or the Twin) has. So you cannot tell at
decision time which plateau is STUCK (safe to dose, A-type) vs SLOW-DECLINE (will crash, F-type). A
blanket descent-dose crashes the F-type users, and no available gate prevents it. **Both meal-fix
candidates — confirm-ramp (ff2) and descent-dosing (dr2) — are closed by their safety anchors.**

The only surviving path is PER-USER: dose the plateau more ONLY for users whose plateaus demonstrably
never go low (A: 0% of 45 cells) — an auto-config trait, not a general algorithm change, and a narrow
population. The deeper lesson: V6's meal problems are real, but the dangerous outcome (the low) comes
from what the algorithm can't observe — so "dose more/less" levers can't be safely gated. That is the
identification wall at the SAFETY level, and it's why floors-first + per-user auto-config is the right
architecture: you can't out-model the unobservable.
