# Foundation firm-up — the confirm-crash fix is DEAD; the under-recovery is REAL

*2026-07-19. Four checks on existing data before shipping anything (ff1 recovery, ff2 crash-anchor,
ff3 all-7, ff4 per-user sim). Outcome: two of the four undercut the confirm-ramp fix, two confirm the
real problem. Per-user JSON gitignored; scripts committed.*

## ff1 — V6 post-meal recovery is genuinely poor (ABSOLUTE, no V1, no flash confound) ✓ REAL
Meal onsets on V6's own current data, follow the recovery. Median peak → recovery plateau (+2–3h):
F 174→**149** (57% still >140), A 174→**148** (61% >140), B 176→131 (41%), tim 171→125 (36%), H 157→132
(33%); C 161→119 and E 158→116 recover fine. **V6 genuinely parks post-meal glucose above the tight
range for hours** for F/A/B/tim/H — an unconfounded, absolute measurement. The under-recovery mechanism
is real and does NOT depend on the V1 before/after.

## ff3 — the −7.5 is NOT selection ✓ (magnitude fuzzy)
Clock-daytime proxy, transition window, all 7. H (an excluded "best performer") regresses **−11.8**,
same as the others; including H the median holds (5-user −10.8 → 6-user −11.1). So H does not dilute it.
E has no V1 daytime data (unmeasurable). Caveat: the proxy disagrees with telemetry per-user (tim +0.3
clock vs −8 telemetry) → magnitude is proxy-sensitive (−7.5 to −11), but the finding survives H.

## ff2 — the confirm shot does NOT cause the crashes ✗ FIX PREMISE FAILS
At MATCHED context (low IOB<1.5, modest rise): **SHOT crashes 18% vs NO-SHOT 18% (Δ 0pp); deep 7.7 vs
7.9%.** The crashes are a property of the context (low-IOB modest-rise cycles tend to a low regardless),
NOT caused by the shot. The "22% confirm-shot crash" is context, not causation. So ramping the shot
won't prevent them — the semi-closed replay's "⅓ crashes prevented" was a MODEL ARTIFACT (fix delivers
less → BG_fix≥BG_actual mechanically raises the nadir), attributing to insulin a low that isn't insulin's.

## ff4 — per-user + winsorised ISF, the fix does nothing for crashes ✗
tim's ISF is genuine U200 sensitivity (~117–151, reason=6.5 mmol; not an 18× bug) but 3× the others +
outliers to 623 → pooling is invalid. Capping ISF at 250 and taking the MEDIAN across users: crash
**18→18% (Δ 0)**, deep **4→4% (Δ 0)**, high>160 **15→21% (+6pp)**. The pooled headline (22→15) was
tim/C-weighted. Per typical user the fix buys **no crash benefit and only a high-plateau cost.**

## Verdict
**Do NOT ship the confirm IOB-ramp.** Its premise (the shot causes low-IOB crashes) fails a matched-
context anchor, and per-user it adds highs for zero crash benefit. The genuine, firmed-up problem is the
OPPOSITE direction: V6 **under-doses the descent** → post-meal plateau at 145–150 (ff1). The real lever
is to sustain corrections THROUGH the high-IOB post-meal window — which the confirm-ramp pulls against.
The confirm-crash chase was a non-causal correlation; the firm-up caught it before it shipped.
