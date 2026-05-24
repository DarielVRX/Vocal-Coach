"""
SESSION — Grabación y detección de frases en tiempo real
=========================================================
voiced_flag de pYIN reemplaza CalibradorSilencio.
Frases se detectan por gaps de silencio entre segmentos de voz.
"""

import time
import numpy as np
from collections import deque

from pipeline import SAMPLE_RATE, HOP_LENGTH, detectar_f0, detectar_f0_rt, hz_a_midi, hz_a_nota, F0_MIN
from analyzer import AnalizadorFrase, Frase, simplificar_plateaus

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

MAX_RECORD_S     = 300
MAX_BUFFER       = SAMPLE_RATE * MAX_RECORD_S
SILENCIO_FRAMES  = 12
FRASE_MIN_S      = 0.3
FRASE_MAX_S      = 10.0
RMS_SILENCIO     = 0.008   # por debajo → skip YIN
RMS_ZONA_GRIS    = 0.030   # zona gris: YIN corre pero filtramos spikes

# Rango vocal humano razonable (MIDI)
MIDI_VOZ_MIN = 36   # C2
MIDI_VOZ_MAX = 81   # A5

# ============================================================================
# SESIÓN
# ============================================================================

class Sesion:

    def __init__(self):
        self.reset()

    def reset(self):
        self.buffer            = []
        self.total_muestras    = 0
        self.grabando          = False
        self.t_inicio          = None
        self.analizador        = AnalizadorFrase()
        self._frase_buf        = []
        self._t_frase_ini      = 0.0
        self._en_frase         = False
        self._silencio_count   = 0
        self._frases           = []
        self._idx_frase        = 0
        self._rt_buf           = np.array([], dtype=np.float32)
        # Historial de midi reciente para filtro de spikes
        self._midi_historia    = deque(maxlen=8)

    def iniciar(self):
        self.reset()
        self.grabando = True
        self.t_inicio = time.time()

    def detener(self) -> list[Frase]:
        self.grabando = False
        if self._en_frase and self._frase_buf:
            t_actual = self.total_muestras / SAMPLE_RATE
            self._cerrar_frase(t_actual)
        return self._frases

    def procesar_chunk(self, chunk: np.ndarray) -> dict | None:
        if not self.grabando:
            return None
        if self.total_muestras + len(chunk) > MAX_BUFFER:
            self.detener()
            return {"estado": "limite_alcanzado"}

        self.buffer.append(chunk.copy())
        self.total_muestras += len(chunk)
        t_actual = self.total_muestras / SAMPLE_RATE
        rms      = float(np.sqrt(np.mean(chunk**2)))

        # Skip silencio completo
        if rms < RMS_SILENCIO:
            self._actualizar_frase(chunk, t_actual, False)
            return {
                "estado": "grabando",
                "t"     : round(t_actual, 2),
                "rms"   : round(rms, 4),
                "frases": self._idx_frase,
                "f0"    : 0.0, "midi": 0.0, "cents": 0.0,
            }

        f0_rt = midi_rt = cents_rt = 0.0
        hay_voz = False

        if len(chunk) >= HOP_LENGTH * 2:
            try:
                f0_arr, voiced_arr = detectar_f0_rt(chunk)
                voiced_idx = np.where(voiced_arr)[0]
                if len(voiced_idx) > 0:
                    f0_rt   = float(f0_arr[voiced_idx[-1]])
                    hay_voz = f0_rt > 0
                    if hay_voz:
                        midi_raw = float(hz_a_midi(f0_rt) or 0)
                        # Filtro de spikes: rango vocal + consistencia con historia
                        if MIDI_VOZ_MIN <= midi_raw <= MIDI_VOZ_MAX:
                            if rms >= RMS_ZONA_GRIS or self._es_consistente(midi_raw):
                                midi_rt = midi_raw
                                _, _, cents_rt, _ = hz_a_nota(f0_rt)
                                self._midi_historia.append(midi_rt)
                            else:
                                hay_voz = False
                        else:
                            hay_voz = False
            except Exception:
                pass

        self._actualizar_frase(chunk, t_actual, hay_voz)

        return {
            "estado": "grabando",
            "t"     : round(t_actual, 2),
            "rms"   : round(rms, 4),
            "frases": self._idx_frase,
            "f0"    : round(f0_rt, 2),
            "midi"  : round(midi_rt, 2),
            "cents" : round(cents_rt, 1),
        }

    def _es_consistente(self, midi: float) -> bool:
        """True si midi no es un salto de octava respecto al historial reciente."""
        if len(self._midi_historia) < 3:
            return True
        mediana = float(np.median(list(self._midi_historia)))
        return abs(midi - mediana) < 12  # menos de una octava de diferencia

    # ── Detección de frases ──────────────────────────────────────────────────

    def _actualizar_frase(self, chunk: np.ndarray, t_actual: float, hay_voz: bool):
        if hay_voz:
            self._silencio_count = 0
            if not self._en_frase:
                self._en_frase    = True
                self._t_frase_ini = t_actual
                self._frase_buf   = []
            self._frase_buf.append(chunk)
            if t_actual - self._t_frase_ini >= FRASE_MAX_S:
                self._cerrar_frase(t_actual)
        else:
            if self._en_frase:
                self._frase_buf.append(chunk)
                self._silencio_count += 1
                if self._silencio_count >= SILENCIO_FRAMES:
                    self._cerrar_frase(t_actual)

    def _cerrar_frase(self, t_fin: float):
        try:
            if not self._frase_buf:
                return
            audio = np.concatenate(self._frase_buf)
            dur   = len(audio) / SAMPLE_RATE
            if dur < FRASE_MIN_S:
                self._resetear_frase()
                return
            self._idx_frase += 1
            frase = self.analizador.analizar(audio, self._idx_frase,
                                             self._t_frase_ini, t_fin)
            if frase:
                frase.plateaus = simplificar_plateaus(frase.plateaus)
                self._frases.append(frase)
        except Exception as e:
            import traceback
            print(f"[SESSION] _cerrar_frase: {e}\n{traceback.format_exc()}")
        finally:
            self._resetear_frase()

    def _resetear_frase(self):
        self._en_frase       = False
        self._frase_buf      = []
        self._silencio_count = 0

    # ── Acceso ───────────────────────────────────────────────────────────────

    @property
    def frases(self) -> list[Frase]:
        return self._frases

    @property
    def audio_completo(self) -> np.ndarray | None:
        if not self.buffer:
            return None
        return np.concatenate(self.buffer).astype(np.float32)

    @property
    def duracion(self) -> float:
        return self.total_muestras / SAMPLE_RATE
