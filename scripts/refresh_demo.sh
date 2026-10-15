#!/usr/bin/env bash
# One-command demo refresh (run before judging / recording / submission):
# SIMULATED data ending now -> BigQuery -> retrain BigQuery ML forecast -> regenerate demo diagnoses -> verify
# Usage:  ./scripts/refresh_demo.sh            (refresh only)
#         ./scripts/refresh_demo.sh --no-deploy   (local test only; live site would then be out of sync)
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-kaarigar-510716}"
export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
export KAARIGAR_MODEL="${KAARIGAR_MODEL:-gemini-2.5-flash}"

echo "== 1/5 Simulate 14 days ending now"
python simulator/simulate.py

echo "== 2/5 Load BigQuery"
bq load --source_format=CSV --skip_leading_rows=1 --replace \
  "$GOOGLE_CLOUD_PROJECT:kaarigar.sensor_readings" data/sim/sensor_readings.csv \
  ts:DATETIME,machine_id:STRING,shift:STRING,status:STRING,spindle_rpm:INT64,spindle_temp_c:FLOAT64,vibration_mm_s:FLOAT64,load_pct:FLOAT64,part_count:INT64,simulated:BOOL

echo "== 3/5 Retrain BigQuery ML forecast"
bq query --use_legacy_sql=false "CREATE OR REPLACE MODEL \`$GOOGLE_CLOUD_PROJECT.kaarigar.vibration_forecast\` OPTIONS(model_type='ARIMA_PLUS', time_series_timestamp_col='hour', time_series_data_col='vib', time_series_id_col='machine_id', data_frequency='HOURLY', horizon=48, auto_arima=TRUE) AS SELECT TIMESTAMP_TRUNC(TIMESTAMP(ts), HOUR) AS hour, machine_id, AVG(vibration_mm_s) AS vib FROM \`$GOOGLE_CLOUD_PROJECT.kaarigar.sensor_readings\` GROUP BY hour, machine_id"

echo "== 4/5 Regenerate demo diagnoses"
python -c "
import time
from pathlib import Path
from agents.action import get_diagnosis, DIAG_CACHE
for p in ['metal_nut_scratch_0', 'metal_nut_color_0', 'real_bar_rust_0', 'real_cover_bad_0']:
    (DIAG_CACHE / f'{p}.json').unlink(missing_ok=True)
    r = get_diagnosis(p)
    fc = (r['evidence_used'].get('forecast') or {}).get('hours_to_zone_d')
    print(f'  {p}: conf {r[\"report\"][\"confidence\"]} | forecast {fc}')
    time.sleep(5)
"

echo "== 5/5 Verify"
python -m agents.tools.forecast

if [[ "${1:-}" != "--no-deploy" ]]; then
  echo "== Deploying to Cloud Run (cached diagnoses must match the fresh data)"
  gcloud run deploy kaarigar --source . --region asia-south1 --allow-unauthenticated \
    --memory 1Gi --cpu 1 --timeout 300 --max-instances 3 --min-instances 1 --cpu-boost --session-affinity \
    --set-env-vars GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=TRUE,KAARIGAR_MODEL=gemini-2.5-flash,KAARIGAR_PAIRS_DIR=demo_parts,KAARIGAR_STORE=firestore,KAARIGAR_AGENT_ENGINE_ID=4583600368285384704
fi
echo "== Done"
