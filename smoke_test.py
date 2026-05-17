"""
SMOKE TEST — Verifica integración pipeline → analyzer → session → diagnostico
Genera señal sintética (sinusoide vocal) y valida el flujo completo.
Correr antes de levantar el servidor: python smoke_test.py
"""

import sys
import numpy as np

def generar_senal(freq_hz=220.0, dur_s=2.0, sr=44100, ruido=0.01) -> np.ndarray:
    """Sinusoide con ruido leve simulando voz."""
    t   = np.linspace(0, dur_s, int(sr * dur_s), endpoint=False)
    sig = np.sin(2 * np.pi * freq_hz * t).astype(np.float32)
    sig += np.random.randn(len(sig)).astype(np.float32) * ruido
    return sig

def ok(msg):  print(f"  ✓ {msg}")
def fail(msg): print(f"  ✗ {msg}"); sys.exit(1)

print("=" * 50)
print("  VOCAL COACH — Smoke Test")
print("=" * 50)

# ── 1. pipeline ──────────────────────────────────────────────
print("\n[1] pipeline.py")
try:
    from pipeline import (
        SAMPLE_RATE, HOP_LENGTH, F0_MIN, F0_MAX,
        detectar_f0, f0_a_tiempos,
        hz_a_midi, hz_a_nota, inferir_escala, calificar,
    )
    ok("imports OK")

    sig    = generar_senal(220.0, dur_s=1.0)
    f0, vf = detectar_f0(sig)
    assert len(f0) > 0 and len(vf) > 0, "detectar_f0 retornó vacío"
    ok(f"detectar_f0: {vf.sum()} frames con voz de {len(f0)}")

    midi = hz_a_midi(220.0)
    assert abs(midi - 57.0) < 0.1, f"hz_a_midi(220) esperado ~57, got {midi}"
    ok(f"hz_a_midi(220Hz) = {midi:.2f}")

    nota, oct, cents, _ = hz_a_nota(220.0)
    assert nota == "A" and oct == 3, f"hz_a_nota(220) esperado A3, got {nota}{oct}"
    ok(f"hz_a_nota(220Hz) = {nota}{oct} ({cents:+.1f}¢)")

    escala = inferir_escala([57, 59, 61, 62, 64, 66, 68])
    assert escala is not None, "inferir_escala retornó None"
    ok(f"inferir_escala = {escala['tonica']} {escala['nombre']} ({escala['confianza']}%)")

except Exception as e:
    fail(f"pipeline: {e}")

# ── 2. analyzer ──────────────────────────────────────────────
print("\n[2] analyzer.py")
try:
    from analyzer import DetectorPlateau, AnalizadorFrase, frase_a_dict

    sig = generar_senal(220.0, dur_s=1.5)
    f0, vf = detectar_f0(sig)
    tiempos = f0_a_tiempos(len(f0))

    det      = DetectorPlateau()
    plateaus = det.detectar(f0, vf, tiempos)
    ok(f"DetectorPlateau: {len(plateaus)} plateaus detectados")

    tipos = set(p.tipo for p in plateaus)
    ok(f"Tipos encontrados: {tipos}")

    an    = AnalizadorFrase()
    frase = an.analizar(sig, idx=1, t_inicio=0.0, t_fin=1.5)
    assert frase is not None, "AnalizadorFrase.analizar retornó None"
    ok(f"AnalizadorFrase: frase={frase.idx} plateaus={len(frase.plateaus)}")

    d = frase_a_dict(frase)
    assert "plateaus" in d and "cal" in d, "frase_a_dict incompleto"
    ok("frase_a_dict: estructura OK")

except Exception as e:
    fail(f"analyzer: {e}")

# ── 3. session ───────────────────────────────────────────────
print("\n[3] session.py")
try:
    from session import Sesion, SAMPLE_RATE as SR

    ses = Sesion()
    ses.iniciar()

    sig      = generar_senal(220.0, dur_s=2.0, sr=SR)
    chunk_sz = 2048
    estados  = []

    for i in range(0, len(sig) - chunk_sz, chunk_sz):
        estado = ses.procesar_chunk(sig[i:i+chunk_sz])
        if estado: estados.append(estado)

    assert len(estados) > 0, "procesar_chunk no retornó estados"
    ok(f"procesar_chunk: {len(estados)} estados procesados")

    frases = ses.detener()
    ok(f"detener: {len(frases)} frases cerradas")

    audio = ses.audio_completo
    assert audio is not None and len(audio) > 0, "audio_completo vacío"
    ok(f"audio_completo: {len(audio)/SR:.2f}s")

except Exception as e:
    fail(f"session: {e}")

# ── 4. diagnostico ───────────────────────────────────────────
print("\n[4] diagnostico.py")
try:
    from diagnostico import generar_diagnostico

    result = generar_diagnostico(frases)
    assert "diagnostico" in result, "generar_diagnostico sin clave 'diagnostico'"
    ok(f"generar_diagnostico: estructura OK")

    diag = result["diagnostico"]
    if diag:
        ok(f"cal_general={diag['cal_general']} "
           f"n_frases={diag['n_frases']} "
           f"n_plateaus={diag['n_plateaus']}")
        ok(f"escala={diag['escala_dominante']} "
           f"cents_prom={diag['cents_promedio']}¢")
    else:
        ok("diagnostico=None (pocas frases — normal en señal corta)")

    frases_dict = result["frases"]
    assert isinstance(frases_dict, list), "frases no es lista"
    ok(f"frases serializadas: {len(frases_dict)}")

except Exception as e:
    fail(f"diagnostico: {e}")

# ── Resultado ────────────────────────────────────────────────
print("\n" + "=" * 50)
print("  ✓ Todos los módulos OK — servidor listo para levantar")
print("=" * 50)
