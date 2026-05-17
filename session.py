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
SILENCIO_FRAMES  = 6     # frames pYIN sin voz para cerrar frase (~70ms a hop=512)
FRASE_MIN_S      = 0.3   # frases más cortas se descartan
FRASE_MAX_S      = 10.0  # corte forzado de frase larga

# ============================================================================
# SESIÓN
# ============================================================================

class Sesion:

    def __init__(self):
        self.reset()

    def reset(self):
        self.buffer            = []        # chunks para export
        self.total_muestras    = 0
        self.grabando          = False
        self.t_inicio          = None
        self.analizador        = AnalizadorFrase()
        # Estado de frases
        self._frase_buf        = []
        self._t_frase_ini      = 0.0
        self._en_frase         = False
        self._silencio_count   = 0
        self._frases           = []
        self._idx_frase        = 0
        # Buffer para F0 en tiempo real (timeline)
        self._rt_buf           = np.array([], dtype=np.float32)

    def iniciar(self):
        self.reset()
        self.grabando = True
        self.t_inicio = time.time()

    def detener(self) -> list[Frase]:
        self.grabando = False
        # Cerrar frase abierta
        if self._en_frase and self._frase_buf:
            t_actual = self.total_muestras / SAMPLE_RATE
            self._cerrar_frase(t_actual)
        return self._frases

    def procesar_chunk(self, chunk: np.ndarray) -> dict | None:
        """
        Recibe chunk float32 del WebSocket.
        Retorna estado para el cliente (timeline en tiempo real).
        """
        if not self.grabando:
            return None
        if self.total_muestras + len(chunk) > MAX_BUFFER:
            self.detener()
            return {"estado": "limite_alcanzado"}

        self.buffer.append(chunk.copy())
        self.total_muestras += len(chunk)
        t_actual = self.total_muestras / SAMPLE_RATE
        rms      = float(np.sqrt(np.mean(chunk**2)))

        if rms < 0.015:
            self._actualizar_frase(chunk, t_actual, False)
            return {
                "estado": "grabando",
                "t"     : round(t_actual, 2),
                "rms"   : round(rms, 4),
                "frases": self._idx_frase,
                "f0"    : 0.0, "midi": 0.0, "cents": 0.0,
            }

        # F0 en tiempo real con pYIN
        f0_rt = midi_rt = cents_rt = 0.0
        hay_voz = False

        if len(chunk) >= HOP_LENGTH * 2:
            try:
                t0 = time.perf_counter()
                f0_arr, voiced_arr = detectar_f0_rt(chunk)
                print(f"[pYIN] {(time.perf_counter()-t0)*1000:.1f}ms chunk={len(chunk)}")
                # Tomar último frame con voz como valor de tiempo real
                voiced_idx = np.where(voiced_arr)[0]
                if len(voiced_idx) > 0:
                    f0_rt   = float(f0_arr[voiced_idx[-1]])
                    hay_voz = f0_rt > 0
                    if hay_voz:
                        midi_rt = float(hz_a_midi(f0_rt) or 0)
                        _, _, cents_rt, _ = hz_a_nota(f0_rt)
            except Exception:
                pass

        # Detección de frases
        self._actualizar_frase(chunk, t_actual, hay_voz)

        return {
            "estado" : "grabando",
            "t"      : round(t_actual, 2),
            "rms"    : round(rms, 4),
            "frases" : self._idx_frase,
            "f0"     : round(f0_rt, 2),
            "midi"   : round(midi_rt, 2),
            "cents"  : round(cents_rt, 1),
        }

    # ── Detección de frases ──────────────────────────────────────────────────

    def _actualizar_frase(self, chunk: np.ndarray, t_actual: float, hay_voz: bool):
        if hay_voz:
            self._silencio_count = 0
            if not self._en_frase:
                self._en_frase    = True
                self._t_frase_ini = t_actual
                self._frase_buf   = []
            self._frase_buf.append(chunk)
            # Corte forzado si frase excede máximo
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
