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
 *
 * DEBUG FLAGS (consola):
 *   window._timeline.DEBUG_REF     = false
 *   window._timeline.DEBUG_REC     = false
 *   window._timeline.DEBUG_OVERLAY = false
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

        // Timestamp sync servidor↔cliente
        this._tServidorUltimo = null;
        this._tLocalUltimo    = null;

        // Datos
        this.puntos      = [];
        this.plateaus    = [];
        this.plateausRef = [];
        this.puntosRef   = [];
        this.duracionRef = 0;
        this.palabras    = [];

        // Estado grabación
        this.grabando   = false;
        this.t_inicio   = null;
        this._tOffset   = 0;

        // Scroll
        this.scrollX    = 0;
        this.scrollY    = 0;
        this.dragging   = false;
        this.dragStartX = 0;
        this.dragStartY = 0;

        // Suavizado en tiempo real
        this._ventana   = [];
        this._segmentos = [];
        this._beatS     = null;
        this._segIni    = null;

        // Detección de tempo (modo free)
        this._tempoOk       = false;
        this._onsets        = [];
        this._lastVoiced    = false;
        this._tempoEstimado = null;

        // Debug
        this.DEBUG_REF     = true;
        this.DEBUG_REC     = true;
        this.DEBUG_OVERLAY = true;

        this.NOTAS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];

        // Zoom init (TimelineZoom)
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

        // Si hay referencia, zoom la usará en el primer punto vocal
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
        this._cerrarSegmento(this._tAhora());
        this.grabando = false;
    }

    cargarLetras(palabras) { this.palabras = palabras; }

    cargarReferencia(puntos, duracionTotal) {
        this.puntosRef   = puntos;
        this.duracionRef = duracionTotal;
    }

    cargarPlateaus(plateaus) {
        this.plateaus   = plateaus || [];
        this.puntos     = [];
        this._segmentos = [];
    }

    cargarPlateausRef(plateaus) {
        this.plateausRef = plateaus || [];
        this.puntosRef   = [];
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

        if (!this._tempoOk) this._detectarOnset(p);
        if (this._tempoOk)  this._procesarVentana(p);

        this._actualizarZoom(midi, t);
    }

    // ── Tempo (modo free) ─────────────────────────────────────────────────

    _detectarOnset(p) {
        const hayVoz = p.midi > 0;
        if (hayVoz && !this._lastVoiced) {
            this._onsets.push(p.t);
            if (this._onsets.length >= 8) this._evaluarTempo();
        }
        this._lastVoiced = hayVoz;
    }

    _evaluarTempo() {
        const intervals = [];
        for (let i = 1; i < this._onsets.length; i++)
            intervals.push(this._onsets[i] - this._onsets[i-1]);
        const mean = intervals.reduce((a, b) => a + b, 0) / intervals.length;
        const std  = Math.sqrt(intervals.map(x => (x - mean) ** 2)
        .reduce((a, b) => a + b, 0) / intervals.length);
        if (std / mean < 0.20) {
            this._beatS         = mean;
            this._tempoOk       = true;
            this._tempoEstimado = Math.round(60 / mean);
            this._segIni        = this._onsets[this._onsets.length - 1];
            console.log(`[Timeline] Tempo: ${this._tempoEstimado} BPM`);
        }
    }

    // ── Suavizado por ventana ─────────────────────────────────────────────

    _procesarVentana(p) {
        if (!this._beatS) return;
        if (this._segIni === null) this._segIni = p.t;
        this._ventana.push(p);
        if (p.t - this._segIni >= this._beatS) this._cerrarSegmento(p.t);
    }

    _cerrarSegmento(tFin) {
        if (!this._ventana.length || this._segIni === null) return;
        const midis = this._ventana.filter(p => p.midi > 0).map(p => p.midi);
        if (midis.length === 0) { this._ventana = []; this._segIni = tFin; return; }
        midis.sort((a, b) => a - b);
        const medMidi  = midis[Math.floor(midis.length / 2)];
        const cents    = this._ventana.filter(p => p.midi > 0).map(p => p.cents);
        cents.sort((a, b) => a - b);
        const medCents = cents[Math.floor(cents.length / 2)];
        this._segmentos.push({ t_ini: this._segIni, t_fin: tFin, midi: medMidi, cents: medCents });
        this._ventana = [];
        this._segIni  = tFin;
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
        return 0; // ← era _duracionTotal(), causaba movimiento sin grabación
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
