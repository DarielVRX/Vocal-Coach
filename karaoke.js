/**
 * KARAOKE.JS — Gestión de stems, referencia vocal e instrumental
 * Flujo local (stems desde Kaggle) y flujo servidor (separación en vivo)
 */

// ── Estado karaoke ────────────────────────────────────────────────────────────
let karaokeTab  = null;
window._audioCtxRef    = null;
window._instrStartTime = 0;
let _instrSource  = null;
let _instrBuffer  = null;
let _localVocals  = null;
let _localInstr   = null;
let _localTrans   = null;

// ── Panel ─────────────────────────────────────────────────────────────────────

function toggleKaraokePanel() {
  if (window._modoKaraoke) {
    _desactivarKaraoke();
    return;
  }
  const panel   = document.getElementById('karaoke-panel');
  const visible = panel.style.display === 'flex';
  panel.style.display = visible ? 'none' : 'flex';
  document.getElementById('btn-karaoke').classList.toggle('activo', !visible);
  if (!visible && !karaokeTab) setKaraokeTab('local');
}

function _desactivarKaraoke() {
  window._modoKaraoke = false;
  _instrBuffer = null;
  if (_instrSource) { try { _instrSource.stop(); } catch(e) {} _instrSource = null; }
  if (window._audioCtxRef) { window._audioCtxRef.close(); window._audioCtxRef = null; }
  window._instrStartTime = 0;
  window._refPuntos   = null;
  window._refPalabras = null;
  window._plateausRef = [];
  window._beatS       = null;
  if (window._timeline) {
    window._timeline.plateausRef = [];
    window._timeline.puntosRef   = [];
    window._timeline._tOffset    = 0;
  }
  _lineas = []; detenerLetra();
  const btn = document.getElementById('btn-karaoke');
  btn.classList.remove('activo');
  btn.textContent = '🎤 MODO KARAOKE';
  document.getElementById('karaoke-panel').style.display = 'none';
  document.getElementById('pista-info').style.display = 'none';
  setEstado('Karaoke desactivado', '#555');
}

function setKaraokeTab(tab) {
  karaokeTab = tab;
  document.getElementById('tab-local').classList.toggle('activo',  tab === 'local');
  document.getElementById('tab-server').classList.toggle('activo', tab === 'server');
  document.getElementById('karaoke-local').style.display  = tab === 'local'  ? 'flex' : 'none';
  document.getElementById('karaoke-server').style.display = tab === 'server' ? 'flex' : 'none';
}

// ── Stems locales ─────────────────────────────────────────────────────────────

function cargarStemLocal(tipo, input) {
  const file = input.files[0]; if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    if (tipo === 'vocals') {
      _localVocals = e.target.result;
      _marcarCargado('lbl-vocals', file.name);
    } else {
      _localInstr = e.target.result;
      _marcarCargado('lbl-instr', file.name);
    }
  };
  reader.readAsArrayBuffer(file);
}

function cargarTranscripcionLocal(input) {
  const file = input.files[0]; if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    try {
      _localTrans = JSON.parse(e.target.result);
      _marcarCargado('lbl-transcripcion', file.name);
    } catch { setEstado('JSON inválido', '#f44336'); }
  };
  reader.readAsText(file);
}

function _marcarCargado(id, nombre) {
  const el = document.getElementById(id);
  el.textContent = '✓ ' + nombre;
  el.classList.add('cargado');
}

async function activarKaraokeLocal() {
  if (!_localVocals || !_localInstr) {
    setEstado('Faltan vocals.wav o accompaniment.wav', '#f44336'); return;
  }
  const btn = document.getElementById('btn-activar-local');
  btn.disabled = true;
  try {
    window._audioCtxRef = new AudioContext({ sampleRate: 44100 });
    _instrBuffer = await window._audioCtxRef.decodeAudioData(_localInstr.slice(0));

    try {
      const blob = new Blob([_localVocals], { type: 'audio/wav' });
      const fd   = new FormData(); fd.append('file', blob, 'vocals_local.wav');
      const upd  = await (await fetch('/upload/karaoke', { method:'POST', body:fd })).json();
      if (upd.success) await cargarReferenciaVocal(upd.path);
      else setEstado(`Referencia: ${upd.error}`, '#ff9800');
    } catch (_) { console.info('Servidor no disponible — referencia F0 omitida'); }

    if (_localTrans?.palabras) {
      window._refPalabras = _localTrans.palabras;
      prepararLineas(_localTrans.palabras);
      if (window._timeline) window._timeline.cargarLetras(_localTrans.palabras);
    }

    window._modoKaraoke = true;
    mostrarBotonKaraoke();
    mostrarPistaInfo('Archivos locales',
                     ['vocals', 'accompaniment', _localTrans ? 'transcripción' : null].filter(Boolean));
    setEstado('Karaoke local listo ✓', '#4caf50');
    document.getElementById('karaoke-panel').style.display = 'none';
  } catch (err) {
    setEstado('Error: ' + err.message, '#f44336');
  } finally {
    btn.disabled = false;
  }
}

// ── Referencia vocal ──────────────────────────────────────────────────────────

async function cargarReferenciaVocal(vocalsPath) {
  try {
    const res  = await fetch('/karaoke/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vocals_path: vocalsPath })
    });
    const init = await res.json();

    if (init.puntos) {
      _aplicarReferencia(init.puntos, init.beat_s, init.plateaus_ref);
      return;
    }

    if (!init.success || !init.task_id) {
      console.warn('analyze falló:', init); return;
    }

    while (true) {
      const prog = await (await fetch(`/karaoke/analyze/progress/${init.task_id}`)).json();
      setEstado(_mensajeAnalisisVocal(prog.progress || 0), '#7c83fd');

      if (prog.status === 'completed') {
        _aplicarReferencia(prog.puntos, prog.beat_s, prog.plateaus_ref);
        break;
      } else if (prog.status === 'failed') {
        console.warn('analyze falló:', prog.message); break;
      } else if (prog.error) {
        console.warn('analyze error:', prog.error); break;
      }
      await new Promise(r => setTimeout(r, 800));
    }
  } catch (e) { console.warn('cargarReferenciaVocal:', e); }
}

function _aplicarReferencia(puntos, beat_s, plateaus_ref) {
  console.log('plateaus_ref:', plateaus_ref?.length, 'puntos:', puntos?.length);
  if (!puntos?.length) return;
  window._refPuntos   = puntos;
  window._refDuracion = puntos[puntos.length-1].t;
  window._beatS       = beat_s || 0.5;
  window._plateausRef = plateaus_ref || [];

  if (window._timeline) {
    if (plateaus_ref?.length > 0) {
      window._timeline.cargarPlateausRef(plateaus_ref);
    } else {
      window._timeline.cargarReferencia(puntos, window._refDuracion);
    }
  }
}

function _mensajeAnalisisVocal(pct) {
  if (pct <= 10) return 'Preparando el análisis de la voz...';
  if (pct <= 40) return `Detectando las notas de la canción... ${pct}%`;
  if (pct <= 75) return `Calculando el ritmo y el tono... ${pct}%`;
  if (pct <= 95) return `Terminando el análisis... ${pct}%`;
  return 'Casi listo...';
}

async function cargarTranscripcionServidor(vocalsPath) {
  setEstado('Transcribiendo la letra... puede demorar un poco ☕', '#7c83fd');
  try {
    const data = await (await fetch('/karaoke/transcribe', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vocals_path: vocalsPath })
    })).json();
    if (data.success && data.palabras.length > 0) {
      window._refPalabras = data.palabras;
      prepararLineas(data.palabras);
      if (window._timeline) window._timeline.cargarLetras(data.palabras);
    }
  } catch (e) { console.warn('cargarTranscripcionServidor:', e); }
}

async function cargarInstrumentalServidor(accompPath) {
  setEstado('Cargando el fondo musical...', '#7c83fd');
  try {
    const filename = accompPath.split('/').pop();
    const buf      = await (await fetch(`/stems/${filename}`)).arrayBuffer();
    window._audioCtxRef = new AudioContext({ sampleRate: 44100 });
    _instrBuffer        = await window._audioCtxRef.decodeAudioData(buf);
    window._modoKaraoke = true;
  } catch (e) { console.warn('cargarInstrumentalServidor:', e); }
}

// ── Reproducción ──────────────────────────────────────────────────────────────

function reproducirInstrumental() {
  if (!_instrBuffer || !window._audioCtxRef) return;
  if (_instrSource) { try { _instrSource.stop(); } catch(e) {} }

  _instrSource = window._audioCtxRef.createBufferSource();
  _instrSource.buffer = _instrBuffer;
  _instrSource.connect(window._audioCtxRef.destination);
  _instrSource.start(0);

  // ── FIX: offset calculado aquí, justo después de start()
  // para que _instrStartTime sea el valor real del momento de reproducción
  window._instrStartTime = window._audioCtxRef.currentTime;

  if (window._timeline) {
    window._timeline._tOffset = 0; // grabación y reproducción arrancan juntos
  }

  if (_lineas.length > 0) arrancarLetra();
}

function detenerInstrumental() {
  if (_instrSource) { try { _instrSource.stop(); } catch(e) {} _instrSource = null; }
  detenerLetra();
}
