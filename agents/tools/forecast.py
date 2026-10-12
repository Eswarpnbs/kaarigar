"""
Predict: BigQuery ML ARIMA_PLUS vibration forecast + time-to-limit (computed in code, not by the LLM).
ISO 10816-3 group 2 (rigid) velocity zones: A < 1.4, B < 2.8, C < 4.5, D >= 4.5 mm/s.
Test:  python -m agents.tools.forecast M1
"""
import os
import sys
import time

from google.cloud import bigquery

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "kaarigar-510716")
MODEL = f"`{PROJECT}.kaarigar.vibration_forecast`"
TABLE = f"`{PROJECT}.kaarigar.sensor_readings`"
ZONES = [(1.4, "A", "good"), (2.8, "B", "acceptable"), (4.5, "C", "restricted operation"),
         (float("inf"), "D", "damage likely")]
LIMIT_D = 4.5
_cache: dict = {}


def zone(v: float):
    for lim, z, meaning in ZONES:
        if v < lim:
            return z, meaning


def forecast_machine(machine_id: str, horizon: int = 24) -> dict:
    """BigQuery ML forecast for one machine and the hours until ISO zone D (expected / earliest / latest)."""
    key = (machine_id, horizon)
    if key in _cache and time.time() - _cache[key][0] < 300:
        return _cache[key][1]
    c = bigquery.Client(project=PROJECT)
    p = [bigquery.ScalarQueryParameter("m", "STRING", machine_id)]
    last = list(c.query(f"""
        SELECT TIMESTAMP_TRUNC(TIMESTAMP(ts), HOUR) AS hour, AVG(vibration_mm_s) AS vib
        FROM {TABLE} WHERE machine_id = @m GROUP BY hour ORDER BY hour DESC LIMIT 1""",
        job_config=bigquery.QueryJobConfig(query_parameters=p)).result())
    rows = list(c.query(f"""
        SELECT forecast_timestamp AS t, forecast_value AS v,
               prediction_interval_lower_bound AS lo, prediction_interval_upper_bound AS hi
        FROM ML.FORECAST(MODEL {MODEL}, STRUCT({int(horizon)} AS horizon, 0.9 AS confidence_level))
        WHERE machine_id = @m ORDER BY t""",
        job_config=bigquery.QueryJobConfig(query_parameters=p)).result())
    if not rows or not last:
        return {"status": "error", "message": f"No forecast available for {machine_id}"}

    t0, v0 = last[0]["hour"], float(last[0]["vib"])

    def first_cross(field: str):
        for r in rows:
            if float(r[field]) >= LIMIT_D:
                return round((r["t"] - t0).total_seconds() / 3600, 1)
        return None  # not within the forecast horizon

    z, meaning = zone(v0)
    hours = ({"expected": 0, "earliest": 0, "latest": 0} if v0 >= LIMIT_D else
             {"expected": first_cross("v"), "earliest": first_cross("hi"), "latest": first_cross("lo")})
    res = {
        "status": "success", "machine_id": machine_id, "model": "BigQuery ML ARIMA_PLUS (hourly)",
        "latest_hour": t0.isoformat(), "latest_vibration": round(v0, 2),
        "zone": z, "zone_meaning": meaning,
        "limit": {"zone_d_mm_s": LIMIT_D, "standard": "ISO 10816-3 group 2, rigid mounting (reference limits; shop can set its own)"},
        "hours_to_zone_d": hours, "horizon_hours": horizon,
        "forecast": [{"t": r["t"].isoformat(), "v": round(float(r["v"]), 2),
                      "lo": round(float(r["lo"]), 2), "hi": round(float(r["hi"]), 2)} for r in rows],
        "data_note": "SIMULATED sensor data; times are relative to the latest reading",
    }
    _cache[key] = (time.time(), res)
    return res


if __name__ == "__main__":
    for m in (sys.argv[1:] or ["M1", "M2"]):
        f = forecast_machine(m)
        if f["status"] != "success":
            print(m, f); continue
        print(f"{m}: now {f['latest_vibration']} mm/s (zone {f['zone']}, {f['zone_meaning']}) | "
              f"hours to zone D: {f['hours_to_zone_d']}")