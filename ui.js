/**
 * UI.JS — Helpers de interfaz
 * Estado, barras, diagnóstico, score por frase, feedback
 */

// ── Score ─────────────────────────────────────────────────────────────────────

const SCORE_COLORS = {
  SS: { bg: '#b8860b', fg: '#fff8dc', glow: '#ffd700' },
  S:  { bg: '#708090', fg: '#f0f8ff', glow: '#c0c0c0' },
  A:  { bg: '#1b5e20', fg: '#c8e6c9', glow: '#4caf50' },
  B:  { bg: '#f9a825', fg: '#212121', glow: '#ffeb3b' },
  C:  { bg: '#e65100', fg: '#fff3e0', glow: '#ff9800' },
  D:  { bg: '#b71c1c', fg: '#ffcdd2', glow: '#f44336' },
};

const FEEDBACK_COLOR = '#ffeb3b'; // naranja/amarillo para ¡Sube!/¡Baja! y resto

function mostrarScoreFrase(score, feedback) {
  // Contenedor anclado debajo del timeline
  let wrap = document.getElementById('score-frase-wrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'score-frase-wrap';
    wrap.style.cssText = `
    width:100%; max-width:420px;
    background:#0d0d0d; border-top:1px solid #1a1a1a;
    padding:8px 14px; display:flex; align-items:center; gap:10px;
    transition:opacity 0.4s; min-height:44px;
    `;
    // Insertar justo después del timeline-wrap
    const tl = document.getElementById('timeline-wrap');
    tl.parentNode.insertBefore(wrap, tl.nextSibling);
  }

  const col = SCORE_COLORS[score] || SCORE_COLORS.D;
  wrap.style.opacity = '1';
  wrap.innerHTML = `
  <span style="
  font-size:1.8rem; font-weight:900; letter-spacing:1px;
  color:${col.fg}; background:${col.bg};
  padding:2px 14px; border-radius:10px;
  box-shadow:0 0 12px ${col.glow}66;
  font-family:'Segoe UI',sans-serif; flex-shrink:0;
  ">${score}</span>
  <span style="
  font-size:0.9rem; font-weight:700; color:${FEEDBACK_COLOR};
  font-family:'Segoe UI',sans-serif;
  ">${feedback.join('  ')}</span>
  `;

  clearTimeout(wrap._timer);
  wrap._timer = setTimeout(() => {
    wrap.style.opacity = '0';
  }, 2000);
}

// ── Tuner en tiempo real ──────────────────────────────────────────────────────

function actualizarTuner(midi, cents) {
  const needle = document.getElementById('tuner-needle');
  const label  = document.getElementById('tuner-label');
  if (!needle || !label) return;

  if (!midi || midi === 0) {
    needle.style.background = '#333';
    needle.style.left       = '50%';
    label.style.color       = '#555';
    label.textContent       = '—';
    return;
  }

  const pct   = 50 + (cents / 50) * 45;
  const color = Math.abs(cents) < 10 ? '#4caf50'
  : Math.abs(cents) < 25 ? '#cddc39'
  : Math.abs(cents) < 45 ? '#ff9800' : '#f44336';

  needle.style.left       = `${Math.max(2, Math.min(98, pct))}%`;
  needle.style.background = color;
  label.style.color       = color;
  label.textContent       = `${cents > 0 ? '+' : ''}${Math.round(cents)}¢`;
}

function setEstado(msg, color) {
  const el = document.getElementById('estado-txt');
  el.textContent = msg;
  el.style.color = color || '#555';
}

function actualizarRMS(rms) {
  document.getElementById('rms-bar').style.width = Math.min(rms * 400, 100) + '%';
}

function actualizarBarraProgreso(pct) {
  const bar = document.getElementById('rms-bar');
  bar.style.width = pct + '%';
  if (pct < 100) { bar.classList.add('processing'); bar.style.background = ''; }
  else           { bar.classList.remove('processing'); bar.style.background = '#4caf50'; }
}

function mostrarPistaInfo(nombre, stems) {
  document.getElementById('pista-info').style.display = 'block';
  document.getElementById('pista-nombre').textContent = nombre;
  document.getElementById('pista-stems').innerHTML =
  stems.map(s => `<span class="stem-item">${s}</span>`).join('');
}

function mostrarBotonKaraoke() {
  const btn = document.getElementById('btn-karaoke');
  btn.classList.add('activo');
  btn.textContent = '🎤 KARAOKE ON';
}

function colorCal(c) {
  return { 'Excelente':'#4caf50', 'Ok':'#ffeb3b', 'Malo':'#ff9800', 'Pésimo':'#f44336' }[c] || '#aaa';
}

function bgCal(c) {
  return { 'Excelente':'#1b3a1b', 'Ok':'#3a3010', 'Malo':'#3a1a0a', 'Pésimo':'#3a0a0a' }[c] || '#222';
}

// ── Diagnóstico ───────────────────────────────────────────────────────────────

function renderDiagnostico(data) {
  setEstado('Diagnóstico listo', '#4caf50');

  if (window._timeline && data.frases?.length > 0) {
    const plateaus = data.frases.flatMap(f => f.plateaus || []);
    if (plateaus.length > 0) window._timeline.cargarPlateaus(plateaus);
  }

  const diag = data.diagnostico;
  if (!diag) return;

  document.getElementById('diag-wrap').style.display = 'block';

  // Score global
  const scoreGlobal = diag.score_global || '';
  const colScore    = SCORE_COLORS[scoreGlobal] || SCORE_COLORS.D;
  const gen         = document.getElementById('diag-general');
  gen.innerHTML = `
  <span style="
  display:inline-block; padding:4px 20px; border-radius:12px;
  background:${colScore.bg}; color:${colScore.fg};
  box-shadow:0 0 16px ${colScore.glow}66; margin-right:10px;
  font-size:2rem;
  ">${scoreGlobal}</span>
  <span style="font-size:1.5rem;color:${colorCal(diag.cal_general)}">${diag.cal_general}</span>
  `;

  const rows = [
    ['Afinación',   diag.cal.afinacion,   `${diag.cents_promedio}¢ prom.`],
    ['Estabilidad', diag.cal.estabilidad, `σ=${diag.estab_promedio}`],
    ['Escala',      null,                  diag.escala_dominante || '—'],
    ['En escala',   null,                  diag.pct_en_escala != null ? `${diag.pct_en_escala}%` : '—'],
    ['Plateaus',    null,                  diag.n_plateaus],
    ['Frases',      null,                  diag.n_frases],
  ];

  document.getElementById('diag-rows').innerHTML = rows.map(([k, cal, val]) => `
  <div class="diag-row">
  <span class="diag-key">${k}</span>
  <span>
  ${cal ? `<span class="diag-badge" style="background:${bgCal(cal)};color:${colorCal(cal)}">${cal}</span>` : ''}
  <span style="color:#aaa;margin-left:6px;font-size:0.8rem">${val}</span>
  </span>
  </div>`).join('');

  // Frases con score individual
  const hasRef = (window._plateausRef?.length > 0) || (window._refPuntos?.length > 0);
  _renderFrasesScore(data.frases, hasRef);
}

function _renderFrasesScore(frases, hasRef) {
  let wrap = document.getElementById('diag-frases');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'diag-frases';
    wrap.style.cssText = 'margin-top:10px;display:flex;flex-direction:column;gap:4px;';
    document.getElementById('diag-wrap').appendChild(wrap);
  }
  wrap.innerHTML = frases.map((f, i) => {
    const col = SCORE_COLORS[f.score] || SCORE_COLORS.D;
    const fb  = (f.feedback || []).join('  ');
    const ref = hasRef ? _comparacionRef(f) : '';
    return `
    <div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid #1a1a1a;">
    <span style="font-size:0.7rem;color:#555;min-width:28px">${f.t_inicio.toFixed(1)}s</span>
    <span style="
    padding:2px 10px; border-radius:6px; font-weight:700; font-size:0.85rem;
    background:${col.bg}; color:${col.fg};
    ">${f.score}</span>
    <span style="font-size:0.75rem;color:${FEEDBACK_COLOR};flex:1">${fb}</span>
    ${ref ? `<span style="font-size:0.7rem;color:#7c83fd">${ref}</span>` : ''}
    </div>
    `;
  }).join('');
}

function _comparacionRef(frase) {
  if (!window._plateausRef?.length) return '';
  // Plateaus de referencia que solapan con esta frase
  const refEnFrase = window._plateausRef.filter(
    r => r.t_fin >= frase.t_inicio && r.t_inicio <= frase.t_fin
  );
  if (!refEnFrase.length) return '';
  const midiRef = refEnFrase.reduce((a, r) => a + r.mediana_midi, 0) / refEnFrase.length;
  const midiFrase = frase.plateaus
  .filter(p => p.tipo !== 'portamento')
  .reduce((a, p, _, arr) => a + p.mediana_midi / arr.length, 0);
  const diff = Math.round(midiFrase - midiRef);
  if (Math.abs(diff) < 2) return '';
  return diff > 0 ? `+${diff} st` : `${diff} st`;
}

// ── Descarga ──────────────────────────────────────────────────────────────────

async function descargarArchivo(ruta, nombre, prefijo = '/stems/') {
  try {
    const filename = ruta.split('/').pop();
    let res = await fetch(`${prefijo}${filename}`);
    if (!res.ok) res = await fetch(`/exports/${filename}`);
    if (!res.ok) return;
    const url = URL.createObjectURL(await res.blob());
    const a   = Object.assign(document.createElement('a'), { href: url, download: nombre });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    await new Promise(r => setTimeout(r, 400));
  } catch (e) { console.warn(`descargarArchivo(${nombre}):`, e); }
}
