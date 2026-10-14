// Quality Passport: a shareable, tamper-evident record of a batch's quality evidence.
async function showPassport() {
  t0 = performance.now(); $('#log').innerHTML = '';
  $('#flow').innerHTML = `<h2>🏷️ Quality Passport</h2><p class="small">A shareable record of a batch's quality evidence for your customer:
  inspections, defects, containment, verified fixes and who approved them. The status is computed in code; the record is fingerprinted, so any later change is detectable.</p>
  <p><select id="ppSel"></select> <button class="primary" id="ppGo">Create passport</button></p><div id="ppOut" data-noai></div>`;
  const d = await api('/api/passport/options');
  $('#ppSel').innerHTML = d.options.map((o, i) => `<option value="${i}">${esc(o.product)} · batch ${esc(o.batch)}</option>`).join('');
  window._ppOpts = d.options; $('#ppGo').onclick = createPassport;
}
async function createPassport() {
  const o = window._ppOpts[+$('#ppSel').value]; if (!o) return;
  if (!window.kAuth || !window.kAuth.user) { if (!confirm('Issuing a passport needs a signed-in supervisor. Sign in as the demo supervisor?')) return; await window.kAuth.signIn(); }
  $('#ppGo').disabled = true; const tok = await window.kAuth.token();
  try {
    const r = await fetch('/api/passport', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok }, body: JSON.stringify({ product: o.product, batch: o.batch }) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || 'Could not create the passport');
    $('#ppOut').innerHTML = `<p><span class="chip ${d.passport_status === 'RELEASED' ? 'ok' : 'warn'}">${esc(d.passport_status)}</span>
      <span class="small">fingerprint ${esc(d.fingerprint.slice(0, 16))}…</span></p>
      <p><img src="data:image/png;base64,${d.qr_png}" style="width:160px;background:#fff;padding:6px;border-radius:8px"></p>
      <p><a href="${d.path}" target="_blank" style="color:#f59e0b">Open the passport</a> · <span class="small">${esc(d.url)}</span></p><p><a href="https://wa.me/?text=${encodeURIComponent("Quality Passport · "+o.product+" · batch "+o.batch+": "+d.url)}" target="_blank" style="color:#22c55e">📤 Share on WhatsApp</a></p>`;
    tool('Action', 'quality_passport', `${o.product} · ${o.batch} → ${d.passport_status} (rule in code, fingerprinted)`);
  } catch (e) { $('#ppOut').innerHTML = `<p class="small">${esc(e.message || e)}</p>`; }
  finally { $('#ppGo').disabled = false; }
}
