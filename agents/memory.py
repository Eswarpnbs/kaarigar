"""
Factory Memory: meaning-based search over past defects using Gemini embeddings (Vertex AI).
Build once:  python -m agents.memory build
Try:         python -m agents.memory "strange loud noise from lathe 1"
"""
import json
import math
import os
from functools import lru_cache
from pathlib import Path

from google import genai
from google.genai import types

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "data" / "seed" / "memory_index.json"
EMBED_MODEL = os.environ.get("KAARIGAR_EMBED_MODEL", "gemini-embedding-001")
DIM = 768


@lru_cache(maxsize=1)
def _client():
    return genai.Client(vertexai=True, project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                        location=os.environ.get("KAARIGAR_EMBED_LOCATION", "us-central1"))


def embed(texts, task: str):
    vecs = []
    for t in texts:  # one input per request
        r = _client().models.embed_content(
            model=EMBED_MODEL, contents=t,
            config=types.EmbedContentConfig(task_type=task, output_dimensionality=DIM))
        vecs.append(r.embeddings[0].values)
    return vecs


def record_text(r: dict) -> str:
    return (f"{r['machine_id']} {r['product']} {r['defect_type']}: {r['description']}. "
            f"Root cause: {r['root_cause']}. Fix: {r['fix']}")


def build_index(records: list) -> int:
    vecs = embed([record_text(r) for r in records], "RETRIEVAL_DOCUMENT")
    INDEX.write_text(json.dumps({"model": EMBED_MODEL, "dim": DIM, "synthetic": True,
                                 "items": [{"defect_id": r["defect_id"], "vector": v} for r, v in zip(records, vecs)]}))
    return len(vecs)


@lru_cache(maxsize=1)
def _index() -> dict:
    if not INDEX.exists():
        return {}
    return {i["defect_id"]: i["vector"] for i in json.loads(INDEX.read_text())["items"]}


def _cos(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def semantic_search(query: str, k: int = 3, min_score: float = 0.6) -> list:
    """Returns [(defect_id, cosine_score)] for the most similar past defects (computed in code)."""
    idx = dict(_index())
    idx.update({r['defect_id']: r['vector'] for r in learned_cases() if r.get('vector')})
    if not idx:
        return []
    try:
        q = embed([query], "RETRIEVAL_QUERY")[0]
    except Exception:
        return []  # memory search must never break a diagnosis
    scored = sorted(((_cos(q, v), did) for did, v in idx.items()), reverse=True)
    return [(did, round(s, 3)) for s, did in scored[:k] if s >= min_score]



# ---------------- Learn: verified fixes become Factory Memory ----------------
import re
import time as _time
from datetime import date as _date

_learned_cache = {"t": 0.0, "rows": []}


def learned_cases() -> list:
    """Cases learned from verified fixes (Firestore or local store), cached 30 s."""
    if _time.time() - _learned_cache["t"] < 30:
        return _learned_cache["rows"]
    try:
        from agents.action import STORE
        rows = STORE.list("factory_memory")
    except Exception:
        rows = []
    _learned_cache.update(t=_time.time(), rows=rows)
    return rows


def learn_from_work_order(wo: dict) -> dict:
    """Turn a CLOSED (verified) work order into a Factory Memory record. One record per
    machine + defect + product; repeated confirmations increment times_confirmed."""
    from agents.action import STORE
    slug = re.sub(r"[^A-Za-z0-9]+", "-", wo.get("product", "part")).strip("-")[:40]
    key = f"L-{wo.get('machine_id', 'NA')}-{wo['defect']['type']}-{slug}"
    existing = STORE.get("factory_memory", key) or {}
    rec = {
        "defect_id": key, "date": _date.today().isoformat(), "machine_id": wo.get("machine_id", ""),
        "product": wo.get("product", ""), "defect_type": wo["defect"]["type"], "severity": wo["defect"]["severity"],
        "description": wo["defect"]["description"], "root_cause": wo.get("root_cause", ""),
        "category_6m": wo.get("category_6m") or "Machine",
        "fix": "; ".join(t["action"] for t in wo.get("tasks", []))[:500],
        "fix_verified": True, "supplier": wo.get("supplier", ""), "batch": wo.get("batch", ""),
        "downtime_hours": 0, "scrap_qty": 0, "synthetic": False,
        "source": f"learned from verified work order {wo['wo_id']}",
        "times_confirmed": int(existing.get("times_confirmed", 0)) + 1,
    }
    try:
        rec["vector"] = embed([record_text(rec)], "RETRIEVAL_DOCUMENT")[0]
    except Exception:
        rec["vector"] = existing.get("vector")
    STORE.put("factory_memory", key, rec)
    _learned_cache["t"] = 0.0      # refresh on next read
    return {"defect_id": key, "times_confirmed": rec["times_confirmed"]}

if __name__ == "__main__":
    import sys
    from agents.diagnosis import _past
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        print("indexed", build_index(_past()), "past defects ->", INDEX)
    else:
        q = " ".join(sys.argv[1:]) or "strange loud noise from lathe 1"
        print("query:", q)
        for did, s in semantic_search(q, 5, 0):
            r = next(x for x in _past() if x["defect_id"] == did)
            print(f"  {did}  {s:.3f}  {r['machine_id']} {r['defect_type']}: {r['root_cause']}")