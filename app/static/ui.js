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
      if (!document.getElementById('wall')) return; document.getElementById('wall').innerHTML = ps.map((p, i) => `<button class="pin" data-p="${p.part_id}" style="--tilt:${[-1.2, .8, -.5, 1.1][i % 4]}deg" aria-label="Inspect ${p.part_id}">
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
    const fix = () => { const pins = document.querySelectorAll('#wall .pin'); if (!pins.length) return; const n = {};
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
      card.querySelector('#causeMore').onclick = () => {
        const steps = [...document.querySelectorAll('#flow .step')];
        const t = steps.find(s => /diagnos/i.test((s.querySelector('h2') || {}).textContent || '')) || steps[0]; if (!t) return;
        window.scrollTo({ top: t.getBoundingClientRect().top + window.scrollY - 90, behavior: 'smooth' });
        t.classList.add('flash'); setTimeout(() => t.classList.remove('flash'), 2200);
      };
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
(function () {
  const wall = window.showHome; window.showWall = wall;
  const go = id => document.getElementById(id).click();
  window.showFloor = function () {
    window._rcReset && window._rcReset();
    document.getElementById('log').innerHTML = '<div class="small">Each step the agents take appears here.</div>';
    const f = document.getElementById('flow');
    f.innerHTML = `<div id="homeAlert" class="home-alert" hidden></div>
    <h1 class="floor-h">Your shop floor, live</h1><p class="floor-sub">Every station is a Kaarigar tool. Tap a machine, a bench or a board.</p>
    <div class="floor"><div class="fcol">
      <section class="zone" style="--z:#F28C00"><span class="zone-l">Inspection bench</span>
        <button class="primary cta-big" data-go="ownBtn">📷 Check a part</button>
        <button class="tool" data-go="demoBtn"><i>▶</i>Watch the full loop</button>
        <button class="tool" data-go="realBtn"><i>🏭</i>Real factory part (Peenya)</button>
        <button class="tool" data-go="calBtn"><i>📏</i>Check a measurement</button>
        <button class="tool" data-go="micBtn"><i>🎙</i>Report a problem by voice</button></section>
      <section class="zone" style="--z:#1E9E4A"><span class="zone-l">Quality board</span><div class="mini-wall" id="miniWall"></div>
        <button class="tool" id="fullWall"><i>📌</i>Open the golden sample wall</button></section>
      <section class="zone" style="--z:#D7261E"><span class="zone-l">Red tag area</span>
        <div class="bin"><b id="rtCount">–</b><span class="small">defects caught and held back from customers</span></div></section>
    </div><div class="aisle" aria-hidden="true"><span></span><span></span><span></span></div><div class="fcol">
      <section class="zone" style="--z:#FFFFFF;--zt:#1B2420"><span class="zone-l">Machine bay</span><div class="bay" id="bay"></div></section>
      <div class="fpair">
        <section class="zone" style="--z:#2E5E4E"><span class="zone-l">Supervisor cabin</span>
          <button class="tool" data-go="askBtn"><i>💬</i>Ask Kaarigar</button>
          <button class="tool" id="woTool"><i>🗂</i>Waiting for approval<span class="badge" id="woBadge" hidden></span></button>
          <button class="tool" data-go="hoBtn"><i>🌅</i>Shift handover</button>
          <button class="tool" data-go="alertBtn"><i>📳</i>Phone alerts</button></section>
        <section class="zone" style="--z:#1D63B8"><span class="zone-l">Stores and gate</span>
          <button class="tool" data-go="supBtn"><i>📊</i>Supplier scorecard</button>
          <button class="tool" data-go="ppBtn"><i>🏷️</i>Quality Passport</button>
          <button class="tool" data-go="regBtn"><i>📒</i>Import paper register</button></section>
      </div>
      <section class="zone" style="--z:#4A5650"><span class="zone-l">Training corner</span>
        <button class="tool" data-go="teachBtn"><i>🎓</i>Kaarigar Teaches: a guide for a new operator</button></section>
    </div></div>`;
    f.querySelectorAll('[data-go]').forEach(b => b.onclick = () => go(b.dataset.go));
    f.querySelector('#fullWall').onclick = () => wall();
    f.querySelector('#woTool').onclick = () => { go('askBtn'); setTimeout(() => { const q = 'What is waiting for my approval?'; document.getElementById('askQ').value = q; runAsk(q); }, 60); };
    window._floorData && window._floorData();
  };
})();
(function () {
  const go = id => document.getElementById(id).click();
  const openPart = id => { const el = [...document.getElementById('parts').children].find(e => e.textContent.includes(id)); if (el) el.click(); };
  window._floorData = function () {
    fetch('/api/factory').then(r => r.json()).then(j => {
      const ms = j.machines || j || []; const bay = document.getElementById('bay'); if (!bay || bay.dataset.map) return;
      bay.innerHTML = ms.map(m => { const s = String(m.status || m.health || '').toLowerCase();
        const lvl = /crit/.test(s) ? 'r' : /warn|watch|elev/.test(s) ? 'a' : 'g';
        return `<button class="mach ${lvl === 'r' ? 'crit' : ''}" data-m="${m.machine_id}" aria-label="${m.machine_id} ${s}">
          <div class="body"><span class="chuck"></span><span class="tower"><i class="lamp r ${lvl === 'r' ? 'on' : ''}"></i><i class="lamp a ${lvl === 'a' ? 'on' : ''}"></i><i class="lamp g ${lvl === 'g' ? 'on' : ''}"></i></span></div>
          <div class="mn">${m.machine_id}</div><div class="mv">${esc(m.name || '')}</div><div class="mv">${esc(s)}</div></button>`; }).join('');
      bay.querySelectorAll('.mach').forEach(b => b.onclick = () => go('mapBtn'));
    }).catch(() => {});
    fetch('/api/parts').then(r => r.json()).then(d => {
      const mw = document.getElementById('miniWall'); if (!mw) return;
      mw.innerHTML = d.parts.filter(p => !p.part_id.startsWith('upload_')).slice(0, 6).map((p, i) =>
        `<button class="pin" data-p="${p.part_id}" style="--tilt:${[-1.5, 1, -.6, 1.3, -1, .7][i]}deg" aria-label="Inspect ${p.part_id}"><img src="/api/parts/${p.part_id}/image/test" alt=""><img class="gold" src="/api/parts/${p.part_id}/image/golden" alt="Golden sample"><span class="ok-tag">OK</span><span class="pin-cap">${esc(p.product.split('(')[0].trim())}</span></button>`).join('');
      mw.querySelectorAll('.pin').forEach(b => b.onclick = () => openPart(b.dataset.p));
    }).catch(() => {});
    fetch('/api/impact').then(r => r.json()).then(j => { const n = j.defects_caught ?? j.defects ?? j.caught; if (n != null) document.getElementById('rtCount').textContent = n; }).catch(() => {});
    fetch('/api/work-orders').then(r => r.json()).then(j => { const a = Array.isArray(j) ? j : (j.work_orders || []);
      const n = a.filter(w => w.status === 'pending_approval').length; const b = document.getElementById('woBadge'); if (b && n) { b.textContent = n; b.hidden = false; } }).catch(() => {});
    const box = document.getElementById('homeAlert'); const bad = document.querySelector('#factory .chip.bad');
    if (box && bad) { box.innerHTML = `<span class="pulse"></span><span><b>${(bad.parentElement.textContent.match(/M\d/) || [''])[0]}</b> ${bad.textContent.trim()}</span><button id="alSee">See why</button>`; box.hidden = false; document.getElementById('alSee').onclick = () => go('mapBtn'); }
  };
  window.showHome = () => (window.matchMedia('(min-width:761px)').matches ? window.showFloor() : window.showWall());
  document.getElementById('homeBtn').onclick = window.showHome; document.querySelector('.logo').onclick = window.showHome;
  window.showHome();
})();
(function () {
  const base = window.showFloor;
  window.showFloor = function () {
    base();
    const f = document.getElementById('flow'), floor = f.querySelector('.floor'); if (!floor || f.querySelector('.bldg')) return;
    const [left, , right] = floor.children, pair = right.querySelector('.fpair');
    const train = [...right.children].find(s => s.textContent.includes('Training'));
    const red = [...left.children].find(s => s.textContent.includes('Red tag'));
    right.appendChild(red);
    const sb = document.createElement('section'); sb.className = 'zone'; sb.style.setProperty('--z', '#4A5650');
    sb.innerHTML = '<span class="zone-l">Tool shadow board</span><div class="shadow-board" aria-hidden="true"><span>🔧</span><span>🔩</span><span>⚙️</span><span>📏</span><span>🪛</span><span>🔨</span></div>';
    right.appendChild(sb);
    const office = document.createElement('div'); office.className = 'office'; office.append(...pair.children); office.appendChild(train); pair.remove();
    const b = document.createElement('div'); b.className = 'bldg';
    const teeth = [0, 166, 332, 498, 664, 830];
    b.innerHTML = `<div class="roof" aria-hidden="true"><svg viewBox="0 0 1000 72" preserveAspectRatio="none">
        <polygon points="0,72 0,40 ${teeth.map(x => `${x},40 ${x + 166},6 ${x + 166},40`).join(' ')} 1000,72" fill="#7C8A83"/>
        ${teeth.map(x => `<rect x="${x + 158}" y="9" width="7" height="30" fill="#BFD8E6"/>`).join('')}</svg></div>
      <div class="chimney" aria-hidden="true"><span class="puff"></span><span class="puff"></span><span class="puff"></span></div>
      <div class="vent" aria-hidden="true">⚙️</div><div class="pipe" aria-hidden="true"></div>
      <nav class="lift" aria-label="Floors"><button data-l="lvl1" aria-label="Level 1, office">1</button><button data-l="lvl0" aria-label="Ground floor, production">G</button></nav>
      <div class="level" id="lvl1"><span class="lvl-tag">Level 1 · Office</span></div><div class="slab"></div>
      <div class="level" id="lvl0"><span class="lvl-tag">Ground floor · Production</span></div><div class="ground"></div>`;
    floor.before(b); b.querySelector('#lvl1').appendChild(office); b.querySelector('#lvl0').appendChild(floor);
    b.querySelectorAll('.lift button').forEach(x => x.onclick = () => { const l = document.getElementById(x.dataset.l);
      l.scrollIntoView({ behavior: 'smooth', block: 'start' }); l.classList.add('lit'); setTimeout(() => l.classList.remove('lit'), 1500); });
  };
  window.showHome = () => (window.matchMedia('(min-width:761px)').matches ? window.showFloor() : window.showWall());
  document.getElementById('homeBtn').onclick = window.showHome; document.querySelector('.logo').onclick = window.showHome;
  window.showHome();
})();
(function () {
  const ICON = { ownBtn: 'camera', demoBtn: 'player-play', realBtn: 'building-factory-2', calBtn: 'ruler-measure', micBtn: 'microphone',
    askBtn: 'message-chatbot', hoBtn: 'arrows-exchange', alertBtn: 'device-mobile-vibration', supBtn: 'chart-bar', ppBtn: 'certificate',
    regBtn: 'notebook', teachBtn: 'school' };
  const base = window.showFloor;
  window.showFloor = function () {
    base();
    const b = document.querySelector('#flow .bldg'); if (!b) return;
    b.querySelectorAll('.roof,.chimney,.vent,.pipe,.lift').forEach(e => e.remove());
    [...b.querySelectorAll('.zone')].filter(z => z.textContent.includes('Tool shadow board')).forEach(z => z.remove());
    b.querySelectorAll('[data-go]').forEach(btn => { const n = ICON[btn.dataset.go]; if (!n) return;
      const old = btn.querySelector('i'); const ic = `<i class="ti ti-${n}" aria-hidden="true"></i>`;
      if (old) old.outerHTML = ic; else btn.innerHTML = ic + btn.textContent.replace(/^[^\w]+/, '').trim(); });
    const swap = (sel, n) => { const e = b.querySelector(sel); if (e) { const i = e.querySelector('i'); if (i) i.outerHTML = `<i class="ti ti-${n}" aria-hidden="true"></i>`; } };
    swap('#woTool', 'clipboard-check'); swap('#fullWall', 'layout-grid');
    const zones = [...b.querySelectorAll('.office .zone')];
    const cabin = zones.find(z => z.textContent.includes('Supervisor')), train = zones.find(z => z.textContent.includes('Training'));
    if (cabin && train) { cabin.append(...train.querySelectorAll('button')); train.remove(); }
  };
  window.showHome = () => (window.matchMedia('(min-width:761px)').matches ? window.showFloor() : window.showWall());
  document.getElementById('homeBtn').onclick = window.showHome; document.querySelector('.logo').onclick = window.showHome;
  window.showHome();
})();
(function () {
  const base = window.showFloor;
  window.showFloor = function () {
    base();
    const b = document.querySelector('#flow .bldg'); if (!b) return;
    const l0 = b.querySelector('#lvl0'), l1 = b.querySelector('#lvl1'), slab = b.querySelector('.slab');
    if (l0 && l1 && slab) { b.prepend(l0); l0.after(slab); slab.after(l1); }
    const t0 = l0 && l0.querySelector('.lvl-tag'), t1 = l1 && l1.querySelector('.lvl-tag');
    if (t0) t0.textContent = 'Production floor'; if (t1) t1.textContent = 'Office, upstairs';
  };
  const flow = document.getElementById('flow');
  new MutationObserver(() => document.body.classList.toggle('home', !!flow.querySelector('.bldg'))).observe(flow, { childList: true });
  window.showHome = () => (window.matchMedia('(min-width:761px)').matches ? window.showFloor() : window.showWall());
  document.getElementById('homeBtn').onclick = window.showHome; document.querySelector('.logo').onclick = window.showHome;
  window.showHome();
})();
(function () {
  const base = window.showFloor;
  window.showFloor = function () {
    base();
    const floor = document.querySelector('#flow .floor'), office = document.querySelector('#flow .office'); if (!floor || !office) return;
    const right = floor.children[2]; const pair = document.createElement('div'); pair.className = 'fpair';
    pair.append(...office.querySelectorAll(':scope > .zone')); right.appendChild(pair);
  };
  window.showHome = () => (window.matchMedia('(min-width:761px)').matches ? window.showFloor() : window.showWall());
  document.getElementById('homeBtn').onclick = window.showHome; document.querySelector('.logo').onclick = window.showHome;
  window.showHome();
})();
(function () {
  const base = window._floorData;
  window._floorData = function () {
    base();
    fetch('/api/map').then(r => r.json()).then(j => {
      const bay = document.getElementById('bay'); if (!bay || !j.machines) return; bay.dataset.map = 1;
      bay.innerHTML = j.machines.map(m => {
        const lvl = m.health === 'critical' ? 'r' : /warn|watch/.test(m.health || '') ? 'a' : 'g';
        const h = (m.history || []).slice(-24).map(x => x.v), lim = 4.5, lo = Math.min(...h, 0.5), hi = Math.max(...h, lim);
        const y = v => (30 - (v - lo) / (hi - lo) * 30).toFixed(1);
        const pts = h.map((v, i) => `${(i / Math.max(h.length - 1, 1) * 100).toFixed(1)},${y(v)}`).join(' ');
        const risk = m.hours_to_zone_d != null ? `<div class="risk">Damage zone in ~${Math.round(m.hours_to_zone_d)} h</div>${m.plan_short ? `<div class="plan" title="${esc(m.plan || '')}">🛠 ${esc(m.plan_short)}</div>` : ''}` : `<div class="mv">${esc(m.trend || '')}</div>`;
        return `<button class="mach ${lvl === 'r' ? 'crit' : ''}" data-m="${m.machine_id}" aria-label="${m.machine_id}, ${m.latest_vibration} millimetres per second, zone ${m.zone}">
          <div class="body"><span class="tower"><i class="lamp r ${lvl === 'r' ? 'on' : ''}"></i><i class="lamp a ${lvl === 'a' ? 'on' : ''}"></i><i class="lamp g ${lvl === 'g' ? 'on' : ''}"></i></span>
            <div class="rd" data-noai><b>${Number(m.latest_vibration).toFixed(2)}</b><small>mm/s</small></div>
            <svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true"><line x1="0" x2="100" y1="${y(lim)}" y2="${y(lim)}"/><polyline points="${pts}"/></svg></div>
          <div class="mn">${m.machine_id}<span class="zc ${m.zone}">Zone ${m.zone}</span></div><div class="mv">${esc(m.name || '')}</div>${risk}</button>`;
      }).join('');
      bay.querySelectorAll('.mach').forEach(b => b.onclick = () => document.getElementById('mapBtn').click());
    }).catch(() => {});
  };
  window.showHome();
})();
(function () {
  const base = window.showFloor;
  window.showFloor = function () {
    base();
    const floor = document.querySelector('#flow .floor'); if (!floor || floor.classList.contains('grid5s')) return;
    const zones = [...floor.querySelectorAll('.zone')], find = t => zones.find(z => (z.querySelector('.zone-l') || {}).textContent?.includes(t));
    const areas = { bench: find('Inspection'), board: find('Quality'), red: find('Red tag'), bay: find('Machine'), cabin: find('Supervisor'), store: find('Stores') };
    const aisle = floor.querySelector('.aisle'); floor.innerHTML = ''; floor.classList.add('grid5s');
    Object.entries(areas).forEach(([k, z]) => { if (z) { z.style.gridArea = k; floor.appendChild(z); } });
    if (aisle) { aisle.style.gridArea = 'aisle'; floor.appendChild(aisle); }
  };
  window.showHome();
})();
(function () {
  const hdr = document.querySelector('header'), tag = hdr.querySelector('.tag');
  const live = document.createElement('span'); live.id = 'hdrLive'; live.innerHTML = '<i></i>Live'; (tag || hdr.firstChild).after(live);
  fetch('/api/map').then(r => r.json()).then(j => { const ms = j.machines || [], c = ms.filter(m => m.health === 'critical').length;
    live.innerHTML = `<i></i>Live · ${ms.length} machines${c ? ` · ${c} critical` : ''}`; live.classList.toggle('bad', c > 0); }).catch(() => {});
  const LBL = { defects_caught: 'Defects caught', repeat_problems: 'Repeat problems found', fixes_verified: 'Fixes verified',
    lessons_learned: 'Lessons learned', sops_improved: 'SOPs improved', ai_cost_today_inr: 'Live AI cost today (₹)' };
  const nice = k => LBL[k] || k.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
  const base = window.showFloor;
  window.showFloor = function () {
    base();
    const floor = document.querySelector('#flow .floor.grid5s'); if (!floor || floor.querySelector('.stack')) return;
    const zs = [...floor.querySelectorAll(':scope > .zone')], f = t => zs.find(z => z.querySelector('.zone-l').textContent.includes(t));
    const store = f('Stores'), red = f('Red tag'); if (!store || !red) return;
    const st = document.createElement('div'); st.className = 'stack'; st.style.gridArea = 'store'; store.style.gridArea = red.style.gridArea = '';
    const sb = document.createElement('section'); sb.className = 'zone'; sb.style.setProperty('--z', '#4A5650');
    sb.innerHTML = '<span class="zone-l">Shift board</span><div class="kpis" id="kpis"></div>';
    floor.appendChild(st); st.append(store, red, sb);
    fetch('/api/impact').then(r => r.json()).then(j => {
      const el = document.getElementById('kpis'); if (!el) return;
      el.innerHTML = Object.entries(j).filter(([, v]) => typeof v === 'number').slice(0, 6)
        .map(([k, v]) => `<div class="kpi"><b>${Math.round(v * 100) / 100}</b><span>${esc(nice(k))}</span></div>`).join('');
    }).catch(() => {});
  };
  window.showHome();
})();
(function () {
  const base = window.showFloor;
  window.showFloor = function () {
    base();
    const h = document.querySelector('#flow .floor-h'); if (!h || document.querySelector('#flow .demo-cta')) return;
    const top = document.createElement('div'); top.className = 'floor-top'; h.before(top);
    const txt = document.createElement('div'); txt.append(h, document.querySelector('#flow .floor-sub')); top.appendChild(txt);
    const b = document.createElement('button'); b.className = 'demo-cta';
    b.innerHTML = '<i class="ti ti-player-play" aria-hidden="true"></i>Try the demo: the full loop in 60 seconds';
    b.onclick = () => document.getElementById('demoBtn').click(); top.appendChild(b);
  };
  window.showHome();
})();
(function () {
  const _gt = window.showGT;
  window.showGT = async function (partId) {
    await _gt.apply(this, arguments);
    const ov = document.querySelector('#s1 img[alt="expert defect mask"]'), btn = document.getElementById('gtBtn'); if (!ov || !btn) return;
    const wrap = ov.parentElement; wrap.style.position = 'relative';
    const c = document.createElement('canvas'); c.setAttribute('aria-label', 'Expert defect area');
    c.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;display:none';
    const img = new Image();
    img.onload = () => { c.width = img.naturalWidth; c.height = img.naturalHeight; const x = c.getContext('2d'); x.drawImage(img, 0, 0);
      const d = x.getImageData(0, 0, c.width, c.height);
      for (let i = 0; i < d.data.length; i += 4) { const on = d.data[i] > 127; d.data[i] = 43; d.data[i + 1] = 212; d.data[i + 2] = 107; d.data[i + 3] = on ? 150 : 0; }
      x.putImageData(d, 0, 0); };
    img.src = ov.src; ov.remove(); wrap.appendChild(c);
    btn.onclick = () => { const on = c.style.display === 'none'; c.style.display = on ? 'block' : 'none';
      btn.textContent = on ? '🎯 Hide ground truth' : '🎯 Ground truth'; btn.classList.toggle('primary', on); };
  };
})();
(function () {
  function numberBoard() {
    const caps = [...document.querySelectorAll('#miniWall .pin-cap')]; if (!caps.length || caps.every(c => c.dataset.n)) return;
    const base = caps.map(c => c.textContent.replace(/ · sample \d+$/, '')), total = {}, n = {};
    base.forEach(t => total[t] = (total[t] || 0) + 1);
    caps.forEach((c, i) => { const t = base[i]; n[t] = (n[t] || 0) + 1; c.textContent = total[t] > 1 ? `${t} · sample ${n[t]}` : t; c.dataset.n = 1; });
  }
  new MutationObserver(numberBoard).observe(document.getElementById('flow'), { childList: true, subtree: true });
  numberBoard();
})();
(function () {   // "Check a measurement": explain instead of doing nothing when no photo is chosen
  document.addEventListener('click', e => {
    const b = e.target.closest('#calGo'); if (!b) return;
    const fi = document.querySelector('#flow input[type=file]');
    if (fi && !fi.files.length) {
      e.stopImmediatePropagation(); e.preventDefault();
      let m = document.getElementById('calNeed');
      if (!m) { m = document.createElement('p'); m.id = 'calNeed'; m.style.cssText = 'color:#A3201A;font-weight:600;margin:6px 0'; b.after(m); }
      m.textContent = 'Take or choose a photo of the caliper display first.';
      fi.addEventListener('change', () => m.remove(), { once: true });
    }
  }, true);
})();
(function () {
  const go = id => document.getElementById(id).click();
  window.showWorker = function () {
    window._rcReset && window._rcReset();
    const f = document.getElementById('flow');
    f.innerHTML = `<h1 class="wk-h">What do you want to do?</h1>
      <button class="wk-btn primary" data-go="ownBtn"><i class="ti ti-camera" aria-hidden="true"></i>Check a part</button>
      <button class="wk-btn b2" data-go="micBtn"><i class="ti ti-microphone" aria-hidden="true"></i>Speak a problem</button>
      <button class="wk-btn" data-go="calBtn"><i class="ti ti-ruler-measure" aria-hidden="true"></i>Measure</button>
      <div class="wk-links"><button id="wkWall">Golden sample wall</button><button id="wkFloor">Shop floor (supervisor)</button></div>`;
    f.querySelectorAll('[data-go]').forEach(b => b.onclick = () => go(b.dataset.go));
    f.querySelector('#wkWall').onclick = () => window.showWall(); f.querySelector('#wkFloor').onclick = () => window.showFloor();
  };
  window.showHome = () => (window.matchMedia('(min-width:761px)').matches ? window.showFloor() : window.showWorker());
  document.getElementById('homeBtn').onclick = window.showHome; document.querySelector('.logo').onclick = window.showHome;
  window.showHome();
})();
(function () {
  const SAY = { ok: { en: 'Part is OK.', kn: 'ಭಾಗ ಸರಿ ಇದೆ.', hi: 'पार्ट ठीक है।', te: 'భాగం సరిగా ఉంది.' },
    bad: { en: 'Defect found. Set the part aside.', kn: 'ದೋಷ ಕಂಡುಬಂದಿದೆ. ಭಾಗವನ್ನು ಪಕ್ಕಕ್ಕಿಡಿ.', hi: 'खराबी मिली। पार्ट को अलग रखें।', te: 'లోపం కనిపించింది. భాగాన్ని పక్కన పెట్టండి.' },
    amber: { en: 'Not sure. Please check by eye.', kn: 'ಖಚಿತವಿಲ್ಲ. ದಯವಿಟ್ಟು ಕಣ್ಣಿನಿಂದ ಪರಿಶೀಲಿಸಿ.', hi: 'पक्का नहीं है। कृपया आँख से जाँचें।', te: 'ఖచ్చితంగా తెలియదు. దయచేసి కంటితో తనిఖీ చేయండి.' } };
  const WORD = { ok: 'OK', bad: 'NOT OK', amber: 'CHECK BY EYE' }, ICON = { ok: '✓', bad: '', amber: '!' };
  const unsure = () => /check by eye|retake photo/i.test(document.getElementById('flow').textContent);
  function beep(kind) { try { const a = new (window.AudioContext || window.webkitAudioContext)(), n = { ok: 1, bad: 2, amber: 3 }[kind];
      for (let i = 0; i < n; i++) { const o = a.createOscillator(), g = a.createGain(); o.frequency.value = kind === 'ok' ? 880 : kind === 'bad' ? 420 : 660;
        o.connect(g); g.connect(a.destination); g.gain.value = .15; o.start(a.currentTime + i * .22); o.stop(a.currentTime + i * .22 + .15); } } catch (e) {} }
  function verdict(kind) {
    if (!window.matchMedia('(max-width:760px)').matches || document.querySelector('.verdict')) return;
    const lang = (typeof LANG !== 'undefined' && SAY[kind][LANG]) ? LANG : 'en', say = SAY[kind][lang];
    const v = document.createElement('div'); v.className = 'verdict ' + kind; v.setAttribute('role', 'alertdialog'); v.setAttribute('aria-label', WORD[kind]);
    v.innerHTML = `<div class="v-ico">${ICON[kind]}</div><div class="v-word">${WORD[kind]}</div><div class="v-say">${say}</div>
      <div><button class="primary" id="vNext">Next part</button> <button id="vMore">See details</button></div>`;
    document.body.appendChild(v); beep(kind); if (navigator.vibrate) navigator.vibrate(kind === 'bad' ? [120, 60, 120] : [60]);
    try { speak(say, typeof uiLangCode === 'function' ? uiLangCode() : 'en-IN'); } catch (e) {}
    v.querySelector('#vNext').onclick = () => { v.remove(); document.getElementById('ownBtn').click(); };
    v.querySelector('#vMore').onclick = () => v.remove();
  }
  const _log = window.log;
  window.log = function (a, m) {
    const r = _log.apply(this, arguments);
    if (a === 'Inspector' && typeof m === 'string' && (/^Found \d+ defect/.test(m) || m === 'No defect found')) {
      const def = /^Found/.test(m);
      setTimeout(() => {
        const kind = unsure() ? 'amber' : def ? 'bad' : 'ok'; verdict(kind);
        const st = document.querySelector('#flow .stamp'); if (st && kind === 'amber') { st.className = 'stamp amber'; st.textContent = 'CHECK'; }
      }, 1200);
    }
    return r;
  };
})();
(function () {
  const flow = document.getElementById('flow');
  new MutationObserver(() => document.body.classList.toggle('worker', !!flow.querySelector('.wk-h'))).observe(flow, { childList: true });
  document.body.classList.toggle('worker', !!flow.querySelector('.wk-h'));
})();
(function () {   // Kaarigar Teaches now lives inside Ask Kaarigar (Trainer agent)
  document.addEventListener('click', e => {
    if (!e.target.closest('#teachBtn')) return;
    e.stopImmediatePropagation(); e.preventDefault();
    document.getElementById('askBtn').click();
    setTimeout(() => { const i = document.getElementById('askQ'); i.value = 'Make a new-operator guide for M1 (CNC Lathe 1).'; i.focus(); i.select(); }, 80);
  }, true);
})();

(function () {   // mark the interface language on <html> so Indian scripts get their own heading sizes
  const mark = () => { document.documentElement.dataset.ui = (typeof LANG !== 'undefined' ? LANG : 'en'); };
  const _sl = window.setLang; window.setLang = function (l) { const r = _sl.apply(this, arguments); mark(); return r; }; mark();
})();
(function () {   // one assistant: "Ask Kaarigar" covers factory questions, how-tos and operator guides
  const base = window.showFloor;
  window.showFloor = function () {
    base();
    document.querySelectorAll('#flow [data-go="teachBtn"]').forEach(b => b.remove());
    const a = document.querySelector('#flow [data-go="askBtn"]');
    if (a && !a.querySelector('.sub')) a.innerHTML = '<i class="ti ti-message-chatbot" aria-hidden="true"></i><span>Ask Kaarigar<span class="sub">Your factory · how-to questions · new-operator guides</span></span>';
  };
  window.showHome = () => (window.matchMedia('(min-width:761px)').matches ? window.showFloor() : window.showWorker());
  document.getElementById('homeBtn').onclick = window.showHome; document.querySelector('.logo').onclick = window.showHome;
  window.showHome();
})();
(function () {   // Polish: interface emojis -> Tabler line icons (also for content rendered later); alt text on images
  const MAP = { '🏠': 'home', '▶': 'player-play', '📷': 'camera', '📏': 'ruler-measure', '🎙': 'microphone', '🏭': 'building-factory-2',
    '💬': 'message-chatbot', '🌅': 'sun-high', '📳': 'device-mobile-vibration', '📊': 'chart-bar', '🏷': 'tag', '📒': 'notebook',
    '🎓': 'school', '🙋': 'user-question', '🔊': 'volume', '🛠': 'tool', '👷': 'user-shield', '⏱': 'clock-hour-4', '📄': 'file-text', '⚠': 'alert-triangle', '📸': 'camera', '🔍': 'search', '🔁': 'repeat', '✅': 'circle-check', '🧠': 'brain', '🛡': 'shield-check' };
  const RX = new RegExp('^(\\s*)(' + Object.keys(MAP).join('|') + ')\\uFE0F?\\s*');
  function fix() {
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), hits = [];
    while (w.nextNode()) { const n = w.currentNode; if (RX.test(n.textContent) && n.parentElement && !n.parentElement.closest('.verdict,.stamp,script,style,textarea,option')) hits.push(n); }
    hits.forEach(n => { const m = n.textContent.match(RX), i = document.createElement('i');
      i.className = 'ti ti-' + MAP[m[2]] + ' emo-i'; i.setAttribute('aria-hidden', 'true');
      n.textContent = n.textContent.slice(m[0].length); n.parentElement.insertBefore(i, n); });
    document.querySelectorAll('img:not([alt]),img[alt=""]').forEach(im => im.alt = im.title || 'Part photo');
  }
  let busy = false;
  new MutationObserver(() => { if (busy) return; busy = true; requestAnimationFrame(() => { fix(); busy = false; }); })
    .observe(document.body, { childList: true, subtree: true });
  fix();
})();
