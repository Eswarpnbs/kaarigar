"""
Smoke tests: core flows + safety rules, with NO paid Gemini calls (cached results, BigQuery, guards).
Run: pytest -q
"""
import os

os.environ.setdefault("KAARIGAR_PAIRS_DIR", "demo_parts")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "kaarigar-510716")

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402

client = TestClient(main.app)


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_parts_include_demo_and_real_factory_parts():
    ids = {p["part_id"] for p in client.get("/api/parts").json()["parts"]}
    assert {"metal_nut_scratch_0", "real_bar_rust_0", "real_cover_bad_0"} <= ids


def test_cached_inspection_finds_and_locates_defect():
    d = client.post("/api/inspect/metal_nut_scratch_0").json()
    assert d["from_cache"] and d["defect_found"]
    assert len(d["defects"][0]["box_2d"]) == 4


def test_cached_diagnosis_is_grounded():
    d = client.post("/api/diagnose/metal_nut_scratch_0").json()
    assert d["report"]["likely_causes"], "no causes"
    assert not d.get("invalid_citations_removed"), "unsupported citations present"
    assert d["evidence_used"]["recurrence"], "recurrence (D016) expected"


def test_factory_and_forecast():
    f = client.get("/api/factory").json()
    m1 = next(m for m in f["machines"] if m["machine_id"] == "M1")
    assert m1["health"] == "critical" and m1.get("hours_to_zone_d") is not None
    fc = client.get("/api/forecast/M2").json()
    assert fc["zone"] in ("A", "B") and fc["hours_to_zone_d"]["expected"] is None


def test_map_has_five_machines_with_history():
    d = client.get("/api/map").json()
    assert len(d["machines"]) == 5 and all(m["history"] for m in d["machines"])


def test_approval_requires_signed_in_supervisor():
    r = client.post("/api/work-orders/WO-TEST/decision", json={"approve": True, "comment": "test"})
    assert r.status_code == 401


def test_budget_guard_blocks_when_limit_reached():
    old = main.LIVE_PER_IP_HOUR
    main.LIVE_PER_IP_HOUR = 0
    try:
        r = client.post("/api/diagnose-report", json={"machine_id": "XX", "defect_type": "other", "description": "t"})
        assert r.status_code == 429
        assert client.post("/api/inspect/metal_nut_scratch_0").status_code == 200   # cached stays free
    finally:
        main.LIVE_PER_IP_HOUR = old


def test_iso_zones():
    from agents.tools.forecast import zone
    assert zone(1.0)[0] == "A" and zone(2.0)[0] == "B" and zone(3.6)[0] == "C" and zone(5.0)[0] == "D"