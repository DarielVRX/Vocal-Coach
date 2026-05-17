"""
TEST PIPELINE — F0 + DetectorPlateau con feedback visual interactivo
====================================================================
Uso: python test_pipeline.py
Abre selector de archivo → genera reporte HTML + consola compacta
"""

import os, sys, json, webbrowser, tempfile
import numpy as np
import soundfile as sf
import tkinter as tk
from tkinter import filedialog

# ── Selector de archivo ───────────────────────────────────────────────────────
root = tk.Tk(); root.withdraw()
audio_path = filedialog.askopenfilename(
    title="Seleccionar audio vocal",
    filetypes=[("Audio", "*.wav *.mp3 *.flac *.ogg *.m4a")]
)
if not audio_path:
    print("Cancelado."); sys.exit(0)

print(f"\n[TEST] Cargando: {os.path.basename(audio_path)}")

# ── Cargar audio ──────────────────────────────────────────────────────────────
audio, sr = sf.read(audio_path, dtype="float32")
if audio.ndim > 1:
    audio = np.mean(audio, axis=1)

dur = len(audio) / sr
print(f"[TEST] Duración: {dur:.1f}s | SR: {sr}Hz | Muestras: {len(audio)}")

# ── Importar pipeline local ───────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(audio_path))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline import detectar_f0, f0_a_tiempos, hz_a_midi, hz_a_nota, SAMPLE_RATE
from analyzer import DetectorPlateau

# Resamplear si necesario
if sr != SAMPLE_RATE:
    from scipy import signal as sp_signal
    print(f"[TEST] Resampling {sr}→{SAMPLE_RATE}Hz...")
    audio = sp_signal.resample(audio, int(len(audio) * SAMPLE_RATE / sr)).astype(np.float32)
    sr    = SAMPLE_RATE

# ── Detectar F0 ───────────────────────────────────────────────────────────────
print("[TEST] Detectando F0 (pYIN)...")
f0, voiced = detectar_f0(audio, sr=sr)
tiempos    = f0_a_tiempos(len(f0), sr=sr)

NOTAS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

def hz_a_nombre(hz):
    if hz <= 0: return "—"
    midi = hz_a_midi(hz)
    if midi is None: return "—"
    r = round(midi)
    return f"{NOTAS[r%12]}{r//12 - 1}"

# ── Bloque B: consola ─────────────────────────────────────────────────────────
f0_voiced = f0[voiced & (f0 > 0)]
n_total   = len(f0)
n_voiced  = len(f0_voiced)
n_silence = n_total - n_voiced

print("\n" + "="*60)
print("  BLOQUE B — ANÁLISIS NUMÉRICO")
print("="*60)

print(f"\n[F0 FRAMES]")
print(f"  Total     : {n_total}")
print(f"  Voiced    : {n_voiced} ({n_voiced/n_total*100:.1f}%)")
print(f"  Silencio  : {n_silence} ({n_silence/n_total*100:.1f}%)")

if len(f0_voiced) > 0:
    p10,p25,p50,p75,p90 = np.percentile(f0_voiced, [10,25,50,75,90])
    print(f"\n[PERCENTILES F0 Hz → nota]")
    for pct, val in zip([10,25,50,75,90],[p10,p25,p50,p75,p90]):
        print(f"  P{pct:<3}: {val:7.1f} Hz  →  {hz_a_nombre(val)}")

    rango_ok = 65 <= p50 <= 1047
    print(f"\n[FLAG] Mediana F0={p50:.1f}Hz ({hz_a_nombre(p50)}) "
          f"{'✓ dentro de rango vocal humano (C2–C6)' if rango_ok else '⚠ FUERA de rango vocal humano'}")

    midis_voiced = np.array([hz_a_midi(f) for f in f0_voiced if f > 0])
    clases = (np.round(midis_voiced) % 12).astype(int)
    conteo = np.bincount(clases, minlength=12)
    total_c = conteo.sum()
    print(f"\n[HISTOGRAMA NOTAS (frames voiced)]")
    orden = np.argsort(conteo)[::-1]
    for i in orden:
        if conteo[i] == 0: continue
        barra = "█" * int(conteo[i]/total_c*40)
        print(f"  {NOTAS[i]:3}: {conteo[i]:5d} ({conteo[i]/total_c*100:5.1f}%)  {barra}")

# ── Detectar plateaus ─────────────────────────────────────────────────────────
print("\n[TEST] Detectando plateaus...")
n_frames_total = int(len(audio) / 512) + 1
pct_voiced     = n_voiced / max(1, n_frames_total)
dur_min_ms     = max(80.0, 150.0 - pct_voiced * 100.0)
cents_thr      = max(25.0, 35.0 - pct_voiced * 15.0)
print(f"[CONSTANTES] DUR={dur_min_ms:.0f}ms CENTS={cents_thr:.1f}¢ pct_voiced={pct_voiced:.2f}")
det      = DetectorPlateau(dur_min_ms=dur_min_ms, cents_thr=cents_thr)
plateaus = det.detectar(f0, voiced, tiempos)

# Simplificación de referencia (mismo paso que vocal_coach_server)
from analyzer import Plateau as _Plateau

def _simplificar_referencia(pls):
    if len(pls) < 2:
        return pls
    changed = True
    while changed:
        changed    = False
        fusionados = [pls[0]]
        for curr in pls[1:]:
            prev     = fusionados[-1]
            mismo    = round(curr.mediana_midi) == round(prev.mediana_midi)
            contiguo = (curr.t_inicio - prev.t_fin) < 0.020
            if mismo and contiguo:
                f0m = np.array(prev.f0_series + curr.f0_series, dtype=np.float32)
                fusionados[-1] = _Plateau(
                    t_inicio    = prev.t_inicio,
                    t_fin       = curr.t_fin,
                    mediana_f0  = prev.mediana_f0,
                    mediana_midi= prev.mediana_midi,
                    cents       = prev.cents,
                    varianza_f0 = round(float(np.std(f0m) / (np.median(f0m) + 1e-9)), 4),
                    tipo        = prev.tipo,
                    nota        = prev.nota,
                    octava      = prev.octava,
                    f0_series   = prev.f0_series + curr.f0_series,
                )
                changed = True
            else:
                fusionados.append(curr)
        pls = fusionados
    fusionados = [pls[0]]
    for curr in pls[1:]:
        prev      = fusionados[-1]
        adyacente = abs(round(curr.mediana_midi) - round(prev.mediana_midi)) <= 1
        contiguo  = (curr.t_inicio - prev.t_fin) < 0.050
        if adyacente and contiguo:
            dur_prev = prev.t_fin - prev.t_inicio
            dur_curr = curr.t_fin - curr.t_inicio
            base     = prev if dur_prev >= dur_curr else curr
            f0m      = np.array(prev.f0_series + curr.f0_series, dtype=np.float32)
            fusionados[-1] = _Plateau(
                t_inicio    = prev.t_inicio,
                t_fin       = curr.t_fin,
                mediana_f0  = base.mediana_f0,
                mediana_midi= base.mediana_midi,
                cents       = base.cents,
                varianza_f0 = round(float(np.std(f0m) / (np.median(f0m) + 1e-9)), 4),
                tipo        = base.tipo,
                nota        = base.nota,
                octava      = base.octava,
                f0_series   = prev.f0_series + curr.f0_series,
            )
        else:
            fusionados.append(curr)
    return fusionados

plateaus = _simplificar_referencia(plateaus)

print(f"\n[PLATEAUS] Total: {len(plateaus)}")

from collections import Counter
tipos = Counter(p.tipo for p in plateaus)
for tipo, cnt in tipos.most_common():
    subset = [p for p in plateaus if p.tipo == tipo]
    durs   = [p.t_fin - p.t_inicio for p in subset]
    cents  = [abs(p.cents) for p in subset]
    print(f"  {tipo:12}: {cnt:4d} | dur {min(durs):.2f}–{max(durs):.2f}s prom={np.mean(durs):.2f}s "
          f"| cents prom={np.mean(cents):.1f} std={np.std(cents):.1f}")

print(f"\n[TOP 10 PLATEAUS MÁS LARGOS]")
top10 = sorted(plateaus, key=lambda p: p.t_fin - p.t_inicio, reverse=True)[:10]
for p in top10:
    print(f"  {p.t_inicio:6.2f}–{p.t_fin:6.2f}s  {p.tipo:12} "
          f"{p.nota}{p.octava}  midi={p.mediana_midi:.1f}  cents={p.cents:+.1f}¢  var={p.varianza_f0:.4f}")

if len(plateaus) > 1:
    gaps = [plateaus[i+1].t_inicio - plateaus[i].t_fin for i in range(len(plateaus)-1)]
    gaps_grandes = [(i, g) for i, g in enumerate(gaps) if g > 1.0]
    print(f"\n[GAPS entre plateaus]")
    print(f"  prom={np.mean(gaps):.3f}s  max={max(gaps):.3f}s  gaps>1s: {len(gaps_grandes)}")

if dur > 0:
    frames_cubiertos = sum(
        int((p.t_fin - p.t_inicio) * sr / 512) for p in plateaus
    )
    print(f"\n[COBERTURA]")
    print(f"  Frames voiced    : {n_voiced}")
    print(f"  Frames en plateau: {frames_cubiertos}")
    print(f"  Cobertura        : {min(100, frames_cubiertos/max(1,n_voiced)*100):.1f}%")

print("\n" + "="*60)

# ── Bloque A: HTML interactivo ────────────────────────────────────────────────
print("\n[TEST] Generando visualización HTML...")

import base64
with open(audio_path, "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode()
ext = os.path.splitext(audio_path)[1].lstrip('.')
if ext == 'wav': mime = 'audio/wav'
elif ext == 'mp3': mime = 'audio/mpeg'
else: mime = 'audio/ogg'

SUBSAMPLE = max(1, len(tiempos) // 2000)
f0_data = [
    {"t": round(float(tiempos[i]), 3),
     "midi": round(float(hz_a_midi(f0[i])), 2) if voiced[i] and f0[i] > 0 else 0,
     "voiced": bool(voiced[i])}
    for i in range(0, len(tiempos), SUBSAMPLE)
]

plateaus_data = [
    {"t_ini": p.t_inicio, "t_fin": p.t_fin,
     "midi": p.mediana_midi, "cents": p.cents,
     "nota": p.nota, "octava": p.octava, "tipo": p.tipo}
    for p in plateaus
]

html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Test Pipeline — {os.path.basename(audio_path)}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #0d0d0d; color: #eee; font-family: monospace; padding: 16px; }}
h2 {{ color: #7c83fd; margin-bottom: 12px; font-size: 1rem; letter-spacing: 2px; }}
#controls {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }}
audio {{ flex: 1; min-width: 200px; }}
#info {{ font-size: 0.8rem; color: #888; }}
#now  {{ font-size: 0.9rem; color: #7c83fd; min-width: 120px; }}
#canvas-wrap {{ position: relative; width: 100%; background: #0a0a0a; border-radius: 8px; overflow: hidden; }}
canvas {{ display: block; width: 100%; }}
#tooltip {{ position: absolute; background: #222; border: 1px solid #444; padding: 4px 8px;
           font-size: 0.75rem; color: #eee; pointer-events: none; display: none; border-radius: 4px; }}
</style>
</head>
<body>
<h2>TEST PIPELINE — {os.path.basename(audio_path)}</h2>
<div id="controls">
  <audio id="aud" controls src="data:{mime};base64,{audio_b64}"></audio>
  <span id="now">t = 0.00s</span>
  <span id="info">Duración: {dur:.1f}s | {len(plateaus)} plateaus</span>
</div>
<div id="canvas-wrap">
  <canvas id="cv"></canvas>
  <div id="tooltip"></div>
</div>

<script>
const DUR      = {dur:.3f};
const PLATEAUS = {json.dumps(plateaus_data)};
const NOTAS    = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
const WINDOW_S = 20;

const COLORS = {{
  plateau: '#4caf50', vibrato: '#7c83fd',
  portamento: '#ff9800', inestable: '#f44336'
}};

const cv    = document.getElementById('cv');
const ctx   = cv.getContext('2d');
const aud   = document.getElementById('aud');
const nowEl = document.getElementById('now');
const tip   = document.getElementById('tooltip');
const wrap  = document.getElementById('canvas-wrap');

const H_LABEL = 28, LABEL_W = 42;
const MIDI_MIN = 36, MIDI_MAX = 84;
let W, H, PX_SEMI;

function resize() {{
  W = wrap.clientWidth;
  H = Math.max(320, Math.min(500, window.innerHeight * 0.65));
  cv.width  = W * devicePixelRatio;
  cv.height = H * devicePixelRatio;
  cv.style.height = H + 'px';
  ctx.scale(devicePixelRatio, devicePixelRatio);
  PX_SEMI = (H - H_LABEL) / (MIDI_MAX - MIDI_MIN + 1);
  draw(aud.currentTime);
}}

function midiToY(midi) {{
  return (H - H_LABEL) - (midi - MIDI_MIN) * PX_SEMI;
}}

function tToX(t, tNow) {{
  return LABEL_W + ((t - tNow + WINDOW_S / 2) / WINDOW_S) * (W - LABEL_W);
}}

function draw(tNow) {{
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#0a0a0a';
  ctx.fillRect(0, 0, W, H);

  // Grid notas
  for (let midi = MIDI_MIN; midi <= MIDI_MAX; midi++) {{
    const nota = NOTAS[midi % 12];
    const y    = midiToY(midi);
    const esC  = nota === 'C';
    const sos  = nota.includes('#');
    ctx.fillStyle = sos ? '#0f0f0f' : '#111';
    ctx.fillRect(LABEL_W, y - PX_SEMI, W - LABEL_W, PX_SEMI);
    if (esC) {{
      ctx.strokeStyle = '#2a2a2a'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(LABEL_W, y); ctx.lineTo(W, y); ctx.stroke();
      const oct = Math.floor(midi/12) - 1;
      ctx.fillStyle = '#7c83fd';
      ctx.font = `bold ${{Math.max(9, PX_SEMI * 0.8)}}px monospace`;
      ctx.textAlign = 'right';
      ctx.fillText(`C${{oct}}`, LABEL_W - 3, y);
    }}
  }}
  ctx.strokeStyle = '#222'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(LABEL_W, 0); ctx.lineTo(LABEL_W, H - H_LABEL); ctx.stroke();

  // Eje tiempo
  ctx.fillStyle = '#111';
  ctx.fillRect(0, H - H_LABEL, W, H_LABEL);
  const tStart = tNow - WINDOW_S / 2;
  const tEnd   = tNow + WINDOW_S / 2;
  const step   = 2;
  const tFirst = Math.ceil(tStart / step) * step;
  ctx.font = '9px monospace'; ctx.textAlign = 'center';
  for (let s = tFirst; s <= tEnd; s += step) {{
    const x = tToX(s, tNow);
    ctx.fillStyle = '#333'; ctx.fillRect(x, 0, 1, H - H_LABEL);
    ctx.fillStyle = '#666';
    ctx.fillText(`${{s.toFixed(0)}}s`, x, H - H_LABEL + 16);
  }}

  // Plateaus estilo piano roll
  for (const p of PLATEAUS) {{
    const x1 = tToX(p.t_ini, tNow);
    const x2 = tToX(p.t_fin, tNow);
    if (x2 < LABEL_W || x1 > W) continue;
    const y  = midiToY(p.midi);
    const c  = COLORS[p.tipo] || '#aaa';
    const lw = Math.max(3, PX_SEMI * 0.6);
    const xa = Math.max(LABEL_W, x1);
    const xb = Math.min(W, x2);

    ctx.strokeStyle = c;
    ctx.lineWidth   = lw;
    ctx.lineCap     = 'round';
    ctx.lineJoin    = 'round';

    if (p.tipo === 'vibrato') {{
      // Línea sinusoidal
      const amp  = PX_SEMI * 0.35;
      const freq = 6;
      const dur  = (xb - xa) || 1;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      for (let x = xa; x <= xb; x += 0.8) {{
        const yv = y + Math.sin(((x - xa) / dur) * Math.PI * 2 * freq) * amp;
        x === xa ? ctx.moveTo(x, yv) : ctx.lineTo(x, yv);
      }}
      ctx.stroke();
    }} else {{
      ctx.beginPath();
      ctx.moveTo(xa, y);
      ctx.lineTo(xb, y);
      ctx.stroke();
    }}

    if (x2 - x1 > 24) {{
      ctx.fillStyle = c;
      ctx.font = 'bold 8px monospace'; ctx.textAlign = 'left';
      ctx.fillText(`${{p.nota}}${{p.octava}}`, xa + 2, y - 4);
    }}
  }}

  // Cursor central
  const cx = tToX(tNow, tNow);
  ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
  ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H - H_LABEL); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#7c83fd'; ctx.font = 'bold 10px monospace'; ctx.textAlign = 'left';
  ctx.fillText(`${{tNow.toFixed(2)}}s`, cx + 4, 14);

  // Leyenda
  let lx = LABEL_W + 8;
  for (const [tipo, color] of Object.entries(COLORS)) {{
    ctx.fillStyle = color;
    ctx.fillRect(lx, H - H_LABEL + 18, 10, 6);
    ctx.fillStyle = '#aaa'; ctx.font = '9px monospace'; ctx.textAlign = 'left';
    ctx.fillText(tipo, lx + 13, H - H_LABEL + 24);
    lx += 80;
  }}
}}

// Tooltip
cv.addEventListener('mousemove', e => {{
  const rect = cv.getBoundingClientRect();
  const mx   = e.clientX - rect.left;
  const my   = e.clientY - rect.top;
  const tNow = aud.currentTime;
  const t    = tNow - WINDOW_S / 2 + (mx - LABEL_W) / (W - LABEL_W) * WINDOW_S;
  const hit  = PLATEAUS.find(p => t >= p.t_ini && t <= p.t_fin &&
               Math.abs(my - midiToY(p.midi)) < 8);
  if (hit) {{
    tip.style.display = 'block';
    tip.style.left = (mx + 10) + 'px';
    tip.style.top  = (my - 20) + 'px';
    tip.textContent = `${{hit.tipo}} ${{hit.nota}}${{hit.octava}} | midi=${{hit.midi.toFixed(1)}} cents=${{hit.cents > 0 ? '+' : ''}}${{hit.cents}}¢ | ${{hit.t_ini.toFixed(2)}}–${{hit.t_fin.toFixed(2)}}s`;
  }} else {{
    tip.style.display = 'none';
  }}
}});

// Click → seek
cv.addEventListener('click', e => {{
  const rect = cv.getBoundingClientRect();
  const tNow = aud.currentTime;
  const t    = tNow - WINDOW_S / 2 + (e.clientX - rect.left - LABEL_W) / (W - LABEL_W) * WINDOW_S;
  if (t >= 0 && t <= DUR) aud.currentTime = t;
}});

function tick() {{
  nowEl.textContent = `t = ${{aud.currentTime.toFixed(2)}}s`;
  draw(aud.currentTime);
  requestAnimationFrame(tick);
}}

window.addEventListener('resize', resize);
resize();
tick();
</script>
</body>
</html>"""

tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8")
tmp.write(html)
tmp.close()
print(f"[TEST] Abriendo: {tmp.name}")
webbrowser.open(f"file://{tmp.name}")
print("[TEST] Listo.")
