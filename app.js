/**
 * APP.JS — Estado principal, WebSocket, grabación, upload, export
 */

// ── Config ────────────────────────────────────────────────────────────────────
const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/audio`;
const SR = 44100, CHUNK = 2048;

// ── Estado ────────────────────────────────────────────────────────────────────
let ws, ctx, stream, processor;
let grabando = false;
window._modoKaraoke  = false;
let t0 = null, timerID = null;
let pistaPath = null, pistaStems = null;
window._sesionGrabada = false;

// ── WebSocket ─────────────────────────────────────────────────────────────────

function conectarWS(cb) {
  if (ws && ws.readyState !== WebSocket.CLOSED) { ws.onclose = null; ws.close(); }
  ws = new WebSocket(WS_URL);
  ws.onopen    = () => { setEstado('Conectado', '#4caf50'); if (cb) cb(); };
  ws.onclose   = () => setEstado('Desconectado', '#f44336');
  ws.onerror   = () => setEstado('Error WS', '#f44336');
  ws.onmessage = e  => _manejarMsg(JSON.parse(e.data));
}

function _manejarMsg(d) {
  if (d.evento === 'grabacion_iniciada') {
    setEstado('Grabando...', '#f44336');
  } else if (d.evento === 'diagnostico') {
    renderDiagnostico(d.data);
  } else if (d.estado === 'grabando') {
    actualizarRMS(d.rms || 0);
    if (d.midi && window._timeline)
      window._timeline.agregarPunto(d.midi, d.cents || 0, d.t);
    actualizarTuner(d.midi || 0, d.cents || 0);
    if (d.score_frase)
      mostrarScoreFrase(d.score_frase, d.feedback_frase || []);
    setEstado(`Grabando — Frases: ${d.frases || 0}`, '#f44336');
  }
}

// ── Grabación ─────────────────────────────────────────────────────────────────

async function toggleRec() {
  if (!grabando) await _iniciarRec();
  else           _pausarRec();
}

async function _iniciarRec() {
  try {
    window._sesionGrabada = false;
    window._timeline = new VocalTimeline('vocal-canvas');
    window._timeline.iniciar();

    if (window._plateausRef?.length > 0) {
      window._timeline.cargarPlateausRef(window._plateausRef);
    } else if (window._refPuntos) {
      window._timeline.cargarReferencia(window._refPuntos, window._refDuracion);
    }

    document.getElementById('diag-wrap').style.display = 'none';

    stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });

    ctx = window._modoKaraoke && window._audioCtxRef
    ? window._audioCtxRef
    : new AudioContext({ sampleRate: SR });
    if (!window._audioCtxRef) window._audioCtxRef = ctx;

    await ctx.resume();
    await ctx.audioWorklet.addModule(_workletURL());

    const src = ctx.createMediaStreamSource(stream);
    processor = new AudioWorkletNode(ctx, 'capture-processor');
    src.connect(processor);
    processor.port.onmessage = e => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(e.data.buffer);
    };

      conectarWS(() => ws.send(JSON.stringify({ cmd: 'start' })));

      grabando = true;
      t0       = Date.now();
      timerID  = setInterval(_actualizarTimer, 500);

      document.getElementById('btn-rec').textContent = '⏸ PAUSA';
      document.getElementById('btn-rec').classList.add('grabando');
      document.getElementById('btn-stop').classList.add('activo');

      if (window._modoKaraoke) reproducirInstrumental();
  } catch (err) {
    setEstado('Error mic: ' + err.message, '#f44336');
  }
}

function _pausarRec() {
  grabando = false;
  clearInterval(timerID);
  if (processor) { processor.disconnect(); processor = null; }
  if (stream)    { stream.getTracks().forEach(t => t.stop()); stream = null; }
  if (ws && ws.readyState === WebSocket.OPEN)
    ws.send(JSON.stringify({ cmd: 'stop' }));
  document.getElementById('btn-rec').textContent = '● REC';
  document.getElementById('btn-rec').classList.remove('grabando');
  setEstado('Pausado', '#ffeb3b');
  actualizarTuner(0, 0);
  if (window._modoKaraoke) detenerInstrumental();
  if (window._timeline) window._timeline.detener();
}

function detener() {
  grabando = false;
  clearInterval(timerID);

  if (processor) { processor.disconnect(); processor = null; }
  if (stream)    { stream.getTracks().forEach(t => t.stop()); stream = null; }

  document.getElementById('btn-rec').textContent = '● REC';
  document.getElementById('btn-rec').classList.remove('grabando');
  document.getElementById('btn-stop').classList.remove('activo');
  actualizarTuner(0, 0);
  actualizarRMS(0);

  if (window._modoKaraoke) detenerInstrumental();

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ cmd: 'stop' }));
    if (window._timeline) window._timeline.detener();
    window._sesionGrabada = true;
    setEstado('Procesando...', '#7c83fd');
  } else {
    if (window._timeline) window._timeline.detener();
    setEstado('Detenido', '#555');
  }
}

function _workletURL() {
  const code = `
  class CaptureProcessor extends AudioWorkletProcessor {
    constructor() { super(); this._buf=[]; this._size=${CHUNK}; }
    process(inputs) {
      const ch=inputs[0][0]; if(!ch) return true;
      for(let i=0;i<ch.length;i++) this._buf.push(ch[i]);
      while(this._buf.length>=this._size){
        const c=new Float32Array(this._buf.splice(0,this._size));
        this.port.postMessage(c,[c.buffer]);
      }
      return true;
    }
  }
  registerProcessor('capture-processor',CaptureProcessor);
  `;
  return URL.createObjectURL(new Blob([code], { type: 'application/javascript' }));
}

// ── Upload pista ──────────────────────────────────────────────────────────────

function triggerUpload() { document.getElementById('file-input').click(); }

async function subirPista() {
  const file = document.getElementById('file-input').files[0];
  if (!file) return;
  const btn = document.getElementById('btn-upload');
  btn.disabled = true;
  btn.innerHTML = '⏳ SUBIENDO<span class="spinner"></span>';
  setEstado('Subiendo pista...', '#ffeb3b');
  try {
    const fd  = new FormData(); fd.append('file', file);
    const upd = await (await fetch('/upload/karaoke', { method:'POST', body:fd })).json();
    if (!upd.success) throw new Error(upd.error);
    pistaPath = upd.path;

    btn.innerHTML = '🔧 SEPARANDO<span class="spinner"></span>';
    const isod = await (await fetch('/isolate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ file_path: pistaPath })
    })).json();
    if (!isod.success) throw new Error(isod.error);
    await _monitorearProgreso(isod.task_id, btn, file.name);
  } catch (err) {
    setEstado('Error: ' + err.message, '#f44336');
    btn.innerHTML = '📁 SUBIR PISTA'; btn.disabled = false;
  }
}

async function _monitorearProgreso(taskId, btn, fileName) {
  while (true) {
    const data = await (await fetch(`/isolate/progress/${taskId}`)).json();
    if (data.error) throw new Error(data.error);
    actualizarBarraProgreso(data.progress || 0);
    btn.innerHTML = `🔧 ${data.progress || 0}%<span class="spinner"></span>`;

    if (data.status === 'completed') {
      pistaStems = data.result;
      mostrarPistaInfo(fileName, ['vocals','accompaniment']);
      btn.innerHTML = '📁 CAMBIAR PISTA'; btn.disabled = false;
      setEstado('Analizando referencia vocal...', '#7c83fd');
      await cargarReferenciaVocal(pistaStems.vocals);
      await cargarInstrumentalServidor(pistaStems.accompaniment);
      await cargarTranscripcionServidor(pistaStems.vocals);
      mostrarBotonKaraoke();
      setEstado('Listo ✓', '#4caf50');
      break;
    } else if (data.status === 'failed') {
      throw new Error(data.message || 'Separación falló');
    }
    await new Promise(r => setTimeout(r, 500));
  }
}

// ── Export ────────────────────────────────────────────────────────────────────

async function exportarSesion() {
  if (grabando) { alert('Detén la grabación antes de exportar'); return; }
  const btn = document.getElementById('btn-export');
  btn.disabled = true; btn.innerHTML = '⏳ EXPORTANDO<span class="spinner"></span>';
  try {
    if (window._sesionGrabada) {
      const data = await (await fetch('/export/session', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          session_id  : `session_${Date.now()}`,
                             karaoke_path: pistaStems?.accompaniment || null,
                             plateaus_ref: window._plateausRef || [],
                             bpm         : window._beatS ? Math.round(60 / window._beatS) : null,
        })
      })).json();
      if (!data.success) throw new Error(data.error);
      for (const [nombre, ruta] of Object.entries(data.files)) {
        const ext    = ruta.endsWith('.pdf') ? '.pdf' : '.wav';
        const prefijo = ruta.endsWith('.pdf') ? '/exports/pdf/' : '/exports/';
        await descargarArchivo(ruta, `${nombre}${ext}`, prefijo);
      }
    }
    setEstado('Export completo ✓', '#4caf50');
  } catch (err) {
    setEstado('Error export: ' + err.message, '#f44336');
  } finally {
    btn.innerHTML = '💾 EXPORTAR'; btn.disabled = false;
  }
}

// ── Timer ─────────────────────────────────────────────────────────────────────

function _actualizarTimer() {
  if (!t0) return;
  const s = Math.floor((Date.now() - t0) / 1000);
  document.getElementById('timer').textContent =
  `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;
  if (s >= 300) detener();
}
