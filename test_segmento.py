# test_segmento.py — análisis detallado de un segmento específico
import os, sys, json, webbrowser, tempfile, base64
import numpy as np
import soundfile as sf

SEG_INI = 32.0
SEG_FIN = 45.0

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import detectar_f0, f0_a_tiempos, hz_a_midi, hz_a_nota, SAMPLE_RATE
from analyzer import DetectorPlateau

audio_path = sys.argv[1] if len(sys.argv) > 1 else input("Ruta al vocals.wav: ").strip()

audio, sr = sf.read(audio_path, dtype="float32")
if audio.ndim > 1: audio = np.mean(audio, axis=1)

if sr != SAMPLE_RATE:
    from scipy import signal as sp_signal
    audio = sp_signal.resample(audio, int(len(audio) * SAMPLE_RATE / sr)).astype(np.float32)
    sr = SAMPLE_RATE

# Recortar segmento
s_ini = int(SEG_INI * sr)
s_fin = int(SEG_FIN * sr)
seg   = audio[s_ini:s_fin]

print(f"\n[SEGMENTO] {SEG_INI}s–{SEG_FIN}s ({SEG_FIN-SEG_INI:.1f}s)")

f0, voiced = detectar_f0(seg, sr=sr)
tiempos    = f0_a_tiempos(len(f0), sr=sr) + SEG_INI

NOTAS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

def nombre(hz):
    if hz <= 0: return "—"
    m = hz_a_midi(hz)
    if m is None: return "—"
    r = round(m)
    return f"{NOTAS[r%12]}{r//12-1}"

# ── Frame a frame ──────────────────────────────────────────────────────────────
print(f"\n[FRAMES F0] total={len(f0)} voiced={voiced.sum()}")
print(f"{'t':>7}  {'Hz':>7}  {'nota':>5}  {'midi':>6}  voiced")
for i in range(len(f0)):
    if not voiced[i] and f0[i] == 0: continue
    midi = hz_a_midi(f0[i]) if f0[i] > 0 else 0
    print(f"{tiempos[i]:7.3f}  {f0[i]:7.1f}  {nombre(f0[i]):>5}  "
          f"{midi:6.2f}  {'✓' if voiced[i] else '·'}")

# ── Detectar plateaus ──────────────────────────────────────────────────────────
n_frames_total = int(len(audio) / 512) + 1
pct_voiced     = voiced.sum() / max(1, n_frames_total)
dur_min_ms     = max(80.0, 150.0 - pct_voiced * 100.0)
cents_thr      = max(25.0, 35.0 - pct_voiced * 15.0)

os.environ['PLATEAU_VERBOSE'] = '1'
det      = DetectorPlateau(dur_min_ms=dur_min_ms, cents_thr=cents_thr)
plateaus = det.detectar(f0, voiced, tiempos)
os.environ.pop('PLATEAU_VERBOSE')

print(f"\n[PLATEAUS RESULTADO] {len(plateaus)}")
for p in plateaus:
    print(f"  {p.t_inicio:6.3f}–{p.t_fin:6.3f}s  {p.tipo:12}  "
          f"{p.nota}{p.octava}  midi={p.mediana_midi:.1f}  "
          f"cents={p.cents:+.1f}¢  dur={p.t_fin-p.t_inicio:.3f}s  "
          f"gap_prev={'—' if plateaus.index(p)==0 else f'{p.t_inicio-plateaus[plateaus.index(p)-1].t_fin:.3f}s'}")
