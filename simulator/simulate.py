"""
Kaarigar sensor simulator — SIMULATED machine data (clearly labelled), with realistic,
gradually developing problems linked to the defects they cause.

Outputs (data/sim/):
  machines.json            machine list (used by the Live Factory Map)
  sensor_readings.csv      readings every 5 min during shifts (for BigQuery)
  anomaly_episodes.json    ground truth: which problem, which machine, when, which defects

Usage:
  python simulator/simulate.py                 # 14 days of history, ends now
  python simulator/simulate.py --days 7 --seed 1
"""
import argparse
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT_DIR = Path("data/sim")
INTERVAL_MIN = 5
SHIFTS = [("A", 6, 14), ("B", 14, 22)]  # (name, start hour, end hour); night is idle

MACHINES = [
    {"machine_id": "M1", "name": "CNC Lathe 1", "type": "cnc_lathe", "rpm": 2400, "temp": 42, "vib": 1.8, "load": 55, "cycle_s": 90, "x": 1, "y": 1},
    {"machine_id": "M2", "name": "CNC Lathe 2", "type": "cnc_lathe", "rpm": 2200, "temp": 41, "vib": 1.9, "load": 52, "cycle_s": 95, "x": 2, "y": 1},
    {"machine_id": "M3", "name": "Gear Hobbing Machine", "type": "gear_hobbing", "rpm": 600, "temp": 44, "vib": 2.2, "load": 60, "cycle_s": 240, "x": 3, "y": 1},
    {"machine_id": "M4", "name": "Shaping Machine", "type": "shaper", "rpm": 60, "temp": 38, "vib": 2.6, "load": 45, "cycle_s": 300, "x": 1, "y": 2},
    {"machine_id": "M5", "name": "Band Saw", "type": "band_saw", "rpm": 900, "temp": 36, "vib": 1.4, "load": 40, "cycle_s": 120, "x": 2, "y": 2},
]

# Problem type -> sensor effects at full severity, and the defects it causes
PROBLEMS = {
    "tool_wear": {
        "effects": {"load": 25, "temp": 8, "vib": 0.8},
        "defects": ["burr", "scratch", "poor_surface_finish"],
        "fix": "Replace or regrind the cutting tool; check tool-change interval.",
    },
    "bearing_wear": {
        "effects": {"vib": 4.0, "temp": 6},
        "defects": ["chatter_marks", "poor_surface_finish"],
        "fix": "Inspect and replace spindle bearings; check lubrication.",
    },
    "coolant_failure": {
        "effects": {"temp": 22, "load": 6},
        "defects": ["discoloration", "burn_marks"],
        "fix": "Check coolant level, pump, and nozzle; clean filters.",
    },
    "spindle_misalignment": {
        "effects": {"vib": 2.5, "rpm_pct": -6},
        "defects": ["dimension_out_of_tolerance", "deformation"],
        "fix": "Re-align spindle and fixture; verify with a dial indicator.",
    },
}


def in_shift(ts: datetime):
    for name, start, end in SHIFTS:
        if start <= ts.hour < end:
            return name
    return None


def make_episodes(start: datetime, end: datetime, rng: random.Random):
    """Create past problem episodes + one ongoing bearing-wear episode on M3."""
    episodes = []
    span_h = (end - start).total_seconds() / 3600
    plan = [("M1", "tool_wear"), ("M2", "coolant_failure"), ("M4", "spindle_misalignment"),
            ("M5", "tool_wear"), ("M1", "bearing_wear")]
    for i, (mid, prob) in enumerate(plan):
        ep_start = start + timedelta(hours=rng.uniform(0.08, 0.75) * span_h)
        ramp_h = rng.uniform(3, 8)
        breakdown = prob in ("bearing_wear", "spindle_misalignment") or rng.random() < 0.3
        episodes.append({
            "episode_id": f"EP{i + 1:02d}",
            "machine_id": mid,
            "problem": prob,
            "start": ep_start.isoformat(timespec="minutes"),
            "peak": (ep_start + timedelta(hours=ramp_h)).isoformat(timespec="minutes"),
            "fixed": (ep_start + timedelta(hours=ramp_h + (2 if breakdown else 0.5))).isoformat(timespec="minutes"),
            "breakdown_hours": 2 if breakdown else 0,
            "severity": round(rng.uniform(0.7, 1.0), 2),
            "defects_caused": PROBLEMS[prob]["defects"],
            "fix": PROBLEMS[prob]["fix"],
            "ongoing": False,
        })
    # Ongoing episode for the demo: Machine 3 bearing wear, building up over the last ~10 h
    ep_start = end - timedelta(hours=10)
    episodes.append({
        "episode_id": f"EP{len(plan) + 1:02d}",
        "machine_id": "M1",
        "problem": "bearing_wear",
        "start": ep_start.isoformat(timespec="minutes"),
        "peak": (end + timedelta(hours=6)).isoformat(timespec="minutes"),  # still rising
        "fixed": None,
        "breakdown_hours": 0,
        "severity": 0.9,
        "defects_caused": PROBLEMS["bearing_wear"]["defects"],
        "fix": PROBLEMS["bearing_wear"]["fix"],
        "ongoing": True,
    })
    return episodes


def effect_level(ts: datetime, ep: dict) -> float:
    """0..1 severity multiplier for an episode at time ts (gradual ramp, then fixed)."""
    s = datetime.fromisoformat(ep["start"])
    p = datetime.fromisoformat(ep["peak"])
    f = datetime.fromisoformat(ep["fixed"]) if ep["fixed"] else None
    if ts < s or (f and ts >= f):
        return 0.0
    if ts <= p:
        return ep["severity"] * (ts - s).total_seconds() / max(1, (p - s).total_seconds())
    return ep["severity"]


def is_down(ts: datetime, ep: dict) -> bool:
    if not ep["breakdown_hours"] or not ep["fixed"]:
        return False
    f = datetime.fromisoformat(ep["fixed"])
    return f - timedelta(hours=ep["breakdown_hours"]) <= ts < f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    end = datetime.now().replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % INTERVAL_MIN)
    start = end - timedelta(days=args.days)
    episodes = make_episodes(start, end, rng)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counts = {m["machine_id"]: 0 for m in MACHINES}
    rows = 0
    with open(OUT_DIR / "sensor_readings.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "machine_id", "shift", "status", "spindle_rpm", "spindle_temp_c",
                    "vibration_mm_s", "load_pct", "part_count", "simulated"])
        ts = start
        while ts <= end:
            shift = in_shift(ts)
            if shift:
                for m in MACHINES:
                    mine = [e for e in episodes if e["machine_id"] == m["machine_id"]]
                    if any(is_down(ts, e) for e in mine):
                        w.writerow([ts.isoformat(timespec="seconds"), m["machine_id"], shift, "down",
                                    0, round(m["temp"] - 8 + rng.gauss(0, 0.5), 1), 0.0, 0.0,
                                    counts[m["machine_id"]], True])
                        rows += 1
                        continue
                    temp, vib, load, rpm = m["temp"], m["vib"], m["load"], m["rpm"]
                    for e in mine:
                        lvl = effect_level(ts, e)
                        eff = PROBLEMS[e["problem"]]["effects"]
                        temp += eff.get("temp", 0) * lvl
                        vib += eff.get("vib", 0) * lvl
                        load += eff.get("load", 0) * lvl
                        rpm *= 1 + eff.get("rpm_pct", 0) / 100 * lvl
                    counts[m["machine_id"]] += max(0, round(INTERVAL_MIN * 60 / m["cycle_s"] + rng.gauss(0, 0.4)))
                    w.writerow([
                        ts.isoformat(timespec="seconds"), m["machine_id"], shift, "running",
                        round(rpm + rng.gauss(0, rpm * 0.01)),
                        round(temp + rng.gauss(0, 0.8), 1),
                        round(max(0.1, vib + rng.gauss(0, 0.15)), 2),
                        round(min(100, max(5, load + rng.gauss(0, 2))), 1),
                        counts[m["machine_id"]],
                        True,
                    ])
                    rows += 1
            ts += timedelta(minutes=INTERVAL_MIN)

    (OUT_DIR / "machines.json").write_text(json.dumps(MACHINES, indent=2))
    (OUT_DIR / "anomaly_episodes.json").write_text(json.dumps(episodes, indent=2))

    print(f"SIMULATED data written to {OUT_DIR}/  ({rows:,} readings, {args.days} days, "
          f"{len(MACHINES)} machines)")
    print("Episodes (ground truth):")
    for e in episodes:
        tag = "ONGOING" if e["ongoing"] else f"fixed {e['fixed']}"
        print(f"  {e['episode_id']} {e['machine_id']:<3} {e['problem']:<21} start {e['start']}  {tag}"
              f"{'  +breakdown' if e['breakdown_hours'] else ''}")


if __name__ == "__main__":
    main()