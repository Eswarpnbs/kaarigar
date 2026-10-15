"""
Kaarigar Action agent core: work orders (deterministic, built from the diagnosis), 8D report drafts
(Gemini, structured, DRAFT until approved), supervisor approval, and verification re-checks.
Store: local JSON by default; Firestore when KAARIGAR_STORE=firestore (Cloud Run).

Test:  python -m agents.action metal_nut_scratch_0
"""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from agents.diagnosis import CACHE as INSPECTION_CACHE
from agents.diagnosis import MACHINES, SEVERITY_RANK, _sops, diagnose_part, part_info
from agents.inspector import _generate

REPO = Path(__file__).resolve().parents[1]
LOCAL_STORE = REPO / "data" / "cache" / "store.json"
DIAG_CACHE = REPO / "data" / "cache" / "diagnoses"
REPORTS = REPO / "data" / "cache" / "reports"
IST = ZoneInfo("Asia/Kolkata")
MODEL = os.environ.get("KAARIGAR_ACTION_MODEL", os.environ.get("KAARIGAR_MODEL", "gemini-2.5-flash"))


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


# ---------------- Storage (local JSON or Firestore) ----------------
class Store:
    def __init__(self):
        self.kind = os.environ.get("KAARIGAR_STORE", "local")
        if self.kind == "firestore":
            from google.cloud import firestore
            self.db = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                                       database=os.environ.get("KAARIGAR_FIRESTORE_DB", "(default)"))

    def _load(self) -> dict:
        return json.loads(LOCAL_STORE.read_text()) if LOCAL_STORE.exists() else {}

    def _save(self, d: dict) -> None:
        LOCAL_STORE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_STORE.write_text(json.dumps(d, indent=2, default=str))

    def put(self, coll: str, doc_id: str, data: dict) -> None:
        if self.kind == "firestore":
            self.db.collection(coll).document(doc_id).set(data)
            return
        d = self._load()
        d.setdefault(coll, {})[doc_id] = data
        self._save(d)

    def get(self, coll: str, doc_id: str):
        if self.kind == "firestore":
            snap = self.db.collection(coll).document(doc_id).get()
            return snap.to_dict() if snap.exists else None
        return self._load().get(coll, {}).get(doc_id)

    def list(self, coll: str) -> list:
        if self.kind == "firestore":
            return [s.to_dict() for s in self.db.collection(coll).stream()]
        return list(self._load().get(coll, {}).values())


STORE = Store()


# ---------------- 8D schema + prompt ----------------
class EightD(BaseModel):
    d1_team: List[str] = Field(description="roles, not names")
    d2_problem: str = Field(description="problem statement covering what, where, when, how many, how detected")
    d3_containment: List[str]
    d4_root_cause: str
    d4_evidence: List[str]
    d5_corrective_actions: List[str]
    d6_verification_plan: List[str] = Field(description="measurable checks")
    d7_prevention: List[str]
    d8_closure_note: str


PROMPT_8D = """You are drafting an 8D corrective-action report for a small machine shop, as an
experienced quality engineer would. Use ONLY the evidence below. Be concise and specific.
- Where information is unknown (names, quantities, dates), never invent it and never insert a placeholder mid-sentence. Write the sentence naturally and end it with "(supervisor to confirm)", e.g. "Re-inspect all Flange nut FN-24 parts made on M1 since the problem started (supervisor to confirm the start time)."
- D1: list roles, not names.
- D3 containment must protect the customer now: segregate and re-inspect suspect parts made on this
  machine since the problem started; stop the machine if the diagnosis marks it immediate.
- D4: state the root cause and why it was not caught earlier, in plain words from the evidence.
  If a recurrence is present, explain that the earlier fix did not last and why that matters.
- D6: measurable checks. For machine limits use the NORMAL RANGE stated in the SOP evidence
  (never use the median baseline value as a limit), plus next 5 parts inspected OK.
- D7: prevention through SOP updates, checks, or monitoring.
- This is a DRAFT for supervisor approval. Machine data in this prototype is SIMULATED.

EVIDENCE (JSON):
{evidence}"""


# ---------------- Helpers ----------------
def get_diagnosis(part_id: str) -> dict:
    """Cached diagnosis for a part (runs inspection + diagnosis if needed)."""
    f = DIAG_CACHE / f"{part_id}.json"
    if f.exists():
        return json.loads(f.read_text())
    diag = diagnose_part(part_id)
    DIAG_CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(diag, indent=2, default=str))
    return diag


def _priority(severity: str, health: str, urgencies: List[str]) -> str:
    if severity == "critical" or health == "critical" or "immediate" in urgencies:
        return "P1 - stop and fix now"
    if severity == "major" or health == "warning" or "today" in urgencies:
        return "P2 - fix today"
    return "P3 - plan this week"


def eight_d_markdown(wo: dict) -> str:
    d = wo["eight_d"]
    lines = [
        f"# 8D Report — {wo['wo_id']} ({'APPROVED' if wo['status'] == 'approved' else 'DRAFT — pending supervisor approval'})",
        f"**Part:** {wo['product']} · **Machine:** {wo['machine_name']} ({wo['machine_id']}) · "
        f"**Supplier / batch:** {wo['supplier']} / {wo['batch']}",
        f"**Priority:** {wo['priority']} · **Created:** {wo['created_at']}", "",
    ]
    sections = [("D1 Team", d["d1_team"]), ("D2 Problem description", d["d2_problem"]),
                ("D3 Containment", d["d3_containment"]), ("D4 Root cause", d["d4_root_cause"]),
                ("D4 Evidence", d["d4_evidence"]), ("D5 Corrective actions", d["d5_corrective_actions"]),
                ("D6 Verification plan", d["d6_verification_plan"]), ("D7 Prevention", d["d7_prevention"]),
                ("D8 Closure", d["d8_closure_note"])]
    for title, val in sections:
        lines.append(f"## {title}")
        lines += [f"- {v}" for v in val] if isinstance(val, list) else [val]
        lines.append("")
    if wo.get("approval"):
        a = wo["approval"]
        lines.append(f"**Decision:** {a['decision']} by {a['by']} at {a['at']}. {a.get('comment', '')}")
    lines.append("\n_AI-drafted, human-approved. Prototype: machine data simulated; past records synthetic._")
    return "\n".join(lines)


# ---------------- Main actions ----------------
def create_work_order(part_id: str) -> dict:
    """Create a work order + 8D draft from the part's diagnosis. Status: pending_approval."""
    diag = get_diagnosis(part_id)
    if diag.get("status") != "success":
        return {"status": "no_action", "message": diag.get("message", "Nothing to act on.")}
    insp = json.loads((INSPECTION_CACHE / f"{part_id}.json").read_text())
    main = max(insp["defects"], key=lambda d: SEVERITY_RANK.get(d["severity"], 0))
    rep, info = diag["report"], diag.get("part") or part_info(part_id)
    mid = info.get("machine_id", "")
    top = rep["likely_causes"][0] if rep["likely_causes"] else {}
    urgencies = [a["urgency"] for a in rep["recommended_actions"]]
    health = diag.get("evidence_used", {}).get("machine_health", "n/a")

    evidence = {"part": info, "machine": MACHINES.get(mid, ("", ""))[0], "defect": main,
                "diagnosis": rep, "machine_health": health,
                "recurrence": diag.get("evidence_used", {}).get("recurrence"),
                "sops": {x: _sops().get(x, "") for x in diag.get("evidence_used", {}).get("sops", [])}}
    eight_d: EightD = _generate(MODEL, [PROMPT_8D.format(evidence=json.dumps(evidence, indent=1, default=str))], EightD)

    wo_id = f"WO-{datetime.now(IST):%y%m%d}-{uuid.uuid4().hex[:4].upper()}"
    wo = {
        "wo_id": wo_id, "created_at": _now(), "status": "pending_approval",
        "priority": _priority(main["severity"], health, urgencies),
        "part_id": part_id, "product": info.get("product", ""), "machine_id": mid,
        "machine_name": MACHINES.get(mid, ("", ""))[0],
        "supplier": info.get("supplier", ""), "batch": info.get("batch", ""),
        "defect": {k: main[k] for k in ("type", "severity", "description")},
        "root_cause": top.get("cause", ""), "category_6m": top.get("category_6m", ""),
        "confidence": rep["confidence"], "needs_human_check": rep["needs_human_check"],
        "recurrence": bool(diag.get("evidence_used", {}).get("recurrence")),
        "similar_case_id": rep.get("similar_case_id", ""),
        "tasks": [{"task_no": i + 1, **a, "status": "open"} for i, a in enumerate(rep["recommended_actions"])],
        "eight_d": eight_d.model_dump(),
        "approval": None, "verification": None,
        "data_note": "Prototype: machine data simulated; past records synthetic",
    }
    STORE.put("work_orders", wo_id, wo)
    return {"status": "success", "work_order": wo}


def decide_work_order(wo_id: str, approve: bool, approver_role: str = "supervisor", comment: str = "") -> dict:
    """Supervisor approves or rejects a work order. Approval schedules a verification re-check."""
    wo = STORE.get("work_orders", wo_id)
    if not wo:
        return {"status": "error", "message": f"Work order {wo_id} not found."}
    if wo["status"] != "pending_approval":
        return {"status": "error", "message": f"Work order {wo_id} is already {wo['status']}."}
    wo["approval"] = {"decision": "approved" if approve else "rejected", "by": approver_role,
                      "at": _now(), "comment": comment}
    wo["status"] = "approved" if approve else "rejected"
    if approve:
        wo["verification"] = {
            "status": "scheduled",
            "plan": f"After the fix: inspect the next 5 parts from {wo['machine_name']} with Kaarigar and "
                    f"confirm machine vibration is back to its normal range.",
            "due_by": (datetime.now(IST) + timedelta(hours=4)).isoformat(timespec="minutes"),
            "result": None,
        }
    STORE.put("work_orders", wo_id, wo)
    return {"status": "success", "work_order": wo}


def record_verification(wo_id: str, passed: bool, note: str = "") -> dict:
    """Record the re-check result. Passed -> closed; failed -> reopened for a deeper root cause."""
    wo = STORE.get("work_orders", wo_id)
    if not wo or not wo.get("verification"):
        return {"status": "error", "message": "No scheduled verification for this work order."}
    wo["verification"].update({"status": "passed" if passed else "failed", "result": note, "at": _now()})
    wo["status"] = "closed" if passed else "reopened"
    STORE.put("work_orders", wo_id, wo)
    return {"status": "success", "work_order": wo}


def list_work_orders() -> dict:
    """All work orders, newest first."""
    wos = sorted(STORE.list("work_orders"), key=lambda w: w["created_at"], reverse=True)
    return {"status": "success", "work_orders": [
        {k: w[k] for k in ("wo_id", "created_at", "status", "priority", "machine_name", "product", "root_cause")}
        for w in wos]}


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "metal_nut_scratch_0"
    res = create_work_order(pid)
    if res["status"] != "success":
        sys.exit(json.dumps(res, indent=2))
    wo = res["work_order"]
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{wo['wo_id']}.md").write_text(eight_d_markdown(wo))
    print(f"Created {wo['wo_id']} | {wo['priority']} | status={wo['status']}")
    print(f"Root cause: {wo['root_cause']} ({wo['category_6m']}) | recurrence={wo['recurrence']}")
    print(f"Tasks: {len(wo['tasks'])} | 8D draft saved to {REPORTS / (wo['wo_id'] + '.md')}")
    res = decide_work_order(wo["wo_id"], approve=True, comment="Approved: stop M1 and check bearings per SOP-02")
    v = res["work_order"]["verification"]
    print(f"Approved -> status={res['work_order']['status']} | re-check due {v['due_by']}: {v['plan']}")