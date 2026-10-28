# Acute-activity insulin withdrawal — spec + step-by-step replay across all V6 users

*2026-07-19. The dose-then-walk lows are activity-driven (forward steps AUC 0.62 vs glucose+insulin
0.55; `2026-07-v6-steps/`) and V6 detects-but-doesn't-act (wouldDeltaIsfPct is shadow-only). Spec'd the
withdrawal lever (`ACTIVITY_WITHDRAWAL_SPEC.md`) and priced it meal-by-meal on all 8 V6 users, same
semi-closed-loop insulin-perturbation method as the mealtime work (`act_replay.py`, insulin-REDUCING so
BG_lever ≥ BG_actual — can raise a nadir, never create a low). ISF winsorised (250), per-user median.*

## Verdict: MARGINAL. Reactive ≈ break-even; anticipation over-withdraws. Only defensible per-user gated.

### Reactive (trigger = steps_5m ≥ per-user p75 + IOB ≥ 0.5U, zero-temp + SMB-suppress the walk)
- **837 activity+IOB bouts; 220 went low (<70), 68 deep (<54).**
- **Prevented 41/220 lows (19% pooled, 16% per-user median); 15/68 deep (22%).**
- **Cost: 39 new highs (>180), only 5 of them bad (>220). Prevented:caused ≈ 41:39 ≈ 1:1.**
- Withheld only **0.25–0.73 U/bout** — because **V6 already reactively zero-temps during the walk**, so
  the lever removes little the loop hadn't. Nadir lift on go-low bouts: median ~6–9 mg/dL (C 15, big).

### Why so weak — the mechanical ceiling
The lever can only remove **future basal** (small, and largely already cut). It cannot touch the
**committed meal-bolus IOB** that drives most walk-lows. So it saves the minority of walk-lows that are
basal/late-IOB-driven and does nothing for the bolus-driven majority.

### Anticipation makes it WORSE, not better (LEAD sensitivity ≈ the habit-prior trigger)
| trigger | lows prevented | deep prevented | highs caused | prevented:caused |
|---|---|---|---|---|
| reactive (0m)   | 41/220 (19%) | 15/68 (22%) | 39  | **1.05** |
| 30 min early    | 111/220 (50%) | 37/68 (54%) | 142 | 0.78 |
| 60 min early    | 160/220 (73%) | 59/68 (87%) | 228 | 0.70 |
Earlier/broader withdrawal prevents more lows but causes **even more highs** — because only **26%**
(220/837) of activity+IOB bouts actually go low, so blanket withdrawal over-treats the 74% that were
fine. The steps predictor (AUC 0.62) can't separate go-low from fine bouts sharply enough. Same wall
the confirm-crash chase hit: the event is not cleanly predictable, so a blunt trigger over-fires.

### The one place it survives: PER-USER gating (this is the auto-config story)
Reactive ratio splits cleanly by user — auto-config would enable only where it helps:
| user | bouts | went-low | prevented | highs caused | ratio | gate |
|---|---|---|---|---|---|---|
| B | 130 | 31 | 12 | 6 | **2.0** | ON |
| F | 92 | 33 | 6 | 4 | 1.5 | ON |
| E | 71 | 15 | 4 | 3 | 1.3 | ON |
| C | 30 | 14 | 3 | 3 | 1.0 (lift 15) | ON |
| tim | 278 | 92 | 13 | 11 | 1.2 | marginal |
| A | 126 | 26 | 3 | 3 | 1.0 | marginal |
| **H** | 91 | **2** | 0 | **8** | pure cost | **OFF** |
| **D** | 19 | 7 | 0 | 1 | 0% | **OFF** |
H barely walks-low (2/91) — the lever is all cost for H. D likewise. The per-user walk-low rate is the
gate: enable where banked go-low rate is material AND the personal prevented:caused ratio ≥ ~1.3.

## Recommendation
1. **Do NOT ship blanket, and do NOT build the anticipatory arm** — earlier withdrawal loses (worse ratio).
2. The **reactive, per-user-gated** version is the only defensible form: modest, safe-direction, and it
   clears asymmetric cost only where a user actually walks-low (prevents 15 deep<54 pooled at just 5 bad
   highs). Deploy **shadow-first exactly like the plateau nudge** — log `activityWithdraw=trig,wouldWith
   holdU,steps5m,iob,bg;`, bank each user's prevented:caused, enable per-user via auto-config only where
   the banked walk-low rate is material and the ratio favours it. Auto-config would put H and D OFF.
3. Honest ceiling: even gated, this prevents ~1 in 5 walk-lows reactively — it trims the tail, it is not
   the meal-window TING fix (that remains the descent under-recovery / plateau-nudge line).

Scripts: `act_replay.py` (reactive), `act_replay_lead.py` (anticipation sensitivity). Per-user JSON
gitignored (intermediates). Method + fidelity: same as `2026-07-v6-sim/`.
