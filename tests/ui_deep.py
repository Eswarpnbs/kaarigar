"""Deep UI check: every screen, every safe button inside it, WCAG text contrast, JS errors, dead buttons. Desktop + phone.
No AI cost and no data changes: live and state-changing API calls are blocked in the test browser. Usage: python tests/ui_deep.py [url]"""
import re, sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
VIEWS = ["homeBtn", "realBtn", "ownBtn", "calBtn", "mapBtn", "supBtn", "ppBtn", "regBtn", "teachBtn", "hoBtn", "alertBtn", "askBtn"]
SKIP = re.compile(r"sign|approve|reject|run live|record|mic|camera|delete|enable|send|alert now|commit|create passport|add to factory|read register|listen|inspect$|^ask$", re.I)
CONTRAST = r"""() => {
 const p = c => { const m = c.match(/[\d.]+/g); if (!m) return null; const [r, g, b, a = 1] = m.map(Number);
   return { v: [r, g, b].map(x => { x /= 255; return x <= .03928 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4; }), a }; };
 const L = v => .2126 * v[0] + .7152 * v[1] + .0722 * v[2];
 const bg = el => { for (let e = el; e; e = e.parentElement) { const s = getComputedStyle(e), c = p(s.backgroundColor);
   if (c && c.a > .5) return c; if (s.backgroundImage !== 'none' && e !== document.body) return null; } return p('rgb(255,255,255)'); };
 const out = [];
 document.querySelectorAll('body *').forEach(el => {
   if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1)) return;
   const r = el.getBoundingClientRect(), s = getComputedStyle(el);
   if (r.width < 2 || r.height < 2 || s.visibility === 'hidden' || +s.opacity < .3 || el.closest('[hidden],img,svg')) return;
   const f = p(s.color), b = bg(el); if (!f || !b) return;
   const a = L(f.v), c = L(b.v), ratio = (Math.max(a, c) + .05) / (Math.min(a, c) + .05);
   const big = parseFloat(s.fontSize) >= 18.66 || (parseFloat(s.fontSize) >= 14 && +s.fontWeight >= 700);
   if (ratio < (big ? 3 : 4.5)) out.push(`"${el.textContent.trim().slice(0, 34)}" ratio ${ratio.toFixed(2)} (${s.color})`);
 });
 return [...new Set(out)].slice(0, 12); }"""


def run(pg, vw, out):
    errs, reqs = [], []
    pg.on("pageerror", lambda e: errs.append("JS: " + str(e)[:150]))
    pg.on("request", lambda r: reqs.append(r.url))
    def route(r):
        q = r.request
        if q.method == "GET" or "/api/diagnose/" in q.url or "/api/inspect" in q.url: return r.continue_()
        return r.fulfill(status=418, content_type="application/json", body='{"detail":"blocked in UI test"}')
    pg.route("**/api/**", route)
    pg.goto(URL); pg.wait_for_timeout(5000)
    pg.evaluate("window.__m=0;new MutationObserver(()=>window.__m++).observe(document.body,{subtree:true,childList:true,attributes:true,characterData:true})")
    for v in VIEWS:
        open_ = lambda: (pg.evaluate(f"document.getElementById('{v}')&&document.getElementById('{v}').click()"), pg.wait_for_timeout(2200))
        open_(); n0 = len(errs)
        low = pg.evaluate(CONTRAST)
        labels = pg.evaluate("""() => [...document.querySelectorAll('#flow button')].filter(b => b.offsetParent).map(b => b.textContent.trim().slice(0, 40))""")
        labels = [l for l in labels if l and not SKIP.search(l)][:10]; dead = []
        for i, lab in enumerate(labels):
            open_(); m0, r0 = pg.evaluate("window.__m"), len(reqs)
            ok = pg.evaluate("""(t) => { const b = [...document.querySelectorAll('#flow button')].filter(x => x.offsetParent && x.textContent.trim().slice(0,40) === t)[0]; if (!b) return false; b.click(); return true; }""", lab)
            pg.wait_for_timeout(1300)
            if ok and pg.evaluate("window.__m") == m0 and len(reqs) == r0: dead.append(lab)
        out.append((vw, v, len(labels), errs[n0:], dead, low))


with sync_playwright() as p:
    b = p.chromium.launch(); out = []
    for vw, size in [("desktop", {"width": 1440, "height": 900}), ("phone", {"width": 390, "height": 844})]:
        pg = b.new_page(viewport=size); run(pg, vw, out); pg.close()
    b.close()
issues = 0
for vw, v, n, e, dead, low in out:
    bad = bool(e or dead or low); issues += bad
    print(f"{'OK ' if not bad else '⚠️ '} {vw:7} {v:9} {n} buttons clicked")
    for x in e[:3]: print("      error:", x)
    for x in dead: print("      dead button:", x)
    for x in low[:6]: print("      hard to read:", x)
print(f"\n{issues} screen(s) with issues")
