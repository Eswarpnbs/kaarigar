"""
Kaarigar ADK team: Orchestrator (root) + Inspector + Diagnosis + Action.

Run from the repo root:  PYTHONPATH=. adk web adk_app
Try:  "Inspect metal_nut_scratch_0" -> "Why did this happen?" -> "Create a work order"
      -> "Show the 8D report" -> "I approve it, go ahead"
"""
import json
import os
from pathlib import Path

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types

from agents import action as act
from agents.diagnosis import CACHE as INSPECTION_CACHE
from agents.inspector import inspect

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "pairs"
AGENT_MODEL = os.environ.get("KAARIGAR_AGENT_MODEL", "gemini-2.5-flash")


def _model() -> Gemini:
    """Gemini model with automatic retries for 429 rate limits."""
    return Gemini(model=AGENT_MODEL, retry_options=types.HttpRetryOptions(initial_delay=2, attempts=5))


def _find(folder: Path, stem: str):
    for ext in (".png", ".jpg", ".jpeg"):
        p = folder / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def _location(box) -> str:
    """Plain-words location from a [ymin, xmin, ymax, xmax] 0-1000 box (deterministic)."""
    if len(box) != 4:
        return "unknown"
    y0, x0, y1, x1 = box
    cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
    v = "upper" if cy < 333 else ("lower" if cy > 666 else "middle")
    h = "left" if cx < 333 else ("right" if cx > 666 else "center")
    if v == "middle" and h == "center":
        return "center"
    if v == "middle":
        return f"middle-{h}"
    if h == "center":
        return f"{v}-center"
    return f"{v}-{h}"


def _wo_view(res: dict) -> dict:
    if res.get("status") != "success":
        return res
    wo = res["work_order"]
    return {"status": "success", "wo_id": wo["wo_id"], "approval_status": wo["status"],
            "priority": wo["priority"], "approval": wo.get("approval"), "verification": wo.get("verification")}


# ---------------- Inspector tools ----------------
def list_demo_parts() -> dict:
    """Lists the demo parts available for inspection (golden samples + one test photo each).

    Returns:
        dict with status and a list of part ids.
    """
    if not DEMO_DIR.exists():
        return {"status": "error", "message": "Demo library not found."}
    parts = sorted(p.name for p in DEMO_DIR.iterdir() if p.is_dir())
    return {"status": "success", "count": len(parts), "parts": parts}


def inspect_part(part_id: str) -> dict:
    """Inspects one part photo against its golden samples.

    Returns defects with type, severity, description, box and plain-words location, plus confidence,
    a recommendation (accept, rework, reject, retake_photo) and notes.

    Args:
        part_id: the demo part id, for example "metal_nut_scratch_0".
    """
    folder = DEMO_DIR / part_id
    if not folder.is_dir():
        return {"status": "error", "message": f"Unknown part '{part_id}'. Call list_demo_parts."}
    golden, test = _find(folder, "golden"), _find(folder, "test")
    if not golden or not test:
        return {"status": "error", "message": f"Part '{part_id}' is missing images."}
    try:
        data = inspect(golden, test).model_dump()
    except Exception as e:
        return {"status": "error", "message": f"Inspection failed: {e}"}
    INSPECTION_CACHE.mkdir(parents=True, exist_ok=True)
    (INSPECTION_CACHE / f"{part_id}.json").write_text(json.dumps(data, indent=2))
    for d in data["defects"]:
        d["location"] = _location(d["box_2d"])
    return {"status": "success", "part_id": part_id, **data}


# ---------------- Diagnosis tool ----------------
def find_root_cause(part_id: str) -> dict:
    """Finds the most likely root cause of a part's defect using the inspection, machine sensor
    data, Factory Memory (past defects), supplier history and SOPs. Returns ranked causes with
    evidence, a 5 Whys, recommended actions, confidence, and whether this is a recurring problem.

    Args:
        part_id: the demo part id that was inspected, for example "metal_nut_scratch_0".
    """
    try:
        d = act.get_diagnosis(part_id)
    except Exception as e:
        return {"status": "error", "message": f"Diagnosis failed: {e}"}
    if d.get("status") != "success":
        return d
    r, eu = d["report"], d["evidence_used"]
    return {"status": "success", "part": d.get("part"), "summary": r["summary"],
            "likely_causes": r["likely_causes"], "five_whys": r["five_whys"],
            "recommended_actions": r["recommended_actions"],
            "similar_case": {"id": r["similar_case_id"], "note": r["similar_case_note"]},
            "recurrence": eu.get("recurrence"), "machine_health": eu.get("machine_health"),
            "confidence": r["confidence"], "needs_human_check": r["needs_human_check"],
            "data_note": d["data_note"]}


# ---------------- Action tools ----------------
def create_work_order(part_id: str) -> dict:
    """Creates a work order and an 8D report DRAFT from the part's diagnosis.
    Status starts as pending_approval: nothing happens until a supervisor approves.

    Args:
        part_id: the demo part id, for example "metal_nut_scratch_0".
    """
    try:
        res = act.create_work_order(part_id)
    except Exception as e:
        return {"status": "error", "message": f"Could not create work order: {e}"}
    if res.get("status") != "success":
        return res
    wo = res["work_order"]
    return {"status": "success", "wo_id": wo["wo_id"], "approval_status": wo["status"],
            "priority": wo["priority"], "root_cause": wo["root_cause"], "recurrence": wo["recurrence"],
            "tasks": wo["tasks"],
            "eight_d_highlights": {"containment": wo["eight_d"]["d3_containment"],
                                   "corrective_actions": wo["eight_d"]["d5_corrective_actions"],
                                   "verification_plan": wo["eight_d"]["d6_verification_plan"]}}


def approve_work_order(wo_id: str, comment: str = "") -> dict:
    """Records the supervisor's APPROVAL of a work order and schedules a verification re-check.
    Only call this when the user has explicitly said they approve this work order.

    Args:
        wo_id: work order id, for example "WO-261011-C7AF".
        comment: optional comment from the supervisor.
    """
    return _wo_view(act.decide_work_order(wo_id, True, "supervisor", comment))


def reject_work_order(wo_id: str, reason: str = "") -> dict:
    """Records the supervisor's REJECTION of a work order.

    Args:
        wo_id: work order id.
        reason: why it was rejected.
    """
    return _wo_view(act.decide_work_order(wo_id, False, "supervisor", reason))


def get_eight_d_report(wo_id: str) -> dict:
    """Returns the full 8D report for a work order as Markdown.

    Args:
        wo_id: work order id.
    """
    wo = act.STORE.get("work_orders", wo_id)
    if not wo:
        return {"status": "error", "message": f"Work order {wo_id} not found."}
    return {"status": "success", "markdown": act.eight_d_markdown(wo)}


def list_work_orders() -> dict:
    """Lists all work orders, newest first, with status and priority."""
    return act.list_work_orders()


# ---------------- Agents ----------------
inspector_agent = Agent(
    name="inspector",
    model=_model(),
    description="Inspects part photos against golden samples and reports defects, severity, location, confidence and a recommendation.",
    instruction="""You are the Kaarigar Inspector, a careful quality inspector for small factories.
1. If you don't know the part id, call list_demo_parts. Then call inspect_part.
2. Report briefly for a shop-floor supervisor: verdict; for each defect its type, severity and
   location (use EXACTLY the "location" field); confidence as "Sure" (85+), "Please check" (60-84)
   or "Retake photo" (below 60); and the recommendation.
3. Never claim more certainty than the tool result. If retake_photo, ask for a clearer photo or a manual check.
4. If a defect was found, offer: "Shall I find the root cause?" The supervisor makes the final decision.""",
    tools=[list_demo_parts, inspect_part],
)

diagnosis_agent = Agent(
    name="diagnosis",
    model=_model(),
    description="Finds the root cause of a defect using machine data, Factory Memory, supplier history and SOPs; gives 5 Whys and actions.",
    instruction="""You are the Kaarigar Diagnosis agent, an experienced quality engineer.
When asked why a defect happened, call find_root_cause with the part id from the conversation.
Present clearly and concisely:
- One-line summary.
- Most likely cause(s) with 6M category and the key evidence in plain words.
- If "recurrence" is present, highlight it prominently: the same problem was fixed recently and came back.
- The 5 Whys as a short numbered list.
- Recommended actions with owner and urgency.
- Confidence; if needs_human_check is true, say a human should verify.
Mention once that machine data is simulated in this prototype. Never add facts that are not in the
tool result. Then offer: "Shall I create a work order and 8D report?" """,
    tools=[find_root_cause],
)

action_agent = Agent(
    name="action",
    model=_model(),
    description="Creates work orders and 8D report drafts, and records supervisor approval or rejection.",
    instruction="""You are the Kaarigar Action agent.
- When asked to create a work order or 8D, call create_work_order with the part id from the conversation.
  Show: work order id, priority, root cause, recurrence (if true), the tasks with owner and urgency,
  and the containment steps. Then ask the supervisor to approve or reject.
- NEVER approve or reject on your own. Call approve_work_order or reject_work_order ONLY after the
  user explicitly says they approve or reject. AI informs; humans decide.
- After approval, show the scheduled verification re-check and its due time.
- Use get_eight_d_report to show the full 8D when asked, and list_work_orders to list them.""",
    tools=[create_work_order, approve_work_order, reject_work_order, get_eight_d_report, list_work_orders],
)

root_agent = Agent(
    name="kaarigar",
    model=_model(),
    description="Kaarigar, an AI quality co-pilot for small factories.",
    instruction="""You are Kaarigar, an AI quality co-pilot for small factories: one photo of a good part,
one phone, zero training. AI informs; humans decide.
Route requests:
- Inspect a part, check a photo, list demo parts -> transfer to inspector.
- Why did it happen, root cause, 5 Whys, what should we do -> transfer to diagnosis.
- Work order, 8D report, approve, reject, list work orders -> transfer to action.
If asked what Kaarigar does, explain briefly: Detect -> Diagnose -> Act -> Verify -> Predict -> Prevent -> Learn.""",
    sub_agents=[inspector_agent, diagnosis_agent, action_agent],
)