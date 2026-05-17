# Vocal Coach

Aplicación web para práctica vocal con análisis de afinación en tiempo real, modo karaoke y diagnóstico por frase.

## Stack

- **Backend:** FastAPI + WebSocket + pYIN/YIN (librosa) + Demucs + Whisper
- **Frontend:** Canvas piano roll, silabizador karaoke, score por frase (SS→D)
- **Audio:** WO Mic (micrófono desde móvil vía WiFi) o micrófono local

---

## Instalación

```bash
git clone https://github.com/TU_USUARIO/vocal-coach
cd vocal-coach
pip install -r requirements.txt
python vocal_coach_server.py
```

Abrir en el navegador: `http://localhost:8000`

---

## Archivos de prueba — Enjambre · Estás Dormida (cover Caifanes)

Para probar el modo karaoke directamente sin separar stems:

**[⬇ Descargar stems de prueba](https://drive.google.com/file/d/1f7sKDJgmhVIHGjBFdjDVBHXkm9n8ljpC/view?usp=sharing)** — ZIP con `vocals.wav`, `accompaniment.wav` y `transcripcion.json`

Extraer el ZIP y cargar los archivos en la app desde **🎤 MODO KARAOKE → Archivos locales**.

---

## Generar stems desde cualquier canción

```bash
python setup.py --input ruta/a/cancion.mp3
```

El script instala las dependencias necesarias, separa la voz del instrumental con Demucs y transcribe la letra con Whisper.

### Requisitos previos

- Python 3.10+
- `ffmpeg` instalado y en PATH
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Mac: `brew install ffmpeg`
  - Windows: [ffmpeg.org/download](https://ffmpeg.org/download.html)
- GPU opcional — sin GPU el proceso tarda ~10-20 min en CPU

### Tiempo estimado

| Hardware | Separación | Transcripción |
|----------|-----------|---------------|
| GPU (T4) | ~2 min    | ~30s          |
| CPU      | ~15 min   | ~3 min        |

---

## Uso

### Modo libre
1. Presionar **● REC** y cantar
2. El timeline muestra afinación en tiempo real
3. Al presionar **■ STOP** se genera el diagnóstico con score por frase

### Modo karaoke
1. Cargar `vocals.wav`, `accompaniment.wav` y `transcripcion.json` en **🎤 MODO KARAOKE**
2. Presionar **✓ Usar estos archivos**
3. Presionar **● REC** — la pista instrumental arranca sincronizada
4. Al terminar, **■ STOP** genera diagnóstico comparando tu voz con la referencia

### Export
**💾 EXPORTAR** genera:
- `grabacion.wav` — tu voz cruda
- `take.wav` — mezcla voz + instrumental (modo karaoke)
- `diagnostico.pdf` — piano roll por compás con score y análisis

---

## Micrófono desde móvil (opcional)

Para usar el móvil como micrófono de mayor calidad vía WiFi:

1. Instalar [WO Mic](https://wolicheng.com/womic/) en el móvil y en el PC
2. Conectar ambos a la misma red WiFi
3. En Linux, crear el sink virtual:
   ```bash
   pactl load-module module-null-sink sink_name=womic_sink
   pactl load-module module-loopback source=womic_sink.monitor
   ```
4. Seleccionar **WO Mic** como fuente de audio en la app

---

## Debug remoto (móvil)

Para depurar desde DevTools del PC mientras grabas desde el móvil:

1. Conectar móvil por USB
2. Activar depuración USB en el móvil
3. Abrir `chrome://inspect` en Chromium del PC
4. La app corre en `http://192.168.X.X:8000`
