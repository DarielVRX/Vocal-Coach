"""
ISOLATOR SERVICE - Demucs
=========================
Separación de fuentes con Demucs htdemucs.
Guarda únicamente vocals.wav y accompaniment.wav.
Producción: llamado desde vocal_coach_server.
Local: reemplazado por notebook Kaggle.
"""

import os
import time
import shutil

import torch
import torchaudio

try:
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    DEMUCS_AVAILABLE = True
except ImportError:
    DEMUCS_AVAILABLE = False
    print("[ISOLATOR] Demucs no disponible")

STEMS_DIR = "./stems"
os.makedirs(STEMS_DIR, exist_ok=True)


class IsolatorService:

    def __init__(self):
        if not DEMUCS_AVAILABLE:
            raise ImportError("Demucs no está instalado")
        print("[ISOLATOR] Cargando modelo Demucs...")
        self.model  = get_model("htdemucs")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)
        print(f"[ISOLATOR] Listo en {self.device}")

    def separar(self, input_path, progress_callback=None):
        # Limpiar stems anteriores
        if os.path.exists(STEMS_DIR):
            shutil.rmtree(STEMS_DIR)
        os.makedirs(STEMS_DIR, exist_ok=True)

        try:
            cb = progress_callback or (lambda *a: None)
            cb("init", 0, "Cargando audio...")

            t0      = time.time()
            wav, sr = torchaudio.load(input_path)
            duracion = wav.shape[-1] / sr
            print(f"[ISOLATOR] {os.path.basename(input_path)} — {duracion:.1f}s")

            cb("load", 10, "Audio cargado")

            if sr != self.model.samplerate:
                cb("resample", 15, f"Resampling {sr}→{self.model.samplerate}Hz...")
                wav = torchaudio.functional.resample(wav, sr, self.model.samplerate)

            cb("separate", 20, "Separando fuentes...")
            wav = wav.to(self.device)

            with torch.no_grad():
                cb("separate", 30, "Procesando...")
                # split=True: procesa en segmentos, reduce pico de VRAM
                sources = apply_model(
                    self.model, wav[None],
                    device=self.device,
                    split=True,
                    overlap=0.25,
                )[0]
                cb("separate", 70, "Reconstruyendo audio...")

            sources = sources.cpu()
            cb("save", 75, "Guardando stems...")

            filename   = os.path.splitext(os.path.basename(input_path))[0]
            output_dir = os.path.join(STEMS_DIR, filename)
            os.makedirs(output_dir, exist_ok=True)

            # htdemucs: drums=0, bass=1, other=2, vocals=3
            vocals_path = os.path.join(output_dir, "vocals.wav")
            cb("save", 80, "Guardando vocals...")
            torchaudio.save(vocals_path, sources[3], self.model.samplerate)

            accomp_path = os.path.join(output_dir, "accompaniment.wav")
            cb("save", 87, "Guardando accompaniment...")
            torchaudio.save(accomp_path,
                            sources[0] + sources[1] + sources[2],
                            self.model.samplerate)

            elapsed = time.time() - t0
            print(f"[ISOLATOR] Completado en {elapsed:.1f}s")
            cb("complete", 100, "Separación completada ✓")

            return {
                "vocals"       : vocals_path,
                "accompaniment": accomp_path,
                "duration"     : duracion,
                "sample_rate"  : self.model.samplerate,
            }

        except Exception as e:
            cb("error", 0, f"Error: {e}")
            print(f"[ISOLATOR ERROR] {e}")
            import traceback; traceback.print_exc()
            return None


# Singleton
_isolator = None

def get_isolator():
    global _isolator
    if _isolator is None:
        if not DEMUCS_AVAILABLE:
            raise ImportError("Demucs no está instalado")
        _isolator = IsolatorService()
    return _isolator
