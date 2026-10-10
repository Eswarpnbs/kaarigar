"""
Kaarigar machine-data tools (BigQuery).

Everything here is DETERMINISTIC: numbers, statuses, and pattern hints are computed in
code. Agents receive this evidence and explain/reason over it; they never compute it.

Test:
    python -m agents.tools.machine_data          # factory overview
    python -m agents.tools.machine_data M3       # one machine in detail
"""
import json
import os
import sys
from functools import lru_cache
from typing import Dict, List

from google.cloud import bigquery

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "kaarigar-510716")
TABLE = os.environ.get("KAARIGAR_SENSOR_TABLE", f"{PROJECT}.kaarigar.sensor_readings")
BQ_LOCATION = os.environ.get("KAARIGAR_BQ_LOCATION", "asia-south1")
MACHINES = ["M1", "M2", "M3", "M4", "M5"]

# metric: (unit, comparison, warn, critical)
#   pct     -> % change vs baseline (increase)
#   abs     -> absolute change vs baseline (increase)
#   pct_abs -> |% change| vs baseline (either direction)
THRESHOLDS = {
    "vibration_mm_s": ("mm/s", "pct", 30, 60),
    "spindle_temp_c": ("°C", "abs", 5, 10),
    "load_pct": ("% load", "abs", 15, 25),
    "spindle_rpm": ("rpm", "pct_abs", 3, 6),
}
METRICS = list(THRESHOLDS)


@lru_cache(maxsize=1)
def _bq() -> bigquery.Client:
    return bigquery.Client(project=PROJECT, location=BQ_LOCATION)


def _run(sql: str, params: List[bigquery.ScalarQueryParameter]) -> List[dict]:
    job = _bq().query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    return [dict(r) for r in job.result()]


# Recent window = mean of the last N hours of running data.
# Baseline = MEDIAN over the previous 7 days (excluding the last day) -> robust to old episodes.
_STATS_SQL = f"""
WITH asof AS (SELECT MAX(ts) AS now FROM `{TABLE}` WHERE machine_id = @mid),
recent AS (
  SELECT COUNT(*) AS n,
         AVG(vibration_mm_s) AS vibration_mm_s, AVG(spindle_temp_c) AS spindle_temp_c,
         AVG(load_pct) AS load_pct, AVG(spindle_rpm) AS spindle_rpm
  FROM `{TABLE}`, asof
  WHERE machine_id = @mid AND status = 'running'
    AND ts > DATETIME_SUB(asof.now, INTERVAL @recent_h HOUR)
),
baseline AS (
  SELECT COUNT(*) AS n,
         APPROX_QUANTILES(vibration_mm_s, 2)[OFFSET(1)] AS vibration_mm_s,
         APPROX_QUANTILES(spindle_temp_c, 2)[OFFSET(1)] AS spindle_temp_c,
         APPROX_QUANTILES(load_pct, 2)[OFFSET(1)] AS load_pct,
         APPROX_QUANTILES(spindle_rpm, 2)[OFFSET(1)] AS spindle_rpm
  FROM `{TABLE}`, asof
  WHERE machine_id = @mid AND status = 'running'
    AND ts BETWEEN DATETIME_SUB(asof.now, INTERVAL 8 DAY) AND DATETIME_SUB(asof.now, INTERVAL 1 DAY)
),
downtime AS (
  SELECT COUNT(*) * 5 / 60 AS down_hours_7d
  FROM `{TABLE}`, asof
  WHERE machine_id = @mid AND status = 'down'
    AND ts > DATETIME_SUB(asof.now, INTERVAL 7 DAY)
)
SELECT (SELECT now FROM asof) AS as_of,
       r.n AS recent_n, r.vibration_mm_s AS r_vib, r.spindle_temp_c AS r_temp,
       r.load_pct AS r_load, r.spindle_rpm AS r_rpm,
       b.n AS base_n, b.vibration_mm_s AS b_vib, b.spindle_temp_c AS b_temp,
       b.load_pct AS b_load, b.spindle_rpm AS b_rpm,
       d.down_hours_7d
FROM recent r, baseline b, downtime d
"""

# Hourly vibration for the trend line (also usable as a sparkline on the map)
_TREND_SQL = f"""
WITH asof AS (SELECT MAX(ts) AS now FROM `{TABLE}` WHERE machine_id = @mid)
SELECT DATETIME_TRUNC(ts, HOUR) AS hour, AVG(vibration_mm_s) AS vib
FROM `{TABLE}`, asof
WHERE machine_id = @mid AND status = 'running'
  AND ts > DATETIME_SUB(asof.now, INTERVAL @trend_h HOUR)
GROUP BY hour ORDER BY hour
"""


def _slope_per_hour(values: List[float]) -> float:
    """Least-squares slope (units per hour) of an hourly series."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = range(n)
    mx, my = (n - 1) / 2, sum(values) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, values)) / den if den else 0.0


def _level(metric: str, change: float) -> str:
    _, kind, warn, crit = THRESHOLDS[metric]
    v = abs(change) if kind == "pct_abs" else change
    return "critical" if v >= crit else ("warning" if v >= warn else "normal")


def _hints(ch: Dict[str, float]) -> List[dict]:
    """Known signatures -> candidate problems. Hints, not conclusions."""
    vib, temp, load, rpm = (ch["vibration_mm_s"], ch["spindle_temp_c"],
                            ch["load_pct"], ch["spindle_rpm"])
    hints = []
    if vib >= 30 and abs(rpm) < 3 and load < 10:
        hints.append({"problem": "bearing_wear",
                      "evidence": "vibration up without a rise in cutting load or speed drift",
                      "typical_defects": ["chatter_marks", "poor_surface_finish"]})
    if load >= 10 and temp >= 3:
        hints.append({"problem": "tool_wear",
                      "evidence": "cutting load and temperature rising together",
                      "typical_defects": ["burr", "scratch", "poor_surface_finish"]})
    if temp >= 10 and vib < 30:
        hints.append({"problem": "coolant_failure",
                      "evidence": "temperature high without a vibration change",
                      "typical_defects": ["discoloration", "burn_marks"]})
    if vib >= 30 and abs(rpm) >= 3:
        hints.append({"problem": "spindle_misalignment",
                      "evidence": "vibration up together with spindle speed drift",
                      "typical_defects": ["dimension_out_of_tolerance", "deformation"]})
    return hints


def machine_health(machine_id: str, recent_hours: int = 3) -> dict:
    """Health of one machine: recent sensor values vs its normal baseline, vibration trend,
    status (normal / warning / critical), problem-pattern hints, and 7-day downtime.
    Data is SIMULATED in the prototype.

    Args:
        machine_id: machine id, e.g. "M3".
        recent_hours: size of the recent window in hours (default 3).

    Returns:
        dict with status, per-metric comparison, trend, hints, and downtime.
    """
    mid = machine_id.strip().upper()
    if mid not in MACHINES:
        return {"status": "error", "message": f"Unknown machine '{machine_id}'. Valid: {MACHINES}"}

    p = [bigquery.ScalarQueryParameter("mid", "STRING", mid),
         bigquery.ScalarQueryParameter("recent_h", "INT64", recent_hours)]
    rows = _run(_STATS_SQL, p)
    if not rows or not rows[0]["recent_n"] or not rows[0]["base_n"]:
        return {"status": "error", "message": f"Not enough recent data for {mid}."}
    r = rows[0]

    recent = {"vibration_mm_s": r["r_vib"], "spindle_temp_c": r["r_temp"],
              "load_pct": r["r_load"], "spindle_rpm": r["r_rpm"]}
    base = {"vibration_mm_s": r["b_vib"], "spindle_temp_c": r["b_temp"],
            "load_pct": r["b_load"], "spindle_rpm": r["b_rpm"]}

    metrics, changes, levels = {}, {}, []
    for m in METRICS:
        unit, kind, _, _ = THRESHOLDS[m]
        if kind == "abs":
            change = recent[m] - base[m]
            change_txt = f"{change:+.1f} {unit}"
        else:
            change = (recent[m] - base[m]) / base[m] * 100 if base[m] else 0.0
            change_txt = f"{change:+.0f}%"
        changes[m] = change
        lvl = _level(m, change)
        levels.append(lvl)
        metrics[m] = {"recent": round(recent[m], 2), "normal": round(base[m], 2),
                      "change": change_txt, "level": lvl}

    trend_rows = _run(_TREND_SQL, [bigquery.ScalarQueryParameter("mid", "STRING", mid),
                                   bigquery.ScalarQueryParameter("trend_h", "INT64", 12)])
    hourly = [round(t["vib"], 2) for t in trend_rows]
    slope = _slope_per_hour(hourly)

    status = ("critical" if "critical" in levels else
              "warning" if "warning" in levels else "normal")
    return {
        "status": "success",
        "machine_id": mid,
        "health": status,                       # normal / warning / critical
        "as_of": r["as_of"].isoformat() if r["as_of"] else None,
        "recent_window_hours": recent_hours,
        "metrics": metrics,
        "vibration_trend": {
            "per_hour": round(slope, 3),
            "direction": "rising" if slope > 0.05 else ("falling" if slope < -0.05 else "stable"),
            "hourly_last_12h": hourly,
        },
        "pattern_hints": _hints(changes),
        "downtime_hours_7d": round(r["down_hours_7d"] or 0, 1),
        "data_note": "SIMULATED sensor data (prototype)",
    }


def factory_overview(recent_hours: int = 3) -> dict:
    """Health status of every machine in the factory (for the Live Factory Map).

    Args:
        recent_hours: size of the recent window in hours (default 3).

    Returns:
        dict with one summary per machine.
    """
    out = []
    for mid in MACHINES:
        h = machine_health(mid, recent_hours)
        if h.get("status") != "success":
            out.append({"machine_id": mid, "health": "unknown"})
            continue
        out.append({
            "machine_id": mid,
            "health": h["health"],
            "vibration_change": h["metrics"]["vibration_mm_s"]["change"],
            "temp_change": h["metrics"]["spindle_temp_c"]["change"],
            "trend": h["vibration_trend"]["direction"],
            "top_hint": h["pattern_hints"][0]["problem"] if h["pattern_hints"] else None,
        })
    return {"status": "success", "machines": out, "data_note": "SIMULATED sensor data (prototype)"}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(machine_health(sys.argv[1]), indent=2, default=str))
    else:
        print(json.dumps(factory_overview(), indent=2, default=str))