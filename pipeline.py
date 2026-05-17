"""
PIPELINE — Detección de F0 y utilidades musicales
==================================================
Usa pYIN (librosa) como detector principal.
voiced_flag reemplaza CalibradorSilencio.
"""

import math
from collections import Counter

import librosa
import numpy as np

# ============================================================================
# CONSTANTES
# ============================================================================

SAMPLE_RATE = 44100
F0_MIN      = 80.0
F0_MAX      = 1100.0
HOP_LENGTH  = 512

NOTAS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

INTERVALOS_ESCALA = {
    "Mayor"       : [0,2,4,5,7,9,11],
    "Menor nat."  : [0,2,3,5,7,8,10],
    "Pentatónica" : [0,2,4,7,9],
    "Menor arm."  : [0,2,3,5,7,8,11],
    "Dórica"      : [0,2,3,5,7,9,10],
}

# ============================================================================
# DETECCIÓN F0 — pYIN
# ============================================================================

def detectar_f0(audio: np.ndarray, sr: int = SAMPLE_RATE,
                hop_length: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """
    Detecta F0 frame a frame con pYIN.

    Retorna:
        f0        — array de frecuencias Hz (0.0 en frames no voz)
        voiced    — array bool, True donde hay voz detectada
    """
    f0, voiced_flag, _ = librosa.pyin(
        audio,
        fmin=F0_MIN,
        fmax=F0_MAX,
        sr=sr,
        hop_length=hop_length,
        fill_na=0.0,
    )
    return f0.astype(np.float32), voiced_flag.astype(bool)

def detectar_f0_rt(audio: np.ndarray, sr: int = SAMPLE_RATE,
                   hop_length: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """
    Detección F0 ligera para tiempo real. Usa YIN en lugar de pYIN.
    ~5-10ms vs ~90ms de pYIN para chunk de 2048 muestras.
    """
    f0 = librosa.yin(
        audio,
        fmin=F0_MIN,
        fmax=F0_MAX,
        sr=sr,
        hop_length=hop_length,
    )
    voiced = f0 > 0
    return f0.astype(np.float32), voiced.astype(bool)


def f0_a_tiempos(n_frames: int, sr: int = SAMPLE_RATE,
                 hop_length: int = 512) -> np.ndarray:
    """Genera array de tiempos en segundos para cada frame de F0."""
    return librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=hop_length)

# ============================================================================
# CONVERSIONES MUSICALES
# ============================================================================

def hz_a_midi(freq: float) -> float | None:
    if freq <= 0:
        return None
    return 12 * math.log2(freq / 440.0) + 69


def hz_a_nota(freq: float) -> tuple:
    """
    Retorna (nota, octava, cents, freq_ideal).
    Deriva todo desde hz_a_midi para garantizar consistencia.
    MIDI 69 = A4 = 440Hz. Octava = midi // 12 - 1.
    """
    try:
        if freq <= 0:
            return None, 0, 0.0, 0.0
        midi    = 12 * math.log2(freq / 440.0) + 69
        midi_r  = round(midi)
        cents   = (midi - midi_r) * 100
        nota    = NOTAS[midi_r % 12]
        octava  = midi_r // 12 - 1
        f_ideal = 440.0 * 2 ** ((midi_r - 69) / 12)
        return nota, int(octava), round(cents, 1), round(f_ideal, 2)
    except Exception:
        return None, 0, 0.0, 0.0


def midi_a_nota(midi: float) -> tuple:
    """Retorna (nota, octava) desde valor MIDI."""
    semis_r = round(midi)
    return NOTAS[(semis_r - 1) % 12], (semis_r - 1) // 12

# ============================================================================
# INFERENCIA DE ESCALA
# ============================================================================

def inferir_escala(notas_midi: list, min_notas: int = 5) -> dict | None:
    """
    Infiere escala desde lista de valores MIDI.
    Retorna dict {tonica, nombre, confianza} o None.
    """
    if len(notas_midi) < min_notas:
        return None
    try:
        clases    = [int(round(m)) % 12 for m in notas_midi]
        conteo    = Counter(clases)
        tonica    = conteo.most_common(1)[0][0]
        presentes = set((c - tonica) % 12 for c in conteo)

        mejor_escala, mejor_score = None, 0.0
        for nombre, intervalos in INTERVALOS_ESCALA.items():
            s     = set(intervalos)
            score = len(presentes & s) - len(presentes - s) * 0.5
            if score > mejor_score:
                mejor_score, mejor_escala = score, nombre

        confianza = min(100, int(mejor_score / len(INTERVALOS_ESCALA["Mayor"]) * 100))
        return {"tonica": NOTAS[tonica], "nombre": mejor_escala, "confianza": confianza}
    except Exception:
        return None


def nota_en_escala(midi: float, tonica: str, intervalos: list) -> bool:
    try:
        return (int(round(midi)) % 12 - NOTAS.index(tonica)) % 12 in intervalos
    except Exception:
        return True


def calificar(valor: float, ex: float, ok: float, mal: float) -> str:
    if valor <= ex:  return "Excelente"
    if valor <= ok:  return "Ok"
    if valor <= mal: return "Malo"
    return "Pésimo"
