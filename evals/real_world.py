"""
Real-world eval on factory photos (Peenya + Mahadevapura). Labels assigned by the team from the photos.
Builds resized, EXIF-free pairs in data/pairs/rw_*, runs Kaarigar, reports TP/FN/TN/FP.
Usage: python -m evals.real_world
"""
import json
import time
from pathlib import Path

from PIL import Image, ImageOps

BASE = Path.home() / "kaarigar_private"
PEENYA = {int(l.split(":")[0][1:]): l.split(": ", 1)[1] for l in (BASE / "peenya_index.txt").read_text().splitlines()}
P, A = BASE / "photos_peenya", BASE / "photos_aaru"
CASES = [  # (name, golden files, test file, truth: True = defect)
    ("rw_bar_rust_74", [P / PEENYA[73], P / PEENYA[62]], P / PEENYA[74], True),
    ("rw_bar_rust_63", [P / PEENYA[73], P / PEENYA[62]], P / PEENYA[63], True),
    ("rw_bar_rust_64", [P / PEENYA[73], P / PEENYA[62]], P / PEENYA[64], True),
    ("rw_bar_good_58", [P / PEENYA[73], P / PEENYA[62]], P / PEENYA[58], False),
    ("rw_bar_good_61", [P / PEENYA[73], P / PEENYA[62]], P / PEENYA[61], False),
    ("rw_sprocket_good_9", [P / PEENYA[10]], P / PEENYA[9], False),
    ("rw_sprocket_good_12", [P / PEENYA[10]], P / PEENYA[12], False),
    ("rw_cover_bad", [A / "cover_clean_1.jpeg"], A / "cover_bad_1.jpeg", True),
    ("rw_cover_good", [A / "cover_clean_1.jpeg"], A / "cover_clean_2.jpeg", False),
]


def save(src: Path, dst: Path):
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    img.thumbnail((1024, 1024)); img.save(dst, quality=92)


if __name__ == "__main__":
    from agents.diagnosis import run_inspection
    rows = []
    for name, goldens, test, truth in CASES:
        out = Path("data/pairs") / name; out.mkdir(parents=True, exist_ok=True)
        for i, g in enumerate(goldens):
            save(g, out / ("golden.jpg" if i == 0 else f"golden_{i + 1}.jpg"))
        save(test, out / "test.jpg")
        try:
            d = run_inspection(name)
            pred = bool(d["defect_found"])
            outcome = ("TP" if truth else "FP") if pred else ("FN" if truth else "TN")
            rows.append({"case": name, "truth_defect": truth, "predicted_defect": pred, "outcome": outcome,
                         "confidence": d["confidence"], "types": [x["type"] for x in d["defects"]]})
        except Exception as e:
            rows.append({"case": name, "truth_defect": truth, "outcome": "ERROR", "error": type(e).__name__})
        r = rows[-1]; print(f"{name:<22} truth={'defect' if truth else 'good':<6} → {r['outcome']:<5} {r.get('types', '')}")
        time.sleep(8)
    c = {k: sum(r["outcome"] == k for r in rows) for k in ("TP", "FN", "TN", "FP", "ERROR")}
    defects, goods = c["TP"] + c["FN"], c["TN"] + c["FP"]
    summary = {"cases": len(rows), **c,
               "recall": round(c["TP"] / defects, 2) if defects else None,
               "good_parts_accepted": round(c["TN"] / goods, 2) if goods else None, "rows": rows}
    print(f"\nRecall {c['TP']}/{defects} · good parts accepted {c['TN']}/{goods} · errors {c['ERROR']}")
    Path("evals/real_world_report.json").write_text(json.dumps(summary, indent=2)); print("Saved evals/real_world_report.json")