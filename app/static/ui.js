// Kaarigar UI layer: route card, grouped navigation, home wall, phone tabs. Layout only; feature code untouched.
(function () {
  const STEPS = [['detect', 'Detect'], ['diagnose', 'Diagnose'], ['act', 'Act'], ['verify', 'Verify'], ['predict', 'Predict'], ['prevent', 'Prevent'], ['learn', 'Learn']];
  const MAP = { guided_capture: 'detect', photo_quality: 'detect', golden_compare: 'detect', locate_defect: 'detect', ground_truth: 'detect',
    tolerance_check: 'detect', vision_ocr_crosscheck: 'detect', machine_health: 'diagnose', factory_memory: 'diagnose', recurrence_check: 'diagnose',
    sop_lookup: 'diagnose', supplier_history: 'diagnose', citation_check: 'diagnose', work_order: 'act', approval_gate: 'act', money_at_risk: 'act',
    quality_passport: 'act', verify: 'verify', 'forecast (BigQuery ML)': 'predict', fcm_send: 'predict', sop_change: 'prevent', learn: 'learn', register_read: 'learn' };
  const rc = document.createElement('div'); rc.id = 'route'; rc.setAttribute('aria-label', 'Kaarigar loop');
  rc.innerHTML = '<span class="rc-title">Route card</span><ol>' + STEPS.map(([k, n]) => `<li data-s="${k}">${n}</li>`).join('') + '</ol>';
  document.querySelector('header').after(rc);
  window._rcReset = () => rc.querySelectorAll('li').forEach(l => l.classList.remove('done', 'now', 'next'));
  function stamp(agent, name) {
    let s = MAP[name]; if (agent === 'Kaarigar' && name === 'factory_memory') s = 'learn'; if (!s) return;
    rc.querySelectorAll('li.now').forEach(l => l.classList.remove('now'));
    const li = rc.querySelector(`li[data-s="${s}"]`); if (li) li.classList.add('done', 'now');
    const v = rc.querySelector('li[data-s="verify"]');
    if (s === 'act' && v && !v.classList.contains('done')) v.classList.add('next'); if (s === 'verify' && v) v.classList.remove('next');
  }
  const _tool = window.tool;
  window.tool = function (a, n) { try { stamp(a, n); } catch (e) {} return _tool.apply(this, arguments); };
})();
(function () {
  const G = [['Start here', ['demoBtn', 'ownBtn']], ['Inspect and report', ['realBtn', 'calBtn', 'micBtn']],
    ['Factory', ['mapBtn', 'askBtn', 'hoBtn', 'alertBtn']], ['Quality records', ['supBtn', 'ppBtn', 'regBtn']], ['Learn', ['teachBtn']]];
  const sec = document.getElementById('demoBtn').parentElement;
  const nav = document.createElement('nav'); nav.id = 'nav'; nav.setAttribute('aria-label', 'Kaarigar features');
  sec.prepend(nav);                       // attach first, so buttons stay findable
  G.forEach(([t, ids]) => {
    const g = document.createElement('div'); g.className = 'navgrp'; g.innerHTML = `<h3>${t}</h3>`;
    ids.forEach(i => { const b = document.getElementById(i); if (b) { b.classList.remove('primary'); g.appendChild(b); } });
    nav.appendChild(g);
  });
  document.getElementById('demoBtn').classList.add('primary');
  document.addEventListener('click', e => { if (e.target.closest('#nav button, #parts')) window._rcReset(); }, true);
})();
(function () {
  function openPart(id) { window._rcReset(); const el = [...document.getElementById('parts').children].find(e => e.textContent.includes(id)); if (el) el.click(); }
  function showAlert(tries) {
    const box = document.getElementById('homeAlert'); if (!box) return;
    const bad = document.querySelector('#factory .chip.bad');
    if (!bad) { if ((tries || 0) < 80) setTimeout(() => showAlert((tries || 0) + 1), 500); return; }
    const mid = (bad.parentElement.textContent.match(/M\d/) || ['Machine'])[0];
    box.innerHTML = `<span class="pulse" aria-hidden="true"></span><span><b>${mid}</b> ${bad.textContent.trim()}</span><button id="alSee">See why</button>`;
    box.hidden = false; document.getElementById('alSee').onclick = () => document.getElementById('mapBtn').click();
  }
  window.showHome = function () {
    window._rcReset(); document.getElementById('log').innerHTML = '<div class="small">Each step the agents take appears here.</div>';
    const f = document.getElementById('flow');
    f.innerHTML = `<div id="homeAlert" class="home-alert" hidden></div><h2 class="home-h">Your golden sample wall</h2>
      <p class="home-sub">Tap a part. Kaarigar compares it with the good one, finds what is wrong and why, and drafts the fix for your supervisor.</p>
      <div id="wall" class="wall"></div>
      <div class="home-acts"><button class="primary" data-go="demoBtn">▶ Watch the full loop</button><button data-go="ownBtn">📷 Inspect your own part</button>
      <button data-go="askBtn">💬 Ask Kaarigar</button><button data-go="mapBtn">🏭 Factory map</button></div>`;
    f.querySelectorAll('[data-go]').forEach(b => b.onclick = () => document.getElementById(b.dataset.go).click());
    fetch('/api/parts').then(r => r.json()).then(d => {
      const ps = d.parts.filter(p => !p.part_id.startsWith('upload_')).slice(0, 8);
      document.getElementById('wall').innerHTML = ps.map((p, i) => `<button class="pin" data-p="${p.part_id}" style="--tilt:${[-1.2, .8, -.5, 1.1][i % 4]}deg" aria-label="Inspect ${p.part_id}">
        <img src="/api/parts/${p.part_id}/image/test" alt="" loading="lazy"><img class="gold" src="/api/parts/${p.part_id}/image/golden" alt="Golden sample">
        <span class="ok-tag">OK</span><span class="pin-name">${p.product.split('(')[0].trim()}</span>
        <span class="pin-m">${p.machine_id === 'IN' ? 'Incoming material' : p.machine_id}</span></button>`).join('');
      document.querySelectorAll('.pin').forEach(b => b.onclick = () => openPart(b.dataset.p));
    });
    showAlert(0);
  };
  const home = document.createElement('button'); home.id = 'homeBtn'; home.textContent = '🏠 Home'; home.style.width = '100%';
  const demo = document.getElementById('demoBtn'); demo.parentElement.insertBefore(home, demo); home.onclick = window.showHome;
  const logo = document.querySelector('.logo'); logo.style.cursor = 'pointer'; logo.onclick = window.showHome;
  window.showHome();
})();
(function () {
  // phone bottom tabs
  const tabs = document.createElement('nav'); tabs.id = 'tabs'; tabs.setAttribute('aria-label', 'Main');
  [['🏠', 'Home', 'homeBtn'], ['📷', 'Inspect', 'ownBtn'], ['💬', 'Ask', 'askBtn'], ['🏭', 'Factory', 'mapBtn'], ['☰', 'More', null]].forEach(([i, t, id]) => {
    const b = document.createElement('button'); b.innerHTML = `<span aria-hidden="true">${i}</span>${t}`;
    b.onclick = () => { if (id) { document.getElementById(id).click(); window.scrollTo({ top: 0, behavior: 'smooth' }); } else document.getElementById('nav').scrollIntoView({ behavior: 'smooth' }); };
    tabs.appendChild(b);
  });
  document.body.appendChild(tabs);
  // reasoning panel folds on phones (tap the title to open)
  const logSec = document.getElementById('log').parentElement; logSec.classList.add('log-wrap');
  if (window.matchMedia('(max-width:760px)').matches) logSec.classList.add('collapsed');
  logSec.querySelector('h2').onclick = () => logSec.classList.toggle('collapsed');
  // a short buzz on the phone when a defect is located
  const _t = window.tool; window.tool = function (a, n) { if (n === 'locate_defect' && navigator.vibrate) navigator.vibrate([120, 60, 120]); return _t.apply(this, arguments); };
  // label fixes
  const sup = document.getElementById('supBtn'); if (sup) sup.innerHTML = sup.innerHTML.replace('🏷️', '📊');
  const _home = window.showHome;
  window.showHome = function () {
    _home();
    const fix = () => { const pins = document.querySelectorAll('.pin'); if (!pins.length) return setTimeout(fix, 200); const n = {};
      const names = [...pins].map(p => p.querySelector('.pin-name').textContent), total = {};
      names.forEach(t => total[t] = (total[t] || 0) + 1);
      pins.forEach((p, i) => { const t = names[i]; n[t] = (n[t] || 0) + 1;
        if (total[t] > 1) p.querySelector('.pin-name').textContent = `${t} · sample ${n[t]}`;
        p.insertAdjacentHTML('beforeend', '<span class="chk-tag">Tap to check</span>'); }); };
    fix();
  };
  document.getElementById('homeBtn').onclick = window.showHome; document.querySelector('.logo').onclick = window.showHome;
  window.showHome();
})();
(function () {
  const flow = document.getElementById('flow');
  function addCompare() {
    if (flow.querySelector('.cmp')) return;
    const pick = q => [...flow.querySelectorAll(q)].find(i => !i.closest('.pin, .scanbox, .cmp'));
    const t = pick('img[src*="/image/test"]'), g = pick('img[src*="/image/golden"]');
    if (!t || !g || !t.parentElement) return;
    const box = document.createElement('div'); box.className = 'cmp';
    box.innerHTML = `<p class="small">Drag across the photo to compare the good part with this part.</p>
      <div class="cmp-stage"><img src="${t.src}" alt="Part being checked"><img class="g" src="${g.src}" alt="Golden sample">
      <span class="cmp-l">Golden sample</span><span class="cmp-r">This part</span><div class="cmp-bar"></div>
      <input type="range" min="0" max="100" value="50" aria-label="Compare the golden sample with this part"></div>`;
    t.parentElement.after(box);
    const st = box.querySelector('.cmp-stage'), r = box.querySelector('input');
    r.oninput = () => st.style.setProperty('--p', r.value + '%');
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {      // one reveal sweep: 100% -> 50%
      let v = 100; const step = () => { v -= 2; st.style.setProperty('--p', v + '%'); r.value = v; if (v > 50) requestAnimationFrame(step); };
      setTimeout(() => requestAnimationFrame(step), 400);
    }
  }
  new MutationObserver(addCompare).observe(flow, { childList: true, subtree: true });
})();
(function () {
  // features drawer (desktop): everything beyond the core actions lives here
  const db = document.createElement('button'); db.id = 'drawerBtn'; db.textContent = '☰ All features';
  const lang = document.querySelector('header select'); lang.parentElement.insertBefore(db, lang);
  db.onclick = () => document.body.classList.toggle('drawer');
  document.addEventListener('click', e => {
    if (e.target.closest('#nav button')) document.body.classList.remove('drawer');
    else if (document.body.classList.contains('drawer') && !e.target.closest('main>section:first-of-type') && e.target !== db) document.body.classList.remove('drawer');
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') document.body.classList.remove('drawer'); });
  // home: one question, one big action, one ask bar, then the wall
  const prev = window.showHome;
  window.showHome = function () {
    prev(); const f = document.getElementById('flow');
    f.querySelector('.home-acts')?.remove(); f.querySelector('.home-sub')?.remove();
    const h = f.querySelector('.home-h'); if (h) { h.className = 'wall-title'; h.textContent = 'Or tap a part on your golden sample wall'; }
    const hero = document.createElement('div'); hero.className = 'hero';
    hero.innerHTML = `<h1 class="hero-h">Is this part good?</h1>
      <p class="hero-sub">Point your phone at a part. Kaarigar compares it with the golden sample and tells you what is wrong, why, and how to fix it.</p>
      <div class="hero-acts"><button class="primary hero-cta" id="heroCheck">📷 Check a part</button><button id="heroLoop">▶ Watch the full loop</button></div>
      <form class="askbar" id="heroAsk"><span aria-hidden="true">💬</span><input id="heroQ" aria-label="Ask Kaarigar" placeholder="Ask your factory… e.g. Which machine worries you most?"><button class="primary">Ask</button></form>`;
    (document.getElementById('homeAlert') || f.firstChild).after(hero);
    hero.querySelector('#heroCheck').onclick = () => document.getElementById('ownBtn').click();
    hero.querySelector('#heroLoop').onclick = () => document.getElementById('demoBtn').click();
    hero.querySelector('#heroAsk').onsubmit = e => { e.preventDefault(); const q = hero.querySelector('#heroQ').value.trim();
      document.getElementById('askBtn').click(); if (q) setTimeout(() => { document.getElementById('askQ').value = q; runAsk(q); }, 60); };
  };
  document.getElementById('homeBtn').onclick = window.showHome; document.querySelector('.logo').onclick = window.showHome;
  window.showHome();
})();
(function () {
  const STEPS = [['photo_quality', 'Checking the photo'], ['golden_compare', 'Comparing with the golden sample'], ['locate_defect', 'Locating the defect'],
    ['machine_health', 'Checking machine health'], ['factory_memory', 'Searching Factory Memory'], ['citation_check', 'Verifying every claim'], ['root_cause', 'Finding the root cause']];
  const flow = document.getElementById('flow'); let box = null, last = 0;
  const later = (fn, gap) => { const t = Math.max(performance.now(), last + gap); last = t; setTimeout(fn, t - performance.now()); };
  function begin(pid) {
    box = document.createElement('div'); box.className = 'scanbox'; last = 0;
    box.innerHTML = `<div class="scan-img"><img src="/api/parts/${pid}/image/test" alt="Part being checked"><div class="beam"></div></div>
      <ol class="scan-list">${STEPS.map(([k, t]) => `<li data-k="${k}">${t}</li>`).join('')}</ol>`;
    flow.prepend(box); box.querySelector('li').classList.add('now');
  }
  function tick(name) {
    const b = box; if (!b) return; const li = b.querySelector(`li[data-k="${name}"]`); if (!li || li.dataset.q) return; li.dataset.q = 1;
    later(() => { if (b !== box) return; const all = [...b.querySelectorAll('li')], i = all.indexOf(li);
      all.slice(0, i).forEach(x => { if (!x.classList.contains('ok')) x.className = 'skip'; });
      li.className = 'ok'; const nx = all.slice(i + 1).find(x => !x.classList.contains('ok')); b.querySelectorAll('li.now').forEach(x => x.classList.remove('now')); if (nx) nx.classList.add('now'); }, 380);
  }
  function stampIt(defect) {
    const b = box; if (!b) return;
    later(() => { if (b !== box) return; const im = b.querySelector('.scan-img'); im.classList.add('done');
      im.insertAdjacentHTML('beforeend', `<div class="stamp ${defect ? 'bad' : 'ok'}">${defect ? 'NOT OK' : 'OK'}</div>`);
      if (defect && navigator.vibrate) navigator.vibrate([90, 50, 90]);
      if (!defect) b.querySelectorAll('li:not(.ok)').forEach(x => x.className = 'skip'); }, 450);
  }
  new MutationObserver(() => { if (box && !flow.contains(box)) flow.prepend(box); }).observe(flow, { childList: true });
  document.addEventListener('click', e => { if (e.target.closest('#nav button, #homeBtn, .logo, #heroCheck, #heroAsk, #tabs button, .pin, #heroLoop')) box = null; }, true);
  const _run = window.run; window.run = function (pid) { const r = _run.apply(this, arguments); setTimeout(() => begin(pid), 0); return r; };
  const _tool = window.tool; window.tool = function (a, n) { try { tick(n); } catch (e) {} return _tool.apply(this, arguments); };
  const _log = window.log; window.log = function (a, m) {
    try { if (a === 'Inspector' && typeof m === 'string') { if (/^Found \d+ defect/.test(m)) stampIt(true); else if (m === 'No defect found') stampIt(false); }
    if (a === 'Diagnosis' && typeof m === 'string' && /^Root cause/.test(m)) tick('root_cause'); } catch (e) {}
    return _log.apply(this, arguments);
  };
})();
(function () {
  const nice = s => s.startsWith('forecast:') ? s.split(':')[1] + ' forecast' : s.startsWith('machine_health:') ? s.split(':')[1] + ' vibration' : s === 'pattern_hints' ? 'Bearing-wear pattern'
    : s.startsWith('past_defect:L-') ? 'Learned from a past fix' : s.startsWith('past_defect:') ? 'Past case ' + s.split(':')[1].split('-').slice(0, 2).join('-') : s === 'recurrence_check' ? 'Repeat problem'
    : s.startsWith('supplier') ? 'Supplier history' : s;
  function showCause(rep) {
    const box = document.querySelector('.scanbox'); const top = (rep.likely_causes || [])[0]; if (!box || !top || box.querySelector('.cause')) return;
    const fix = ((rep.recommended_actions || [])[0] || {}).action || '';
    const chips = [...new Set((top.evidence_sources || []).map(nice))].slice(0, 4).map(c => `<span class="chip">${esc(c)}</span>`).join('');
    const card = document.createElement('div'); card.className = 'cause';
    card.innerHTML = `<div class="cause-k">Why</div><div class="cause-v">${esc(top.cause)}</div><div class="ev">${chips}</div>
      ${fix ? `<div class="cause-k">Fix</div><div class="cause-v">${esc(fix)}</div>` : ''}
      <div class="cause-acts"><button class="primary" id="causeGo">Review and approve the fix</button><button id="causeMore">See the full report</button></div>`;
    setTimeout(() => {
      box.appendChild(card);
      card.querySelector('#causeMore').onclick = () => document.querySelector('#flow .step')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      card.querySelector('#causeGo').onclick = () => {
        const btns = [...document.querySelectorAll('#flow button')].filter(b => !b.closest('.cause'));
        const t = btns.find(b => /approve/i.test(b.textContent)) || btns.find(b => /work order/i.test(b.textContent));
        if (t) { t.scrollIntoView({ behavior: 'smooth', block: 'center' }); t.classList.add('flash'); setTimeout(() => t.classList.remove('flash'), 2500); }
      };
    }, 900);
  }
  const _api = window.api;
  window.api = async function (path) {
    const d = await _api.apply(this, arguments);
    try { if (typeof path === 'string' && path.startsWith('/api/diagnose/') && d && d.report) showCause(d.report); } catch (e) {}
    return d;
  };
})();
(function () {
  function label() {
    const pins = [...document.querySelectorAll('#wall .pin')];
    if (!pins.length || pins.every(p => p.querySelector('.chk-tag'))) return;
    const base = pins.map(p => p.querySelector('.pin-name').textContent.replace(/ · sample \d+$/, '')), total = {}, n = {};
    base.forEach(t => total[t] = (total[t] || 0) + 1);
    pins.forEach((p, i) => { const t = base[i]; n[t] = (n[t] || 0) + 1;
      p.querySelector('.pin-name').textContent = total[t] > 1 ? `${t} · sample ${n[t]}` : t;
      if (!p.querySelector('.chk-tag')) p.insertAdjacentHTML('beforeend', '<span class="chk-tag">Tap to check</span>'); });
  }
  new MutationObserver(label).observe(document.getElementById('flow'), { childList: true, subtree: true });
  label();
})();
