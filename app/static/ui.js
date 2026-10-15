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
  window._rcReset = () => rc.querySelectorAll('li').forEach(l => l.classList.remove('done', 'now'));
  function stamp(agent, name) {
    let s = MAP[name]; if (agent === 'Kaarigar' && name === 'factory_memory') s = 'learn'; if (!s) return;
    rc.querySelectorAll('li.now').forEach(l => l.classList.remove('now'));
    const li = rc.querySelector(`li[data-s="${s}"]`); if (li) li.classList.add('done', 'now');
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
    const t = flow.querySelector('img[src*="/image/test"]'), g = flow.querySelector('img[src*="/image/golden"]');
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
