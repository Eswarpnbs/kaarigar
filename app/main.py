"""
Kaarigar web backend: hero-flow REST API + static frontend.
Local:  KAARIGAR_PAIRS_DIR=demo_parts uvicorn app.main:app --reload --port 8080
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents import action as act
from agents.diagnosis import CACHE as INSPECTION_CACHE, PAIRS, part_info, run_inspection
from agents.tools.machine_data import factory_overview, machine_health

app = FastAPI(title="Kaarigar", version="0.1")
STATIC = Path(__file__).parent / "static"


def _find(folder: Path, stem: str):
    for ext in (".png", ".jpg", ".jpeg"):
        if (folder / f"{stem}{ext}").exists():
            return folder / f"{stem}{ext}"
    return None


def _location(box) -> str:
    """Plain-words location from a [ymin, xmin, ymax, xmax] 0-1000 box (deterministic)."""
    if not box or len(box) != 4:
        return "unknown"
    y0, x0, y1, x1 = box
    cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
    v = "upper" if cy < 333 else ("lower" if cy > 666 else "middle")
    h = "left" if cx < 333 else ("right" if cx > 666 else "center")
    if v == "middle" and h == "center":
        return "center"
    return f"middle-{h}" if v == "middle" else (f"{v}-center" if h == "center" else f"{v}-{h}")


class Decision(BaseModel):
    approve: bool
    comment: str = ""


@app.get("/api/health")
def health():
    return {"status": "ok", "pairs_dir": str(PAIRS)}


@app.get("/api/parts")
def parts():
    if not PAIRS.exists():
        return {"parts": []}
    out = []
    for d in sorted(p for p in PAIRS.iterdir() if p.is_dir()):
        info = part_info(d.name)
        out.append({"part_id": d.name, "product": info.get("product", ""),
                    "machine_id": info.get("machine_id", ""),
                    "cached": (INSPECTION_CACHE / f"{d.name}.json").exists()})
    return {"parts": out}


@app.get("/api/parts/{part_id}/image/{which}")
def part_image(part_id: str, which: str):
    if which not in ("golden", "test"):
        raise HTTPException(400, "which must be golden or test")
    img = _find(PAIRS / part_id, which)
    if not img:
        raise HTTPException(404, "image not found")
    return FileResponse(img)


@app.post("/api/inspect/{part_id}")
def inspect_part(part_id: str, fresh: bool = False):
    cache = INSPECTION_CACHE / f"{part_id}.json"
    try:
        data = json.loads(cache.read_text()) if (cache.exists() and not fresh) else run_inspection(part_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(503, f"Inspection service is busy, please try again in a moment ({type(e).__name__})")
    for d in data.get("defects", []):
        d["location"] = _location(d.get("box_2d"))
    return {"part_id": part_id, "from_cache": cache.exists() and not fresh, **data}


@app.post("/api/diagnose/{part_id}")
def diagnose(part_id: str, fresh: bool = False):
    f = act.DIAG_CACHE / f"{part_id}.json"
    if fresh and f.exists():
        f.unlink()
    try:
        return act.get_diagnosis(part_id)
    except Exception as e:
        raise HTTPException(503, f"Diagnosis service is busy, please try again ({type(e).__name__})")


@app.post("/api/work-orders/{part_id}")
def create_work_order(part_id: str):
    return act.create_work_order(part_id)


@app.post("/api/work-orders/{wo_id}/decision")
def decide(wo_id: str, d: Decision):
    return act.decide_work_order(wo_id, d.approve, "supervisor", d.comment)


@app.get("/api/work-orders")
def work_orders():
    return act.list_work_orders()


@app.get("/api/work-orders/{wo_id}/8d", response_class=PlainTextResponse)
def eight_d(wo_id: str):
    wo = act.STORE.get("work_orders", wo_id)
    if not wo:
        raise HTTPException(404, "work order not found")
    return act.eight_d_markdown(wo)


@app.get("/api/factory")
def factory():
    return factory_overview()


@app.get("/api/machines/{machine_id}")
def machine(machine_id: str):
    return machine_health(machine_id)



# ---------------- Voice report + Text-to-Speech ----------------
from typing import Literal
from fastapi import File, UploadFile
from fastapi.responses import Response
from pydantic import Field
from google.genai import types as gtypes
from agents.inspector import MODEL as GEMINI_MODEL, _generate, client as gemini_client
from agents.diagnosis import MACHINES, diagnose as diagnose_report_fn

class VoiceReport(BaseModel):
    language: str = Field(description="language spoken, e.g. Kannada, Hindi, Telugu, English")
    language_code: str = Field(description="BCP-47 code: kn-IN, hi-IN, te-IN, ta-IN, ml-IN, mr-IN or en-IN")
    transcript_original: str
    transcript_english: str
    machine_id: str = Field(description="M1..M5 if mentioned or clearly implied, else empty")
    defect_type: Literal["scratch", "dent", "crack", "rust", "deformation", "discoloration", "missing_material",
                         "burr", "dimension_out_of_tolerance", "poor_surface_finish", "chatter_marks", "other"]
    description: str = Field(description="the problem in clear English, including any noise, smell, heat or vibration")

VOICE_PROMPT = """A worker in a small Indian machine shop is reporting a problem by voice. Transcribe exactly
(original language), translate to English, and fill the report. Machines in this shop:
M1 = CNC Lathe 1, M2 = CNC Lathe 2, M3 = Gear Hobbing Machine, M4 = Shaping Machine, M5 = Band Saw.
Map spoken names (e.g. "lathe one", "first lathe", "hobbing") to these IDs. If no machine is mentioned, leave
machine_id empty. Never invent details that were not said."""

@app.post("/api/voice")
async def voice(audio: UploadFile = File(...)):
    data = await audio.read()
    if not data or len(data) > 10_000_000:
        raise HTTPException(413, "Recording is empty or too long (keep it under about a minute).")
    mime = (audio.content_type or "audio/webm").split(";")[0]
    try:
        rep = _generate(GEMINI_MODEL, [gtypes.Part.from_bytes(data=data, mime_type=mime), VOICE_PROMPT], VoiceReport)
    except Exception as e:
        raise HTTPException(503, f"Could not understand the recording, please try again ({type(e).__name__})")
    return rep.model_dump()

class ProblemReport(BaseModel):
    machine_id: str
    defect_type: str
    description: str

@app.post("/api/diagnose-report")
def diagnose_report(r: ProblemReport):
    if r.machine_id not in MACHINES:
        raise HTTPException(400, "Please mention which machine (for example: lathe 1).")
    try:
        return diagnose_report_fn(r.machine_id, r.defect_type, r.description)
    except Exception as e:
        raise HTTPException(503, f"Diagnosis service is busy, please try again ({type(e).__name__})")

TTS_LANGS = {"en-IN", "hi-IN", "kn-IN", "te-IN", "ta-IN", "ml-IN", "mr-IN", "gu-IN", "bn-IN"}

class SpeakRequest(BaseModel):
    text: str
    language_code: str = "en-IN"

@app.post("/api/speak")
def speak(req: SpeakRequest):
    from google.cloud import texttospeech
    lang = req.language_code if req.language_code in TTS_LANGS else "en-IN"
    text = req.text[:1200]
    try:
        if lang != "en-IN":
            text = gemini_client().models.generate_content(
                model=GEMINI_MODEL,
                contents=[f"Translate for a factory supervisor into simple spoken language ({lang}). "
                          f"Keep machine IDs like M1 and numbers unchanged. Output only the translation:\n{text}"]).text
        audio = texttospeech.TextToSpeechClient().synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(language_code=lang),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)).audio_content
    except Exception as e:
        raise HTTPException(503, f"Speech is unavailable right now ({type(e).__name__})")
    return Response(content=audio, media_type="audio/mpeg")

if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")