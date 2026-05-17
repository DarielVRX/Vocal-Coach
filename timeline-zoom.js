/**
 * TIMELINE-ZOOM.JS — Calibración dinámica y zoom inteligente
 * ===========================================================
 * Fases:
 *   calibrando  — acumula puntos, ajusta centro suavemente
 *   estable     — centro fijo, zoom normal (SEMI_NORMAL)
 *   zoomout     — punto fuera de rango, expande a SEMI_OUT
 *                 si persiste > RECALIB_S → recalibrar
 *
 * Con referencia cargada: salta calibración, usa mediana de plateausRef.
 */

const SEMI_NORMAL   = 12;   // semitonos visibles en estado estable
const SEMI_OUT      = 20;   // semitonos visibles en zoom out
const MARGEN_SEMI   = 2;    // margen antes de trigger zoom out
const CONFIANZA_CV  = 0.12; // coeficiente de variación para declarar calibrado
const CONFIANZA_MIN = 16;   // mínimo de puntos vocales para calibrar
const RECALIB_S     = 3.5;  // segundos en zoom out antes de recalibrar
const ALPHA_CALIB   = 0.06; // suavizado del centro durante calibración
const ALPHA_ZOOM    = 0.04; // suavizado de visibleSemi (expansión/contracción)

const TimelineZoom = {

    _zoomInit() {
        this._zoom = {
            fase        : 'calibrando', // 'calibrando' | 'estable' | 'zoomout'
            visibleSemi : SEMI_NORMAL,
            centro      : null,         // midi calibrado
            tZoomOut    : null,         // timestamp entrada a zoomout
            puntosVocales: [],          // buffer para calibración
        };
    },

    // Llamado desde agregarPunto — único punto de entrada
    _actualizarZoom(midi, t) {
        const z = this._zoom;
        if (midi <= 0) return; // silencio

        // ── Con referencia: calibración instantánea ───────────────────────
        if (z.fase === 'calibrando' && this._centroRef() !== null) {
            z.centro = this._centroRef();
            z.fase   = 'estable';
            this.topMidi = z.centro + SEMI_NORMAL / 2;
            return;
        }

        // ── Fase calibrando ───────────────────────────────────────────────
        if (z.fase === 'calibrando') {
            z.puntosVocales.push(midi);
            // Suavizar centro mientras calibra
            if (z.centro === null) z.centro = midi;
            z.centro += (midi - z.centro) * ALPHA_CALIB;
            this.topMidi = z.centro + z.visibleSemi / 2;

            if (z.puntosVocales.length >= CONFIANZA_MIN) {
                const cv = this._cv(z.puntosVocales);
                const densidad = this._beatS ? Math.min(1, 1 / this._beatS) : 0.5;
                const umbral   = CONFIANZA_CV * (1 + densidad * 0.5); // más rápido con tempo rápido
                if (cv < umbral) {
                    z.centro = this._mediana(z.puntosVocales);
                    z.fase   = 'estable';
                    // Exponer mediana global para transposición automática
                    window._medianaUsuario = z.centro;
                    console.log(`[Zoom] Calibrado: centro=${z.centro.toFixed(1)} CV=${cv.toFixed(3)}`);
                }
            }
            return;
        }

        // ── Fase estable / zoomout ────────────────────────────────────────
        const semiTarget = z.fase === 'zoomout' ? SEMI_OUT : SEMI_NORMAL;
        z.visibleSemi += (semiTarget - z.visibleSemi) * ALPHA_ZOOM;

        const margenMidi = MARGEN_SEMI + (z.visibleSemi - SEMI_NORMAL) * 0.3;
        const fuera      = Math.abs(midi - z.centro) > (z.visibleSemi / 2 - margenMidi);

        if (fuera && z.fase === 'estable') {
            z.fase      = 'zoomout';
            z.tZoomOut  = t;
        } else if (!fuera && z.fase === 'zoomout') {
            z.fase      = 'estable';
            z.tZoomOut  = null;
        } else if (z.fase === 'zoomout' && (t - z.tZoomOut) >= RECALIB_S) {
            // Recalibrar con puntos recientes
            const recientes = this.puntos
            .filter(p => p.midi > 0 && p.t >= t - 10)
            .map(p => p.midi);
            if (recientes.length >= CONFIANZA_MIN) {
                z.centro = this._mediana(recientes);
                z.fase   = 'estable';
                z.tZoomOut = null;
                console.log(`[Zoom] Recalibrado: centro=${z.centro.toFixed(1)}`);
            }
        }

        // Centrar siempre en el centro calibrado
        const topTarget = z.centro + z.visibleSemi / 2;
        this.topMidi += (topTarget - this.topMidi) * 0.08;
        this.topMidi  = Math.max(this.MIDI_MIN + z.visibleSemi,
                                 Math.min(this.MIDI_MAX, this.topMidi));
    },

    // ── Helpers ───────────────────────────────────────────────────────────

    _centroRef() {
        if ((this.plateausRef || []).length > 0) {
            const midis = this.plateausRef.map(p => p.mediana_midi);
            return this._mediana(midis);
        }
        if ((this.puntosRef || []).length > 0) {
            const midis = this.puntosRef.map(p => p.midi).filter(m => m > 0);
            return midis.length ? this._mediana(midis) : null;
        }
        return null;
    },

    _mediana(arr) {
        const s = [...arr].sort((a, b) => a - b);
        return s[Math.floor(s.length / 2)];
    },

    _cv(arr) {
        const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
        const std  = Math.sqrt(arr.map(x => (x - mean) ** 2)
        .reduce((a, b) => a + b, 0) / arr.length);
        return std / (mean + 1e-9);
    },
};
