"""
Kaarigar web team (ADK): the agents behind "Ask Kaarigar" in the live app.
Read-only by design: approvals happen only in the app, by a supervisor verified with Firebase Authentication.
"""
import os

# ADK talks to Gemini through Vertex AI (same project and region as the rest of Kaarigar)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "kaarigar-510716")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.genai import types as _gt

from adk_app.kaarigar.agent import (_model, find_root_cause, get_eight_d_report, inspect_part,
                                    list_demo_parts, list_work_orders)


def factory_status() -> dict:
    """Health of every machine now (vibration change, trend, top hint) plus the BigQuery ML forecast:
    hours until the ISO damage zone. Machine data is SIMULATED."""
    from agents.tools.forecast import forecast_all
    from agents.tools.machine_data import factory_overview
    f = factory_overview()
    try:
        fa = forecast_all()
    except Exception:
        fa = {}
    for m in f.get("machines", []):
        fc = fa.get(m["machine_id"], {})
        m["zone"] = fc.get("zone")
        m["hours_to_damage_zone"] = (fc.get("hours_to_zone_d") or {}).get("expected")
    return f


def supplier_scorecard() -> dict:
    """Supplier ratings from Factory Memory (rules in code): material problems in the last 30 days,
    repeat batches, and the most common problems."""
    from app.main import suppliers
    return suppliers()


def work_orders_summary() -> dict:
    """Work orders: counts by status, and the ones waiting for a supervisor decision or a re-check (newest first)."""
    from agents.action import STORE
    wos = sorted(STORE.list("work_orders"), key=lambda w: w.get("created_at", ""), reverse=True)
    by_status: dict = {}
    for w in wos:
        by_status[w.get("status", "?")] = by_status.get(w.get("status", "?"), 0) + 1
    open_ = [{"wo_id": w.get("wo_id"), "machine": w.get("machine_name"), "priority": w.get("priority"),
              "status": w.get("status"), "root_cause": (w.get("root_cause") or "")[:120]}
             for w in wos if w.get("status") in ("pending_approval", "approved", "reopened")][:10]
    return {"total": len(wos), "by_status": by_status, "open": open_}


def search_factory_memory(query: str) -> dict:
    """Search past defects and learned fixes (Factory Memory) by meaning. Returns the most similar
    records with their root cause and fix."""
    from agents.diagnosis import _past
    from agents.memory import semantic_search
    by_id = {r["defect_id"]: r for r in _past()}
    hits = semantic_search(query, k=5, min_score=0.6)
    keys = ("defect_id", "date", "machine_id", "defect_type", "root_cause", "fix", "supplier", "batch")
    return {"results": [{**{k: by_id[d].get(k) for k in keys}, "similarity": s} for d, s in hits if d in by_id],
            "note": "seed records are SYNTHETIC samples; L-... records were learned from verified fixes"}


_FAST = BuiltInPlanner(thinking_config=_gt.ThinkingConfig(thinking_budget=0))

RULES = ("Use ONLY tool results; cite machine ids, work order ids and defect ids. Never invent numbers. "
         "You cannot approve, reject or change anything: approvals happen only in the app, by a signed-in supervisor. "
         "Machine data is SIMULATED and past records are SYNTHETIC samples; say so when relevant. "
         "Answer in the language the user asks for. Keep answers short, specific and practical.")

web_inspector = Agent(planner=_FAST, name="inspector", model=_model(), description="Inspects demo parts against golden samples.",
                      instruction="You inspect demo parts with your tools and report defects with their location. " + RULES,
                      tools=[list_demo_parts, inspect_part])
web_diagnosis = Agent(planner=_FAST, name="diagnosis", model=_model(), description="Finds the root cause of a defect on a part.",
                      instruction="You find root causes with find_root_cause and explain the evidence briefly. " + RULES,
                      tools=[find_root_cause])
insights_agent = Agent(planner=_FAST, name="insights", model=_model(),
                       description="Answers questions about the factory: machine health and forecasts, suppliers, work orders, past defects.",
                       instruction=("You answer questions about the whole factory. Pick the tools that answer the question and "
                                    "combine them when needed: factory_status, supplier_scorecard, work_orders_summary, "
                                    "search_factory_memory, list_work_orders, get_eight_d_report. " + RULES),
                       tools=[factory_status, supplier_scorecard, work_orders_summary, search_factory_memory,
                              list_work_orders, get_eight_d_report])
web_root = Agent(planner=_FAST, name="kaarigar", model=_model(), description="Kaarigar orchestrator for the web app.",
                 instruction=("You are Kaarigar, an AI quality co-pilot for a small machine shop. Route every question to "
                              "the right specialist immediately: insights for machines, forecasts, suppliers, work orders "
                              "or history; diagnosis for why a part failed; inspector to inspect a demo part. "
                              "Do not answer factory questions yourself. " + RULES),
                 sub_agents=[web_inspector, web_diagnosis, insights_agent])