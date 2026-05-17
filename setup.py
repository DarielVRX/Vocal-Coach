"""
setup.py — Preparación de stems para Vocal Coach
=================================================
Uso:
    python setup.py --download              # descarga stems de prueba
    python setup.py --input cancion.mp3     # genera stems desde archivo
    python setup.py --input cancion.mp3 --no-transcribe  # sin Whisper
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ── Archivos de prueba (Enjambre · Está Dormida, cover Caifanes) ──────────────
DEMO_GDRIVE_ID  = "1f7sKDJgmhVIHGjBFdjDVBHXkm9n8ljpC"
DEMO_ZIP_NAME   = "estás_dormida_stems.zip"
OUTPUT_DIR      = Path("./stems_demo")

# ── Dependencias ──────────────────────────────────────────────────────────────
DEPS = {
    "gdown"         : "gdown",
    "demucs"        : "demucs",
    "openai-whisper": "whisper",
    "soundfile"     : "soundfile",
}


def instalar_dep(paquete: str):
    print(f"  Instalando {paquete}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", paquete])


def verificar_deps(necesita_demucs=True, necesita_whisper=True):
    print("Verificando dependencias...")
    requeridos = ["gdown"]
    if necesita_demucs:  requeridos.append("demucs")
    if necesita_whisper: requeridos.append("openai-whisper")
    requeridos.append("soundfile")

    for dep in requeridos:
        mod = DEPS[dep]
        try:
            __import__(mod)
        except ImportError:
            instalar_dep(dep)
    print("  OK\n")


def verificar_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: ffmpeg no encontrado.")
        print("  Ubuntu/Debian: sudo apt install ffmpeg")
        print("  Mac:           brew install ffmpeg")
        print("  Windows:       https://ffmpeg.org/download.html")
        sys.exit(1)


# ── Descarga demo ─────────────────────────────────────────────────────────────

def descargar_demo():
    verificar_deps(necesita_demucs=False, necesita_whisper=False)

    import gdown
    import zipfile

    OUTPUT_DIR.mkdir(exist_ok=True)
    zip_path = OUTPUT_DIR / DEMO_ZIP_NAME

    print(f"Descargando stems de prueba...")
    gdown.download(id=DEMO_GDRIVE_ID, output=str(zip_path), quiet=False)

    print(f"\nExtrayendo...")
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(OUTPUT_DIR)
    zip_path.unlink()

    archivos = list(OUTPUT_DIR.glob("*"))
    print(f"\nArchivos listos en {OUTPUT_DIR}/:")
    for f in archivos:
        size_mb = f.stat().st_size / 1024 / 1024
        print(f"  {f.name} ({size_mb:.1f} MB)")

    print("\nEn la app, ir a 🎤 MODO KARAOKE → Archivos locales y cargar cada archivo.")


# ── Separación desde archivo ──────────────────────────────────────────────────

def separar_stems(input_path: str, transcribir: bool = True):
    verificar_ffmpeg()
    verificar_deps(necesita_demucs=True, necesita_whisper=transcribir)

    input_path = Path(input_path)
    if not input_path.exists():
        print(f"ERROR: Archivo no encontrado: {input_path}")
        sys.exit(1)

    out_dir = Path("./stems") / input_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Demucs ────────────────────────────────────────────────────────────────
    print(f"\nSeparando stems con Demucs...")
    print(f"  Entrada: {input_path}")
    print(f"  Salida:  {out_dir}/")
    print(f"  (esto puede tardar varios minutos en CPU)\n")

    cmd = [
        sys.executable, "-m", "demucs",
        "--two-stems", "vocals",
        "-o", str(out_dir.parent),
        str(input_path)
    ]
    resultado = subprocess.run(cmd)
    if resultado.returncode != 0:
        print("ERROR: Demucs falló.")
        sys.exit(1)

    # Demucs genera: out_dir/htdemucs/<nombre>/{vocals,no_vocals}.wav
    demucs_out = out_dir.parent / "htdemucs" / input_path.stem
    vocals_src  = demucs_out / "vocals.wav"
    accomp_src  = demucs_out / "no_vocals.wav"

    if not vocals_src.exists():
        print(f"ERROR: No se encontró {vocals_src}")
        sys.exit(1)

    # Copiar a destino final
    import shutil
    vocals_dst  = out_dir / "vocals.wav"
    accomp_dst  = out_dir / "accompaniment.wav"
    shutil.copy2(vocals_src, vocals_dst)
    shutil.copy2(accomp_src, accomp_dst)
    print(f"  vocals.wav         → {vocals_dst}")
    print(f"  accompaniment.wav  → {accomp_dst}")

    # ── Whisper ───────────────────────────────────────────────────────────────
    trans_dst = out_dir / "transcripcion.json"
    if transcribir:
        print(f"\nTranscribiendo con Whisper...")
        import whisper
        import json

        model = whisper.load_model("base")
        result = model.transcribe(str(vocals_dst), word_timestamps=True,
                                  verbose=False)
        palabras = [
            {"word": w.word.strip(),
             "start": round(float(w.start), 3),
             "end"  : round(float(w.end), 3)}
            for seg in result["segments"]
            for w in seg.get("words", [])
        ]
        with open(trans_dst, "w", encoding="utf-8") as f:
            json.dump({"palabras": palabras, "idioma": result["language"]}, f,
                      ensure_ascii=False, indent=2)
        print(f"  transcripcion.json → {trans_dst}")
        print(f"  Idioma detectado: {result['language']}")
        print(f"  Palabras: {len(palabras)}")
    else:
        print("\nTranscripción omitida (--no-transcribe)")

    # ── Resumen ───────────────────────────────────────────────────────────────
    print(f"\nListo. Archivos en {out_dir}/:")
    for f in sorted(out_dir.iterdir()):
        size_mb = f.stat().st_size / 1024 / 1024
        print(f"  {f.name} ({size_mb:.1f} MB)")
    print("\nEn la app, ir a 🎤 MODO KARAOKE → Archivos locales y cargar cada archivo.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Preparación de stems para Vocal Coach"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--download", action="store_true",
                       help="Descarga stems de prueba (Enjambre · Está Dormida)")
    group.add_argument("--input", metavar="ARCHIVO",
                       help="Ruta a archivo de audio para separar stems")
    parser.add_argument("--no-transcribe", action="store_true",
                        help="Omitir transcripción con Whisper")

    args = parser.parse_args()

    if args.download:
        descargar_demo()
    else:
        separar_stems(args.input, transcribir=not args.no_transcribe)


if __name__ == "__main__":
    main()
