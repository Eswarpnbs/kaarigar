"""
Predict: BigQuery ML ARIMA_PLUS vibration forecast + time-to-limit (computed in code, not by the LLM).
ISO 10816-3 group 2 (rigid) velocity zones: A < 1.4, B < 2.8, C < 4.5, D >= 4.5 mm/s.
Test:  python -m agents.tools.forecast
"""
import os
import time

from google.cloud import bigquery

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "kaarigar-510716")
MODEL = f"`{PROJECT}.kaarigar.vibration_forecast`"
TABLE = f"`{PROJECT}.kaarigar.sensor_readings`"
ZONES = [(1.4, "A", "good"), (2.8, "B", "acceptable"), (4.5, "C", "restricted operation"),
         (float("inf"), "D", "damage likely")]
LIMIT_D = 4.5
STANDARD = "ISO 10816-3 group 2, rigid mounting (reference limits; shop can set its own)"
_cache: dict = {}


def zone(v: float):
    for lim, z, meaning in ZONES:
        if v < lim:
            return z, meaning


def _summarize(machine_id, t0, v0, rows, horizon):
    def first_cross(field):
        for r in rows:
            if r[field] >= LIMIT_D:
                return round((r["t"] - t0).total_seconds() / 3600, 1)
        return None
    z, meaning = zone(v0)
    hours = ({"expected": 0, "earliest": 0, "latest": 0} if v0 >= LIMIT_D else
             {"expected": first_cross("v"), "earliest": first_cross("hi"), "latest": first_cross("lo")})
    return {
        "status": "success", "machine_id": machine_id, "model": "BigQuery ML ARIMA_PLUS (hourly)",
        "latest_hour": t0.isoformat(), "latest_vibration": round(v0, 2),
        "zone": z, "zone_meaning": meaning, "limit": {"zone_d_mm_s": LIMIT_D, "standard": STANDARD},
        "hours_to_zone_d": hours, "horizon_hours": horizon,
        "forecast": [{"t": r["t"].isoformat(), "v": round(r["v"], 2), "lo": round(r["lo"], 2),
                      "hi": round(r["hi"], 2)} for r in rows],
        "data_note": "SIMULATED sensor data; times are relative to the latest reading",
    }


def forecast_all(horizon: int = 24) -> dict:
    """One query for latest readings + one ML.FORECAST for all machines; cached 5 minutes."""
    key = ("ALL", horizon)
    if key in _cache and time.time() - _cache[key][0] < 300:
        return _cache[key][1]
    c = bigquery.Client(project=PROJECT)
    last = {r["machine_id"]: (r["hour"], float(r["vib"])) for r in c.query(f"""
        WITH h AS (SELECT machine_id, TIMESTAMP_TRUNC(TIMESTAMP(ts), HOUR) AS hour, AVG(vibration_mm_s) AS vib
                   FROM {TABLE} GROUP BY machine_id, hour)
        SELECT machine_id, hour, vib FROM h WHERE TRUE
        QUALIFY ROW_NUMBER() OVER (PARTITION BY machine_id ORDER BY hour DESC) = 1""").result()}
    rows: dict = {}
    for r in c.query(f"""
        SELECT machine_id, forecast_timestamp AS t, forecast_value AS v,
               prediction_interval_lower_bound AS lo, prediction_interval_upper_bound AS hi
        FROM ML.FORECAST(MODEL {MODEL}, STRUCT({int(horizon)} AS horizon, 0.9 AS confidence_level))
        ORDER BY machine_id, t""").result():
        rows.setdefault(r["machine_id"], []).append(
            {"t": r["t"], "v": float(r["v"]), "lo": float(r["lo"]), "hi": float(r["hi"])})
    res = {m: _summarize(m, last[m][0], last[m][1], rows.get(m, []), horizon) for m in last}
    _cache[key] = (time.time(), res)
    return res


def forecast_machine(machine_id: str, horizon: int = 24) -> dict:
    return forecast_all(horizon).get(machine_id, {"status": "error", "message": f"No forecast for {machine_id}"})


if __name__ == "__main__":
    t = time.time()
    for m, f in sorted(forecast_all().items()):
        print(f"{m}: now {f['latest_vibration']} mm/s (zone {f['zone']}, {f['zone_meaning']}) | "
              f"hours to zone D: {f['hours_to_zone_d']}")
    print(f"({time.time() - t:.1f}s for all machines)")