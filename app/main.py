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


if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")