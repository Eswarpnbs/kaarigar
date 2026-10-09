"""
Kaarigar Inspector v3 — golden-sample inspection with detail scan, verification,
and zoom-in refinement.

Pipeline:
  1. Detect (sensitive):  compare the test part with 1-3 golden samples; flag anything
                          that might be a defect.
  2. Detail scan:         if nothing was flagged, look again at 4 zoomed tiles in one call
                          (catches small defects on small parts).
  3. Verify + refine:     for each candidate, show the verifier the FULL part and a ZOOMED
                          CROP; it confirms with a tight box or dismisses as normal variation.
                          A flag may only be dismissed with confidence >= DISMISS_CONFIDENCE;
                          otherwise the part is escalated to a human.
  4. Rules:               consistency between findings and recommendation.

Env:
  GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION (default "global")
  KAARIGAR_MODEL         (default gemini-2.5-flash)
  KAARIGAR_VERIFY_MODEL  (default = KAARIGAR_MODEL)
"""
import io
import os
from pathlib import Path
from typing import List, Literal, Sequence, Tuple, Union

from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

MODEL = os.environ.get("KAARIGAR_MODEL", "gemini-2.5-flash")
VERIFY_MODEL = os.environ.get("KAARIGAR_VERIFY_MODEL", MODEL)
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
MAX_DEFECTS_TO_VERIFY = 4
DISMISS_CONFIDENCE = 90          # verifier must be this sure to dismiss a flag
TILE_SIDE = 0.6                  # 4 overlapping tiles, each 60% of the image side
TILES: List[Tuple[float, float]] = [(0.0, 0.0), (0.0, 0.4), (0.4, 0.0), (0.4, 0.4)]  # (top, left)

_client = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    return _client


# ---------------- Schemas ----------------
DefectType = Literal["scratch", "dent", "crack", "rust", "deformation", "discoloration",
                     "missing_material", "wrong_orientation", "other"]
Severity = Literal["minor", "major", "critical"]
Recommendation = Literal["accept", "rework", "reject", "retake_photo"]


class Defect(BaseModel):
    type: DefectType
    severity: Severity
    description: str
    box_2d: List[int] = Field(description="[ymin, xmin, ymax, xmax] normalized 0-1000")


class Inspection(BaseModel):
    defect_found: bool
    defects: List[Defect]
    confidence: int = Field(description="0 to 100")
    recommendation: Recommendation
    notes: str = Field(default="", description="short note on how the decision was made")


class TileDefect(BaseModel):
    tile: int = Field(description="1=top-left, 2=top-right, 3=bottom-left, 4=bottom-right")
    type: DefectType
    severity: Severity
    description: str
    box_2d: List[int] = Field(description="box inside THAT TILE, [ymin, xmin, ymax, xmax] 0-1000")


class DetailScan(BaseModel):
    defects: List[TileDefect]


class Verification(BaseModel):
    is_real_defect: bool
    type: DefectType
    severity: Severity
    description: str
    box_2d: List[int] = Field(description="tight box in THE ZOOMED CROP, [ymin, xmin, ymax, xmax] 0-1000")
    confidence: int = Field(description="0 to 100")
    reason: str


# ---------------- Prompts ----------------
DETECT_PROMPT = """You are an experienced quality inspector in a small manufacturing plant.
The GOLDEN SAMPLES are approved good parts. Together they show NORMAL variation:
good parts may be rotated, shifted, or lit differently, and surface texture, machining
marks, and small reflections vary naturally between good parts.

Inspect the PART UNDER INSPECTION carefully, including edges, tips, threads, heads,
and the overall shape compared with the golden samples. Small defects matter.
If something MIGHT be a defect, report it: a second inspector will verify every flag.
Possible defects: scratch, dent, crack, rust, deformation or bent feature,
discoloration or stain, missing material, changed shape, or wrong orientation
(the opposite face of the part is visible).

Do NOT report pure rotation or position differences, lighting, shadows, reflections,
or background.

For each possible defect, give a tight bounding box on the PART UNDER INSPECTION as
[ymin, xmin, ymax, xmax] normalized to 0-1000. For long thin defects such as scratches,
cover the full length. Describe only what is visible; do not guess causes.

If there is clearly no defect: defect_found=false, empty list, recommendation "accept".
If the image is too blurry, dark, or angled to judge: low confidence and "retake_photo"."""

DETAIL_PROMPT = """These are 4 ZOOMED, overlapping tiles of the PART UNDER INSPECTION:
tile 1 = top-left, tile 2 = top-right, tile 3 = bottom-left, tile 4 = bottom-right.
Compare against the golden samples (approved good parts; rotation, texture, machining
marks, lighting, and reflections are normal variation).

Look closely for SMALL defects a quick glance could miss: scratches, nicks, dents,
cracks, stains, damaged or missing material, deformed tips, edges, threads, or heads.
For each possible defect, give the tile number and a tight box INSIDE THAT TILE as
[ymin, xmin, ymax, xmax] normalized 0-1000. If you see nothing suspicious, return an
empty list. Describe only what is visible."""

VERIFY_PROMPT = """An earlier inspection pass flagged a possible defect:
  type: {type}
  description: {description}

You are given the golden samples (approved good parts), the FULL VIEW of the part under
inspection, and a ZOOMED CROP around the flagged region. Rotation, texture, machining
marks, lighting, and reflections are normal variation. Use the full view to judge shape
and geometry (for example a deformed tip or edge) and the crop to judge surface detail.

Decide: is there a REAL defect here that a quality inspector would reject or rework?
- If yes: is_real_defect=true; correct the type, severity, and description if needed;
  give a TIGHT box around the defect in THE ZOOMED CROP as [ymin, xmin, ymax, xmax] 0-1000.
  For long thin defects, cover the full visible length.
- If it is normal variation: is_real_defect=false and explain in reason.
- confidence: how sure you are, 0-100. Only use 90+ if you are truly certain.
Describe only what is visible."""


# ---------------- Helpers ----------------
def _part(img: Image.Image) -> types.Part:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=92)
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=60),
       reraise=True)
def _generate(model: str, contents: list, schema):
    resp = client().models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0,
        ),
    )
    return resp.parsed if resp.parsed is not None else schema.model_validate_json(resp.text)


def _crop(img: Image.Image, top: float, left: float, side: float) -> Image.Image:
    w, h = img.size
    return img.crop((int(left * w), int(top * h), int((left + side) * w), int((top + side) * h)))


def _crop_window(box: Sequence[int], margin: float = 0.5, min_side: float = 0.3):
    """Square crop window (normalized 0-1) around a box, with margin."""
    y0, x0, y1, x1 = [v / 1000 for v in box]
    y0, y1 = sorted((y0, y1))
    x0, x1 = sorted((x0, x1))
    cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
    side = max((y1 - y0) * (1 + 2 * margin), (x1 - x0) * (1 + 2 * margin), min_side)
    side = min(1.0, side)
    top = min(max(0.0, cy - side / 2), 1 - side)
    left = min(max(0.0, cx - side / 2), 1 - side)
    return top, left, side


def _crop_to_full(box: Sequence[int], top: float, left: float, side: float) -> List[int]:
    yc0, xc0, yc1, xc1 = box
    return [
        round((top + yc0 / 1000 * side) * 1000),
        round((left + xc0 / 1000 * side) * 1000),
        round((top + yc1 / 1000 * side) * 1000),
        round((left + xc1 / 1000 * side) * 1000),
    ]


def _golden_parts(golden_imgs: List[Image.Image]) -> list:
    parts = []
    for i, g in enumerate(golden_imgs, 1):
        parts += [f"GOLDEN SAMPLE {i} (approved good part):", _part(g)]
    return parts


def _consistent(r: Inspection) -> Inspection:
    """Business rules so the recommendation always matches the findings."""
    if r.defect_found and r.defects and r.recommendation == "accept":
        critical = any(d.severity == "critical" for d in r.defects)
        r.recommendation = "reject" if critical else "rework"
    if (not r.defect_found or not r.defects) and r.recommendation in ("reject", "rework"):
        r.defect_found = False
        r.recommendation = "retake_photo"
    return r


def _resolve_goldens(golden: Union[Path, Sequence[Path]]) -> List[Path]:
    """Accept one golden path (siblings golden*.png/jpg are auto-added) or a list."""
    if isinstance(golden, (str, Path)):
        g = Path(golden)
        siblings = sorted(p for p in g.parent.glob("golden*")
                          if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
        return siblings or [g]
    return [Path(p) for p in golden]


def _detail_scan(golden_imgs: List[Image.Image], test_img: Image.Image) -> List[Defect]:
    contents = _golden_parts(golden_imgs)
    for i, (top, left) in enumerate(TILES, 1):
        contents += [f"TILE {i}:", _part(_crop(test_img, top, left, TILE_SIDE))]
    contents.append(DETAIL_PROMPT)
    scan: DetailScan = _generate(MODEL, contents, DetailScan)
    found = []
    for td in scan.defects:
        if not (1 <= td.tile <= 4) or len(td.box_2d) != 4:
            continue
        top, left = TILES[td.tile - 1]
        found.append(Defect(type=td.type, severity=td.severity, description=td.description,
                            box_2d=_crop_to_full(td.box_2d, top, left, TILE_SIDE)))
    return found


# ---------------- Main entry ----------------
def inspect(golden: Union[Path, Sequence[Path]], test: Path) -> Inspection:
    """Inspect a part photo against one or more golden samples."""
    golden_imgs = [Image.open(p) for p in _resolve_goldens(golden)[:3]]
    test_img = Image.open(test)

    # 1. Sensitive detection
    contents = _golden_parts(golden_imgs) + ["PART UNDER INSPECTION:", _part(test_img), DETECT_PROMPT]
    first: Inspection = _generate(MODEL, contents, Inspection)
    candidates = list(first.defects) if first.defect_found else []
    source = "first pass"

    # 2. Detail scan if nothing was flagged (and the photo is usable)
    if not candidates and first.recommendation != "retake_photo":
        candidates = _detail_scan(golden_imgs, test_img)
        source = "detail scan"

    if not candidates:
        first.defect_found, first.defects = False, []
        first.notes = "no defect in first pass or detail scan"
        return _consistent(first)

    # 3. Verify + zoom-in refine each candidate (full view + crop)
    confirmed: List[Defect] = []
    verifier_conf: List[int] = []
    unsure = False
    for d in candidates[:MAX_DEFECTS_TO_VERIFY]:
        if len(d.box_2d) != 4:
            continue
        top, left, side = _crop_window(d.box_2d)
        vcontents = _golden_parts(golden_imgs) + [
            "FULL VIEW of the part under inspection:", _part(test_img),
            "ZOOMED CROP of the flagged region:", _part(_crop(test_img, top, left, side)),
            VERIFY_PROMPT.format(type=d.type, description=d.description),
        ]
        v: Verification = _generate(VERIFY_MODEL, vcontents, Verification)
        verifier_conf.append(v.confidence)
        if v.is_real_defect and len(v.box_2d) == 4:
            confirmed.append(Defect(type=v.type, severity=v.severity, description=v.description,
                                    box_2d=_crop_to_full(v.box_2d, top, left, side)))
        elif v.confidence < DISMISS_CONFIDENCE:
            unsure = True

    # 4. Decide (asymmetric: dismissing a flag needs high confidence)
    avg_v = round(sum(verifier_conf) / len(verifier_conf)) if verifier_conf else first.confidence
    if confirmed:
        critical = any(d.severity == "critical" for d in confirmed)
        result = Inspection(defect_found=True, defects=confirmed,
                            confidence=round((first.confidence + avg_v) / 2),
                            recommendation="reject" if critical else "rework",
                            notes=f"{len(confirmed)} defect(s) from {source}, confirmed by verifier")
    elif unsure:
        result = Inspection(defect_found=False, defects=[], confidence=40,
                            recommendation="retake_photo",
                            notes=f"{source} flagged a defect; verifier unsure -> human check")
    else:
        result = Inspection(defect_found=False, defects=[], confidence=avg_v,
                            recommendation="accept",
                            notes=f"{source} flags dismissed confidently by verifier")
    return _consistent(result)