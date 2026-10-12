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
    idx = _index()
    if not idx:
        return []
    try:
        q = embed([query], "RETRIEVAL_QUERY")[0]
    except Exception:
        return []  # memory search must never break a diagnosis
    scored = sorted(((_cos(q, v), did) for did, v in idx.items()), reverse=True)
    return [(did, round(s, 3)) for s, did in scored[:k] if s >= min_score]


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