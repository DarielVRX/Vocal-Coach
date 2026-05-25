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

const FEEDBACK_COLOR = '#ffeb3b';

function mostrarScoreFrase(score, feedback) {
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
  wrap._timer = setTimeout(() => { wrap.style.opacity = '0'; }, 2000);
}

// ── Afinador canvas ───────────────────────────────────────────────────────────

const _TN = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
const _tnNota = m => _TN[((Math.round(m) % 12) + 12) % 12] + (Math.floor(Math.round(m) / 12) - 1);

let _tnCurMidi = 0, _tnCurCents = 0;
let _tnTgtMidi = 0, _tnTgtCents = 0;
let _tnRAF = null;

function actualizarTuner(midi, cents) {
  _tnTgtMidi  = midi  || 0;
  _tnTgtCents = cents || 0;
  if (!_tnRAF) _tnRAF = requestAnimationFrame(_tnFrame);
}

function _tnFrame() {
  _tnRAF = null;
  _tnCurMidi  += (_tnTgtMidi  - _tnCurMidi)  * 0.18;
  _tnCurCents += (_tnTgtCents - _tnCurCents) * 0.25;
  _tnRender();
  const moving = Math.abs(_tnCurMidi - _tnTgtMidi) > 0.01
               || Math.abs(_tnCurCents - _tnTgtCents) > 0.2;
  if (moving) _tnRAF = requestAnimationFrame(_tnFrame);
}

function _tnRender() {
  const cv = document.getElementById('tuner-canvas');
  if (!cv) return;
  const W = cv.clientWidth, H = cv.clientHeight;
  if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#0d0d0d';
  ctx.fillRect(0, 0, W, H);

  const WA = Math.round(W * 0.58), WB = W - WA - 1;
  _tnRange(ctx, 0, WA, H);
  ctx.fillStyle = '#1a1a1a';
  ctx.fillRect(WA, 4, 1, H - 8);
  _tnFine(ctx, WA + 1, WB, H);
}

function _tnRange(ctx, x0, W, H) {
  const SEMIS = 13;
  const pxS   = W / SEMIS;
  const fMidi = _tnCurMidi + _tnCurCents / 100;
  const absCents = Math.abs(_tnTgtCents);
  const color = _tnTgtMidi > 0
    ? (absCents < 10 ? '#4caf50' : absCents < 25 ? '#cddc39' : absCents < 45 ? '#ff9800' : '#f44336')
    : '#333';

  ctx.save();
  ctx.translate(x0, 0);

  // Fondo degradado de notas sostenidas/naturales
  for (let dm = -7; dm <= 7; dm++) {
    const semi = Math.round(fMidi) + dm;
    const xc   = W / 2 + (semi - fMidi) * pxS;
    const nota  = _TN[((semi % 12) + 12) % 12];
    const isSos = nota.includes('#');
    const x1 = xc - pxS / 2, bw = pxS;
    if (x1 + bw < 0 || x1 > W) continue;
    ctx.fillStyle = isSos ? '#111' : '#141414';
    ctx.fillRect(Math.max(0, x1), 0, Math.min(bw, W - Math.max(0, x1)), H);
  }

  // Tick marks y nombres de nota
  for (let dm = -7; dm <= 7; dm++) {
    const semi = Math.round(fMidi) + dm;
    const xc   = W / 2 + (semi - fMidi) * pxS;
    if (xc < -pxS || xc > W + pxS) continue;
    const nota  = _TN[((semi % 12) + 12) % 12];
    const isNat = !nota.includes('#');
    const isC   = nota === 'C';

    ctx.strokeStyle = isC ? '#333' : (isNat ? '#222' : '#1a1a1a');
    ctx.lineWidth   = isC ? 1.5 : 0.8;
    ctx.beginPath(); ctx.moveTo(xc, H * 0.55); ctx.lineTo(xc, H); ctx.stroke();

    if (isNat) {
      ctx.fillStyle  = isC ? '#5a6aff' : '#3a3a3a';
      ctx.font       = `${isC ? 'bold ' : ''}${Math.max(9, H * 0.2)}px monospace`;
      ctx.textAlign  = 'center';
      ctx.fillText(nota + (Math.floor(semi / 12) - 1), xc, H * 0.45);
    }
  }

  // Nota actual en el centro (grande)
  if (_tnTgtMidi > 0) {
    ctx.fillStyle = color;
    ctx.font      = `bold ${H * 0.38}px monospace`;
    ctx.textAlign = 'center';
    ctx.fillText(_tnNota(Math.round(_tnTgtMidi)), W / 2, H * 0.3);
  }

  // Aguja central fija
  ctx.strokeStyle = color;
  ctx.lineWidth   = 3; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H); ctx.stroke();

  ctx.restore();
}

function _tnFine(ctx, x0, W, H) {
  const pxPC = W / 200; // ±100 cents
  const near = Math.round(_tnTgtMidi);
  const absCents = Math.abs(_tnTgtCents);
  const color = _tnTgtMidi > 0
    ? (absCents < 10 ? '#4caf50' : absCents < 25 ? '#cddc39' : absCents < 45 ? '#ff9800' : '#f44336')
    : '#333';

  ctx.save();
  ctx.translate(x0, 0);

  // Zona verde central
  ctx.fillStyle = '#1b3a1b';
  ctx.fillRect(W / 2 - 15 * pxPC, 0, 30 * pxPC, H);

  // Línea central
  ctx.strokeStyle = '#2a4a2a'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H); ctx.stroke();

  // Ticks en ±25, ±50, ±75
  for (const dc of [-75, -50, -25, 25, 50, 75]) {
    const x = W / 2 + dc * pxPC;
    ctx.strokeStyle = '#222'; ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(x, H * 0.6); ctx.lineTo(x, H); ctx.stroke();
  }

  if (_tnTgtMidi > 0) {
    // Nota vecinas (arriba y abajo)
    ctx.fillStyle = '#2a2a2a';
    ctx.font = `${H * 0.18}px monospace`;
    ctx.textAlign = 'left';
    ctx.fillText(_tnNota(near + 1), 4, H * 0.2);
    ctx.fillText(_tnNota(near - 1), 4, H * 0.92);

    // Nota actual (centro, grande)
    ctx.fillStyle = color;
    ctx.font = `bold ${H * 0.35}px monospace`;
    ctx.textAlign = 'center';
    ctx.fillText(_tnNota(near), W / 2, H * 0.32);

    // Aguja móvil (cents)
    const nx = Math.max(2, Math.min(W - 2, W / 2 + _tnTgtCents * pxPC));
    ctx.strokeStyle = color;
    ctx.lineWidth = 3; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(nx, H * 0.45); ctx.lineTo(nx, H); ctx.stroke();

    // Label cents
    ctx.fillStyle = color;
    ctx.font = `${H * 0.2}px monospace`;
    ctx.textAlign = 'right';
    ctx.fillText(`${_tnTgtCents > 0 ? '+' : ''}${Math.round(_tnTgtCents)}¢`, W - 4, H * 0.92);
  }

  ctx.restore();
}

// Iniciar loop del afinador
(function _tnInit() {
  const cv = document.getElementById('tuner-canvas');
  if (!cv) return;
  function resize() { cv.width = cv.clientWidth || 300; cv.height = cv.clientHeight || 80; _tnRender(); }
  window.addEventListener('resize', resize);
  window.addEventListener('load', () => { resize(); requestAnimationFrame(() => { _tnRender(); }); });
})();

// ── Estado y barras ───────────────────────────────────────────────────────────

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

  const scoreGlobal = diag.score_global || '';
  const colScore    = SCORE_COLORS[scoreGlobal] || SCORE_COLORS.D;
  document.getElementById('diag-general').innerHTML = `
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

  const hasRef = (window._plateausRef?.length > 0) || (window._refPuntos?.length > 0);
  _renderFrasesScore(data.frases, hasRef);
}

// ── Score por frase ───────────────────────────────────────────────────────────

function _renderFrasesScore(frases, hasRef) {
  let wrap = document.getElementById('diag-frases');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'diag-frases';
    wrap.style.cssText = 'margin-top:10px;display:flex;flex-direction:column;gap:4px;';
    document.getElementById('diag-wrap').appendChild(wrap);
  }

  wrap.innerHTML = frases.map(f => {
    const col = SCORE_COLORS[f.score] || SCORE_COLORS.D;
    const fb  = (f.feedback || []).join('  ');
    const cmp = hasRef ? _comparacionRef(f) : null;

    const cmpHtml = cmp ? `
    <span style="display:inline-flex;align-items:center;gap:3px;flex-shrink:0;">
    <span style="font-size:0.65rem;color:#555">${cmp.notaRef}</span>
    <span style="font-size:0.8rem;color:${cmp.color}">${cmp.flecha}</span>
    <span style="font-size:0.65rem;color:${cmp.color}">${cmp.notaGrab}</span>
    </span>` : '';

    return `
    <div style="
    display:flex; align-items:center; gap:8px;
    padding:4px 0; border-bottom:1px solid #1a1a1a;
    ">
    <span style="font-size:0.7rem;color:#555;min-width:28px">${f.t_inicio.toFixed(1)}s</span>
    <span style="
    padding:2px 10px; border-radius:6px; font-weight:700; font-size:0.85rem;
    background:${col.bg}; color:${col.fg}; flex-shrink:0;
    ">${f.score}</span>
    <span style="font-size:0.75rem;color:${FEEDBACK_COLOR};flex:1">${fb}</span>
    ${cmpHtml}
    </div>`;
  }).join('');
}

// ── Comparación con referencia ────────────────────────────────────────────────

function _comparacionRef(frase) {
  if (!window._plateausRef?.length) return null;

  const refEnFrase = window._plateausRef.filter(
    r => r.t_fin >= frase.t_inicio && r.t_inicio <= frase.t_fin
  );
  if (!refEnFrase.length) return null;

  const midiRef = refEnFrase.reduce((a, r) => a + r.mediana_midi, 0) / refEnFrase.length;

  const grabPls = (frase.plateaus || []).filter(p => p.tipo !== 'portamento');
  if (!grabPls.length) return null;
  const midiGrab = grabPls.reduce((a, p) => a + p.mediana_midi, 0) / grabPls.length;

  const diff = Math.round(midiGrab - midiRef);
  if (Math.abs(diff) < 2) return null;

  const NOTAS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
  const notaNombre = m => NOTAS[Math.round(m) % 12] + (Math.floor(Math.round(m) / 12) - 1);

  // Color por rango de semitono
  const abs = Math.abs(diff);
  const color = abs <= 2 ? '#4caf50'
  : abs <= 5 ? '#ff9800'
  :             '#f44336';

  const flecha = diff > 0 ? '↑' : '↓';

  return {
    notaRef : notaNombre(midiRef),
    notaGrab: notaNombre(midiGrab),
    flecha,
    color,
  };
}

// ── Diagnóstico RT ────────────────────────────────────────────────────────────

const _SCORE_TABLA = [
  ['SS', 10, 0.05], ['S', 15, 0.08], ['A', 25, 0.15],
  ['B',  35, 0.25], ['C', 45, 0.35], ['D', 999, 999],
];

const _ESCALAS_RT = {
  'Mayor':        [0,2,4,5,7,9,11],
  'Menor nat.':   [0,2,3,5,7,8,10],
  'Menor arm.':   [0,2,3,5,7,8,11],
  'Pentatónica':  [0,2,4,7,9],
};
const _NOTAS_RT = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];

function _calcularScore(cents, estab) {
  for (const [label, cMax, eMax] of _SCORE_TABLA)
    if (cents <= cMax && estab <= eMax) return label;
  return 'D';
}

function _calificar(val, ex, ok, mal) {
  if (val <= ex) return 'Excelente';
  if (val <= ok) return 'Ok';
  if (val <= mal) return 'Malo';
  return 'Pésimo';
}

function _generarFeedbackRT(segs) {
  const msgs    = [];
  const stables = segs.filter(s => s.tipo !== 'portamento');
  if (stables.length) {
    const media = stables.reduce((a, s) => a + s.cents, 0) / stables.length;
    if (media < -15)      msgs.push('¡Sube!');
    else if (media > 15)  msgs.push('¡Baja!');
  }
  const tipos = segs.map(s => s.tipo);
  if (tipos.includes('vibrato'))                                       msgs.push('¡Vibrato!');
  if (tipos.includes('portamento'))                                    msgs.push('¡Slide!');
  if (tipos.filter(t => t === 'inestable').length > tipos.length * 0.4) msgs.push('¡Inestable!');
  return msgs;
}

function _inferirEscalaRT(midis) {
  if (!midis.length) return null;
  const freq = new Array(12).fill(0);
  for (const m of midis) freq[Math.round(m) % 12]++;
  let mejor = null, mejorScore = -1;
  for (let t = 0; t < 12; t++) {
    for (const [nombre, ints] of Object.entries(_ESCALAS_RT)) {
      const score = ints.reduce((s, i) => s + freq[(t + i) % 12], 0);
      if (score > mejorScore) { mejorScore = score; mejor = `${_NOTAS_RT[t]} ${nombre}`; }
    }
  }
  return mejor;
}

function _detectarFrasesRT(segs, gapMin = 0.5) {
  if (!segs.length) return [];
  const frases = [];
  let actual = [segs[0]];
  for (let i = 1; i < segs.length; i++) {
    if (segs[i].t_ini - segs[i - 1].t_fin > gapMin) { frases.push(actual); actual = []; }
    actual.push(segs[i]);
  }
  frases.push(actual);
  return frases.filter(f => f.length > 0);
}

function _comparacionRefRT(frase) {
  if (!window._plateausRef?.length) return null;
  const refEnFrase = window._plateausRef.filter(
    r => r.t_fin >= frase.t_inicio && r.t_inicio <= frase.t_fin
  );
  if (!refEnFrase.length) return null;
  const midiRef  = refEnFrase.reduce((a, r) => a + r.mediana_midi, 0) / refEnFrase.length;
  const grabSegs = (frase.segmentos || []).filter(s => s.tipo !== 'portamento');
  if (!grabSegs.length) return null;
  const midiGrab = grabSegs.reduce((a, s) => a + s.midi, 0) / grabSegs.length;
  const diff     = Math.round(midiGrab - midiRef);
  if (Math.abs(diff) < 2) return null;
  const notaNombre = m => _NOTAS_RT[Math.round(m) % 12] + (Math.floor(Math.round(m) / 12) - 1);
  const abs   = Math.abs(diff);
  const color = abs <= 2 ? '#4caf50' : abs <= 5 ? '#ff9800' : '#f44336';
  return { notaRef: notaNombre(midiRef), notaGrab: notaNombre(midiGrab),
           flecha: diff > 0 ? '↑' : '↓', color };
}

function _renderFrasesScoreRT(frases, hasRef) {
  let wrap = document.getElementById('diag-frases');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'diag-frases';
    wrap.style.cssText = 'margin-top:10px;display:flex;flex-direction:column;gap:4px;';
    document.getElementById('diag-wrap').appendChild(wrap);
  }
  wrap.innerHTML = frases.map(f => {
    const col = SCORE_COLORS[f.score] || SCORE_COLORS.D;
    const fb  = (f.feedback || []).join('  ');
    const cmp = hasRef ? _comparacionRefRT(f) : null;
    const cmpHtml = cmp ? `
      <span style="display:inline-flex;align-items:center;gap:3px;flex-shrink:0;">
        <span style="font-size:0.65rem;color:#555">${cmp.notaRef}</span>
        <span style="font-size:0.8rem;color:${cmp.color}">${cmp.flecha}</span>
        <span style="font-size:0.65rem;color:${cmp.color}">${cmp.notaGrab}</span>
      </span>` : '';
    return `
      <div style="display:flex;align-items:center;gap:8px;
                  padding:4px 0;border-bottom:1px solid #1a1a1a;">
        <span style="font-size:0.7rem;color:#555;min-width:28px">${f.t_inicio.toFixed(1)}s</span>
        <span style="padding:2px 10px;border-radius:6px;font-weight:700;font-size:0.85rem;
                     background:${col.bg};color:${col.fg};flex-shrink:0;">${f.score}</span>
        <span style="font-size:0.75rem;color:${FEEDBACK_COLOR};flex:1">${fb}</span>
        ${cmpHtml}
      </div>`;
  }).join('');
}

function renderDiagnosticoRT() {
  const segs = window._timeline?._segmentos || [];
  if (!segs.length) { setEstado('Sin datos de grabación', '#555'); return; }

  const stables       = segs.filter(s => s.tipo !== 'portamento');
  const centsPromedio = stables.length
    ? stables.reduce((a, s) => a + Math.abs(s.cents), 0) / stables.length : 0;
  const estabPromedio = stables.length
    ? stables.reduce((a, s) => a + (s.varianza || 0), 0) / stables.length : 0;

  const scoreGlobal    = _calcularScore(centsPromedio, estabPromedio);
  const escalaInferida = _inferirEscalaRT(stables.map(s => s.midi));
  const calAfinacion   = _calificar(centsPromedio, 10, 25, 45);
  const calEstabilidad = _calificar(estabPromedio, 0.05, 0.15, 0.30);
  const calGeneral     = [calAfinacion, calEstabilidad].includes('Pésimo') ? 'Pésimo'
    : [calAfinacion, calEstabilidad].includes('Malo') ? 'Malo'
    : [calAfinacion, calEstabilidad].includes('Ok')   ? 'Ok' : 'Excelente';

  const frases = _detectarFrasesRT(segs).map((segsF, idx) => {
    const pl = segsF.filter(s => s.tipo !== 'portamento');
    const cM = pl.length ? pl.reduce((a, s) => a + Math.abs(s.cents), 0) / pl.length : 0;
    const eM = pl.length ? pl.reduce((a, s) => a + (s.varianza || 0), 0) / pl.length : 0;
    return {
      idx,
      t_inicio : segsF[0].t_ini,
      t_fin    : segsF[segsF.length - 1].t_fin,
      score    : _calcularScore(cM, eM),
      feedback : _generarFeedbackRT(segsF),
      segmentos: segsF,
    };
  });

  setEstado('Diagnóstico listo', '#4caf50');
  document.getElementById('diag-wrap').style.display = 'block';

  const colScore = SCORE_COLORS[scoreGlobal] || SCORE_COLORS.D;
  document.getElementById('diag-general').innerHTML = `
    <span style="display:inline-block;padding:4px 20px;border-radius:12px;
                 background:${colScore.bg};color:${colScore.fg};
                 box-shadow:0 0 16px ${colScore.glow}66;margin-right:10px;
                 font-size:2rem;">${scoreGlobal}</span>
    <span style="font-size:1.5rem;color:${colorCal(calGeneral)}">${calGeneral}</span>`;

  const rows = [
    ['Afinación',   calAfinacion,   `${Math.round(centsPromedio)}¢ prom.`],
    ['Estabilidad', calEstabilidad, `σ=${estabPromedio.toFixed(4)}`],
    ['Escala',      null,            escalaInferida || '—'],
    ['Segmentos',   null,            segs.length],
    ['Frases',      null,            frases.length],
  ];
  document.getElementById('diag-rows').innerHTML = rows.map(([k, cal, val]) => `
    <div class="diag-row">
      <span class="diag-key">${k}</span>
      <span>
        ${cal ? `<span class="diag-badge" style="background:${bgCal(cal)};color:${colorCal(cal)}">${cal}</span>` : ''}
        <span style="color:#aaa;margin-left:6px;font-size:0.8rem">${val}</span>
      </span>
    </div>`).join('');

  const hasRef = (window._plateausRef?.length > 0) || (window._refPuntos?.length > 0);
  _renderFrasesScoreRT(frases, hasRef);
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
