"""
Prevent: turn an 8D's prevention actions into ONE concrete SOP change proposal (Gemini drafts,
code validates, supervisor approves). Approved changes are appended to the SOP used by future diagnoses.
"""
import json
import os
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from agents.action import IST, STORE, _now
from agents.inspector import _generate

MODEL = os.environ.get("KAARIGAR_MODEL", "gemini-2.5-flash")


class SopChange(BaseModel):
    sop_id: str = Field(description="id of the SOP to change, exactly as given, e.g. SOP-02")
    change_type: Literal["add_step", "modify_step", "add_check"]
    new_text: str = Field(description="the exact step or check to add, written as one short SOP line")
    reason: str = Field(description="why, in one sentence, linked to the root cause")
    verification: str = Field(description="how the shop will know the change works (measurable)")


PROMPT = """You are a quality engineer in a small machine shop. A defect was fixed and verified.
Propose ONE concrete change to the most relevant SOP so this root cause cannot happen again.
Rules: use only the evidence; pick sop_id from the SOPs given; write the new line so an operator can
follow it; use numbers only if they appear in the evidence or SOPs; keep it short and measurable.

EVIDENCE (JSON):
{evidence}"""


def propose_sop_change(wo_id: str) -> dict:
    from agents.diagnosis import _sops
    wo = STORE.get("work_orders", wo_id)
    if not wo:
        return {"status": "error", "message": f"Work order {wo_id} not found."}
    if wo.get("status") not in ("approved", "closed"):
        return {"status": "error", "message": "Approve the work order first."}
    sops = _sops()
    refs = [t.get("sop_ref") for t in wo.get("tasks", []) if t.get("sop_ref")]
    cand = {s: sops[s] for s in dict.fromkeys(refs) if s in sops} or dict(list(sops.items())[:2])
    evidence = {"work_order": {k: wo.get(k) for k in ("wo_id", "machine_name", "product", "root_cause",
                                                     "category_6m", "recurrence")},
                "prevention_from_8d": wo.get("eight_d", {}).get("d7_prevention", []), "sops": cand}
    ch: SopChange = _generate(MODEL, [PROMPT.format(evidence=json.dumps(evidence, indent=1, default=str))], SopChange)
    if ch.sop_id not in sops:                       # validated in code
        ch.sop_id = next(iter(cand))
    cid = f"SC-{datetime.now(IST):%y%m%d}-{uuid.uuid4().hex[:4].upper()}"
    rec = {"change_id": cid, "wo_id": wo_id, "status": "pending_approval", "created_at": _now(), **ch.model_dump()}
    STORE.put("sop_changes", cid, rec)
    return {"status": "success", "change": rec}


def decide_sop_change(cid: str, approve: bool, who: str) -> dict:
    rec = STORE.get("sop_changes", cid)
    if not rec:
        return {"status": "error", "message": f"SOP change {cid} not found."}
    if rec["status"] != "pending_approval":
        return {"status": "error", "message": f"SOP change {cid} is already {rec['status']}."}
    rec.update(status="approved" if approve else "rejected", decided_by=who, decided_at=_now())
    STORE.put("sop_changes", cid, rec)
    from agents import diagnosis
    diagnosis._sop_cache["t"] = 0.0                  # refresh SOPs on next read
    return {"status": "success", "change": rec}