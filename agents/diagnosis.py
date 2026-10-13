"""
Kaarigar Diagnosis agent core: evidence is gathered in CODE (machine health, Factory Memory,
supplier history, SOPs); Gemini reasons over it and returns a structured root-cause report.
Citations are validated in code; invalid ones are removed and flagged.

Test:  python -m agents.diagnosis metal_nut_scratch_0
"""
import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from agents.inspector import _generate, inspect
from agents.tools.machine_data import machine_health

REPO = Path(__file__).resolve().parents[1]
SEED = REPO / "data" / "seed"
PAIRS = Path(os.environ.get("KAARIGAR_PAIRS_DIR", str(REPO / "data" / "pairs")))
CACHE = REPO / "data" / "cache" / "inspections"
MODEL = os.environ.get("KAARIGAR_DIAGNOSIS_MODEL", os.environ.get("KAARIGAR_MODEL", "gemini-2.5-flash"))

MACHINES = {
    "M1": ("CNC Lathe 1", "cnc_lathe"), "M2": ("CNC Lathe 2", "cnc_lathe"),
    "M3": ("Gear Hobbing Machine", "gear_hobbing"), "M4": ("Shaping Machine", "shaper"),
    "M5": ("Band Saw", "band_saw"), "IN": ("Incoming material inspection", "incoming"),
}
# Inspector defect type -> related shop-floor defect types in Factory Memory
RELATED = {
    "scratch": {"scratch", "poor_surface_finish", "chatter_marks", "burr"},
    "dent": {"dent", "deformation", "dimension_out_of_tolerance"},
    "crack": {"crack"},
    "rust": {"rust", "pit"},
    "deformation": {"deformation", "dimension_out_of_tolerance", "chatter_marks"},
    "discoloration": {"discoloration", "burn_marks"},
    "missing_material": {"burr", "rough_cut", "pit", "dimension_out_of_tolerance"},
    "wrong_orientation": {"dimension_out_of_tolerance"},
}
SEVERITY_RANK = {"critical": 3, "major": 2, "minor": 1}


# ---------------- Schemas ----------------
Category = Literal["Machine", "Method", "Material", "Man", "Measurement", "Environment"]


class Cause(BaseModel):
    cause: str
    category_6m: Category
    likelihood: Literal["high", "medium", "low"]
    evidence: List[str] = Field(description="short evidence statements in plain words")
    evidence_sources: List[str] = Field(description="ids from the evidence, e.g. machine_health:M1, past_defect:D016, SOP-02, inspection")


class Why(BaseModel):
    question: str
    answer: str


class Action(BaseModel):
    action: str
    owner_role: Literal["operator", "supervisor", "maintenance", "quality", "purchase"]
    urgency: Literal["immediate", "today", "this_week"]
    sop_ref: str = ""


class RootCauseReport(BaseModel):
    summary: str
    likely_causes: List[Cause]
    five_whys: List[Why]
    recommended_actions: List[Action]
    similar_case_id: str = Field(default="", description="best matching past defect id, or empty")
    similar_case_note: str = ""
    confidence: int = Field(description="0 to 100")
    needs_human_check: bool
    missing_information: List[str]


PROMPT = """You are Kaarigar's Diagnosis agent: an experienced quality engineer in a small machine shop.
Find the most likely ROOT CAUSE of the defect using ONLY the evidence below.
Rules:
- Rank at most 3 causes, using 6M categories (Machine, Method, Material, Man, Measurement, Environment).
- A cause must explain WHY the defect happened, never restate the defect itself (wrong: "material is rusty";
  right: "bars stored wet at the supplier without oiling"). If past records give a root cause for the same
  machine or supplier batch, use it. For repeated supplier problems, recommend a formal supplier corrective
  action request (SCAR), quarantine of the batch, and tighter incoming checks for that supplier.
- Every cause must cite evidence_sources using ONLY the ids shown in the evidence (keys like
  "machine_health:M1", "past_defect:D016", "SOP-02", "inspection", "part", "supplier_history", "recurrence_check", "forecast:M1").
- Do not invent numbers, dates, or records. If evidence is weak or conflicting, say so, lower the
  confidence, set needs_human_check=true, and list missing_information.
- five_whys: exactly 5 steps, from the visible defect down to a root cause someone can fix.
- Actions must be practical for a small shop; reference SOP ids when relevant.
- If recurrence_check is present, a recent fix did not last. Make the 5 Whys explain WHY the
  earlier fix failed (e.g. lubrication, installation, contamination, part quality) and add an action
  to verify the earlier fix (CAPA effectiveness). Cite recurrence_check.
- If a forecast is present (computed by BigQuery ML, not by you), state in the summary how many hours
  remain before the damage zone if nothing is done, set action urgency to match, and cite forecast:<machine>.
- Machine sensor data is SIMULATED in this prototype; still reason from it.

EVIDENCE (JSON):
{evidence}"""


# ---------------- Evidence helpers (deterministic) ----------------
@lru_cache(maxsize=1)
def _seed_past() -> list:
    return json.loads((SEED / "past_defects.json").read_text())


def _past() -> list:
    """Seed records + cases Kaarigar has learned from verified fixes (Learn step)."""
    try:
        from agents.memory import learned_cases
        learned = [{k: v for k, v in r.items() if k != "vector"} for r in learned_cases()]
    except Exception:
        learned = []
    return _seed_past() + learned


@lru_cache(maxsize=1)
def _sops() -> dict:
    return {p.name.split("_")[0]: p.read_text() for p in sorted((SEED / "sops").glob("SOP-*.md"))}


def part_info(part_id: str) -> dict:
    rules = json.loads((SEED / "parts.json").read_text())["rules"]
    for r in rules:
        if part_id.startswith(r["prefix"]):
            return {k: v for k, v in r.items() if k != "prefix"} | {"part_id": part_id}
    return {"part_id": part_id, "machine_id": "", "product": "", "supplier": "", "batch": ""}


def similar_past_defects(machine_id: str, defect_type: str, product: str = "",
                         supplier: str = "", batch: str = "", k: int = 3) -> list:
    related = RELATED.get(defect_type, set()) | {defect_type}
    scored = []
    for r in _past():
        s = 0
        s += 3 if r["machine_id"] == machine_id else 0
        s += 3 if r["defect_type"] in related else 0
        s += 1 if product and r["product"] == product else 0
        s += 2 if batch and r["batch"] == batch else (1 if supplier and r["supplier"] == supplier else 0)
        if s >= 4:
            scored.append((s, r["date"], r))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r for _, _, r in scored[:k]]


def supplier_history(supplier: str, batch: str = "") -> dict:
    rs = [r for r in _past() if supplier and r["supplier"] == supplier and r["category_6m"] == "Material"]
    return {
        "supplier": supplier,
        "material_issues_total": len(rs),
        "same_batch_issues": sum(1 for r in rs if batch and r["batch"] == batch),
        "examples": [{k: r[k] for k in ("defect_id", "date", "defect_type", "root_cause", "batch")}
                     for r in rs[:3]],
    }


def select_sops(machine_id: str, defect_type: str, hints: List[str]) -> List[str]:
    mtype = MACHINES.get(machine_id, ("", ""))[1]
    chosen = []
    if mtype == "cnc_lathe":
        chosen.append("SOP-01")
    if "bearing_wear" in hints or (mtype == "cnc_lathe" and defect_type in {"scratch", "deformation"}):
        chosen.append("SOP-02")
    if "coolant_failure" in hints or defect_type == "discoloration":
        chosen.append("SOP-03")
    if machine_id == "IN" or defect_type in {"rust", "crack"}:
        chosen.append("SOP-04")
    if mtype == "gear_hobbing":
        chosen.append("SOP-05")
    return [s for s in dict.fromkeys(chosen) if s in _sops()]


# ---------------- Main entry ----------------
def diagnose(machine_id: str, defect_type: str, description: str, product: str = "",
             supplier: str = "", batch: str = "", inspection: Optional[dict] = None) -> dict:
    evidence, valid = {}, set()

    evidence["part"] = {"machine_id": machine_id, "machine_name": MACHINES.get(machine_id, ("", ""))[0],
                        "product": product, "supplier": supplier, "batch": batch}
    evidence["inspection"] = inspection or {"defect_type": defect_type, "description": description}
    valid |= {"part", "inspection"}

    hints = []
    if machine_id in MACHINES and machine_id != "IN":
        mh = machine_health(machine_id)
        if mh.get("status") == "success":
            evidence[f"machine_health:{machine_id}"] = mh
            valid.add(f"machine_health:{machine_id}")
            hints = [h["problem"] for h in mh.get("pattern_hints", [])]
            try:
                from agents.tools.forecast import forecast_machine
                fc = forecast_machine(machine_id)
                if fc.get("status") == "success":
                    evidence[f"forecast:{machine_id}"] = {k: fc[k] for k in (
                        "machine_id", "model", "latest_vibration", "zone", "zone_meaning", "limit", "hours_to_zone_d", "data_note")}
                    valid.add(f"forecast:{machine_id}")
            except Exception:
                pass

    similar = similar_past_defects(machine_id, defect_type, product, supplier, batch)
    similar_kw = list(similar)                      # keyword matches (used for confidence)
    try:
        from agents.memory import semantic_search
        sem = semantic_search(f"{MACHINES.get(machine_id, ('', ''))[0]} {product} {defect_type}: {description}",
                              k=3, min_score=0.65)
    except Exception:
        sem = []
    by_id = {r["defect_id"]: r for r in _past()}
    for did, _score in sem:                          # add meaning-based matches (Factory Memory)
        if did in by_id and all(x["defect_id"] != did for x in similar):
            similar.append(by_id[did])
    similar = similar[:5]
    for r in similar:
        evidence[f"past_defect:{r['defect_id']}"] = r
        valid.add(f"past_defect:{r['defect_id']}")

    # Recurrence check (CAPA effectiveness): same machine + same failure mode fixed recently?
    from datetime import date
    keywords = {"bearing_wear": "bearing", "tool_wear": ("insert", "tool", "blade"),
                "coolant_failure": "coolant", "spindle_misalignment": "align"}
    today = date.today()
    recur = []
    for h in hints:
        kw = keywords.get(h, ())
        kw = (kw,) if isinstance(kw, str) else kw
        for r in _past():
            days = (today - date.fromisoformat(r["date"])).days
            if (r["machine_id"] == machine_id and r.get("fix_verified") and days <= 30
                    and any(k in r["root_cause"].lower() for k in kw)):
                recur.append({"defect_id": r["defect_id"], "date": r["date"], "days_ago": days,
                              "root_cause": r["root_cause"], "fix": r["fix"], "matches_hint": h})
    if supplier and batch:
        fam = RELATED.get(defect_type, set()) | {defect_type}
        for r in _past():
            days = (today - date.fromisoformat(r["date"])).days
            if (r["supplier"] == supplier and r["batch"] == batch and r["defect_type"] in fam
                    and r.get("category_6m") == "Material"
                    and r.get("fix_verified") and days <= 45
                    and not any(c["defect_id"] == r["defect_id"] for c in recur)):
                recur.append({"defect_id": r["defect_id"], "date": r["date"], "days_ago": days,
                              "root_cause": r["root_cause"], "fix": r["fix"],
                              "matches_hint": f"same supplier batch {batch}"})
    if recur:
        evidence["recurrence_check"] = {
            "warning": "The same problem (same machine or same supplier batch) was handled recently and has "
                       "come back: the earlier fix did not address the true root cause.",
            "cases": recur}
        valid.add("recurrence_check")
        for r in recur:
            if f"past_defect:{r['defect_id']}" not in valid:
                evidence[f"past_defect:{r['defect_id']}"] = next(x for x in _past() if x["defect_id"] == r["defect_id"])
                valid.add(f"past_defect:{r['defect_id']}")

    if supplier:
        evidence["supplier_history"] = supplier_history(supplier, batch)
        valid.add("supplier_history")

    sop_ids = select_sops(machine_id, defect_type, hints)
    for s in sop_ids:
        evidence[s] = _sops()[s]
        valid.add(s)

    report: RootCauseReport = _generate(
        MODEL, [PROMPT.format(evidence=json.dumps(evidence, indent=1, default=str))], RootCauseReport)

    # Anti-hallucination: keep only citations that exist in the evidence
    removed = []
    for c in report.likely_causes:
        bad = [s for s in c.evidence_sources if s not in valid]
        removed += bad
        c.evidence_sources = [s for s in c.evidence_sources if s in valid]
    if report.similar_case_id and f"past_defect:{report.similar_case_id}" not in valid:
        removed.append(report.similar_case_id)
        report.similar_case_id, report.similar_case_note = "", ""
    # Evidence-strength guard (computed in code): thin evidence -> cap confidence, require a human check
    strong = bool(hints) or len(similar_kw) >= 2 or ("recurrence_check" in valid)
    if not strong:
        report.confidence = min(report.confidence, 70)
        report.needs_human_check = True
    if removed:
        report.needs_human_check = True

    return {
        "status": "success",
        "report": report.model_dump(),
        "evidence_used": {
            "machine_health": evidence.get(f"machine_health:{machine_id}", {}).get("health", "n/a"),
            "pattern_hints": hints,
            "similar_past_defects": [{k: r[k] for k in ("defect_id", "date", "machine_id", "defect_type",
                                                         "root_cause", "fix")} for r in similar],
            "sops": sop_ids,
            "semantic_matches": [{"defect_id": d, "similarity": sc} for d, sc in sem],
            "supplier_history": evidence.get("supplier_history"),
            "recurrence": evidence.get("recurrence_check"),
            "forecast": evidence.get(f"forecast:{machine_id}"),
        },
        "invalid_citations_removed": removed,
        "data_note": "Machine data SIMULATED; past defects and SOPs are SYNTHETIC samples (prototype)",
    }


def _main_defect(inspection: dict) -> Optional[dict]:
    defects = inspection.get("defects") or []
    return max(defects, key=lambda d: SEVERITY_RANK.get(d.get("severity"), 0)) if defects else None


def run_inspection(part_id: str) -> dict:
    folder = PAIRS / part_id
    golden = next((folder / f"golden{e}" for e in (".png", ".jpg", ".jpeg") if (folder / f"golden{e}").exists()), None)
    test = next((folder / f"test{e}" for e in (".png", ".jpg", ".jpeg") if (folder / f"test{e}").exists()), None)
    if not golden or not test:
        raise FileNotFoundError(f"Images missing for {part_id}")
    data = inspect(golden, test).model_dump()
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{part_id}.json").write_text(json.dumps(data, indent=2))
    return data


def diagnose_part(part_id: str) -> dict:
    """Root cause for a demo part: uses the cached inspection (runs it if missing)."""
    cache = CACHE / f"{part_id}.json"
    inspection = json.loads(cache.read_text()) if cache.exists() else run_inspection(part_id)
    main = _main_defect(inspection)
    if not main:
        return {"status": "no_defect", "message": "No confirmed defect on this part; nothing to diagnose.",
                "inspection": inspection}
    info = part_info(part_id)
    return diagnose(info.get("machine_id", ""), main["type"], main["description"], info.get("product", ""),
                    info.get("supplier", ""), info.get("batch", ""), inspection=main) | {"part": info}


if __name__ == "__main__":
    print(json.dumps(diagnose_part(sys.argv[1] if len(sys.argv) > 1 else "metal_nut_scratch_0"),
                     indent=2, default=str, ensure_ascii=False))