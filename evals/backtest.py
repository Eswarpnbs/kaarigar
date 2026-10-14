"""Backtest the Predict step on SIMULATED ground truth (data/sim): for each breakdown, replay BigQuery ML
ARIMA_PLUS forecasts trained ONLY on data before each hour, and check whether the 12-hour alert fired in time.
Usage: python -m evals.backtest"""
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from google.cloud import bigquery

PROJECT = "kaarigar-510716"
T, M = f"`{PROJECT}.kaarigar.sensor_readings`", f"`{PROJECT}.kaarigar.bt_model`"
LIMIT, WINDOW_H = 4.5, 12
bq = bigquery.Client(project=PROJECT)
ROWS = list(csv.DictReader(open("data/sim/sensor_readings.csv")))
EPS = json.load(open("data/sim/anomaly_episodes.json"))


def hours_to_limit(machine, cutoff):
    """Train on data BEFORE cutoff only; hours until the forecast reaches the limit (None if not within 24 h)."""
    cut = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
    src = (f"SELECT TIMESTAMP_TRUNC(TIMESTAMP(ts), HOUR) AS hour, AVG(vibration_mm_s) AS vib FROM {T} "
           f"WHERE machine_id='{machine}' AND ts < DATETIME('{cut}') GROUP BY hour")
    bq.query(f"CREATE OR REPLACE MODEL {M} OPTIONS(model_type='ARIMA_PLUS', time_series_timestamp_col='hour', "
             f"time_series_data_col='vib', data_frequency='HOURLY', horizon=24, auto_arima=TRUE) AS {src}").result()
    last = list(bq.query(f"SELECT hour, vib FROM ({src}) ORDER BY hour DESC LIMIT 1").result())[0]
    if last["vib"] >= LIMIT:
        return 0.0
    q = f"SELECT forecast_timestamp t, forecast_value v FROM ML.FORECAST(MODEL {M}, STRUCT(24 AS horizon, 0.9 AS confidence_level)) ORDER BY t"
    for r in bq.query(q).result():
        if r["v"] >= LIMIT:
            return round((r["t"] - last["hour"]).total_seconds() / 3600, 1)
    return None


def reading_hours(machine, start, end):
    hs = sorted({r["ts"][:13] for r in ROWS if r["machine_id"] == machine and start <= r["ts"] < end})
    return [datetime.strptime(h, "%Y-%m-%dT%H") + timedelta(hours=1) for h in hs]   # cutoff = end of each hour with data


def safe(machine, cut):
    try:
        return hours_to_limit(machine, cut)
    except Exception as e:
        print("   (skipped:", type(e).__name__, ")"); return None


if __name__ == "__main__":
    out = {"data": "SIMULATED (data/sim, ground-truth episodes)", "rule": f"alert if forecast reaches {LIMIT} mm/s within {WINDOW_H} h",
           "breakdowns": [], "healthy_checks": []}
    for ep in [e for e in EPS if e.get("breakdown_hours") and not e.get("ongoing")]:
        downs = [r["ts"] for r in ROWS if r["machine_id"] == ep["machine_id"] and r["status"] == "down"
                 and ep["start"] <= r["ts"] <= ep["fixed"] + "~"]
        if not downs:
            print(ep["episode_id"], "breakdown happened outside shift hours (no readings): skipped"); continue
        bd, first = datetime.fromisoformat(downs[0]), None
        start = (datetime.fromisoformat(ep["start"]) - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M")
        for cut in [c for c in reading_hours(ep["machine_id"], start, downs[0]) if c <= bd]:
            h = safe(ep["machine_id"], cut)
            print(f"  {ep['episode_id']} {ep['machine_id']} at {cut:%m-%d %H:%M}: {h} h to limit")
            if h is not None and h <= WINDOW_H:
                first = cut; break
        lead = round((bd - first).total_seconds() / 3600, 1) if first else None
        out["breakdowns"].append({"episode": ep["episode_id"], "machine": ep["machine_id"], "problem": ep["problem"],
                                  "breakdown": downs[0], "first_alert": first.isoformat() if first else None, "lead_hours": lead})
        print(f"{ep['episode_id']} {ep['problem']}: " + (f"warned {lead} h before the breakdown" if first else "MISSED"))
    for m in ("M2", "M3"):
        allh = reading_hours(m, "2026-01-01", "2100-01-01"); allh = allh[len(allh) // 3:]
        for cut in allh[::max(1, len(allh) // 4)][:4]:
            h = safe(m, cut)
            out["healthy_checks"].append({"machine": m, "at": cut.isoformat(), "alert": h is not None and h <= WINDOW_H})
            print(f"  healthy {m} at {cut:%m-%d %H:%M}: {h} h to limit")
    det = [b for b in out["breakdowns"] if b["lead_hours"] is not None]
    out["summary"] = {"breakdowns_warned": f"{len(det)}/{len(out['breakdowns'])}",
                      "lead_hours": [b["lead_hours"] for b in det],
                      "false_alarms": f"{sum(c['alert'] for c in out['healthy_checks'])}/{len(out['healthy_checks'])}"}
    bq.query(f"DROP MODEL IF EXISTS {M}").result()
    Path("evals/backtest_report.json").write_text(json.dumps(out, indent=2))
    print("\nSUMMARY (SIMULATED data):", out["summary"])
