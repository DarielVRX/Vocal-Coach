/**
 * TIMELINE-DRAW.JS — Métodos de renderizado del piano roll
 * =========================================================
 * Sistema visual por tipo:
 *   forma    → plateau/vibrato/inestable/portamento/arreglos
 *   grosor   → fino/medio/grueso/doble
 *   opacidad → 100% confiable / 70% arreglo conocido / 40% undefined
 */

const TimelineDraw = {

    _draw() {
        const cv = this.canvas, ctx = this.ctx;
        const W = cv.width, H = cv.height;

        ctx.clearRect(0, 0, W, H);
        ctx.fillStyle = '#0a0a0a';
        ctx.fillRect(0, 0, W, H);

        this._drawGrid(W, H);

        if (this.DEBUG_REF) {
            if ((this.plateausRef || []).length > 0)
                this._drawPlateaus(W, H, this.plateausRef, true);
            else if ((this.puntosRef || []).length > 0 && !this.grabando)
                this._drawLinea(W, H, this.puntosRef, true);
        }

        if (this.DEBUG_REC) {
            if ((this.plateaus || []).length > 0)
                this._drawPlateaus(W, H, this.plateaus, false);
            else
                this._drawSegmentos(W, H);
        }

        this._drawLetras(W, H);
        this._drawCursorLine(W, H);
        if (this.DEBUG_OVERLAY) this._drawDebugOverlay(W, H);
        this._drawScrollIndicators(W, H);
    },

    _drawGrid(W, H) {
        const ctx = this.ctx, labelW = 36;
        const semi = this._zoom.visibleSemi;
        const pxS  = H / semi;

        for (let i = 0; i <= semi; i++) {
            const midi = Math.round(this.topMidi - i);
            if (midi < this.MIDI_MIN || midi > this.MIDI_MAX) continue;
            const y    = i * pxS;
            const nota = this.NOTAS[midi % 12];
            const esC  = nota === 'C';
            const sos  = nota.includes('#');

            ctx.fillStyle = sos ? '#111' : '#141414';
            ctx.fillRect(labelW, y, W - labelW, pxS);

            ctx.strokeStyle = esC ? '#333' : '#1a1a1a';
            ctx.lineWidth   = esC ? 1.5 : 0.5;
            ctx.beginPath(); ctx.moveTo(labelW, y); ctx.lineTo(W, y); ctx.stroke();

            if (!sos) {
                const oct = Math.floor(midi / 12) - 1;
                ctx.fillStyle = esC ? '#7c83fd' : '#333';
                ctx.font      = `${esC ? 'bold ' : ''}${Math.max(9, pxS * 0.7)}px monospace`;
                ctx.textAlign = 'right';
                ctx.fillText(`${nota}${oct}`, labelW - 3, y + pxS * 0.75);
            }
        }
        ctx.strokeStyle = '#222'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(36, 0); ctx.lineTo(36, H); ctx.stroke();
    },

    _calcUmbralGap(puntos) {
        if (puntos.length < 4) return 0.2;
        const gaps = [];
        for (let i = 1; i < puntos.length; i++)
            gaps.push(puntos[i].t - puntos[i-1].t);
        gaps.sort((a, b) => a - b);
        const med = gaps[Math.floor(gaps.length / 2)];
        return Math.max(0.15, Math.min(0.5, med * 3));
    },

    _drawLinea(W, H, puntos, isRef) {
        const ctx = this.ctx, labelW = 36;
        if (!puntos || puntos.length < 2) return;
        const tAhora = this._tAhora();
        const umbral = this._calcUmbralGap(puntos);
        const pxS    = this._pxSemi();

        ctx.save();
        ctx.globalAlpha = isRef ? 0.28 : 1.0;
        ctx.lineWidth   = isRef ? 1.5 : 2.5;
        ctx.lineJoin = 'round'; ctx.lineCap = 'round';

        let prev = null;
        for (const p of puntos) {
            const x = W - (tAhora - p.t) * this.PX_SEG + this.scrollX;
            const y = this._midiToY(p.midi, pxS);
            const vis = x >= labelW && x <= W && y >= 0 && y <= H;
            const color = isRef ? '#7c9fbf' : this._colorCents(p.cents);
            if (prev && (p.t - prev.t < umbral)) {
                ctx.strokeStyle = color;
                ctx.beginPath(); ctx.moveTo(prev.x, prev.y); ctx.lineTo(x, y); ctx.stroke();
            }
            if (vis) {
                ctx.fillStyle = color;
                ctx.beginPath(); ctx.arc(x, y, isRef ? 1.5 : 2, 0, Math.PI*2); ctx.fill();
            }
            prev = { x, y };
        }
        ctx.restore();
    },

    _drawSegmentos(W, H) {
        const ctx = this.ctx, labelW = 36;
        const tAhora = this._tAhora();
        const pxS    = this._pxSemi();
        ctx.save();

        // Segmentos confirmados
        for (const s of this._segmentos) {
            const x1 = W - (tAhora - s.t_ini) * this.PX_SEG + this.scrollX;
            const x2 = W - (tAhora - s.t_fin) * this.PX_SEG + this.scrollX;
            const y  = this._midiToY(s.midi, pxS);
            if (x2 < labelW || x1 > W || y < 0 || y > H) continue;
            const color = this._colorCents(s.cents);
            ctx.globalAlpha = 1.0;
            switch (s.tipo) {
                case 'vibrato':
                    this._drawVibrato(x1, x2, y, color, false, pxS);
                    break;
                case 'inestable':
                    this._drawInestable(x1, x2, y, color, false, s.varianza, pxS);
                    break;
                case 'portamento':
                    ctx.strokeStyle = '#6a7a8a'; ctx.lineWidth = 1.5; ctx.lineCap = 'round';
                    ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(x2, y); ctx.stroke();
                    break;
                default: // plateau
                    this._drawPlateauEstable(x1, x2, y, color, false);
            }
        }

        // Segmento en construcción (preview semitransparente)
        if (this._segActual) {
            const s  = this._segActual;
            const x1 = W - (tAhora - s.t_ini) * this.PX_SEG;
            const y  = this._midiToY(s.midi, pxS);
            if (x1 < W && y >= 0 && y <= H) {
                ctx.globalAlpha = 0.45;
                const color = this._colorCents(s.cents);
                ctx.strokeStyle = color; ctx.lineWidth = 4; ctx.lineCap = 'round';
                ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(W, y); ctx.stroke();
            }
        }

        ctx.restore();
    },

    _drawDebugOverlay(W, H) {
        const ctx = this.ctx;
        const pls = this.plateausRef.length > 0 ? this.plateausRef : this.plateaus;
        if (!pls.length) return;
        const pxS    = this._pxSemi();
        ctx.save();
        ctx.font = '9px monospace'; ctx.textAlign = 'left';
        const tAhora = this._tAhora();
        for (const p of pls) {
            const x1 = W - (tAhora - p.t_inicio) * this.PX_SEG;
            const x2 = W - (tAhora - p.t_fin)    * this.PX_SEG;
            const y  = this._midiToY(p.mediana_midi, pxS);
            if (x2 < 36 || x1 > W) continue;
            const dur = (p.t_fin - p.t_inicio).toFixed(2);
            const sub = p.subtipo_arreglo ? ` [${p.subtipo_arreglo}]` : '';
            const lbl = `${p.tipo[0].toUpperCase()} m${p.mediana_midi?.toFixed(1)} ${p.cents !== undefined ? (p.cents > 0 ? '+' : '') + p.cents + '¢' : ''} ${dur}s${sub}`;
            ctx.fillStyle = '#fff8';
            ctx.fillText(lbl, Math.max(38, x1 + 2), y - 4);
        }
        ctx.restore();
    },

    _drawPlateaus(W, H, plateaus, isRef) {
        const ctx = this.ctx, labelW = 36;
        if (!plateaus || plateaus.length === 0) return;
        const tAhora = this._tAhora();
        const pxS    = this._pxSemi();

        for (let i = 0; i < plateaus.length; i++) {
            const p  = plateaus[i];
            const x1 = W - (tAhora - p.t_inicio) * this.PX_SEG + this.scrollX;
            const x2 = W - (tAhora - p.t_fin)    * this.PX_SEG + this.scrollX;
            const y  = this._midiToY(p.mediana_midi, pxS);
            if (x2 < labelW || x1 > W || y < 0 || y > H) continue;

            ctx.save();

            // Opacidad base por tipo
            const opacidad = isRef ? 0.45 : this._opacidadPlateau(p);
            ctx.globalAlpha = opacidad;

            const color = isRef ? null : this._colorCents(p.cents);

            // Arreglos tienen su propio drawer
            if (!isRef && p.fusionado && p.subtipo_arreglo) {
                this._drawArreglo(x1, x2, y, p, pxS);
            } else {
                switch (p.tipo) {
                    case 'plateau':
                        this._drawPlateauEstable(x1, x2, y, color, isRef);
                        break;
                    case 'inestable':
                        this._drawInestable(x1, x2, y, color, isRef, p.varianza_f0, pxS);
                        break;
                    case 'vibrato':
                        this._drawVibrato(x1, x2, y, color, isRef, pxS);
                        break;
                    case 'portamento':
                        this._drawPortamento(p, i, W, plateaus, isRef, pxS);
                        break;
                }
            }
            ctx.restore();
        }
    },

    // ── Opacidad por tipo ─────────────────────────────────────────────────

    _opacidadPlateau(p) {
        if (p.fusionado) {
            return p.subtipo_arreglo === 'arreglo_undefined' ? 0.40 : 0.70;
        }
        if (p.tipo === 'inestable') return 0.70;
        return 1.0;
    },

    // ── Drawers individuales ──────────────────────────────────────────────

    _drawPlateauEstable(x1, x2, y, color, isRef) {
        const ctx   = this.ctx;
        const c     = color || '#4a7a9b';
        ctx.strokeStyle = c; ctx.lineWidth = 4; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(x2, y); ctx.stroke();
        ctx.fillStyle = c;
        ctx.beginPath(); ctx.arc(x1, y, 3, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(x2, y, 3, 0, Math.PI*2); ctx.fill();
    },

    _drawVibrato(x1, x2, y, color, isRef, pxS) {
        const ctx = this.ctx;
        const c   = color || '#4a7a9b';
        ctx.strokeStyle = c; ctx.lineWidth = 3.5;
        ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        const amp  = pxS * 0.3, freq = 6;
        const dur  = (x2 - x1) || 1;
        ctx.beginPath();
        for (let x = x1; x <= x2; x += 0.8) {
            const yv = y + Math.sin(((x - x1) / dur) * Math.PI * 2 * freq) * amp;
            x === x1 ? ctx.moveTo(x, yv) : ctx.lineTo(x, yv);
        }
        ctx.stroke();
    },

    _drawInestable(x1, x2, y, color, isRef, varianza, pxS) {
        const ctx  = this.ctx;
        const c    = color || '#4a7a9b';
        const amp1 = pxS * 0.15;
        const amp2 = pxS * 0.30;
        const freq = 5;
        const dur  = (x2 - x1) || 1;

        // Línea doble: dos pasadas desplazadas
        for (let offset of [-1.5, 1.5]) {
            ctx.strokeStyle = c; ctx.lineWidth = 1.5;
            ctx.lineCap = 'round'; ctx.lineJoin = 'round';
            ctx.beginPath();
            let toggle = 0;
            for (let x = x1; x <= x2; x += 0.8) {
                const amp = toggle % 2 === 0 ? amp1 : amp2;
                const yv  = y + offset + Math.sin(((x - x1) / dur) * Math.PI * 2 * freq) * amp;
                x === x1 ? ctx.moveTo(x, yv) : ctx.lineTo(x, yv);
                toggle++;
            }
            ctx.stroke();
        }
    },

    _drawPortamento(p, idx, W, plateaus, isRef, pxS) {
        const ctx    = this.ctx;
        const tAhora = this._tAhora();
        const x1     = W - (tAhora - p.t_inicio) * this.PX_SEG;
        const x2     = W - (tAhora - p.t_fin)    * this.PX_SEG;
        const prev   = plateaus[idx - 1];
        const next   = plateaus[idx + 1];
        if (!prev || !next) return;
        const y1  = this._midiToY(prev.mediana_midi, pxS);
        const y2  = this._midiToY(next.mediana_midi, pxS);
        const cpx = (x1 + x2) / 2;
        ctx.strokeStyle = isRef ? '#3a5a7a' : '#6a7a8a';
        ctx.lineWidth = 1.5; ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.bezierCurveTo(cpx, y1, cpx, y2, x2, y2);
        ctx.stroke();
    },

    // ── Arreglos ──────────────────────────────────────────────────────────

    _drawArreglo(x1, x2, y, p, pxS) {
        switch (p.subtipo_arreglo) {
            case 'ornamento':
                this._drawZigzag(x1, x2, y, this._colorCents(p.cents), 1.5, pxS * 0.15, 12);
                break;
            case 'appoggiatura':
                this._drawZigzagCaida(x1, x2, y, this._colorCents(p.cents), 2.5, pxS * 0.20, 8);
                break;
            case 'melisma':
                this._drawZigzag(x1, x2, y, this._colorCents(p.cents), 3.5, pxS * 0.35, 4);
                break;
            default: // arreglo_undefined
                this._drawZigzag(x1, x2, y, this._colorCents(p.cents), 2.0, pxS * 0.22, 7);
        }
    },

    _drawZigzag(x1, x2, y, color, grosor, amp, freq) {
        const ctx = this.ctx;
        const dur = (x2 - x1) || 1;
        ctx.strokeStyle = color; ctx.lineWidth = grosor;
        ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.beginPath();
        let up = true;
        const step = dur / (freq * 2);
        for (let x = x1; x <= x2; x += step) {
            const yv = y + (up ? -amp : amp);
            x === x1 ? ctx.moveTo(x, y) : ctx.lineTo(x, yv);
            up = !up;
        }
        ctx.lineTo(x2, y);
        ctx.stroke();
    },

    _drawZigzagCaida(x1, x2, y, color, grosor, amp, freq) {
        const ctx  = this.ctx;
        const dur  = (x2 - x1) || 1;
        ctx.strokeStyle = color; ctx.lineWidth = grosor;
        ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.beginPath();
        ctx.moveTo(x1, y);
        let up = true;
        const step = dur / (freq * 2);
        for (let x = x1 + step; x <= x2; x += step) {
            const prog = (x - x1) / dur;
            const ampLocal = amp * (1 - prog * 0.6); // decae hacia el final
            const yv = y + (up ? -ampLocal : ampLocal);
            ctx.lineTo(x, yv);
            up = !up;
        }
        ctx.lineTo(x2, y);
        ctx.stroke();
    },

    // ── Letras ────────────────────────────────────────────────────────────

    _drawLetras(W, H) {
        if (!this.palabras || this.palabras.length === 0) return;
        const ctx = this.ctx, labelW = 36;
        const tAhora = this._tAhora();
        ctx.save();
        ctx.font = 'bold 11px monospace'; ctx.textAlign = 'center';
        for (const w of this.palabras) {
            const tMid = (w.start + w.end) / 2;
            const xMid = W - (tAhora - tMid) * this.PX_SEG;
            if (xMid < labelW || xMid > W) continue;
            const dt = Math.abs(tAhora - tMid);
            ctx.globalAlpha = Math.max(0.2, 1.0 - dt / 8);
            ctx.fillStyle   = '#c8d8e8';
            ctx.fillText(w.word, xMid, H - 8);
        }
        ctx.restore();
    },

    _drawCursorLine(W, H) {
        if (!this.grabando) return;
        const ctx = this.ctx;
        ctx.strokeStyle = '#ffffff18'; ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(W, 0); ctx.lineTo(W, H); ctx.stroke();
        ctx.setLineDash([]);
    },

    _drawScrollIndicators(W, H) {
        if (this.grabando) return;
        const ctx  = this.ctx;
        const semi = this._zoom.visibleSemi;
        const dur  = this._duracionTotal();
        const maxX = Math.max(0, dur * this.PX_SEG - (W - 36));
        if (maxX > 0) {
            const prog = this.scrollX / maxX;
            const bw   = Math.max(30, (W-36) * ((W-36) / (dur * this.PX_SEG)));
            ctx.fillStyle = '#ffffff33';
            ctx.fillRect(36 + (W-36-bw)*prog, H-3, bw, 3);
        }
        const range = this.TOTAL_SEMITONOS - semi;
        if (range > 0) {
            const prog = (this.topMidi - (this.MIDI_MIN + semi)) / range;
            const bh   = Math.max(30, H * (semi / this.TOTAL_SEMITONOS));
            ctx.fillStyle = '#ffffff33';
            ctx.fillRect(W-3, (H-bh)*prog, 3, bh);
        }
    },

    // ── Helpers visuales ─────────────────────────────────────────────────

    _pxSemi() {
        return this.canvas.height / this._zoom.visibleSemi;
    },

    _midiToY(midi, pxS) {
        const px = pxS !== undefined ? pxS : this._pxSemi();
        return (this.topMidi - midi) * px;
    },

    _colorCents(cents) {
        const a = Math.abs(cents);
        if (a < 10) return '#4caf50';
        if (a < 25) return '#cddc39';
        if (a < 45) return '#ff9800';
        return '#f44336';
    },
};
