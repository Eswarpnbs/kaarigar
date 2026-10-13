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


from fastapi import Header


def _verify_supervisor(authorization):
    """Firebase Authentication: approvals require a signed-in supervisor (ID token verified server-side)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please sign in as a supervisor to approve or reject.")
    try:
        import os
        import firebase_admin
        from firebase_admin import auth as fb_auth
        if not firebase_admin._apps:
            firebase_admin.initialize_app(options={"projectId": os.environ.get("GOOGLE_CLOUD_PROJECT", "kaarigar-510716")})
        return fb_auth.verify_id_token(authorization.split(" ", 1)[1])
    except Exception as e:
        raise HTTPException(401, f"Sign-in could not be verified ({type(e).__name__}). Please sign in again.")


@app.post("/api/work-orders/{wo_id}/decision")
def decide(wo_id: str, d: Decision, authorization: str | None = Header(default=None)):
    claims = _verify_supervisor(authorization)
    provider = claims.get("firebase", {}).get("sign_in_provider", "unknown")
    who = f"supervisor (Firebase Auth uid {claims['uid'][:8]}…, {provider})"
    return act.decide_work_order(wo_id, d.approve, who, d.comment)


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
    f = factory_overview()
    try:
        from agents.tools.forecast import forecast_all
        fa = forecast_all()
        for m in f.get("machines", []):
            fc = fa.get(m["machine_id"])
            if fc and fc.get("status") == "success":
                m["zone"] = fc["zone"]
                m["hours_to_zone_d"] = fc["hours_to_zone_d"]["expected"]
    except Exception:
        pass
    return f



@app.get("/api/map")
def factory_map():
    from agents.diagnosis import MACHINES as MCH
    from agents.tools.forecast import forecast_all, history_all
    f = factory_overview()
    try:
        fa, hist = forecast_all(), history_all(24)
    except Exception:
        fa, hist = {}, {}
    out = []
    for m in f.get("machines", []):
        mid = m["machine_id"]; fc = fa.get(mid, {})
        out.append({**m, "name": MCH.get(mid, ("", ""))[0],
                    "zone": fc.get("zone"), "zone_meaning": fc.get("zone_meaning"),
                    "latest_vibration": fc.get("latest_vibration"),
                    "hours_to_zone_d": (fc.get("hours_to_zone_d") or {}).get("expected"),
                    "history": hist.get(mid, []), "forecast": (fc.get("forecast") or [])[:12]})
    return {"machines": out, "data_note": "SIMULATED sensor data"}

@app.get("/api/forecast/{machine_id}")
def forecast(machine_id: str):
    from agents.tools.forecast import forecast_machine
    return forecast_machine(machine_id)


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


# ---------------- Caliper check: Gemini reads the display, code decides OK / NOT OK ----------------
from fastapi import Form

class CaliperReading(BaseModel):
    legible: bool
    display_text: str = Field(description="digits exactly as shown on the display, e.g. 40.53")
    reading: float = Field(description="numeric value shown; 0 if not legible")
    unit: Literal["mm", "inch", "unknown"]
    confidence: int = Field(description="0-100: how sure the digits are read correctly")
    note: str = Field(description="short note, e.g. glare, several displays, blurry")

CALIPER_PROMPT = """Read the measuring instrument display (digital caliper or micrometer) in this photo.
Report the digits EXACTLY as shown; do not round or guess. If several displays are visible, read the one
closest to the centre of the photo and mention that in the note. If the digits are not clearly readable
(blur, glare, cut off), set legible=false and confidence below 50. Unit: look for mm/in indicators."""

@app.post("/api/measure")
async def measure(image: UploadFile = File(...), nominal: float = Form(...), tol: float = Form(...)):
    data = await image.read()
    if not data or len(data) > 15_000_000:
        raise HTTPException(413, "Photo is empty or too large.")
    if tol <= 0:
        raise HTTPException(400, "Tolerance must be greater than zero.")
    mime = image.content_type or "image/jpeg"
    try:
        r: CaliperReading = _generate(GEMINI_MODEL, [gtypes.Part.from_bytes(data=data, mime_type=mime), CALIPER_PROMPT], CaliperReading)
    except Exception as e:
        raise HTTPException(503, f"Could not read the photo, please try again ({type(e).__name__})")
    value = round(r.reading * (25.4 if r.unit == "inch" else 1.0), 3)
    lo, hi = round(nominal - tol, 3), round(nominal + tol, 3)
    if not r.legible or r.confidence < 60:
        verdict, margin, near = "retake_photo", None, False
    else:
        ok = lo - 1e-9 <= value <= hi + 1e-9
        verdict = "ok" if ok else "not_ok"
        margin = round(min(value - lo, hi - value), 3)          # distance to nearest limit (negative = outside)
        near = ok and margin <= 0.2 * tol                        # within 20% of the band edge
    return {"verdict": verdict, "value_mm": value, "spec": {"nominal": nominal, "tol": tol, "min": lo, "max": hi},
            "margin_mm": margin, "near_limit": near, "reading": r.model_dump(),
            "decided_by": "code (Gemini only reads the digits)"}

if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")