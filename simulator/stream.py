"""
Live sensor stream (SIMULATED machine gateway): publishes one reading per machine every few seconds to
Pub/Sub topic `sensor-readings`; a BigQuery subscription writes them into kaarigar.sensor_stream.
Continues from each machine's latest reading (M1 bearing wear keeps rising).
Usage: python simulator/stream.py [seconds_between_rounds] [rounds]
"""
import json
import random
import sys
import time
from datetime import datetime

from google.cloud import bigquery, pubsub_v1

PROJECT = "kaarigar-510716"
EVERY = float(sys.argv[1]) if len(sys.argv) > 1 else 5
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 60


def latest() -> dict:
    q = f"""SELECT * FROM `{PROJECT}.kaarigar.sensor_all`
            WHERE TRUE QUALIFY ROW_NUMBER() OVER (PARTITION BY machine_id ORDER BY ts DESC) = 1"""
    return {r["machine_id"]: dict(r) for r in bigquery.Client(project=PROJECT).query(q).result()}


if __name__ == "__main__":
    state = latest()
    pub = pubsub_v1.PublisherClient()
    topic = pub.topic_path(PROJECT, "sensor-readings")
    print(f"Streaming {len(state)} machines every {EVERY}s for {ROUNDS} rounds → Pub/Sub → BigQuery (SIMULATED)")
    for n in range(ROUNDS):
        for mid, s in state.items():
            drift = 0.003 if mid == "M1" else 0.0            # M1 bearing wear keeps worsening
            s["vibration_mm_s"] = max(0.3, float(s["vibration_mm_s"]) + drift + random.gauss(0, 0.03))
            s["spindle_temp_c"] = float(s["spindle_temp_c"]) + random.gauss(0, 0.05)
            s["part_count"] = int(s["part_count"]) + 1
            msg = {"ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "machine_id": mid, "shift": s["shift"],
                   "status": s["status"], "spindle_rpm": int(s["spindle_rpm"]),
                   "spindle_temp_c": round(s["spindle_temp_c"], 2), "vibration_mm_s": round(s["vibration_mm_s"], 3),
                   "load_pct": round(float(s["load_pct"]), 1), "part_count": s["part_count"], "simulated": True}
            pub.publish(topic, json.dumps(msg).encode()).result()
        print(f"round {n + 1}: M1 vibration {state['M1']['vibration_mm_s']:.2f} mm/s", end="\r")
        time.sleep(EVERY)
    print("\nDone.")