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

const SEMI_NORMAL   = 12;
const SEMI_OUT      = 20;
const MARGEN_SEMI   = 2;
const CONFIANZA_CV  = 0.12;
const CONFIANZA_MIN = 16;
const RECALIB_S     = 3.5;
const ALPHA_CALIB   = 0.06;
const ALPHA_ZOOM    = 0.04;

const TimelineZoom = {

    _zoomInit() {
        this._zoom = {
            fase         : 'calibrando',
            visibleSemi  : SEMI_NORMAL,
            centro       : null,
            tZoomOut     : null,
            puntosVocales: [],
        };
    },

    _actualizarZoom(midi, t) {
        const z = this._zoom;
        if (midi <= 0) return;

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
            if (z.centro === null) z.centro = midi;
            z.centro += (midi - z.centro) * ALPHA_CALIB;
            this.topMidi = z.centro + z.visibleSemi / 2;

            if (z.puntosVocales.length >= CONFIANZA_MIN) {
                const cv      = this._cv(z.puntosVocales);
                const densidad = this._beatS ? Math.min(1, 1 / this._beatS) : 0.5;
                const umbral   = CONFIANZA_CV * (1 + densidad * 0.5);
                if (cv < umbral) {
                    z.centro = this._mediana(z.puntosVocales);
                    z.fase   = 'estable';
                    window._medianaUsuario = z.centro;
                    console.log(`[Zoom] Calibrado: centro=${z.centro.toFixed(1)} CV=${cv.toFixed(3)}`);
                }
            }
            return;
        }

        // ── Fase estable / zoomout ────────────────────────────────────────
        const margenMidi = MARGEN_SEMI + (z.visibleSemi - SEMI_NORMAL) * 0.3;
        const fuera      = Math.abs(midi - z.centro) > (z.visibleSemi / 2 - margenMidi);

        if (fuera && z.fase === 'estable') {
            z.fase     = 'zoomout';
            z.tZoomOut = t;
        } else if (!fuera && z.fase === 'zoomout') {
            z.fase     = 'estable';
            z.tZoomOut = null;
        } else if (z.fase === 'zoomout' && (t - z.tZoomOut) >= RECALIB_S) {
            const centroRef = this._centroRef();
            if (centroRef !== null) {
                z.centro   = centroRef;
                z.fase     = 'estable';
                z.tZoomOut = null;
                console.log(`[Zoom] Recalibrado → ref: centro=${z.centro.toFixed(1)}`);
            } else {
                const recientes = this.puntos
                .filter(p => p.midi > 0 && p.t >= t - 10)
                .map(p => p.midi);
                if (recientes.length >= CONFIANZA_MIN) {
                    z.centro   = this._mediana(recientes);
                    z.fase     = 'estable';
                    z.tZoomOut = null;
                    console.log(`[Zoom] Recalibrado: centro=${z.centro.toFixed(1)}`);
                }
            }
        }

        // ── Centrado y zoom dinámico ──────────────────────────────────────
        // En karaoke grabando: anticipa notas futuras de la referencia
        // En libre grabando: respuesta más rápida al pitch actual
        const centroRef = (window._modoKaraoke && this.grabando)
            ? this._centroRefFuturo(t)
            : this._centroRef();

        let semiTarget, topTarget;

        if (centroRef !== null && z.centro !== null && Math.abs(centroRef - z.centro) > 2) {
            const hi = Math.max(centroRef, z.centro) + MARGEN_SEMI + 1;
            const lo = Math.min(centroRef, z.centro) - MARGEN_SEMI - 1;
            semiTarget = Math.min(this.TOTAL_SEMITONOS, Math.max(SEMI_NORMAL, hi - lo));
            topTarget  = hi;
        } else {
            semiTarget = z.fase === 'zoomout' ? SEMI_OUT : SEMI_NORMAL;
            topTarget  = (centroRef !== null ? centroRef : z.centro) + semiTarget / 2;
        }

        // Karaoke: lerp lento (anticipa suavemente la nota que llega)
        // Libre grabando: lerp más rápido (respuesta inmediata al pitch)
        const alphaZoom = (this.grabando && !window._modoKaraoke) ? 0.10 : ALPHA_ZOOM;
        const alphaTop  = (this.grabando && !window._modoKaraoke) ? 0.14 : 0.05;

        z.visibleSemi += (semiTarget - z.visibleSemi) * alphaZoom;
        this.topMidi  += (topTarget  - this.topMidi)  * alphaTop;
        this.topMidi   = Math.max(this.MIDI_MIN + z.visibleSemi,
                                  Math.min(this.MIDI_MAX, this.topMidi));
    },

    // ── Helpers ───────────────────────────────────────────────────────────

    _centroRefFuturo(tAhora) {
        if (!this.plateausRef?.length) return this._centroRef();
        const upcoming = this.plateausRef.filter(p => {
            const t = p.t_inicio ?? p.t_ini;
            return t > tAhora && t < tAhora + 2.5;
        });
        if (!upcoming.length) return this._centroRef();
        return this._mediana(upcoming.map(p => p.mediana_midi));
    },

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
