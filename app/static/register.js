// Paper register -> Factory Memory: Gemini reads the page, code validates every field, supervisor approves.
let regRows = [];
function showRegister() {
  t0 = performance.now(); $('#log').innerHTML = '';
  $('#flow').innerHTML = `<h2>📒 Import paper register</h2>
  <p class="small">Photograph a page of your rejection or maintenance register. Gemini reads the handwriting; code checks every field
  (date, machine, defect, cause, fix); you approve; clean rows join Factory Memory. Unclear rows are flagged, never guessed.</p>
  <p><input id="regF" type="file" accept="image/*" capture="environment"> <button class="primary" id="regGo">Read register</button></p>
  <div id="regOut" data-noai></div>`;
  $('#regGo').onclick = readRegister;
}
async function readRegister() {
  const f = $('#regF').files[0]; if (!f) { alert('Please choose or take a photo of a register page'); return; }
  $('#regGo').disabled = true; $('#regOut').innerHTML = '<span class="spinner"></span><span class="small">Reading the handwriting…</span>';
  log('Kaarigar', 'Register: Gemini reads the page; code validates every field');
  try {
    const fd = new FormData(); fd.append('image', f);
    const r = await fetch('/api/register/read', { method: 'POST', body: fd }); const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Could not read the page');
    regRows = d.rows;
    const row = (x, i) => `<tr style="border-top:1px solid #262b36"><td><input type="checkbox" class="regC" data-i="${i}" ${x.status === 'ok' ? 'checked' : 'disabled'}></td>
      <td>${esc(x.date || x.date_text)}</td><td>${esc(x.machine_id || x.machine_text)}</td><td>${esc(x.part)}</td>
      <td>${esc(x.defect_type)}<br><span class="small">${esc(x.defect_text)}</span></td><td>${esc(x.cause)}</td><td>${esc(x.fix)}</td>
      <td>${x.status === 'ok' ? '<span class="chip ok">✅</span>' : `<span class="chip warn">${esc(x.issues.join(', '))}</span>`}</td></tr>`;
    $('#regOut').innerHTML = `<p><span class="chip ok">${d.ok} clean row(s)</span> <span class="chip warn">${d.rows.length - d.ok} need a check</span></p>
      <table style="width:100%;border-collapse:collapse;font-size:12px"><tr style="color:#9aa0a6;text-align:left"><th></th><th>Date</th><th>Machine</th>
      <th>Part</th><th>Defect</th><th>Cause</th><th>Fix</th><th>Check</th></tr>${d.rows.map(row).join('')}</table>
      ${d.notes ? `<p class="small">${esc(d.notes)}</p>` : ''}<p><button class="ok" id="regOk">Approve & add to Factory Memory</button></p><div id="regDone"></div>`;
    tool('Kaarigar', 'register_read', `${d.rows.length} rows read · ${d.ok} pass the code checks`);
    $('#regOk').onclick = commitRegister;
  } catch (e) { $('#regOut').innerHTML = `<p class="small">${esc(e.message || e)}</p>`; }
  finally { $('#regGo').disabled = false; }
}
async function commitRegister() {
  const rows = [...document.querySelectorAll('.regC')].filter(c => c.checked).map(c => regRows[+c.dataset.i]);
  if (!rows.length) { alert('No rows selected'); return; }
  if (!window.kAuth || !window.kAuth.user) {
    if (!confirm('Adding history needs a signed-in supervisor. Sign in as the demo supervisor?')) return;
    await window.kAuth.signIn();
  }
  $('#regOk').disabled = true; const tok = await window.kAuth.token();
  const r = await fetch('/api/register/commit', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok }, body: JSON.stringify({ rows }) });
  const d = await r.json();
  if (!r.ok) { $('#regDone').innerHTML = `<p class="small">${esc(d.detail || 'Error')}</p>`; $('#regOk').disabled = false; return; }
  $('#regDone').innerHTML = `<p><span class="chip ok">🧠 ${d.added.length} record(s) added to Factory Memory</span>
    <span class="small">Marked "imported from paper register". Diagnoses, recurrence checks and the supplier scorecard use them from now on.</span></p>`;
  tool('Kaarigar', 'factory_memory', `+${d.added.length} from the paper register (approved by a supervisor)`);
}
