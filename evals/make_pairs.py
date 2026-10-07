import csv, random, shutil, sys
from pathlib import Path
src = Path(sys.argv[1]).expanduser(); cat = src.name   # e.g. ~/Downloads/mvtec/metal_nut
dst = Path("data/pairs"); dst.mkdir(parents=True, exist_ok=True)
golden = sorted((src / "train" / "good").glob("*.png"))[0]
random.seed(42); rows = []
for d in sorted(p for p in (src / "test").iterdir() if p.is_dir()):
    imgs = sorted(d.glob("*.png"))
    for i, img in enumerate(random.sample(imgs, min(2, len(imgs)))):
        name = f"{cat}_{d.name}_{i}"; p = dst / name; p.mkdir(exist_ok=True)
        shutil.copy(golden, p / "golden.png"); shutil.copy(img, p / "test.png")
        rows.append((name, d.name != "good"))
lf = dst / "labels.csv"; new = not lf.exists()
with open(lf, "a", newline="") as f:
    w = csv.writer(f)
    if new: w.writerow(["pair", "has_defect"])
    w.writerows(rows)
print(f"Created {len(rows)} pairs from {cat}")