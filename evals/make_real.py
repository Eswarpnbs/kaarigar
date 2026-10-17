"""Real-world benchmark v2: 33 cases from two Bengaluru shops; labels assigned by the team (who visited) from site photos.
Builds EXIF-free, resized pairs in data/bench_real (private, not committed). Usage: python -m evals.make_real"""
import csv, hashlib
from pathlib import Path
from PIL import Image, ImageOps

B = Path.home() / "kaarigar_private"
PE = {int(l.split(":")[0][1:]): l.split(": ", 1)[1] for l in (B / "peenya_index.txt").read_text().splitlines()}
AA = sorted((B / "photos_aaru").glob("*.jp*g"))
P = lambda n: B / "photos_peenya" / PE[n]
A = lambda n: AA[n]
GROUPS = [  # (group, goldens, good tests, defective tests)
    ("bar", [P(73), P(62)], [P(58), P(61)], [P(74), P(63), P(64)]),
    ("block", [P(38)], [P(39)], [P(n) for n in (40, 41, 42, 43, 44, 45, 46, 48)]),
    ("strip", [P(47)], [P(49), P(50)], [P(52), P(53)]),
    ("squarebar", [P(65)], [P(67), P(68)], []),
    ("sprocket_top", [P(10)], [P(9), P(12)], []),
    ("sprocket_angle", [P(13)], [P(11), P(14), P(15)], []),
    ("sprocket_pair", [P(4)], [P(0), P(5), P(7)], []),
    ("aaru_cover", [A(12)], [A(13), A(8), A(10)], [A(11), A(9)]),
]
md5 = lambda f: hashlib.md5(f.read_bytes()).hexdigest()


def save(src, dst):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB"); im.thumbnail((1024, 1024)); im.save(dst, quality=92)


dst = Path("data/bench_real"); dst.mkdir(parents=True, exist_ok=True); rows, skipped = [], 0
for g, goldens, goods, bads in GROUPS:
    gh = {md5(x) for x in goldens}
    for kind, tests in (("good", goods), ("defect", bads)):
        for t in tests:
            if md5(t) in gh: skipped += 1; continue
            tag = "".join(c for c in t.stem[-12:] if c.isalnum())
            p = dst / f"{g}_{kind}_{tag}"; p.mkdir(exist_ok=True)
            for i, x in enumerate(goldens): save(x, p / ("golden.jpg" if i == 0 else f"golden_{i + 1}.jpg"))
            save(t, p / "test.jpg"); rows.append((p.name, kind == "defect", g if kind == "defect" else "good"))
with open(dst / "labels.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["pair", "has_defect", "defect_type"]); w.writerows(rows)
print(len(rows), "pairs built ·", skipped, "skipped (identical to golden) ·", sum(r[1] for r in rows), "defective")
print("Aaru check: A11 =", AA[11].name, "| A12 =", AA[12].name)
