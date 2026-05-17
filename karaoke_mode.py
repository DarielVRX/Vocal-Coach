"""
KARAOKE MODE
============
Graba micrófono sincronizado con pista instrumental.
La reproducción del instrumental la maneja el frontend (AudioContext).
Este módulo solo gestiona grabación + mezcla final.
"""

import numpy as np
import soundfile as sf
import time

class KaraokeSession:

    def __init__(self, instrumental_path, sample_rate=44100):
        self.sample_rate        = sample_rate
        self.instrumental_path  = instrumental_path

        # Cargar instrumental para mezcla final
        self.instrumental, sr = sf.read(instrumental_path, dtype='float32')
        if len(self.instrumental.shape) > 1:
            self.instrumental = np.mean(self.instrumental, axis=1)

        if sr != sample_rate:
            from scipy import signal
            num_samples       = int(len(self.instrumental) * sample_rate / sr)
            self.instrumental = signal.resample(self.instrumental, num_samples)

        self.duracion  = len(self.instrumental) / sample_rate
        self.t_inicio  = None
        self.mic_buffer = []  # [(timestamp, chunk)]

        print(f"[KARAOKE] Pista cargada: {self.duracion:.1f}s")

    def iniciar(self):
        self.t_inicio   = time.time()
        self.mic_buffer = []
        print("[KARAOKE] Sesión iniciada")

    def agregar_mic_chunk(self, chunk):
        if not self.t_inicio:
            return
        t_chunk = time.time() - self.t_inicio
        self.mic_buffer.append((t_chunk, chunk.copy()))

    def detener(self):
        duracion = time.time() - self.t_inicio if self.t_inicio else 0
        print(f"[KARAOKE] Detenido: {duracion:.1f}s")
        return self._generar_mezcla()

    def _generar_mezcla(self):
        try:
            if not self.mic_buffer:
                print("[KARAOKE] Sin audio de micrófono")
                return None

            max_t       = max(t for t, _ in self.mic_buffer)
            max_samples = int((max_t + 2.0) * self.sample_rate)
            vocals      = np.zeros(max_samples, dtype=np.float32)

            for t_chunk, chunk in self.mic_buffer:
                pos     = int(t_chunk * self.sample_rate)
                end_pos = pos + len(chunk)
                if end_pos <= max_samples:
                    vocals[pos:end_pos] = chunk
                else:
                    available = max_samples - pos
                    if available > 0:
                        vocals[pos:max_samples] = chunk[:available]

            inst_aligned = np.zeros(max_samples, dtype=np.float32)
            copy_len     = min(len(self.instrumental), max_samples)
            inst_aligned[:copy_len] = self.instrumental[:copy_len]

            mix  = vocals * 1.0 + inst_aligned * 0.6
            peak = np.max(np.abs(mix))
            if peak > 0.99:
                mix = mix * (0.99 / peak)

            print(f"[KARAOKE] Mezcla generada: {len(vocals)/self.sample_rate:.1f}s")
            return {
                'vocals'       : vocals,
                'instrumental' : inst_aligned,
                'mix'          : mix,
                'sample_rate'  : self.sample_rate,
            }

        except Exception as e:
            print(f"[KARAOKE ERROR] _generar_mezcla: {e}")
            import traceback
            traceback.print_exc()
            return None


# Singleton
_karaoke_session = None

def get_karaoke_session():
    return _karaoke_session

def crear_sesion_karaoke(instrumental_path):
    global _karaoke_session
    _karaoke_session = KaraokeSession(instrumental_path)
    return _karaoke_session

def detener_sesion_karaoke():
    global _karaoke_session
    if _karaoke_session:
        result           = _karaoke_session.detener()
        _karaoke_session = None
        return result
    return None
