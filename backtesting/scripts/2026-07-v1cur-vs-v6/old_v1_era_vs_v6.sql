-- Old V1 (pre-ML, running LIVE, Feb–Apr) vs V6 (summer) — DIRECT actual daytime outcomes, per user.
-- "Old V1" = variant='v1' before the ML/V6 line became available (~2026-05-01). Pure old V1 exists for
-- A, B, E, F, tim (C/D/H joined the shadow later, no pre-ML data). Daytime = 07:00–22:00 Europe/London
-- (meal-dosing-active, excludes night mode). SEASON-CONFOUNDED (old V1 spring vs V6 summer) — read with
-- the within-cycle counterfactual (whole_meal_replay.py), which removes season and shows V1's dosing
-- POLICY does not beat V6.
with m as (
  select user_id,
    case when variant='v1' and ts_epoch < extract(epoch from (timestamp '2026-05-01 00:00' at time zone 'Europe/London'))
           then 'old_V1(preML)'
         when variant='boost-other' then 'V6' end era,
    cgm_mgdl g
  from boost_decisions
  where cgm_mgdl is not null
    and extract(hour from (to_timestamp(ts_epoch) at time zone 'Europe/London')) between 7 and 22
)
select user_id, era, count(*) n,
  round(avg(g)) mean_bg,
  round(100.0*avg((g>=63 and g<=140)::int),1) ting,
  round(100.0*avg((g>=70 and g<=180)::int),1) tir,
  round(100.0*avg((g>140)::int),1) pct_over140,
  round(100.0*avg((g<70)::int),1) tbr70
from m where era is not null and user_id in ('tim','A','B','E','F')
group by user_id, era order by user_id, era;

-- RESULT (2026-07-19):
--  user  era             TING   TIR   >140   TBR
--  A     old_V1(preML)   56.1   82.9  43.5   1.2      A   V6  44.1  73.0  55.4  1.1
--  B     old_V1(preML)   67.9   83.6  30.9   3.1      B   V6  56.8  75.7  42.2  2.0
--  E     old_V1(preML)   77.1   91.2  22.6   2.2      E   V6  84.4  97.5  15.1  1.4
--  F     old_V1(preML)   45.4   63.0  52.6   4.3      F   V6  48.0  77.9  51.3  2.4
--  tim   old_V1(preML)   67.1   85.1  31.0   2.9      tim V6  61.1  81.7  37.0  3.4
-- Old V1 higher TING for A(+12) B(+11) tim(+6) but MORE lows (B/E/F TBR up) + worse TIR for F (ran high);
-- V6 safer (lower TBR, better TIR), slightly less tight-band TING. E/F better on V6. = tighter-but-more-hypo
-- old V1 vs safer V6 — the aggression V6's brake tames. Season-confounded; policy-counterfactual says V1 ≈/< V6.
