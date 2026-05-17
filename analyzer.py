"""
ANALYZER — Detección de plateaus y análisis de frases
======================================================
Jerarquía:
  Plateau → unidad de análisis de afinación
  Frase   → agrupa plateaus entre silencios
  Sesión  → acumula todos los plateaus (escala global, informe)

Tipos de segmento vocal:
  plateau     — F0 varía < CENTS_PLATEAU durante >= DUR_PLATEAU_MS
  vibrato     — oscilación periódica ~5-7 Hz dentro del plateau
  portamento  — transición suave entre plateaus
  inestable   — variación no periódica, no clasificable

Tipos de arreglo (fusionado=True):
  ornamento        — nota de paso corta entre dos notas principales
  appoggiatura     — nota de apoyo que resuelve a la siguiente
  melisma          — múltiples notas sobre una sílaba
  arreglo_undefined — fusionado pero no clasificable
"""
import os
import numpy as np
from dataclasses import dataclass, field

from pipeline import (
    SAMPLE_RATE, INTERVALOS_ESCALA, HOP_LENGTH,
    detectar_f0, f0_a_tiempos,
    hz_a_midi, hz_a_nota, midi_a_nota,
    inferir_escala, nota_en_escala, calificar,
)

# ============================================================================
# CONSTANTES DE ANÁLISIS
# ============================================================================

CENTS_PLATEAU      = 30.0
DUR_PLATEAU_MS     = 150.0
PORTAMENTO_DUR_MIN_MS  = 60.0
PORTAMENTO_SALTO_MIN   = 1.0
PORTAMENTO_SALTO_MAX   = 12.0
PORTAMENTO_MONOTONIA   = 0.65
VIBRATO_HZ_MIN     = 4.5
VIBRATO_HZ_MAX     = 7.5
VIBRATO_MIN_CICLOS = 2
HOP_LENGTH         = 512

DIAG = dict(
    cents_excelente  = 10,
    cents_ok         = 25,
    cents_malo       = 45,
    estabilidad_ex   = 0.05,
    estabilidad_ok   = 0.15,
    estabilidad_mal  = 0.30,
    min_notas_escala = 5,
)

# Score por frase
SCORE_TABLA = [
    ("SS", 10,  0.05),
    ("S",  15,  0.08),
    ("A",  25,  0.15),
    ("B",  35,  0.25),
    ("C",  45,  0.35),
    ("D",  999, 999 ),
]

# ============================================================================
# TIPOS DE DATOS
# ============================================================================

@dataclass
class Plateau:
    t_inicio      : float
    t_fin         : float
    mediana_f0    : float
    mediana_midi  : float
    cents         : float
    varianza_f0   : float
    tipo          : str
    nota          : str  = ""
    octava        : int  = 0
    f0_series     : list = field(default_factory=list)
    fusionado     : bool = False
    subtipo_arreglo: str | None = None


@dataclass
class Frase:
    idx       : int
    t_inicio  : float
    t_fin     : float
    plateaus  : list
    cents_med : float = 0.0
    estab_med : float = 0.0
    cal       : dict  = field(default_factory=dict)
    escala    : dict  = field(default_factory=dict)
    score     : str   = ""
    feedback  : list  = field(default_factory=list)

# ============================================================================
# SCORE Y FEEDBACK
# ============================================================================

def calcular_score(cents: float, estab: float) -> str:
    for label, c_max, e_max in SCORE_TABLA:
        if cents <= c_max and estab <= e_max:
            return label
    return "D"


def generar_feedback(frase: "Frase") -> list[str]:
    msgs = []
    tipos = [p.tipo for p in frase.plateaus]

    # Dirección de afinación
    cents_con_signo = [p.cents for p in frase.plateaus if p.tipo in ("plateau", "vibrato")]
    if cents_con_signo:
        media = float(np.mean(cents_con_signo))
        if media < -15:
            msgs.append("¡Sube!")
        elif media > 15:
            msgs.append("¡Baja!")

    # Tipos notables
    if "vibrato" in tipos:
        msgs.append("¡Vibrato!")
    if "portamento" in tipos:
        msgs.append("¡Slide!")
    if tipos.count("inestable") > len(tipos) * 0.4:
        msgs.append("¡Inestable!")

    return msgs

# ============================================================================
# DETECTOR DE PLATEAUS
# ============================================================================

class DetectorPlateau:

    def __init__(self, dur_min_ms=None, cents_thr=None):
        self._dur_min_ms = dur_min_ms or DUR_PLATEAU_MS
        self._cents_thr  = cents_thr  or CENTS_PLATEAU

    def detectar(self, f0: np.ndarray, voiced: np.ndarray,
                 tiempos: np.ndarray) -> list[Plateau]:
        plateaus = []
        n = len(f0)
        i = 0
        while i < n:
            if not voiced[i]:
                i += 1
                continue
            j = i
            while j < n and voiced[j]:
                j += 1
            seg_f0 = f0[i:j]
            seg_t  = tiempos[i:j]
            seg_pl = self._segmentar_en_plateaus(seg_f0, seg_t)
            plateaus.extend(seg_pl)
            i = j
        return plateaus

    def _segmentar_en_plateaus(self, f0_seg: np.ndarray,
                                t_seg: np.ndarray) -> list[Plateau]:
        if len(f0_seg) == 0:
            return []

        midi_seg  = np.array([hz_a_midi(f) or 0.0 for f in f0_seg], dtype=np.float32)
        cents_abs = midi_seg * 100.0
        resultados = []
        n = len(f0_seg)
        inicio = 0

        while inicio < n:
            fin = inicio + 1
            while fin < n:
                ventana = cents_abs[inicio:fin+1]
                if np.ptp(ventana) > self._cents_thr:
                    break
                fin += 1

            duracion_s  = t_seg[fin-1] - t_seg[inicio] if fin > inicio else 0.0
            rango_final = np.ptp(cents_abs[inicio:fin])

            if duracion_s * 1000 >= self._dur_min_ms:
                pl = self._construir_plateau(
                    f0_seg[inicio:fin], midi_seg[inicio:fin],
                    t_seg[inicio], t_seg[fin-1]
                )
                if pl:
                    resultados.append(pl)
            else:
                if fin - inicio >= 2:
                    pl = self._construir_portamento(
                        f0_seg[inicio:fin], midi_seg[inicio:fin],
                        t_seg[inicio], t_seg[fin-1],
                        prev_midi=resultados[-1].mediana_midi if resultados else None,
                    )
                    if pl:
                        resultados.append(pl)
                    else:
                        # Fallback: construir como plateau aunque sea corto
                        pl = self._construir_plateau(
                            f0_seg[inicio:fin], midi_seg[inicio:fin],
                            t_seg[inicio], t_seg[fin-1]
                        )
                        if pl:
                            resultados.append(pl)
            inicio = fin

        # Fusión de portamentos adyacentes
        if len(resultados) > 1:
            changed = True
            while changed:
                changed    = False
                fusionados = [resultados[0]]
                for curr in resultados[1:]:
                    prev       = fusionados[-1]
                    mismo_semi = abs(round(curr.mediana_midi) - round(prev.mediana_midi)) <= 1
                    es_porto   = curr.tipo == 'portamento' or prev.tipo == 'portamento'
                    contiguo   = (curr.t_inicio - prev.t_fin) < 0.05
                    if mismo_semi and es_porto and contiguo:
                        f0m  = np.array(prev.f0_series + curr.f0_series, dtype=np.float32)
                        base = prev if prev.tipo != 'portamento' else curr
                        tipo_nuevo = self._clasificar_tipo(
                            f0m, prev.t_inicio, curr.t_fin,
                            float(np.std(f0m) / (np.median(f0m) + 1e-9))
                        )
                        fusionados[-1] = Plateau(
                            t_inicio     = prev.t_inicio,
                            t_fin        = curr.t_fin,
                            mediana_f0   = base.mediana_f0,
                            mediana_midi = base.mediana_midi,
                            cents        = base.cents,
                            varianza_f0  = round(float(np.std(f0m) / (np.median(f0m) + 1e-9)), 4),
                            tipo         = tipo_nuevo,
                            nota         = base.nota,
                            octava       = base.octava,
                            f0_series    = prev.f0_series + curr.f0_series,
                        )
                        changed = True
                    else:
                        fusionados.append(curr)
                resultados = fusionados

        return resultados

    def _construir_plateau(self, f0: np.ndarray, midi: np.ndarray,
                           t_ini: float, t_fin: float) -> Plateau | None:
        if len(f0) == 0:
            return None
        mediana_f0   = float(np.median(f0))
        mediana_midi = float(np.median(midi))
        varianza     = float(np.std(f0) / (mediana_f0 + 1e-9))
        nota, octava, cents, _ = hz_a_nota(mediana_f0)
        if nota is None:
            return None
        tipo = self._clasificar_tipo(f0, t_ini, t_fin, varianza)
        return Plateau(
            t_inicio     = round(t_ini, 3),
            t_fin        = round(t_fin, 3),
            mediana_f0   = round(mediana_f0, 2),
            mediana_midi = round(mediana_midi, 2),
            cents        = round(cents, 1),
            varianza_f0  = round(varianza, 4),
            tipo         = tipo,
            nota         = nota,
            octava       = octava,
            f0_series    = f0.tolist(),
        )

    def _construir_portamento(self, f0: np.ndarray, midi: np.ndarray,
                               t_ini: float, t_fin: float,
                               prev_midi: float | None = None) -> Plateau | None:
        if len(f0) < 2:
            return None
        dur_ms = (t_fin - t_ini) * 1000.0
        if dur_ms < PORTAMENTO_DUR_MIN_MS:
            return None
        mediana_f0   = float(np.median(f0))
        mediana_midi = float(np.median(midi))
        if prev_midi is not None:
            salto = abs(mediana_midi - prev_midi)
            if salto < PORTAMENTO_SALTO_MIN or salto > PORTAMENTO_SALTO_MAX:
                return None
        if len(midi) >= 3:
            diffs     = np.diff(midi)
            n_pos     = np.sum(diffs > 0)
            n_neg     = np.sum(diffs < 0)
            n_total   = len(diffs)
            monotonia = max(n_pos, n_neg) / (n_total + 1e-9)
            if monotonia < PORTAMENTO_MONOTONIA:
                return None
        nota, octava, cents, _ = hz_a_nota(mediana_f0)
        if nota is None:
            return None
        return Plateau(
            t_inicio     = round(t_ini, 3),
            t_fin        = round(t_fin, 3),
            mediana_f0   = round(mediana_f0, 2),
            mediana_midi = round(mediana_midi, 2),
            cents        = round(cents, 1),
            varianza_f0  = round(float(np.std(f0) / (mediana_f0 + 1e-9)), 4),
            tipo         = "portamento",
            nota         = nota,
            octava       = octava,
            f0_series    = f0.tolist(),
        )

    def _clasificar_tipo(self, f0: np.ndarray, t_ini: float, t_fin: float,
                          varianza: float) -> str:
        dur = t_fin - t_ini
        if dur < DUR_PLATEAU_MS / 1000.0 * 2:
            return "plateau"
        if len(f0) >= 8:
            try:
                fft_f0 = np.abs(np.fft.rfft(f0 - np.mean(f0)))
                freqs  = np.fft.rfftfreq(len(f0), d=dur/len(f0))
                mask   = (freqs >= VIBRATO_HZ_MIN) & (freqs <= VIBRATO_HZ_MAX)
                if mask.sum() > 0:
                    pot_vibrato = np.max(fft_f0[mask])
                    pot_total   = np.sum(fft_f0) + 1e-9
                    if pot_vibrato / pot_total > 0.30:
                        ciclos = (VIBRATO_HZ_MIN + VIBRATO_HZ_MAX) / 2 * dur
                        if ciclos >= VIBRATO_MIN_CICLOS:
                            return "vibrato"
            except Exception:
                pass
        if varianza > 0.05:
            return "inestable"
        return "plateau"


# ============================================================================
# CLASIFICACIÓN DE ARREGLOS
# ============================================================================

def _clasificar_subtipo_arreglo(prev: Plateau | None, curr: Plateau,
                                  next_: Plateau | None, beat_s: float) -> str:
    dur = curr.t_fin - curr.t_inicio

    # Ornamento: muy corto, entre dos notas más largas
    if dur < beat_s * 0.5:
        if prev and next_:
            dur_prev = prev.t_fin - prev.t_inicio
            dur_next = next_.t_fin - next_.t_inicio
            if dur_prev > dur * 2 and dur_next > dur * 2:
                return "ornamento"

    # Appoggiatura: corto que resuelve (salta y cae)
    if dur < beat_s and next_:
        salto = abs(curr.mediana_midi - next_.mediana_midi)
        if 1 <= salto <= 2:
            return "appoggiatura"

    # Melisma: rango estrecho pero muchos plateaus cortos (detectado en contexto)
    if dur < beat_s * 0.75:
        return "melisma"

    return "arreglo_undefined"


def _marcar_arreglos(plateaus: list[Plateau], beat_s: float = 0.5) -> list[Plateau]:
    """Clasifica subtipos en plateaus fusionados."""
    for i, p in enumerate(plateaus):
        if p.fusionado:
            prev  = plateaus[i-1] if i > 0 else None
            next_ = plateaus[i+1] if i < len(plateaus)-1 else None
            p.subtipo_arreglo = _clasificar_subtipo_arreglo(prev, p, next_, beat_s)
    return plateaus


# ============================================================================
# SIMPLIFICACIÓN
# ============================================================================

def _simplificar_referencia(plateaus: list[Plateau],
                             beat_s: float = 0.5) -> list[Plateau]:
    if len(plateaus) < 2:
        return plateaus

    # Paso 1: fusionar mismo semitono exacto con gap < 20ms
    changed = True
    while changed:
        changed    = False
        fusionados = [plateaus[0]]
        for curr in plateaus[1:]:
            prev     = fusionados[-1]
            mismo    = round(curr.mediana_midi) == round(prev.mediana_midi)
            contiguo = (curr.t_inicio - prev.t_fin) < 0.020
            if mismo and contiguo:
                f0m = np.array(prev.f0_series + curr.f0_series, dtype=np.float32)
                fusionados[-1] = Plateau(
                    t_inicio     = prev.t_inicio,
                    t_fin        = curr.t_fin,
                    mediana_f0   = prev.mediana_f0,
                    mediana_midi = prev.mediana_midi,
                    cents        = prev.cents,
                    varianza_f0  = round(float(np.std(f0m) / (np.median(f0m) + 1e-9)), 4),
                    tipo         = prev.tipo,
                    nota         = prev.nota,
                    octava       = prev.octava,
                    f0_series    = prev.f0_series + curr.f0_series,
                    fusionado    = True,
                )
                changed = True
            else:
                fusionados.append(curr)
        plateaus = fusionados

    # Paso 2: colapsar ornamentación adyacente
    fusionados = [plateaus[0]]
    for curr in plateaus[1:]:
        prev      = fusionados[-1]
        adyacente = abs(round(curr.mediana_midi) - round(prev.mediana_midi)) <= 1
        contiguo  = (curr.t_inicio - prev.t_fin) < 0.050
        if adyacente and contiguo:
            dur_prev = prev.t_fin - prev.t_inicio
            dur_curr = curr.t_fin - curr.t_inicio
            base     = prev if dur_prev >= dur_curr else curr
            f0m      = np.array(prev.f0_series + curr.f0_series, dtype=np.float32)
            fusionados[-1] = Plateau(
                t_inicio     = prev.t_inicio,
                t_fin        = curr.t_fin,
                mediana_f0   = base.mediana_f0,
                mediana_midi = base.mediana_midi,
                cents        = base.cents,
                varianza_f0  = round(float(np.std(f0m) / (np.median(f0m) + 1e-9)), 4),
                tipo         = base.tipo,
                nota         = base.nota,
                octava       = base.octava,
                f0_series    = prev.f0_series + curr.f0_series,
                fusionado    = True,
            )
        else:
            fusionados.append(curr)
    plateaus = fusionados

    return _marcar_arreglos(plateaus, beat_s)


def simplificar_plateaus(plateaus: list, gap_max_s: float = 0.020,
                          beat_s: float = 0.5) -> list:
    """Fusión post-detección para grabación en tiempo real."""
    if len(plateaus) < 2:
        return plateaus
    changed = True
    while changed:
        changed    = False
        fusionados = [plateaus[0]]
        for curr in plateaus[1:]:
            prev     = fusionados[-1]
            mismo    = round(curr.mediana_midi) == round(prev.mediana_midi)
            contiguo = (curr.t_inicio - prev.t_fin) < gap_max_s
            # Fusión plateau+plateau mismo semitono aunque gap sea mayor
            mismo_tipo_plateau = (prev.tipo in ("plateau","vibrato") and
                                  curr.tipo in ("plateau","vibrato") and
                                  round(curr.mediana_midi) == round(prev.mediana_midi) and
                                  (curr.t_inicio - prev.t_fin) < 0.150)
            if mismo and contiguo or mismo_tipo_plateau:
                f0m = np.array(prev.f0_series + curr.f0_series, dtype=np.float32)
                fusionados[-1] = Plateau(
                    t_inicio     = prev.t_inicio,
                    t_fin        = curr.t_fin,
                    mediana_f0   = prev.mediana_f0,
                    mediana_midi = prev.mediana_midi,
                    cents        = prev.cents,
                    varianza_f0  = round(float(np.std(f0m) / (np.median(f0m) + 1e-9)), 4),
                    tipo         = prev.tipo,
                    nota         = prev.nota,
                    octava       = prev.octava,
                    f0_series    = prev.f0_series + curr.f0_series,
                    fusionado    = True,
                )
                changed = True
            else:
                fusionados.append(curr)
        plateaus = fusionados
    return _marcar_arreglos(plateaus, beat_s)


# ============================================================================
# ANALIZADOR DE FRASES
# ============================================================================

def frase_a_dict(frase: "Frase") -> dict:
    return {
        "idx"      : frase.idx,
        "t_inicio" : frase.t_inicio,
        "t_fin"    : frase.t_fin,
        "cents_med": frase.cents_med,
        "estab_med": frase.estab_med,
        "cal"      : frase.cal,
        "escala"   : frase.escala,
        "score"    : frase.score,
        "feedback" : frase.feedback,
        "plateaus" : [
            {
                "t_inicio"      : p.t_inicio,
                "t_fin"         : p.t_fin,
                "mediana_midi"  : p.mediana_midi,
                "cents"         : p.cents,
                "varianza_f0"   : p.varianza_f0,
                "tipo"          : p.tipo,
                "nota"          : p.nota,
                "octava"        : p.octava,
                "f0_series"     : p.f0_series,
                "fusionado"     : p.fusionado,
                "subtipo_arreglo": p.subtipo_arreglo,
            }
            for p in frase.plateaus
        ],
    }


class AnalizadorFrase:

    def __init__(self):
        self.detector = DetectorPlateau()

    def analizar(self, audio: np.ndarray, idx: int,
                t_inicio: float, t_fin: float) -> Frase | None:
        if len(audio) < int(SAMPLE_RATE * 0.1):
            return None

        f0, voiced = detectar_f0(audio)
        tiempos    = f0_a_tiempos(len(f0)) + t_inicio
        plateaus   = self.detector.detectar(f0, voiced, tiempos)

        if not plateaus:
            return None

        cents_vals = [abs(p.cents) for p in plateaus if p.tipo in ("plateau","vibrato")]
        estab_vals = [p.varianza_f0 for p in plateaus if p.tipo in ("plateau","vibrato")]

        cents_med = float(np.mean(cents_vals)) if cents_vals else 0.0
        estab_med = float(np.mean(estab_vals)) if estab_vals else 0.0

        cal = {
            "afinacion"  : calificar(cents_med,
                                     DIAG["cents_excelente"], DIAG["cents_ok"], DIAG["cents_malo"]),
            "estabilidad": calificar(estab_med,
                                     DIAG["estabilidad_ex"], DIAG["estabilidad_ok"],
                                     DIAG["estabilidad_mal"]),
        }

        midis_frase = [p.mediana_midi for p in plateaus]
        escala      = inferir_escala(midis_frase, DIAG["min_notas_escala"]) or {}
        score       = calcular_score(cents_med, estab_med)

        frase = Frase(
            idx      = idx,
            t_inicio = round(t_inicio, 2),
            t_fin    = round(t_fin, 2),
            plateaus = plateaus,
            cents_med= round(cents_med, 1),
            estab_med= round(estab_med, 4),
            cal      = cal,
            escala   = escala,
            score    = score,
        )
        frase.feedback = generar_feedback(frase)
        return frase
