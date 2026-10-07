"""
Kaarigar - Golden-sample inspection test (core of the Inspector agent).

Compares each test image against its golden sample using Gemini on Vertex AI,
draws defect boxes, and reports accuracy against labels.csv.

Setup:
    pip install google-genai pydantic pillow
    gcloud auth application-default login
    export GOOGLE_CLOUD_PROJECT=your-project-id
    export GOOGLE_CLOUD_LOCATION=us-central1      # try "global" if the model isn't found
    export KAARIGAR_MODEL=gemini-2.5-flash        # replace with the latest Flash model in Vertex AI

Run:
    python inspect_test.py data/pairs
"""
import csv
import json
import os
import sys
from pathlib import Path
from typing import List, Literal

from google import genai
from google.genai import types
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

API_KEY = os.environ.get("GEMINI_API_KEY")          # AI Studio key (no billing needed)
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")    # Vertex AI (needs billing)
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
MODEL = os.environ.get("KAARIGAR_MODEL", "gemini-2.5-flash")
DATA_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "data/pairs")
OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)


# ---------- Structured output schema ----------
class Defect(BaseModel):
    type: Literal["scratch", "dent", "crack", "rust", "deformation",
                  "discoloration", "missing_material", "wrong_orientation", "other"]
    severity: Literal["minor", "major", "critical"]
    description: str
    box_2d: List[int] = Field(
        description="[ymin, xmin, ymax, xmax] on the inspected image, normalized 0-1000")


class Inspection(BaseModel):
    defect_found: bool
    defects: List[Defect]
    confidence: int = Field(description="0 to 100")
    recommendation: Literal["accept", "rework", "reject", "retake_photo"]


PROMPT = """You are an experienced quality inspector in a manufacturing plant.
Image 1 is the GOLDEN SAMPLE: a perfect, approved part.
Image 2 is the PART UNDER INSPECTION.

Compare Image 2 against Image 1. Report only real physical defects
(scratches, dents, cracks, rust, deformation, discoloration, missing material).
Also report wrong_orientation if the part is flipped, upside down, or mounted the
wrong way compared to the golden sample (check which face/features are visible).
Ignore differences caused only by lighting, shadows, background, or camera angle.

For each defect, give a tight bounding box on Image 2 as [ymin, xmin, ymax, xmax]
normalized to 0-1000.
If no defect exists, return defect_found=false, an empty defects list,
and recommendation "accept".
If the photo is too blurry, dark, or angled to judge, use low confidence
and recommendation "retake_photo". Never invent defects."""

if API_KEY:
    client = genai.Client(api_key=API_KEY)  # testing via Google AI Studio
    print("Using Google AI Studio API key")
elif PROJECT:
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    print("Using Gemini on Vertex AI")
else:
    sys.exit("Set GEMINI_API_KEY (AI Studio) or GOOGLE_CLOUD_PROJECT (Vertex AI).")


# ---------- Helpers ----------
def find_image(folder: Path, stem: str) -> Path:
    for ext in (".jpg", ".jpeg", ".png"):
        p = folder / f"{stem}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(f"{folder}/{stem}.jpg or .png not found")


def to_part(path: Path) -> types.Part:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=60),
       reraise=True)  # handles 429 rate limits on new projects
def inspect(golden: Path, test: Path) -> Inspection:
    resp = client.models.generate_content(
        model=MODEL,
        contents=[
            "Image 1 (GOLDEN SAMPLE):", to_part(golden),
            "Image 2 (PART UNDER INSPECTION):", to_part(test),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Inspection,
            temperature=0,
        ),
    )
    return resp.parsed if resp.parsed else Inspection.model_validate_json(resp.text)


def draw_boxes(test: Path, result: Inspection, out_path: Path) -> None:
    img = Image.open(test).convert("RGB")
    w, h = img.size
    d = ImageDraw.Draw(img)
    for df in result.defects:
        if len(df.box_2d) != 4:
            continue
        y0, x0, y1, x1 = df.box_2d
        box = [x0 * w / 1000, y0 * h / 1000, x1 * w / 1000, y1 * h / 1000]
        d.rectangle(box, outline="red", width=max(3, w // 200))
        d.text((box[0] + 4, box[1] + 4), f"{df.type} ({df.severity})", fill="red")
    img.save(out_path)


def load_labels() -> dict:
    labels = {}
    lf = DATA_DIR / "labels.csv"
    if lf.exists():
        with open(lf, newline="") as f:
            for row in csv.DictReader(f):
                labels[row["pair"].strip()] = row["has_defect"].strip().lower() == "true"
    return labels


# ---------- Main ----------
def main() -> None:
    labels = load_labels()
    pairs = sorted(p for p in DATA_DIR.iterdir() if p.is_dir())
    correct = total = 0
    results = {}

    print(f"Model: {MODEL} | Pairs: {len(pairs)}\n")
    for pair in pairs:
        try:
            golden, test = find_image(pair, "golden"), find_image(pair, "test")
            r = inspect(golden, test)
        except Exception as e:
            print(f"[{pair.name}] ERROR: {e}")
            continue

        results[pair.name] = r.model_dump()
        draw_boxes(test, r, OUT_DIR / f"{pair.name}_annotated.jpg")

        mark = ""
        if pair.name in labels:
            total += 1
            ok = r.defect_found == labels[pair.name]
            correct += ok
            mark = "PASS" if ok else "FAIL"

        print(f"[{pair.name}] defect={r.defect_found} conf={r.confidence} "
              f"rec={r.recommendation} {mark}")
        for df in r.defects:
            print(f"    - {df.type}/{df.severity}: {df.description}")

    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2))
    if total:
        print(f"\nAccuracy (defect yes/no): {correct}/{total} = {100 * correct / total:.0f}%")
    print(f"Annotated images saved in: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()