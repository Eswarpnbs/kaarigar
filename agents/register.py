"""Import a photographed PAPER REGISTER page into Factory Memory (Gemini reads; code validates; supervisor approves)."""
import hashlib
import json
import os
import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from agents.inspector import _generate

MODEL = os.environ.get("KAARIGAR_MODEL", "gemini-2.5-flash")
DEFECTS = ("scratch", "dent", "crack", "rust", "deformation", "discoloration", "missing_material", "burr",
           "dimension_out_of_tolerance", "poor_surface_finish", "chatter_marks", "other")
SIXM = ("Machine", "Method", "Material", "Man", "Measurement", "Environment", "Unknown")


class RegRow(BaseModel):
    date_text: str
    part: str
    machine_text: str
    machine_id: str = Field(description="M1..M5, or IN for incoming material, only if clear; else empty")
    defect_text: str
    defect_type: Literal[DEFECTS]
    cause: str
    fix: str
    supplier: str = ""
    batch: str = ""
    category_6m: Literal[SIXM]
    legible: bool


class RegPage(BaseModel):
    rows: list[RegRow]
    notes: str = ""


PROMPT = ("Photo of a handwritten register page from a small machine shop. Extract ONE item per written row, in order. "
          "Copy what is written; never guess. Unreadable cell: leave it empty and set legible=false. Machines: M1 CNC Lathe 1, "
          "M2 CNC Lathe 2, M3 Gear Hobbing, M4 Shaping, M5 Band Saw, IN incoming material. Map defect words to the closest "
          "defect_type (else 'other') and the cause to a 6M category (else 'Unknown').")

DATE_FORMATS = ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d",
                "%d %b %Y", "%d %B %Y", "%d %b %y"]


def _parse_date(t):
    t = re.sub(r"\s+", " ", (t or "").strip())
    for f in DATE_FORMATS:
        try:
            d = datetime.strptime(t, f).date()
            if date(2015, 1, 1) <= d <= date.today():
                return d.isoformat()
        except ValueError:
            pass
    return None


def validate(row: dict) -> dict:
    """Every field checked in code. Anything unclear -> needs_check (never guessed)."""
    from agents.diagnosis import MACHINES
    issues = []
    d = _parse_date(row.get("date_text"))
    if not d:
        issues.append("date unclear")
    if row.get("machine_id") not in MACHINES:
        issues.append("machine unclear")
    if row.get("defect_type") not in DEFECTS or row.get("defect_type") == "other":
        issues.append("defect type unclear")
    if not (row.get("cause") or "").strip():
        issues.append("cause missing")
    if not (row.get("fix") or "").strip():
        issues.append("fix missing")
    if not row.get("legible", True):
        issues.append("hard to read")
    return {**row, "date": d, "status": "ok" if not issues else "needs_check", "issues": issues}


def read_register(jpeg: bytes) -> dict:
    from google.genai import types as gt
    page = _generate(MODEL, [gt.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), PROMPT], RegPage)
    rows = [validate(r.model_dump()) for r in page.rows]
    return {"rows": rows, "notes": page.notes, "ok": sum(r["status"] == "ok" for r in rows)}


def commit_rows(rows: list, approver: str) -> dict:
    """Re-validates in code; only clean rows enter Factory Memory (with an embedding for meaning-based search)."""
    from agents.action import STORE, _now
    from agents.memory import embed, record_text
    added = []
    for r in rows:
        v = validate(dict(r))
        if v["status"] != "ok":
            continue
        key = "R-" + hashlib.sha1(json.dumps([v["date"], v["machine_id"], v["defect_text"], v["cause"]]).encode()).hexdigest()[:8]
        rec = {"defect_id": key, "date": v["date"], "machine_id": v["machine_id"], "product": v.get("part", ""),
               "defect_type": v["defect_type"], "severity": "unknown", "description": v["defect_text"],
               "root_cause": v["cause"], "category_6m": v["category_6m"], "fix": v["fix"], "fix_verified": False,
               "supplier": v.get("supplier", ""), "batch": v.get("batch", ""), "downtime_hours": 0, "scrap_qty": 0,
               "synthetic": False, "source": f"imported from paper register, approved by {approver} at {_now()}"}
        try:
            rec["vector"] = embed([record_text(rec)], "RETRIEVAL_DOCUMENT")[0]
        except Exception:
            pass
        STORE.put("factory_memory", key, rec)
        added.append(key)
    try:
        from agents import memory
        memory._learned_cache["t"] = 0.0
    except Exception:
        pass
    return {"added": added, "skipped": len(rows) - len(added)}