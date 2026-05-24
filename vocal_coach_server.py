"""
VOCAL COACH SERVER v3
=====================
Router delgado. Lógica en módulos especializados.
"""

import asyncio
import json
import os
import traceback
import uuid

import librosa
import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from analyzer import DetectorPlateau, Plateau
from diagnostico import generar_diagnostico
try:
    from isolator_service import get_isolator
    ISOLATOR_AVAILABLE = True
except ImportError:
    ISOLATOR_AVAILABLE = False
    def get_isolator(): return None
from pipeline import detectar_f0, f0_a_tiempos, hz_a_midi, hz_a_nota
from session import Sesion
from session_export import get_exporter
from upload_handler import guardar_upload

# ============================================================================
# CONFIG
# ============================================================================

SAMPLE_RATE = 44100
STEMS_DIR   = "./stems"
EXPORT_DIR  = "./exports"
HTML_PATH   = os.path.join(os.path.dirname(__file__), "index.html")

MODULES = {
    "coach"    : True,
    "timeline" : True,
    "isolator" : True,
    "karaoke"  : True,
}

_whisper_model = None
def set_whisper_model(model):
    global _whisper_model
    _whisper_model = model

# ============================================================================
# APP
# ============================================================================

app    = FastAPI(title="Vocal Coach v3")
sesion = Sesion()

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="."), name="static")

# ============================================================================
# HELPERS
# ============================================================================

def safe_json(obj):
    if isinstance(obj, dict):        return {k: safe_json(v) for k, v in obj.items()}
    if isinstance(obj, list):        return [safe_json(v) for v in obj]
    if isinstance(obj, np.bool_):    return bool(obj)
    if isinstance(obj, np.integer):  return int(obj)
    if isinstance(obj, np.floating): return float(obj)
    if isinstance(obj, np.ndarray):  return obj.tolist()
    return obj

def log(mod, nivel, msg):
    import time
    print(f"[{time.strftime('%H:%M:%S')}][{nivel}][{mod}] {msg}")

def buscar_archivo(dirs, filename):
    for d in dirs:
        for root, _, files in os.walk(d):
            if filename in files:
                return os.path.join(root, filename)
    return None

def file_response(path, filename):
    return FileResponse(path, media_type="audio/wav",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# ============================================================================
# TAREAS BACKGROUND
# ============================================================================

_isolate_tasks: dict = {}
_analyze_tasks: dict = {}

async def _run_isolate(task_id: str, file_path: str):
    _isolate_tasks[task_id] = {"status": "processing", "progress": 0, "message": "Iniciando..."}
    try:
        def cb(etapa, pct, msg):
            _isolate_tasks[task_id].update({"progress": pct, "message": msg, "etapa": etapa})
        result = get_isolator().separar(file_path, progress_callback=cb)
        if result:
            _isolate_tasks[task_id].update({
                "status": "completed", "progress": 100, "message": "Completado ✓",
                "result": {"vocals": result["vocals"], "accompaniment": result["accompaniment"]}
            })
        else:
            _isolate_tasks[task_id].update({"status": "failed", "message": "Separación falló"})
    except Exception as e:
        log("ISOLATOR", "ERROR", str(e))
        _isolate_tasks[task_id].update({"status": "failed", "message": str(e)})

def _simplificar_referencia(plateaus, beat_s=0.5):
    from analyzer import _simplificar_referencia as _sr
    return _sr(plateaus, beat_s)

async def _run_analyze(task_id: str, vocals_path: str):
    _analyze_tasks[task_id] = {"status": "processing", "progress": 0, "message": "Cargando audio..."}
    try:
        audio, sr = sf.read(vocals_path, dtype="float32")
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        if sr != SAMPLE_RATE and sr != 16000:
            from scipy import signal
            audio = signal.resample(audio, int(len(audio) * SAMPLE_RATE / sr))
            sr = SAMPLE_RATE

        _analyze_tasks[task_id].update({"progress": 5, "message": "Detectando tempo..."})
        tempo, _ = librosa.beat.beat_track(y=audio, sr=sr)
        bpm      = round(float(np.array(tempo).item()), 1)
        beat_s   = 60.0 / bpm
        log("KARAOKE", "INFO", f"Tempo: {bpm} BPM")

        _analyze_tasks[task_id].update({"progress": 10, "message": "Analizando F0..."})

        seg_sz = sr * 30
        n_segs = max(1, len(audio) // seg_sz + 1)
        puntos = []

        for i in range(n_segs):
            seg = audio[i*seg_sz:(i+1)*seg_sz]
            if len(seg) < sr * 0.5:
                continue
            f0, voiced = detectar_f0(seg, sr=sr)
            tiempos    = f0_a_tiempos(len(f0), sr=sr) + i * 30.0
            for j, (f, v) in enumerate(zip(f0, voiced)):
                if not v or f <= 0: continue
                midi = hz_a_midi(f)
                if midi is None: continue
                _, _, cents, _ = hz_a_nota(f)
                puntos.append({
                    "t"    : round(float(tiempos[j]), 3),
                    "midi" : round(float(midi), 2),
                    "cents": round(float(cents), 1),
                })
            pct = min(90, 10 + int((i+1) / n_segs * 75))
            _analyze_tasks[task_id].update({"progress": pct, "message": f"Segmento {i+1}/{n_segs}..."})
            await asyncio.sleep(0)

        _analyze_tasks[task_id].update({"progress": 92, "message": "Detectando plateaus..."})
        plateaus_ref = []
        if puntos:
            midis          = np.array([p["midi"] for p in puntos], dtype=np.float32)
            midis_voiced   = midis[midis > 0]
            mediana_global = float(np.median(midis_voiced)) if len(midis_voiced) > 0 else float(np.median(midis))
            puntos         = [p for p in puntos if abs(p["midi"] - mediana_global) < 18]
            f0_ref     = np.array([440.0 * 2**((p["midi"] - 69) / 12) for p in puntos], dtype=np.float32)
            t_ref      = np.array([p["t"] for p in puntos], dtype=np.float32)
            voiced_ref = f0_ref > 0
            n_frames_total = int(len(audio) / 512) + 1
            pct_voiced     = len(puntos) / max(1, n_frames_total)
            dur_min_ms     = max(80.0, 150.0 - pct_voiced * 100.0)
            cents_thr      = max(25.0, 35.0 - pct_voiced * 15.0)
            log("KARAOKE", "INFO", f"Constantes: DUR={dur_min_ms:.0f}ms CENTS={cents_thr:.1f}¢ pct_voiced={pct_voiced:.2f}")
            det          = DetectorPlateau(dur_min_ms=dur_min_ms, cents_thr=cents_thr)
            pls          = det.detectar(f0_ref, voiced_ref, t_ref)
            pls          = _simplificar_referencia(pls, beat_s)
            plateaus_ref = [
                {
                    "t_inicio"       : p.t_inicio,
                    "t_fin"          : p.t_fin,
                    "mediana_midi"   : p.mediana_midi,
                    "cents"          : p.cents,
                    "tipo"           : p.tipo,
                    "fusionado"      : p.fusionado,
                    "subtipo_arreglo": p.subtipo_arreglo,
                }
                for p in pls
                if p.tipo != "portamento"
            ]

        log("KARAOKE", "INFO", f"Análisis: {len(puntos)} puntos, {len(plateaus_ref)} plateaus, {bpm} BPM")
        _analyze_tasks[task_id].update({
            "status"      : "completed",
            "progress"    : 100,
            "message"     : f"{len(puntos)} puntos, {len(plateaus_ref)} plateaus ✓",
            "puntos"      : puntos,
            "plateaus_ref": plateaus_ref,
            "bpm"         : bpm,
            "beat_s"      : beat_s,
        })

    except Exception as e:
        log("KARAOKE", "ERROR", f"_run_analyze: {e}\n{traceback.format_exc()}")
        _analyze_tasks[task_id].update({"status": "failed", "message": str(e)})

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    if os.path.exists(HTML_PATH):
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>index.html no encontrado</h1>")

@app.get("/modules")
async def get_modules():
    return MODULES

@app.post("/upload/karaoke")
async def upload_karaoke(file: UploadFile = File(...)):
    try:
        path = await guardar_upload(file)
        return {"success": True, "path": path}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/isolate")
async def isolate_track(request: dict):
    if not ISOLATOR_AVAILABLE:
        return {"success": False, "error": "Separación no disponible en este entorno"}
    try:
        file_path = request.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "error": "Archivo no encontrado"}
        task_id = str(uuid.uuid4())
        asyncio.create_task(_run_isolate(task_id, file_path))
        return {"success": True, "task_id": task_id}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/isolate/progress/{task_id}")
async def isolate_progress(task_id: str):
    return _isolate_tasks.get(task_id, {"error": "Tarea no encontrada"})

@app.get("/stems/{filename}")
async def serve_stem(filename: str):
    path = buscar_archivo([STEMS_DIR], filename)
    if not path: return {"error": "Stem no encontrado"}
    return file_response(path, filename)

@app.get("/exports/{filename}")
async def serve_export(filename: str):
    path = buscar_archivo([EXPORT_DIR], filename)
    if not path: return {"error": "Export no encontrado"}
    return file_response(path, filename)

@app.get("/exports/pdf/{filename}")
async def serve_export_pdf(filename: str):
    path = buscar_archivo([EXPORT_DIR], filename)
    if not path: return {"error": "PDF no encontrado"}
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.post("/karaoke/analyze")
async def karaoke_analyze(request: dict):
    try:
        vocals_path = request.get("vocals_path")
        if not vocals_path or not os.path.exists(vocals_path):
            return {"success": False, "error": "Archivo no encontrado"}
        task_id = str(uuid.uuid4())
        log("KARAOKE", "INFO", f"Analyze task {task_id} iniciada")
        asyncio.create_task(_run_analyze(task_id, vocals_path))
        return {"success": True, "task_id": task_id}
    except Exception as e:
        log("KARAOKE", "ERROR", f"karaoke_analyze: {e}\n{traceback.format_exc()}")
        return {"success": False, "error": str(e)}

@app.get("/karaoke/analyze/progress/{task_id}")
async def analyze_progress(task_id: str):
    return safe_json(_analyze_tasks.get(task_id, {"error": "Tarea no encontrada"}))

@app.post("/karaoke/transcribe")
async def karaoke_transcribe(request: dict):
    try:
        vocals_path = request.get("vocals_path")
        if not vocals_path or not os.path.exists(vocals_path):
            return {"success": False, "error": "Archivo no encontrado"}
        if _whisper_model is None:
            return {"success": False, "error": "Modelo Whisper no inyectado"}
        result   = _whisper_model.transcribe(vocals_path, word_timestamps=True,
                                             language=None, verbose=False)
        palabras = [{"word": w.word.strip(),
                     "start": round(float(w.start), 3),
                     "end"  : round(float(w.end), 3)}
                    for seg in result.segments for w in seg.words]
        return {"success": True, "palabras": palabras, "idioma": result.language}
    except Exception as e:
        log("WHISPER", "ERROR", str(e))
        return {"success": False, "error": str(e)}

@app.post("/export/session")
async def export_session(request: dict):
    try:
        audio = sesion.audio_completo
        if audio is None:
            return {"error": "No hay sesión para exportar"}

        karaoke_audio = None
        kp = request.get("karaoke_path")
        if kp and os.path.exists(kp):
            ka, sr = sf.read(kp, dtype="float32")
            if ka.ndim > 1: ka = np.mean(ka, axis=1)
            if sr != SAMPLE_RATE:
                from scipy import signal
                ka = signal.resample(ka, int(len(ka) * SAMPLE_RATE / sr))
            karaoke_audio = ka

        plateaus_ref = request.get("plateaus_ref", [])

        paths = get_exporter().export(
            session_audio = audio,
            karaoke_audio = karaoke_audio,
            session_id    = request.get("session_id"),
            frases        = sesion.frases,
            plateaus_ref  = plateaus_ref,
            bpm           = request.get("bpm"),
        )
        if paths is None: return {"error": "Exportación falló"}
        return {"success": True, "files": paths}
    except Exception as e:
        log("EXPORT", "ERROR", f"{e}\n{traceback.format_exc()}")
        return {"error": str(e)}

# ============================================================================
# WEBSOCKET
# ============================================================================

@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket):
    await ws.accept()
    log("WS", "INFO", "Cliente conectado")
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if "text" in msg:
                cmd = json.loads(msg["text"]).get("cmd")
                if cmd == "start":
                    sesion.iniciar()
                    await ws.send_text(json.dumps({"evento": "grabacion_iniciada"}))
                elif cmd == "stop":
                    data_cmd  = json.loads(msg["text"])
                    segmentos = data_cmd.get("segmentos", [])
                    frases    = sesion.detener()
                    resultado = generar_diagnostico(frases, segmentos=segmentos)
                    await ws.send_text(json.dumps(safe_json(
                        {"evento": "diagnostico", "data": resultado})))
            elif "bytes" in msg:
                chunk = np.frombuffer(msg["bytes"], dtype=np.float32)
                if len(chunk) == 0: continue
                estado = sesion.procesar_chunk(chunk)
                if estado:
                    # Exponer score y feedback de última frase cerrada
                    if sesion.frases:
                        uf = sesion.frases[-1]
                        estado["score_frase"]    = uf.score
                        estado["feedback_frase"] = uf.feedback
                    await ws.send_text(json.dumps(safe_json(estado)))
                    await asyncio.sleep(0)
    except WebSocketDisconnect:
        log("WS", "INFO", "Desconectado")
    except Exception as e:
        log("WS", "ERROR", f"{e}\n{traceback.format_exc()}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  VOCAL COACH SERVER v3")
    print(f"  Módulos: {[k for k,v in MODULES.items() if v]}")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), log_level="warning",
                ws_ping_interval=None, ws_ping_timeout=None,
                h11_max_incomplete_event_size=200*1024*1024)
