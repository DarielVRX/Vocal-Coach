/**
 * TIMELINE.JS — Constructor, API pública, loop, estado, scroll
 * =============================================================
 * Depende de:
 *   timeline-zoom.js  → TimelineZoom  (mixin)
 *   timeline-draw.js  → TimelineDraw  (mixin)
 *
 * Cargar en HTML en orden:
 *   <script src="timeline-zoom.js"></script>
 *   <script src="timeline-draw.js"></script>
 *   <script src="timeline.js"></script>
 */

class VocalTimeline {

    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx    = this.canvas.getContext('2d');

        this.MIDI_MIN        = 36;
        this.MIDI_MAX        = 84;
        this.TOTAL_SEMITONOS = this.MIDI_MAX - this.MIDI_MIN + 1;
        this.PX_SEG          = 80;
        this.topMidi         = this.MIDI_MAX - 12;

        this._tServidorUltimo = null;
        this._tLocalUltimo    = null;

        this.puntos      = [];
        this.plateaus    = [];
        this.plateausRef = [];
        this.puntosRef   = [];
        this.duracionRef = 0;
        this.palabras    = [];

        this.grabando   = false;
        this.t_inicio   = null;
        this._tOffset   = 0;

        this.scrollX    = 0;
        this.scrollY    = 0;
        this.dragging   = false;
        this.dragStartX = 0;
        this.dragStartY = 0;

        this._ventana      = [];
        this._segmentos    = [];
        this._segActual    = null;
        this._segIni       = null;
        this._ventanaT     = 1.0;

        this.DEBUG_REF     = true;
        this.DEBUG_REC     = true;
        this.DEBUG_OVERLAY = true;

        this.NOTAS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];

        this._zoomInit();

        this._resize();
        window.addEventListener('resize', () => this._resize());
        this._bindScroll();
        this._loop();
    }

    _resize() {
        const w = this.canvas.parentElement.clientWidth || 420;
        this.canvas.width  = w;
        this.canvas.height = Math.min(260, window.innerHeight * 0.32);
    }

    // ── API pública ───────────────────────────────────────────────────────

    iniciar() {
        this.puntos     = [];
        this.plateaus   = [];
        this._ventana   = [];
        this._segmentos = [];
        this._segIni    = null;
        this.grabando   = true;
        this.t_inicio   = performance.now();
        this.scrollX    = 0;
        this.scrollY    = 0;
        this._tOffset   = 0;

        this._zoomInit();

        if (window._beatS) {
            this._beatS   = window._beatS;
            this._tempoOk = true;
        } else {
            this._beatS         = null;
            this._tempoOk       = false;
            this._onsets        = [];
            this._lastVoiced    = false;
            this._tempoEstimado = null;
        }
    }

    detener() {
        if (this._segActual) {
            this._segmentos.push(this._segActual);
            this._segActual = null;
        }
        this.grabando         = false;
        this._tServidorUltimo = null;
        this._tLocalUltimo    = null;
        const dur = this._duracionTotal();
        const W   = this.canvas.width - 36;
        this.PX_SEG  = Math.min(80, W / Math.min(dur, 30));
        this.scrollX = Math.max(0, dur * this.PX_SEG - W);
    }

    cargarLetras(palabras)  { this.palabras    = palabras; }
    cargarPlateausRef(plateaus) {
        this.plateausRef = plateaus || [];
        this.puntosRef   = [];
    }
    cargarReferencia(puntos, duracionTotal) {
        this.puntosRef   = puntos;
        this.duracionRef = duracionTotal;
    }
    cargarPlateaus(plateaus) {
        this.plateaus   = plateaus || [];
        this.puntos     = [];
        this._segmentos = [];
    }

    agregarPunto(midi, cents, tServidor) {
        if (!this.grabando) return;
        const t = (tServidor !== undefined)
        ? tServidor
        : (performance.now() - this.t_inicio) / 1000;
        const p = { midi: parseFloat(midi), cents: parseFloat(cents), t };
        this.puntos.push(p);

        this._tServidorUltimo = t;
        this._tLocalUltimo    = performance.now() / 1000;

        if (midi > 0) this._procesarPuntoRT(p);
        this._actualizarZoom(midi, t);
    }

    // ── Segmentación RT (ventana 1s deslizante) ───────────────────────────

    _procesarPuntoRT(p) {
        this._ventana.push(p);
        if (this._segIni === null) this._segIni = p.t;
        if (p.t - this._segIni >= this._ventanaT) {
            this._cerrarVentanaRT(p.t);
        }
    }

    _cerrarVentanaRT(tFin) {
        const voiced = this._ventana.filter(p => p.midi > 0);
        if (voiced.length === 0) {
            this._ventana = [];
            this._segIni  = tFin;
            return;
        }

        const midis    = voiced.map(p => p.midi).sort((a, b) => a - b);
        const cents    = voiced.map(p => p.cents).sort((a, b) => a - b);
        const medMidi  = midis[Math.floor(midis.length / 2)];
        const medCents = cents[Math.floor(cents.length / 2)];
        const varianza = this._varianza(voiced.map(p => p.midi));
        const tipo     = this._clasificarTipoRT(voiced, varianza);

        const nuevo = { t_ini: this._segIni, t_fin: tFin, midi: medMidi, cents: medCents, tipo, varianza };

        if (this._segActual && Math.round(this._segActual.midi) === Math.round(medMidi)) {
            this._segActual.t_fin    = tFin;
            this._segActual.varianza = (this._segActual.varianza + varianza) / 2;
            this._segActual.tipo     = this._clasificarTipoAcumulado(this._segActual);
        } else {
            if (this._segActual) {
                const salto = Math.abs(medMidi - this._segActual.midi);
                if (salto >= 1 && salto <= 6) {
                    this._segmentos.push({ ...this._segActual, t_fin: nuevo.t_ini });
                    this._segmentos.push({
                        t_ini: this._segActual.t_fin,
                        t_fin: nuevo.t_ini,
                        midi : (this._segActual.midi + medMidi) / 2,
                                         cents: medCents,
                                         tipo : 'portamento',
                                         varianza: 0,
                    });
                } else {
                    this._segmentos.push(this._segActual);
                }
            }
            this._segActual = nuevo;
        }

        this._ventana = [];
        this._segIni  = tFin;
    }

    _clasificarTipoRT(puntos, varianza) {
        if (puntos.length < 4) return 'plateau';
        const midis = puntos.map(p => p.midi);
        const med   = midis.reduce((a, b) => a + b, 0) / midis.length;
        let cruces  = 0;
        for (let i = 1; i < midis.length; i++)
            if ((midis[i-1] - med) * (midis[i] - med) < 0) cruces++;
            const frecCruces = cruces / ((puntos[puntos.length-1].t - puntos[0].t) || 1);
        if (frecCruces > 6 && varianza > 0.002) return 'vibrato';
        if (varianza > 0.015) return 'inestable';
        return 'plateau';
    }

    _clasificarTipoAcumulado(seg) {
        if (seg.varianza > 0.015) return 'inestable';
        if (seg.varianza > 0.004) return 'vibrato';
        return 'plateau';
    }

    _varianza(arr) {
        const m = arr.reduce((a, b) => a + b, 0) / arr.length;
        return arr.reduce((a, b) => a + (b - m) ** 2, 0) / arr.length / (m * m + 1e-9);
    }

    // ── Scroll ────────────────────────────────────────────────────────────

    _bindScroll() {
        const c = this.canvas;
        c.addEventListener('touchstart', e => {
            if (this.grabando) return;
            this.dragging   = true;
            this.dragStartX = e.touches[0].clientX;
            this.dragStartY = e.touches[0].clientY;
        });
        c.addEventListener('touchmove', e => {
            if (!this.dragging) return;
            e.preventDefault();
            const dx = e.touches[0].clientX - this.dragStartX;
            const dy = e.touches[0].clientY - this.dragStartY;
            this._aplicarScroll(dx, dy);
            this.dragStartX = e.touches[0].clientX;
            this.dragStartY = e.touches[0].clientY;
        }, { passive: false });
        c.addEventListener('touchend', () => { this.dragging = false; });
        c.addEventListener('wheel', e => {
            if (this.grabando) return;
            this._aplicarScroll(-e.deltaX, e.deltaY);
        });
    }

    _aplicarScroll(dx, dy) {
        const semi = this._zoom.visibleSemi;
        const maxX = Math.max(0, this._duracionTotal() * this.PX_SEG - (this.canvas.width - 36));
        this.scrollX = Math.max(0, Math.min(maxX, this.scrollX - dx));
        this.scrollY -= dy * 0.05;
        this.topMidi = Math.max(this.MIDI_MIN + semi,
                                Math.min(this.MIDI_MAX,
                                         this.MIDI_MAX - semi / 2 + this.scrollY));
        this.scrollY = this.topMidi - (this.MIDI_MAX - semi / 2);
    }

    // ── Loop ──────────────────────────────────────────────────────────────

    _loop() {
        this._draw();
        requestAnimationFrame(() => this._loop());
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    _duracionTotal() {
        const durSeg = (this._segmentos || []).length > 0
        ? this._segmentos[this._segmentos.length-1].t_fin : 0;
        const durPl  = (this.plateaus   || []).length > 0
        ? this.plateaus[this.plateaus.length-1].t_fin : 0;
        return Math.max(durSeg, durPl, this.duracionRef || 0);
    }

    _tAhora() {
        if (this.grabando && this._tServidorUltimo !== null) {
            const avance = performance.now() / 1000 - this._tLocalUltimo;
            return this._tServidorUltimo + avance;
        }
        if (this.grabando) return (performance.now() - this.t_inicio) / 1000;
        if ((this._segmentos || []).length > 0)
            return this._segmentos[this._segmentos.length-1].t_fin;
        if ((this.plateaus || []).length > 0)
            return this.plateaus[this.plateaus.length-1].t_fin;
        return 0;
    }

    _xDeAbsoluto(t, W) {
        const dur = this.duracionRef || this._duracionTotal();
        return 36 + (t / dur) * (W - 36) - this.scrollX;
    }
}

// ── Mixins ────────────────────────────────────────────────────────────────────
Object.assign(VocalTimeline.prototype, TimelineDraw);
Object.assign(VocalTimeline.prototype, TimelineZoom);

window.VocalTimeline = VocalTimeline;
