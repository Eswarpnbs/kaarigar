"""Build golden/test pairs from the Kaggle casting dataset (Pilot Technocast impellers, CC BY-NC-ND 4.0).
Original 512x512 photos, MD5 de-duplicated, seed 42: 3 OK goldens, 50 other OK + 50 defective tests.
Images are NOT committed (license). Usage: python -m evals.make_casting <folder containing ok_front and def_front>"""
import csv, hashlib, random, sys
from pathlib import Path
from PIL import Image

src = Path(sys.argv[1]).expanduser(); dst = Path("data/bench_casting"); dst.mkdir(parents=True, exist_ok=True)


def uniq(folder):
    seen, out = set(), []
    for f in sorted((src / folder).glob("*.jp*g")):
        h = hashlib.md5(f.read_bytes()).hexdigest()
        if h not in seen:
            seen.add(h); out.append(f)
    return out


ok, bad = uniq("ok_front"), uniq("def_front")
rng = random.Random(42); rng.shuffle(ok); rng.shuffle(bad)
goldens, rows = ok[:3], []
for kind, imgs in (("good", ok[3:53]), ("defect", bad[:50])):
    for i, img in enumerate(imgs):
        p = dst / f"casting_{kind}_{i}"; p.mkdir(exist_ok=True)
        for j, g in enumerate(goldens):
            Image.open(g).convert("RGB").save(p / ("golden.png" if j == 0 else f"golden_{j + 1}.png"))
        Image.open(img).convert("RGB").save(p / "test.png")
        rows.append((p.name, kind == "defect", "casting_defect" if kind == "defect" else "good"))
with open(dst / "labels.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["pair", "has_defect", "defect_type"]); w.writerows(rows)
print(f"{len(ok)} unique OK, {len(bad)} unique defective -> {len(rows)} pairs (3 goldens each), seed 42")
