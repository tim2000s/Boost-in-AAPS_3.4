#!/usr/bin/env bash
# Wait for the machine to have capacity, then run the meal-size study on half the cores.
#
# Half the cores, and niced, so that this yields to whatever the machine is already doing.
# The gate is the one-minute load average leaving at least the requested cores free, held over
# several consecutive checks so that a momentary dip does not start a long run.
set -uo pipefail

D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NCPU=$(sysctl -n hw.ncpu)
WORKERS=${WORKERS:-$((NCPU / 2))}
NEED_FREE=${NEED_FREE:-$WORKERS}       # cores that must look idle before starting
CONSEC=${CONSEC:-3}                    # consecutive passing checks required
INTERVAL=${INTERVAL:-60}               # seconds between checks
MAXWAIT=${MAXWAIT:-21600}              # give up waiting after six hours and run anyway
LOG="$D/out/run.log"

mkdir -p "$D/out"
exec >>"$LOG" 2>&1
echo "=== $(date '+%F %T') start; ${NCPU} cores, ${WORKERS} workers, need ${NEED_FREE} free ==="

waited=0; pass=0
while (( pass < CONSEC )); do
  load=$(sysctl -n vm.loadavg | awk '{print $2}')
  free=$(echo "$NCPU $load" | awk '{printf "%.1f", $1-$2}')
  if awk -v f="$free" -v n="$NEED_FREE" 'BEGIN{exit !(f>=n)}'; then
    pass=$((pass+1)); echo "$(date '+%T') load ${load}, ~${free} cores free, pass ${pass}/${CONSEC}"
  else
    if (( pass > 0 )); then echo "$(date '+%T') load ${load}, back to busy, resetting"; fi
    pass=0
  fi
  (( pass >= CONSEC )) && break
  if (( waited >= MAXWAIT )); then echo "$(date '+%T') waited ${waited}s, proceeding anyway"; break; fi
  sleep "$INTERVAL"; waited=$((waited+INTERVAL))
done

echo "=== $(date '+%T') running ==="
run() { echo "--- $* ---"; nice -n 10 "$@" || { echo "FAILED: $*"; return 1; }; }

run python3 "$D/extract_meals.py" --workers "$WORKERS" --out "$D/out" || exit 1
for study in Loop ReplaceBG; do
  [ -f "$D/out/meals_${study}.parquet" ] || { echo "no parquet for $study, skipping"; continue; }
  run python3 "$D/size_readability.py"    --study "$study" --workers "$WORKERS" --data "$D/out"
  run python3 "$D/slope_heterogeneity.py" --study "$study" --data "$D/out"
  run python3 "$D/report_tables.py"       --study "$study" --data "$D/out" > "$D/out/TABLES_${study}.md"
done
echo "=== $(date '+%T') done ==="
