"""Multi-seed backtest of the Predict step on SIMULATED data with realistic failure build-up.
Reuses the simulator's physics; only the episode planner is replaced (breakdowns during shifts; bearing wear 24-72 h,
misalignment 12-36 h, tool wear 2-6 h). Each seed loads into a SEPARATE BigQuery table (bt_readings), never the demo table.
Usage: python -m evals.backtest_multi 5"""
import csv, importlib.util, json, random, statistics, sys, tempfile
from datetime import datetime, timedelta
from pathlib import Path

from google.cloud import bigquery

import evals.backtest as bt

spec = importlib.util.spec_from_file_location("sim", "simulator/simulate.py")
sim = importlib.util.module_from_spec(spec); spec.loader.exec_module(sim)
TABLE = "kaarigar-510716.kaarigar.bt_readings"; bt.T = f"`{TABLE}`"
RAMP = {"bearing_wear": (24, 72), "spindle_misalignment": (12, 36), "tool_wear": (2, 6)}
PLAN = [("M1", "bearing_wear"), ("M3", "bearing_wear"), ("M4", "spindle_misalignment"),
        ("M2", "spindle_misalignment"), ("M5", "tool_wear")]
SCHEMA = [bigquery.SchemaField(n, t) for n, t in [("ts", "DATETIME"), ("machine_id", "STRING"), ("shift", "STRING"),
          ("status", "STRING"), ("spindle_rpm", "FLOAT64"), ("spindle_temp_c", "FLOAT64"), ("vibration_mm_s", "FLOAT64"),
          ("load_pct", "FLOAT64"), ("part_count", "INT64"), ("simulated", "BOOL")]]


def realistic_episodes(start, end, rng):
    eps = []
    for i, (mid, prob) in enumerate(PLAN):
        day = rng.randint(5, max(5, (end - start).days - 1))
        peak = (start + timedelta(days=day)).replace(hour=rng.randint(8, 19), minute=rng.choice([0, 15, 30, 45]))
        st = peak - timedelta(hours=rng.uniform(*RAMP[prob]))
        eps.append({"episode_id": f"S{i + 1:02d}", "machine_id": mid, "problem": prob, "start": st.isoformat(timespec="minutes"),
                    "peak": peak.isoformat(timespec="minutes"), "fixed": (peak + timedelta(hours=2)).isoformat(timespec="minutes"),
                    "breakdown_hours": 2, "severity": round(rng.uniform(0.75, 1.0), 2),
                    "defects_caused": sim.PROBLEMS[prob]["defects"], "fix": sim.PROBLEMS[prob]["fix"], "ongoing": False})
    return eps


def simulate(seed, folder):
    sim.OUT_DIR = folder; sim.make_episodes = realistic_episodes
    sys.argv = ["simulate.py", "--days", "14", "--seed", str(seed)]; sim.main()
    cfg = bigquery.LoadJobConfig(schema=SCHEMA, skip_leading_rows=1, source_format="CSV", write_disposition="WRITE_TRUNCATE")
    with open(folder / "sensor_readings.csv", "rb") as f:
        bigquery.Client(project="kaarigar-510716").load_table_from_file(f, TABLE, job_config=cfg).result()
    return list(csv.DictReader(open(folder / "sensor_readings.csv"))), json.loads((folder / "anomaly_episodes.json").read_text())


def run_seed(seed):
    rows, eps = simulate(seed, Path(tempfile.mkdtemp())); bt.ROWS = rows; rng = random.Random(seed); out, healthy = [], []
    for ep in eps:
        downs = [r["ts"] for r in rows if r["machine_id"] == ep["machine_id"] and r["status"] == "down" and ep["start"] <= r["ts"] <= ep["fixed"] + "~"]
        if not downs:
            continue
        bd = datetime.fromisoformat(downs[0]); lo = max(datetime.fromisoformat(ep["start"]) - timedelta(hours=6), bd - timedelta(hours=48))
        cuts = [c for c in bt.reading_hours(ep["machine_id"], lo.strftime("%Y-%m-%dT%H:%M"), downs[0]) if c <= bd][::3]
        first = None
        for c in cuts:
            h = bt.safe(ep["machine_id"], c)
            if h is not None and h <= bt.WINDOW_H:
                first = c; break
        lead = round((bd - first).total_seconds() / 3600, 1) if first else None
        out.append({"seed": seed, "machine": ep["machine_id"], "problem": ep["problem"], "lead_hours": lead})
        print(f"  seed {seed} {ep['machine_id']} {ep['problem']}: " + (f"warned {lead} h ahead" if first else "MISSED"))
    d0 = datetime.fromisoformat(rows[0]["ts"])
    for m in ("M1", "M2", "M3", "M4", "M5"):
        hs = bt.reading_hours(m, (d0 + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"), (d0 + timedelta(days=4)).strftime("%Y-%m-%dT%H:%M"))
        if not hs:
            continue
        cut = rng.choice(hs)
        if any(datetime.fromisoformat(e["start"]) < cut + timedelta(hours=24) and datetime.fromisoformat(e["fixed"]) > cut - timedelta(hours=1)
               for e in eps if e["machine_id"] == m):
            continue                      # not a healthy window
        h = bt.safe(m, cut); healthy.append(h is not None and h <= bt.WINDOW_H)
    return out, healthy


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5; allb, allh = [], []
    for seed in range(1, n + 1):
        print(f"== seed {seed}"); b, h = run_seed(seed); allb += b; allh += h
    summ = {}
    for prob in RAMP:
        L = [x["lead_hours"] for x in allb if x["problem"] == prob]; got = [v for v in L if v is not None]
        summ[prob] = {"warned": f"{len(got)}/{len(L)}", "median_lead_h": statistics.median(got) if got else None,
                      "min_lead_h": min(got) if got else None}
    summ["false_alarms_on_healthy"] = f"{sum(allh)}/{len(allh)}"
    Path("evals/backtest_multi_report.json").write_text(json.dumps(
        {"data": "SIMULATED, realistic build-up, separate BigQuery table", "breakdowns": allb, "summary": summ}, indent=2))
    bigquery.Client(project="kaarigar-510716").query(f"DROP MODEL IF EXISTS {bt.M}").result()
    print("\nSUMMARY (SIMULATED):", json.dumps(summ, indent=1))
