"""
Reset live demo state: work orders, learned Factory Memory cases, SOP change proposals.
Seed data (SYNTHETIC past defects, SOPs) is never touched.
Usage:  KAARIGAR_STORE=firestore python scripts/reset_demo.py          (dry run: counts only)
        KAARIGAR_STORE=firestore python scripts/reset_demo.py --yes    (delete)
"""
import json
import os
import sys
from pathlib import Path

COLLECTIONS = ["work_orders", "factory_memory", "sop_changes", "passports"]
DELETE = "--yes" in sys.argv


def main():
    mode = os.environ.get("KAARIGAR_STORE", "local")
    print(f"Store: {mode} · {'DELETING' if DELETE else 'dry run (add --yes to delete)'}")
    if mode == "firestore":
        from google.cloud import firestore
        db = firestore.Client()
        for c in COLLECTIONS:
            docs = list(db.collection(c).stream())
            print(f"  {c}: {len(docs)} document(s)")
            if DELETE:
                for d in docs:
                    d.reference.delete()
    else:
        p = Path("data/cache/store.json")
        if not p.exists():
            print("  local store is empty"); return
        data = json.loads(p.read_text())
        for c in COLLECTIONS:
            print(f"  {c}: {len(data.get(c, {}))} document(s)")
            if DELETE:
                data.pop(c, None)
        if DELETE:
            p.write_text(json.dumps(data, indent=2))
    print("Done.")


if __name__ == "__main__":
    main()