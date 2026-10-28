#!/usr/bin/env bash
# Build the Boost engine harness JAR by compiling the REAL engine sources (from plugins/aps) + minimal
# shims + Harness.kt. Single source of truth: when an engine .kt changes, rebuilding picks it up.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
SRC="$REPO/plugins/aps/src/main/kotlin/app/aaps/plugins/aps"
JSON="$(find "$HOME/.gradle/caches" -name 'json-*.jar' 2>/dev/null | grep -iE '/org\.json/|/json-[0-9]' | head -1)"
[ -z "$JSON" ] && { echo "ERROR: org.json jar not found in ~/.gradle/caches"; exit 1; }

echo "[harness] org.json = $JSON"
echo "[harness] compiling real engine sources + shims + Harness.kt ..."
kotlinc \
  "$SRC/openAPSBoostTwin/TwinModel.kt" \
  "$SRC/openAPSBoostTwin/TwinEnkf.kt" \
  "$SRC/openAPSBoostTwin/TwinShadow.kt" \
  "$SRC/openAPSBoostTwin/AnticipationBackoutShadow.kt" \
  "$SRC/openAPSBoostTwin/TwinWithdrawalShadow.kt" \
  "$HERE/shims/HR.kt" \
  "$HERE/shims/Logging.kt" \
  "$SRC/openAPSBoost/SleepStateDetector.kt" \
  "$HERE/Harness.kt" \
  -cp "$JSON" -include-runtime -d "$HERE/boost-harness.jar"

# stash the json jar path for the runner
echo "$JSON" > "$HERE/.jsonjar"
echo "[harness] built $HERE/boost-harness.jar"
