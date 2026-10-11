import csv, hashlib, random, shutil, sys
from pathlib import Path
src = Path(sys.argv[1]).expanduser(); cat = src.name; n = int(sys.argv[2])
dst = Path("data/pairs"); lf = dst / "labels.csv"
h = lambda p: hashlib.md5(p.read_bytes()).hexdigest()
used = {h(p / "test.png") for p in dst.iterdir() if (p / "test.png").exists()}
goldens = random.Random(0).sample(sorted((src / "train" / "good").glob("*.png")), 3)
imgs = sorted((src / "test" / "good").glob("*.png")); random.Random(7).shuffle(imgs)
rows = []
for img in imgs:
    if len(rows) >= n: break
    if h(img) in used: continue
    name = f"{cat}_good_x{len(rows)}"; p = dst / name; p.mkdir(exist_ok=True)
    for j, g in enumerate(goldens):
        shutil.copy(g, p / ("golden.png" if j == 0 else f"golden_{j + 1}.png"))
    shutil.copy(img, p / "test.png"); rows.append((name, False, "good"))
with open(lf, "a", newline="") as f: csv.writer(f).writerows(rows)
print(f"Added {len(rows)} extra good pairs from {cat}")