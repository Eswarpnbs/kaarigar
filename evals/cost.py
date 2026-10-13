"""
Measure real Gemini cost per inspection / diagnosis / work order from token usage.
Gemini 2.5 Flash on Vertex AI: $0.30 per 1M input tokens, $2.50 per 1M output tokens (thinking billed as output).
Usage: python -m evals.cost [INR_per_USD]
"""
import json
import sys
import time
from pathlib import Path

from google.genai import models as gm

IN_USD, OUT_USD = 0.30 / 1e6, 2.50 / 1e6
INR = float(sys.argv[1]) if len(sys.argv) > 1 else 88.0
usage = {"in": 0, "out": 0, "calls": 0}
_orig = gm.Models.generate_content


def _counted(self, *a, **k):
    r = _orig(self, *a, **k)
    u = getattr(r, "usage_metadata", None)
    if u:
        usage["in"] += u.prompt_token_count or 0
        usage["out"] += (u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0)
        usage["calls"] += 1
    return r


gm.Models.generate_content = _counted          # count every Gemini call


def measure(label, fn):
    before, t = dict(usage), time.time()
    fn()
    i, o, c = usage["in"] - before["in"], usage["out"] - before["out"], usage["calls"] - before["calls"]
    usd = i * IN_USD + o * OUT_USD
    row = {"stage": label, "calls": c, "input_tokens": i, "output_tokens": o,
           "usd": round(usd, 5), "inr": round(usd * INR, 3), "seconds": round(time.time() - t, 1)}
    print(f"{label:<34} calls {c:>2} | in {i:>7,} | out {o:>6,} | ${usd:.4f} | ₹{usd * INR:.2f} | {row['seconds']}s")
    return row


if __name__ == "__main__":
    from agents.action import DIAG_CACHE, create_work_order, get_diagnosis
    from agents.diagnosis import run_inspection
    print(f"Gemini 2.5 Flash (Vertex AI) · ₹{INR}/USD (assumed)\n")
    rows = [
        measure("Inspect: good part (heaviest)", lambda: run_inspection("metal_nut_good_2")),
        measure("Inspect: defective part", lambda: run_inspection("real_bar_rust_1")),
    ]
    (DIAG_CACHE / "real_bar_rust_1.json").unlink(missing_ok=True)
    rows.append(measure("Diagnose (root cause, 5 Whys)", lambda: get_diagnosis("real_bar_rust_1")))
    rows.append(measure("Act (work order + 8D draft)", lambda: create_work_order("real_bar_rust_1")))
    insp = max(rows[0]["usd"], rows[1]["usd"])
    full = rows[1]["usd"] + rows[2]["usd"] + rows[3]["usd"]
    month = 100 * 26 * insp + 5 * 26 * (rows[2]["usd"] + rows[3]["usd"])
    summary = {"per_inspection_usd": round(insp, 4), "per_inspection_inr": round(insp * INR, 2),
               "full_defect_case_inr": round(full * INR, 2),
               "month_100_inspections_per_day_5_defect_cases_inr": round(month * INR, 0),
               "inr_per_usd_assumed": INR, "rows": rows}
    print(f"\nPer inspection (worst case): ₹{summary['per_inspection_inr']}")
    print(f"Full defect case (inspect + diagnose + work order + 8D): ₹{summary['full_defect_case_inr']}")
    print(f"Typical shop month (100 inspections/day, 5 defect cases/day, 26 days): ₹{summary['month_100_inspections_per_day_5_defect_cases_inr']:,.0f}")
    out = Path("evals/cost_report.json"); out.write_text(json.dumps(summary, indent=2)); print("\nSaved", out)