"""Automated UI check: opens every Kaarigar screen (desktop + phone), runs a cached inspection, records JS errors, saves screenshots.
No paid AI calls. Usage: python tests/ui_check.py [url]"""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
OUT = Path("/tmp/ui_test"); OUT.mkdir(exist_ok=True)
VIEWS = ["homeBtn", "ownBtn", "calBtn", "mapBtn", "supBtn", "ppBtn", "regBtn", "teachBtn", "hoBtn", "alertBtn", "askBtn"]
report = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for vw, size in [("desktop", {"width": 1440, "height": 900}), ("phone", {"width": 390, "height": 844})]:
        pg = b.new_page(viewport=size); errs = []
        pg.on("pageerror", lambda e: errs.append("JS: " + str(e)))
        pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
        pg.goto(URL); pg.wait_for_timeout(5000); pg.screenshot(path=str(OUT / f"{vw}_0_home.png"), full_page=True)
        for v in VIEWS:
            n = len(errs); pg.evaluate(f"document.getElementById('{v}') && document.getElementById('{v}').click()")
            pg.wait_for_timeout(2500); pg.screenshot(path=str(OUT / f"{vw}_{v}.png")); report.append((vw, v, errs[n:]))
        n = len(errs); pg.evaluate("window.showHome()"); pg.wait_for_timeout(3000)
        pg.evaluate("(()=>{const el=[...document.getElementById('parts').children].find(e=>e.textContent.includes('metal_nut_scratch_0')); el&&el.click();})()")
        pg.wait_for_timeout(15000)
        checks = pg.evaluate("""() => ({stamp: !!document.querySelector('.stamp'), cause_card: !!document.querySelector('.cause'),
          slider: !!document.querySelector('.cmp'), ground_truth_btn: !!document.getElementById('gtBtn'),
          route_stamps: document.querySelectorAll('#route li.done').length})""")
        pg.screenshot(path=str(OUT / f"{vw}_inspection.png"), full_page=True)
        report.append((vw, "inspection " + json.dumps(checks), errs[n:])); pg.close()
    b.close()
bad = 0
for vw, v, e in report:
    print(f"{'OK ' if not e else 'ERR'} {vw:7} {v}" + ("" if not e else "\n      " + "\n      ".join(x[:170] for x in e[:3])))
    bad += bool(e)
print(f"\n{bad} screen(s) with errors · screenshots in {OUT}")
