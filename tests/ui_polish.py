"""Visual polish audit: emojis in UI text, overflowing text, small tap targets (phone), horizontal scroll, font variety,
images without alt. Desktop + phone, every screen; screenshots in /tmp/ui_polish. No AI cost. Usage: python tests/ui_polish.py [url]"""
import sys
from collections import Counter, defaultdict
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
VIEWS = ["homeBtn", "realBtn", "ownBtn", "calBtn", "mapBtn", "supBtn", "ppBtn", "regBtn", "hoBtn", "alertBtn", "askBtn"]
OUT = Path("/tmp/ui_polish"); OUT.mkdir(exist_ok=True)
AUDIT = r"""(phone) => {
 const vis = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
   return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && +s.opacity > .2 && !el.closest('[hidden]'); };
 const EMO = /\p{Extended_Pictographic}/u, o = { emoji: [], overflow: [], tap: [], fonts: {}, sizes: {}, noalt: 0 };
 document.querySelectorAll('body *').forEach(el => {
   if (!vis(el)) return;
   const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').trim();
   if (!own) return;
   const s = getComputedStyle(el);
   if (EMO.test(own)) o.emoji.push(own.slice(0, 42));
   if (el.scrollWidth > el.clientWidth + 3 && s.whiteSpace !== 'nowrap' || el.scrollHeight > el.clientHeight + 6 && s.overflow === 'hidden')
     o.overflow.push(own.slice(0, 42));
   const f = s.fontFamily.split(',')[0].replace(/["']/g, ''); o.fonts[f] = (o.fonts[f] || 0) + 1; o.sizes[s.fontSize] = (o.sizes[s.fontSize] || 0) + 1;
 });
 if (phone) document.querySelectorAll('button,a,input,select,[role=button]').forEach(b => {
   if (!vis(b)) return; const r = b.getBoundingClientRect();
   if (r.height < 40) o.tap.push(((b.textContent || b.getAttribute('aria-label') || b.tagName).trim().slice(0, 28)) + ` (${Math.round(r.height)}px)`);
 });
 document.querySelectorAll('img').forEach(i => { if (vis(i) && !i.alt) o.noalt++; });
 o.hscroll = document.documentElement.scrollWidth > innerWidth + 2;
 return o; }"""


def block(r):
    return r.continue_() if r.request.method == "GET" or "/api/diagnose/" in r.request.url or "/api/inspect" in r.request.url \
        else r.fulfill(status=418, content_type="application/json", body='{"detail":"blocked in UI test"}')


issues = defaultdict(lambda: defaultdict(set)); fonts, sizes, hs, noalt = Counter(), Counter(), [], 0
with sync_playwright() as p:
    b = p.chromium.launch()
    for vw, size in [("desktop", {"width": 1440, "height": 900}), ("phone", {"width": 390, "height": 844})]:
        pg = b.new_page(viewport=size); pg.route("**/api/**", block); pg.goto(URL); pg.wait_for_timeout(5000)
        for v in VIEWS:
            pg.evaluate(f"document.getElementById('{v}') && document.getElementById('{v}').click()"); pg.wait_for_timeout(2500)
            r = pg.evaluate(AUDIT, vw == "phone"); pg.screenshot(path=str(OUT / f"{vw}_{v}.png"), full_page=True)
            for k in ("emoji", "overflow", "tap"):
                for x in r[k]: issues[k][x].add(f"{vw}:{v}")
            fonts.update(r["fonts"]); sizes.update(r["sizes"]); noalt += r["noalt"]
            if r["hscroll"]: hs.append(f"{vw}:{v}")
        pg.close()
    b.close()
for k, title in (("emoji", "EMOJIS IN UI TEXT"), ("overflow", "TEXT OVERFLOWING ITS BOX"), ("tap", "SMALL TAP TARGETS (phone)")):
    print(f"\n== {title}: {len(issues[k])}")
    for x, where in sorted(issues[k].items(), key=lambda kv: -len(kv[1]))[:15]: print(f"  {x!r}  ({len(where)} screens)")
print("\n== HORIZONTAL SCROLL:", hs or "none")
print("== FONT FAMILIES:", dict(fonts.most_common(6)))
print("== FONT SIZES in use:", len(sizes), "->", [s for s, _ in sizes.most_common(12)])
print("== IMAGES WITHOUT ALT:", noalt, "\nScreenshots:", OUT)
