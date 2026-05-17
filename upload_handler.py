"""
UPLOAD HANDLER
==============
Maneja uploads de archivos de audio.
Límite: 100MB — necesario para stems WAV sin comprimir de Demucs (~33MB vocals).
"""

import os
import time
from fastapi import UploadFile, HTTPException

UPLOAD_DIR     = "./uploads"
MAX_SIZE_MB    = 100
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.flac', '.ogg'}

os.makedirs(UPLOAD_DIR, exist_ok=True)


async def guardar_upload(file: UploadFile) -> str:
    """
    Guarda archivo subido y retorna path.
    Valida tamaño y extensión.
    """
    try:
        ext = os.path.splitext(file.filename or 'file.wav')[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Formato no soportado. Usa: {ALLOWED_EXTENSIONS}"
            )

        contents = await file.read()
        size_mb  = len(contents) / (1024 * 1024)

        if len(contents) > MAX_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Archivo muy grande ({size_mb:.1f}MB). Máximo: {MAX_SIZE_MB}MB"
            )

        timestamp = int(time.time() * 1000)
        safe_name = f"{timestamp}_{file.filename or 'upload.wav'}"
        save_path = os.path.join(UPLOAD_DIR, safe_name)

        with open(save_path, 'wb') as f:
            f.write(contents)

        print(f"[UPLOAD] {safe_name} ({size_mb:.1f}MB)")
        return save_path

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error guardando archivo: {e}")
