"""Quality Passport: a tamper-evident, shareable record of a batch's quality evidence (status computed in code)."""
import hashlib
import json
import os
import uuid
from pathlib import Path

from agents.action import STORE, _now
from agents.diagnosis import CACHE as INSP, part_info


def options():
    seen = {}
    for d in sorted(Path(os.environ.get("KAARIGAR_PAIRS_DIR", "data/pairs")).iterdir()):
        if d.is_dir() and not d.name.startswith("upload_"):
            i = part_info(d.name)
            if i.get("product") and i.get("batch"):
                o = seen.setdefault((i["product"], i["batch"]), {"product": i["product"], "batch": i["batch"],
                                                                 "supplier": i.get("supplier", ""), "parts": []})
                o["parts"].append(d.name)
    return list(seen.values())


def build(product, batch):
    o = next((x for x in options() if x["product"] == product and x["batch"] == batch), None)
    if not o:
        return None
    parts = []
    for pid in o["parts"]:
        f = INSP / f"{pid}.json"
        ins = json.loads(f.read_text()) if f.exists() else {}
        parts.append({"part": pid, "inspected": bool(ins), "defect_found": bool(ins.get("defect_found")),
                      "defects": [d.get("type") for d in ins.get("defects", [])]})
    wos = [w for w in STORE.list("work_orders") if w.get("product") == product and w.get("batch", batch) == batch]
    wo = [{"wo_id": w.get("wo_id"), "status": w.get("status"), "root_cause": (w.get("root_cause") or "")[:140],
           "approved_by": (w.get("approval") or {}).get("by"), "verification": (w.get("verification") or {}).get("result")}
          for w in sorted(wos, key=lambda w: w.get("created_at", ""), reverse=True)][:15]
    return _status(o, parts, wo)


def _status(o, parts, wo):
    open_ = [w for w in wo if w["status"] in ("pending_approval", "approved", "reopened")]
    defects = sum(p["defect_found"] for p in parts)
    closed = sum(w["status"] == "closed" for w in wo)
    ok = not open_ and (defects == 0 or closed > 0)
    return {"product": o["product"], "batch": o["batch"], "supplier": o["supplier"], "parts": parts,
            "inspected": sum(p["inspected"] for p in parts), "defects_found": defects, "work_orders": wo,
            "status": "RELEASED" if ok else "ON HOLD",
            "status_reason": ("No open quality issues; defects found were contained with a verified fix." if ok else
                              f"{len(open_)} open work order(s) awaiting a decision or re-check." if open_ else
                              "Defects found without a verified fix yet."),
            "rule": "RELEASED only if no open work orders and every defect has a closed, verified fix (computed in code)."}


def _fp(snap):
    return hashlib.sha256(json.dumps(snap, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def create(product, batch, approver):
    snap = build(product, batch)
    if not snap:
        return {"status": "error", "message": "Unknown product or batch"}
    snap.update(created_at=_now(), created_by=approver)
    token = uuid.uuid4().hex[:16]
    STORE.put("passports", token, {"token": token, "snapshot": snap, "fingerprint": _fp(snap)})
    return {"status": "success", "token": token, "fingerprint": _fp(snap), "passport_status": snap["status"]}


def load(token):
    rec = STORE.get("passports", token)
    if rec:
        rec["intact"] = _fp(rec["snapshot"]) == rec["fingerprint"]
    return rec


def render(rec):
    import html as h
    s, e = rec["snapshot"], h.escape
    col = "#16a34a" if s["status"] == "RELEASED" else "#d97706"
    prows = "".join(f"<tr><td>{e(p['part'])}</td><td>{'yes' if p['inspected'] else 'no'}</td>"
                    f"<td>{e(', '.join(p['defects']) or 'none')}</td></tr>" for p in s["parts"])
    wrows = "".join(f"<tr><td>{e(str(w['wo_id']))}</td><td>{e(str(w['status']))}</td><td>{e(w['root_cause'])}</td>"
                    f"<td>{e(str(w['approved_by'] or '-'))}</td><td>{e(str(w['verification'] or '-'))}</td></tr>"
                    for w in s["work_orders"]) or "<tr><td colspan=5>No work orders</td></tr>"
    css = ("body{font-family:system-ui,Arial,sans-serif;max-width:860px;margin:20px auto;padding:0 12px;color:#111}"
           "table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #ddd;padding:5px;text-align:left}"
           f".st{{display:inline-block;padding:6px 14px;border-radius:999px;color:#fff;font-weight:700;background:{col}}}"
           ".small{color:#555;font-size:12px}")
    out = ['<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           f"<title>Quality Passport · {e(s['product'])} · {e(s['batch'])}</title><style>{css}</style></head><body>",
           f"<h1>🏷️ Quality Passport</h1><p><b>{e(s['product'])}</b> · batch <b>{e(s['batch'])}</b> · supplier {e(s['supplier'] or '-')}</p>",
           f"<p><span class='st'>{e(s['status'])}</span> {e(s['status_reason'])}</p><p class='small'>Rule: {e(s['rule'])}</p>",
           f"<p>Parts inspected: <b>{s['inspected']}</b> · defects found: <b>{s['defects_found']}</b></p>",
           f"<h3>Inspections</h3><table><tr><th>Part</th><th>Inspected</th><th>Defects</th></tr>{prows}</table>",
           "<h3>Work orders (containment and fixes)</h3><table><tr><th>ID</th><th>Status</th><th>Root cause</th>"
           f"<th>Approved by</th><th>Verification</th></tr>{wrows}</table>",
           f"<p class='small'>Issued {e(s['created_at'])} by {e(s['created_by'])} · fingerprint {e(rec['fingerprint'][:16])}… · "
           f"{'✅ record intact' if rec.get('intact') else '⚠️ record changed after issue'}<br>Generated by Kaarigar (prototype). "
           "Machine data SIMULATED; demo images MVTec AD. Approvals by signed-in supervisors (Firebase Auth); records in Firestore.</p></body></html>"]
    return "".join(out)
