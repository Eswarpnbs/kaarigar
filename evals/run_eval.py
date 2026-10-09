"""
Kaarigar evaluation runner.

Measures, on labelled golden/test pairs:
  - detection accuracy          (defect yes/no correct)
  - defect recall               (share of real defects caught)
  - safe-outcome rate           (real defects caught OR escalated via "retake_photo")
  - false-alarm rate            (perfect parts wrongly flagged)
  - localization (MVTec masks)  hit rate, defect coverage, box precision
  - average latency

Each run is saved to evals/runs/<timestamp>_<tag>/ and appended to evals/runs/history.csv.

Usage (from the repo root):
    python -m evals.run_eval data/pairs --tag baseline
"""
import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from evals.inspect_test import draw_boxes, find_image
from agents.inspector import MODEL, inspect

RUNS_DIR = Path("evals/runs")


def to_px(box, w, h):
    y0, x0, y1, x1 = box
    xa, xb = sorted((int(x0 * w / 1000), int(x1 * w / 1000)))
    ya, yb = sorted((int(y0 * h / 1000), int(y1 * h / 1000)))
    return max(0, xa), max(0, ya), min(w, xb), min(h, yb)


def localization(result, mask_path: Path):
    """Compare predicted boxes with the ground-truth defect mask."""
    mask = np.array(Image.open(mask_path).convert("L")) > 127
    if mask.sum() == 0:
        return None
    h, w = mask.shape
    covered = np.zeros_like(mask)
    for d in result.defects:
        if len(d.box_2d) != 4:
            continue
        x0, y0, x1, y1 = to_px(d.box_2d, w, h)
        covered[y0:y1, x0:x1] = True
    inter = int((covered & mask).sum())
    box_area = int(covered.sum())
    return {
        "hit": inter > 0,                                       # box touches the defect at all
        "coverage": inter / int(mask.sum()),                    # share of defect inside boxes
        "precision": inter / box_area if box_area else 0.0,     # share of box that is defect
        "whole_part_box": box_area > 0.6 * w * h,               # box covers most of the image
    }


def pct(values):
    values = [v for v in values if v is not None]
    return round(100 * sum(values) / len(values), 1) if values else None


def avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", help="folder with pair subfolders and labels.csv")
    ap.add_argument("--tag", default="run", help="short name for this run, e.g. baseline")
    args = ap.parse_args()

    data = Path(args.data)
    with open(data / "labels.csv", newline="") as f:
        labels = {r["pair"].strip(): r for r in csv.DictReader(f)}

    run_dir = RUNS_DIR / f"{datetime.now():%Y%m%d_%H%M}_{args.tag}"
    (run_dir / "images").mkdir(parents=True, exist_ok=True)

    rows = []
    pairs = sorted(p for p in data.iterdir() if p.is_dir() and p.name in labels)
    print(f"Model: {MODEL} | Pairs: {len(pairs)} | Run: {run_dir}\n")

    for pair in pairs:
        lab = labels[pair.name]
        truth = lab["has_defect"].strip().lower() == "true"
        golden, test = find_image(pair, "golden"), find_image(pair, "test")

        t0 = time.time()
        try:
            r = inspect(golden, test)
        except Exception as e:
            print(f"[{pair.name}] ERROR: {e}")
            rows.append({"pair": pair.name, "error": str(e)})
            continue
        latency = round(time.time() - t0, 2)

        draw_boxes(test, r, run_dir / "images" / f"{pair.name}.jpg")
        mask = pair / "mask.png"
        loc = localization(r, mask) if (truth and r.defect_found and mask.exists()) else None
        safe = (r.defect_found or r.recommendation == "retake_photo") if truth else True

        row = {
            "pair": pair.name,
            "truth": truth,
            "truth_type": lab.get("defect_type", ""),
            "pred": r.defect_found,
            "correct": r.defect_found == truth,
            "safe": safe,
            "false_alarm": (not truth) and r.defect_found,
            "recommendation": r.recommendation,
            "confidence": r.confidence,
            "pred_types": [d.type for d in r.defects],
            "latency_s": latency,
            "loc": loc,
            "raw": r.model_dump(),
        }
        rows.append(row)

        mark = "PASS" if row["correct"] else ("ESCALATED" if safe and truth else "FAIL")
        loc_txt = (f" | loc hit={loc['hit']} cov={loc['coverage']:.2f} prec={loc['precision']:.2f}"
                   if loc else "")
        print(f"[{pair.name}] pred={r.defect_found} conf={r.confidence} "
              f"rec={r.recommendation} {mark}{loc_txt}")
        time.sleep(1)  # gentle on rate limits

    ok = [x for x in rows if "error" not in x]
    pos = [x for x in ok if x["truth"]]
    neg = [x for x in ok if not x["truth"]]
    locs = [x["loc"] for x in pos if x["loc"] and not x["loc"]["whole_part_box"]]

    summary = {
        "run": run_dir.name,
        "model": MODEL,
        "pairs": len(ok),
        "errors": len(rows) - len(ok),
        "detection_accuracy_pct": pct([x["correct"] for x in ok]),
        "defect_recall_pct": pct([x["pred"] for x in pos]),
        "safe_outcome_pct": pct([x["safe"] for x in pos]),
        "false_alarm_pct": pct([x["false_alarm"] for x in neg]),
        "good_escalated_pct": pct([x["recommendation"] == "retake_photo" for x in neg]),
        "loc_hit_pct": pct([l["hit"] for l in locs]),
        "avg_defect_coverage": avg([l["coverage"] for l in locs]),
        "avg_box_precision": avg([l["precision"] for l in locs]),
        "whole_part_boxes": sum(1 for x in pos if x["loc"] and x["loc"]["whole_part_box"]),
        "avg_latency_s": avg([x["latency_s"] for x in ok]),
    }

    (run_dir / "results.json").write_text(json.dumps(rows, indent=2))
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    history = RUNS_DIR / "history.csv"
    new = not history.exists()
    with open(history, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary.keys()))
        if new:
            w.writeheader()
        w.writerow(summary)

    print("\n===== SUMMARY =====")
    for k, v in summary.items():
        print(f"{k:>24}: {v}")
    print(f"\nSaved to {run_dir}")


if __name__ == "__main__":
    main()