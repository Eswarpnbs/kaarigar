// Kaarigar guided capture: framing guide, live quality checks, auto-capture, golden "ghost" overlay.
let camStream = null, camTimer = null;
function frameStats(video, ctx, W = 160, H = 120) {
  ctx.drawImage(video, 0, 0, W, H);
  const d = ctx.getImageData(0, 0, W, H).data, g = new Float32Array(W * H); let sum = 0;
  for (let i = 0, j = 0; i < d.length; i += 4, j++) { const v = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]; g[j] = v; sum += v; }
  let lap = 0, eb = 0, nb = 0, ec = 0, nc = 0; const bx = Math.round(W * 0.08), by = Math.round(H * 0.08);
  for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
    const i = y * W + x, e = Math.abs(4 * g[i] - g[i - 1] - g[i + 1] - g[i - W] - g[i + W]); lap += e * e;
    if (x < bx || x >= W - bx || y < by || y >= H - by) { eb += e; nb++; } else { ec += e; nc++; }
  }
  return { mean: sum / (W * H), sharp: lap / ((W - 2) * (H - 2)), border: (eb / nb) / ((ec / nc) + 1e-6), gray: g };
}
async function openCam(slot) {
  const m = document.createElement('div');
  m.style.cssText = 'position:fixed;inset:0;background:#000d;z-index:200;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px';
  const gsrc = window._shots.g || (document.getElementById('ownG') && document.getElementById('ownG').files[0]);
  const ghost = (slot === 't' && gsrc) ? URL.createObjectURL(gsrc) : null;
  m.innerHTML = `<div style="position:relative;width:min(96vw,720px)">
    <video id="camV" autoplay playsinline muted style="width:100%;border-radius:10px;display:block"></video>
    ${ghost ? `<img src="${ghost}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.35;pointer-events:none;border-radius:10px">` : ''}
    <div style="position:absolute;inset:8%;border:3px dashed #f59e0b;border-radius:12px;pointer-events:none"></div></div>
    <p style="color:#e8eaed;margin:8px 0">${slot === 'g' ? 'Photograph a GOOD part' : 'Photograph the part to CHECK'} · keep it inside the box${ghost ? ' · line it up with the faint golden photo' : ''}</p>
    <p id="camChecks"></p><p><button class="primary" id="camShot">Capture now</button> <button id="camCancel">Cancel</button></p>`;
  document.body.appendChild(m);
  const close = () => { clearInterval(camTimer); if (camStream) camStream.getTracks().forEach(t => t.stop()); camStream = null; m.remove(); };
  document.getElementById('camCancel').onclick = close;
  try { camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false }); }
  catch (e) { alert('Camera not available: ' + e.message); close(); return; }
  const v = document.getElementById('camV'); v.srcObject = camStream; await v.play().catch(() => {});
  const small = document.createElement('canvas'); small.width = 160; small.height = 120;
  const sctx = small.getContext('2d', { willReadFrequently: true }); let prev = null, good = 0;
  const capture = () => {
    const c = document.createElement('canvas'); c.width = v.videoWidth; c.height = v.videoHeight; c.getContext('2d').drawImage(v, 0, 0);
    c.toBlob(b => {
      window._shots[slot] = b;
      document.getElementById(slot === 'g' ? 'shotG' : 'shotT').innerHTML = `<img src="${URL.createObjectURL(b)}" style="height:48px;vertical-align:middle;border-radius:6px"> ✅`;
      if (window.tool) tool('Inspector', 'guided_capture', `${slot === 'g' ? 'golden' : 'part'} photo captured (light, sharp, steady, framed: checked in code)`);
      close();
    }, 'image/jpeg', 0.92);
  };
  document.getElementById('camShot').onclick = capture;
  camTimer = setInterval(() => {
    if (!v.videoWidth) return; const s = frameStats(v, sctx); let motion = 0;
    if (prev) { let t = 0; for (let i = 0; i < s.gray.length; i += 7) t += Math.abs(s.gray[i] - prev[i]); motion = t / (s.gray.length / 7); }
    prev = s.gray;
    const ok = { 'Light': s.mean > 50 && s.mean < 215, 'Sharp': s.sharp > 80, 'Steady': motion < 6, 'Whole part in frame': s.border < 0.7 };
    document.getElementById('camChecks').innerHTML = Object.entries(ok).map(([k, x]) => `<span class="chip ${x ? 'ok' : 'warn'}">${x ? '✅' : '⏳'} ${k}</span>`).join('');
    good = Object.values(ok).every(Boolean) ? good + 1 : 0;
    if (good >= 4) capture();
  }, 300);
}
