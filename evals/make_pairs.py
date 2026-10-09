import csv, random, shutil, sys
from pathlib import Path
src = Path(sys.argv[1]).expanduser(); cat = src.name
n = int(sys.argv[2]) if len(sys.argv) > 2 else 2
dst = Path("data/pairs"); dst.mkdir(parents=True, exist_ok=True)
goldens = random.Random(0).sample(sorted((src / "train" / "good").glob("*.png")), 3)
random.seed(42); rows = []
for d in sorted(p for p in (src / "test").iterdir() if p.is_dir()):
    imgs = sorted(d.glob("*.png"))
    for i, img in enumerate(random.sample(imgs, min(n, len(imgs)))):
        name = f"{cat}_{d.name}_{i}"; p = dst / name; p.mkdir(exist_ok=True)
        for j, g in enumerate(goldens):
            shutil.copy(g, p / ("golden.png" if j == 0 else f"golden_{j + 1}.png"))
        shutil.copy(img, p / "test.png")
        mask = src / "ground_truth" / d.name / f"{img.stem}_mask.png"
        if mask.exists(): shutil.copy(mask, p / "mask.png")
        rows.append((name, d.name != "good", d.name))
lf = dst / "labels.csv"; new = not lf.exists()
with open(lf, "a", newline="") as f:
    w = csv.writer(f)
    if new: w.writerow(["pair", "has_defect", "defect_type"])
    w.writerows(rows)
print(f"Created {len(rows)} pairs from {cat}")