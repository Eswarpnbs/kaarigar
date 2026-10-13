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

_VOICE_CACHE: dict = {}


def _best_voice(lang: str):
    """Most natural available voice for the language: Chirp3-HD > Neural2 > Wavenet > Standard."""
    if lang in _VOICE_CACHE:
        return _VOICE_CACHE[lang]
    from google.cloud import texttospeech
    name = None
    try:
        names = [v.name for v in texttospeech.TextToSpeechClient().list_voices(language_code=lang).voices]
        for tier in ("Chirp3-HD", "Neural2", "Wavenet", "Standard"):
            m = sorted(n for n in names if tier in n)
            if m:
                name = m[0]; break
    except Exception:
        pass
    _VOICE_CACHE[lang] = name
    return name


@app.post("/api/speak")
def speak(req: SpeakRequest):
    from google.cloud import texttospeech
    lang = req.language_code if req.language_code in TTS_LANGS else "en-IN"
    text = req.text[:1500]
    try:
        if lang != "en-IN":
            text = gemini_client().models.generate_content(
                model=GEMINI_MODEL,
                contents=[f"Rewrite this for a senior machinist speaking to a new operator, in natural spoken language ({lang}). "
                          "Short, simple sentences. Keep common shop-floor words in English as workers say them "
                          "(machine, spindle, chuck, coolant, insert, vibration). Say numbers and units as words. "
                          "No bullet points, symbols or brackets. Output only the spoken text:\n" + text]).text
            text = text[:1600]
        name = _best_voice(lang)
        voice = (texttospeech.VoiceSelectionParams(language_code=lang, name=name) if name
                 else texttospeech.VoiceSelectionParams(language_code=lang))
        audio = texttospeech.TextToSpeechClient().synthesize_speech(
            input=texttospeech.SynthesisInput(text=text), voice=voice,
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
    display_box_2d: list[int] = Field(default_factory=list, description="[ymin, xmin, ymax, xmax] of the display that was read, 0-1000 scale")

CALIPER_PROMPT = """Read the measuring instrument display (digital caliper or micrometer) in this photo.
Report the digits EXACTLY as shown; do not round or guess. If several displays are visible, read the one
closest to the centre of the photo and mention that in the note. If the digits are not clearly readable
(blur, glare, cut off), set legible=false and confidence below 50. Unit: look for mm/in indicators. Also give display_box_2d: the box around the display you read."""



def _normalize_photo(data: bytes):
    """Straighten (EXIF) and re-encode once, so Gemini and Cloud Vision see the identical image."""
    import io
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    im.thumbnail((2000, 2000))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=90)
    return buf.getvalue(), im.size


def _vision_numbers(data: bytes, box, size):
    """Cloud Vision OCR numbers found INSIDE the display box (printed labels elsewhere don't count)."""
    try:
        import re as _re
        from google.cloud import vision
        resp = vision.ImageAnnotatorClient().text_detection(image=vision.Image(content=data))
        if resp.error.message or not box or len(box) != 4:
            return None
        W, H = size
        y0, x0, y1, x1 = box
        pad = 60
        inside = []
        for w in resp.text_annotations[1:]:
            vs = w.bounding_poly.vertices
            cx = sum(v.x for v in vs) / len(vs) / W * 1000
            cy = sum(v.y for v in vs) / len(vs) / H * 1000
            if x0 - pad <= cx <= x1 + pad and y0 - pad <= cy <= y1 + pad:
                inside.append(w.description.replace(",", "."))
        cands = inside + [a + b for a, b in zip(inside, inside[1:])]
        return sorted({float(x) for t in cands for x in _re.findall(r"\d+\.\d+", t)})
    except Exception:
        return None


@app.post("/api/measure")
async def measure(image: UploadFile = File(...), nominal: float = Form(...), tol: float = Form(...)):
    data = await image.read()
    if not data or len(data) > 15_000_000:
        raise HTTPException(413, "Photo is empty or too large.")
    if tol <= 0:
        raise HTTPException(400, "Tolerance must be greater than zero.")
    data, size = _normalize_photo(data)
    mime = "image/jpeg"
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
    vnums = _vision_numbers(data, r.display_box_2d, size)   # second reader, same place only
    if not vnums:
        cross = {"status": "not_checked", "note": "Cloud Vision found no readable digits at the display (common on LCD displays)."}
    else:
        agree = any(abs(n - r.reading) < 0.006 for n in vnums)
        cross = {"status": "agree" if agree else "disagree", "vision_numbers": vnums[:6]}
        if not agree and verdict in ("ok", "not_ok"):
            verdict, margin, near = "retake_photo", None, False   # readers disagree: never guess
    return {"verdict": verdict, "value_mm": value, "spec": {"nominal": nominal, "tol": tol, "min": lo, "max": hi},
            "margin_mm": margin, "near_limit": near, "reading": r.model_dump(),
            "cross_check": cross, "decided_by": "code (Gemini reads the digits; Cloud Vision OCR cross-checks)"}


# ---------------- Verify: re-check after the fix (decided in code) ----------------
class VerifyRequest(BaseModel):
    next_part_id: str
    vibration_mm_s: float


@app.post("/api/work-orders/{wo_id}/verify")
def verify_fix(wo_id: str, v: VerifyRequest, authorization: str | None = Header(default=None)):
    claims = _verify_supervisor(authorization)
    cache = INSPECTION_CACHE / f"{v.next_part_id}.json"
    try:
        ins = json.loads(cache.read_text()) if cache.exists() else run_inspection(v.next_part_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Part {v.next_part_id} not found")
    except Exception as e:
        raise HTTPException(503, f"Inspection service is busy, please try again ({type(e).__name__})")
    part_ok = not ins.get("defect_found")
    vib_ok = v.vibration_mm_s < 2.8          # ISO 10816-3 zones A/B = acceptable
    passed = part_ok and vib_ok
    note = (f"Next part {v.next_part_id}: {'no defect' if part_ok else 'DEFECT found'}; "
            f"vibration {v.vibration_mm_s} mm/s ({'acceptable, zone A/B' if vib_ok else 'still zone C/D'}). "
            f"Checked by supervisor uid {claims['uid'][:8]}… (Firebase Auth).")
    res = act.record_verification(wo_id, passed, note)
    if res.get("status") != "success":
        raise HTTPException(400, res.get("message", "Could not record the re-check"))
    learned = None
    if passed:
        try:
            from agents.memory import learn_from_work_order
            learned = learn_from_work_order(res["work_order"])
        except Exception as e:
            learned = {"error": type(e).__name__}
    return {**res, "part_ok": part_ok, "vibration_ok": vib_ok, "passed": passed, "learned": learned}


# ---------------- Prevent: SOP change proposals (Gemini drafts, supervisor approves) ----------------
class SopDecision(BaseModel):
    approve: bool


@app.post("/api/work-orders/{wo_id}/sop-change")
def sop_change(wo_id: str):
    from agents.prevent import propose_sop_change
    try:
        return propose_sop_change(wo_id)
    except Exception as e:
        raise HTTPException(503, f"Could not draft the SOP change, please try again ({type(e).__name__})")


@app.post("/api/sop-changes/{cid}/decision")
def sop_decision(cid: str, d: SopDecision, authorization: str | None = Header(default=None)):
    claims = _verify_supervisor(authorization)
    from agents.prevent import decide_sop_change
    return decide_sop_change(cid, d.approve, f"supervisor (Firebase Auth uid {claims['uid'][:8]}…)")


# ---------------- Budget guard: limits live (paid) Gemini calls; cached paths stay free ----------------
import os
import re as _re_guard
import time as _time_guard
from collections import defaultdict, deque
from fastapi import Request
from fastapi.responses import JSONResponse

LIVE_PER_IP_HOUR = int(os.environ.get("KAARIGAR_LIVE_PER_IP_HOUR", "40"))
LIVE_PER_DAY = int(os.environ.get("KAARIGAR_LIVE_PER_DAY", "600"))
_ip_hits = defaultdict(deque)
_day_local = {"d": "", "n": 0}
LIVE_RULES = [
    (r"^/api/inspect/([^/]+)$", "inspect"),
    (r"^/api/diagnose/([^/]+)$", "diagnose"),
    (r"^/api/diagnose-report$", None), (r"^/api/voice$", None), (r"^/api/speak$", None),
    (r"^/api/measure$", None), (r"^/api/inspect-upload$", None), (r"^/api/teach/[^/]+$", None), (r"^/api/work-orders/[^/]+/sop-change$", None),
    (r"^/api/work-orders/[^/]+$", None),          # create work order + 8D draft
]


def _client_ip(request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    return xff.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _daily_count() -> int:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    d = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d")
    if os.environ.get("KAARIGAR_STORE") == "firestore":
        try:
            from google.cloud import firestore
            ref = firestore.Client().collection("usage").document(d)
            ref.set({"live_calls": firestore.Increment(1)}, merge=True)
            return int((ref.get().to_dict() or {}).get("live_calls", 0))
        except Exception:
            pass
    if _day_local["d"] != d:
        _day_local.update(d=d, n=0)
    _day_local["n"] += 1
    return _day_local["n"]


@app.middleware("http")
async def live_budget(request, call_next):
    if request.method == "POST":
        path, fresh = request.url.path, request.query_params.get("fresh") in ("true", "1")
        for pat, kind in LIVE_RULES:
            m = _re_guard.match(pat, path)
            if not m:
                continue
            if kind == "inspect" and not fresh and (INSPECTION_CACHE / f"{m.group(1)}.json").exists():
                break                                   # cached: free
            if kind == "diagnose" and not fresh and (act.DIAG_CACHE / f"{m.group(1)}.json").exists():
                break                                   # cached: free
            ip, now = _client_ip(request), _time_guard.time()
            q = _ip_hits[ip]
            while q and now - q[0] > 3600:
                q.popleft()
            if len(q) >= LIVE_PER_IP_HOUR:
                return JSONResponse({"detail": "You've reached the live-demo limit for this hour. "
                                     "The demo buttons (cached results) still work; please try live features later."}, 429)
            if _daily_count() > LIVE_PER_DAY:
                return JSONResponse({"detail": "Today's live-demo budget is used up. The demo buttons "
                                     "(cached results) still work; live features reset at midnight IST."}, 429)
            q.append(now)
            break
    return await call_next(request)


# ---------------- Impact counter: counted from real stored data (no estimates) ----------------
@app.get("/api/impact")
def impact():
    def safe_list(c):
        try:
            return act.STORE.list(c)
        except Exception:
            return []
    wos = safe_list("work_orders")
    calls = 0
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        d = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d")
        if os.environ.get("KAARIGAR_STORE") == "firestore":
            from google.cloud import firestore
            calls = int((firestore.Client().collection("usage").document(d).get().to_dict() or {}).get("live_calls", 0))
        else:
            calls = _day_local["n"] if _day_local["d"] == d else 0
    except Exception:
        pass
    return {
        "defects_caught": len(wos),
        "repeat_problems": sum(1 for w in wos if w.get("recurrence")),
        "fixes_verified": sum(1 for w in wos if w.get("status") == "closed"),
        "reopened": sum(1 for w in wos if w.get("status") == "reopened"),
        "lessons_learned": len(safe_list("factory_memory")),
        "sop_improvements": sum(1 for c in safe_list("sop_changes") if c.get("status") == "approved"),
        "live_ai_calls_today": calls,
        "est_ai_cost_today_inr": round(calls * 0.6),      # measured avg ~₹0.3-0.8 per live call
    }


# ---------------- Supplier scorecard (rules in code, from Factory Memory) ----------------
@app.get("/api/suppliers")
def suppliers():
    from datetime import date
    from agents.diagnosis import _past
    today, rows = date.today(), {}
    for r in _past():
        if not r.get("supplier"):
            continue
        d = rows.setdefault(r["supplier"], {"supplier": r["supplier"], "material_issues": 0, "last_30_days": 0,
                                            "batches": {}, "types": {}})
        if r.get("category_6m") != "Material":
            continue                                  # listed, but only material problems count
        d["material_issues"] += 1
        try:
            if (today - date.fromisoformat(r["date"])).days <= 30:
                d["last_30_days"] += 1
        except Exception:
            pass
        b = r.get("batch") or "?"
        d["batches"][b] = d["batches"].get(b, 0) + 1
        d["types"][r["defect_type"]] = d["types"].get(r["defect_type"], 0) + 1
    out = []
    for d in rows.values():
        repeat = sorted(b for b, n in d["batches"].items() if n >= 2)
        rating = ("C · action (SCAR)" if (d["last_30_days"] >= 3 or repeat)
                  else "B · watch" if d["last_30_days"] >= 1 else "A · good")
        out.append({"supplier": d["supplier"], "material_issues": d["material_issues"],
                    "last_30_days": d["last_30_days"], "repeat_batches": repeat,
                    "top_defects": sorted(d["types"], key=d["types"].get, reverse=True)[:3], "rating": rating})
    out.sort(key=lambda x: (-x["last_30_days"], -x["material_issues"]))
    return {"suppliers": out,
            "rule": "Rated in code: C if 3+ material problems in 30 days or a repeat batch; B if any in 30 days; else A",
            "data_note": "Past records are SYNTHETIC samples; learned cases are added as Kaarigar is used"}


# ---------------- Inspect your own part (guided capture + photo-quality gate in code) ----------------
def _photo_quality(jpeg: bytes) -> dict:
    """Cheap checks in code BEFORE any Gemini call: exposure and sharpness."""
    import io
    from PIL import Image, ImageFilter, ImageStat
    g = Image.open(io.BytesIO(jpeg)).convert("L")
    g.thumbnail((800, 800))
    brightness = ImageStat.Stat(g).mean[0]
    sharpness = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]
    issues = []
    if brightness < 35:
        issues.append("too dark: add light")
    if brightness > 235:
        issues.append("too bright / glare: avoid direct light")
    if sharpness < 8:
        issues.append("blurry: hold steady and tap to focus")
    return {"brightness": round(brightness), "sharpness": round(sharpness, 1), "issues": issues}


@app.post("/api/inspect-upload")
async def inspect_upload(golden: UploadFile = File(...), test: UploadFile = File(...), machine_id: str = Form("IN")):
    import uuid
    g_raw, t_raw = await golden.read(), await test.read()
    if not g_raw or not t_raw or max(len(g_raw), len(t_raw)) > 15_000_000:
        raise HTTPException(413, "Please add both photos (each under 15 MB).")
    g, _ = _normalize_photo(g_raw)
    t, _ = _normalize_photo(t_raw)
    q = {"golden": _photo_quality(g), "test": _photo_quality(t)}
    if q["golden"]["issues"] or q["test"]["issues"]:
        return {"verdict": "retake_photo", "quality": q}
    pid = f"upload_{uuid.uuid4().hex[:8]}"
    d = Path(os.environ.get("KAARIGAR_PAIRS_DIR", "data/pairs")) / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "golden.jpg").write_bytes(g)
    (d / "test.jpg").write_bytes(t)
    try:
        ins = run_inspection(pid)
    except Exception as e:
        raise HTTPException(503, f"Inspection service is busy, please try again ({type(e).__name__})")
    return {"verdict": "inspected", "part_id": pid, "machine_id": machine_id, "inspection": ins, "quality": q}


# ---------------- Kaarigar Teaches: new-operator guide from SOPs + Factory Memory ----------------
@app.post("/api/teach/{machine_id}")
def teach_machine(machine_id: str):
    from agents.teach import teach
    try:
        return teach(machine_id)
    except Exception as e:
        raise HTTPException(503, f"Could not prepare the guide, please try again ({type(e).__name__})")

if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")