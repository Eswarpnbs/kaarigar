"""
Kaarigar ADK skeleton: Orchestrator (root) + Inspector sub-agent.

Run from the repo root:
    PYTHONPATH=. adk web adk_app
Then open http://localhost:8000, pick "kaarigar", and try:
    "Which demo parts can you inspect?"
    "Inspect metal_nut_scratch_0"
"""
import os
from pathlib import Path

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types

from agents.inspector import inspect

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "pairs"
AGENT_MODEL = os.environ.get("KAARIGAR_AGENT_MODEL", "gemini-2.5-flash")


def _model() -> Gemini:
    """Gemini model with automatic retries for 429 rate limits."""
    return Gemini(
        model=AGENT_MODEL,
        retry_options=types.HttpRetryOptions(initial_delay=2, attempts=5),
    )


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


# ---------------- Tools ----------------
def list_demo_parts() -> dict:
    """Lists the demo parts available for inspection.

    Each demo part has golden samples (approved good parts) and one test photo.

    Returns:
        dict with status and a list of part ids.
    """
    if not DEMO_DIR.exists():
        return {"status": "error", "message": "Demo library not found."}
    parts = sorted(p.name for p in DEMO_DIR.iterdir() if p.is_dir())
    return {"status": "success", "count": len(parts), "parts": parts}


def inspect_part(part_id: str) -> dict:
    """Inspects one part photo against its golden samples.

    Returns detected defects with type, severity, description and bounding box
    ([ymin, xmin, ymax, xmax], normalized 0-1000), plus confidence, a recommendation
    (accept, rework, reject, retake_photo) and notes on how the decision was made.

    Args:
        part_id: the demo part id, for example "metal_nut_scratch_0".

    Returns:
        dict with status and the inspection result.
    """
    folder = DEMO_DIR / part_id
    if not folder.is_dir():
        return {"status": "error",
                "message": f"Unknown part '{part_id}'. Call list_demo_parts to see valid ids."}
    golden, test = _find(folder, "golden"), _find(folder, "test")
    if not golden or not test:
        return {"status": "error", "message": f"Part '{part_id}' is missing images."}
    try:
        result = inspect(golden, test)
    except Exception as e:  # surface errors to the agent instead of crashing
        return {"status": "error", "message": f"Inspection failed: {e}"}
    data = result.model_dump()
    for d in data["defects"]:
        d["location"] = _location(d["box_2d"])
    return {"status": "success", "part_id": part_id, **data}


# ---------------- Agents ----------------
inspector_agent = Agent(
    name="inspector",
    model=_model(),
    description="Inspects part photos against golden samples and reports defects, "
                "severity, location, confidence and a recommendation.",
    instruction="""You are the Kaarigar Inspector, a careful quality inspector for small factories.

When asked to inspect a part:
1. If you don't know the part id, call list_demo_parts.
2. Call inspect_part with the part id.
3. Report clearly and briefly for a shop-floor supervisor:
   - Verdict: defect found or not.
   - For each defect: type, severity, and where it is, using EXACTLY the "location"
     field from the tool result (never work out the location yourself from box_2d).
   - Confidence as "Sure" (85+), "Please check" (60-84), or "Retake photo" (below 60).
   - Recommendation: accept, rework, reject, or retake photo / check manually.
4. Never claim more certainty than the tool result. If the recommendation is
   retake_photo, ask for a clearer photo or a manual check.
5. Remind the supervisor that they make the final decision.""",
    tools=[list_demo_parts, inspect_part],
)

root_agent = Agent(
    name="kaarigar",
    model=_model(),
    description="Kaarigar, an AI quality co-pilot for small factories.",
    instruction="""You are Kaarigar, an AI quality co-pilot for small factories.
Kaarigar helps workers and supervisors catch defects, find root causes, and fix problems.

- For any request to inspect a part, check a photo, or list demo parts, transfer to the
  inspector agent.
- If asked what Kaarigar does, explain briefly: one photo of a good part, one phone,
  zero training; AI informs and humans decide.
- Be concise and practical. Root cause analysis and work orders are coming soon;
  say so if asked.""",
    sub_agents=[inspector_agent],
)