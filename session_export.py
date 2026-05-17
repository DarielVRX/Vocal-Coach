"""
SESSION EXPORT
==============
Exporta sesión a:
  - grabacion.wav     : audio crudo sin modificaciones
  - take.wav          : mezcla voz + accompaniment (solo modo karaoke)
  - diagnostico.pdf   : piano roll por compás + score por frase + resumen
"""

import os
import time
import numpy as np
import soundfile as sf
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

EXPORT_DIR  = "./exports"
SAMPLE_RATE = 44100
os.makedirs(EXPORT_DIR, exist_ok=True)

# ── Colores score ─────────────────────────────────────────────────────────────
SCORE_COLORS = {
    "SS": "#ffd700",
    "S" : "#c0c0c0",
    "A" : "#4caf50",
    "B" : "#ffeb3b",
    "C" : "#ff9800",
    "D" : "#f44336",
}

TIPO_COLORS = {
    "plateau"   : "#4caf50",
    "vibrato"   : "#7c83fd",
    "inestable" : "#ff9800",
    "portamento": "#888888",
    "ornamento" : "#26c6da",
    "appoggiatura": "#ab47bc",
    "melisma"   : "#ef5350",
    "arreglo_undefined": "#546e7a",
}


class SessionExporter:

    def export(self, session_audio: np.ndarray,
               karaoke_audio: np.ndarray | None = None,
               session_id: str | None = None,
               frases: list | None = None,
               plateaus_ref: list | None = None,
               bpm: float | None = None) -> dict | None:
        try:
            if session_id is None:
                session_id = f"session_{int(time.time())}"

            out_dir = os.path.join(EXPORT_DIR, session_id)
            os.makedirs(out_dir, exist_ok=True)
            paths = {}

            # 1. Grabación cruda
            grab_path = os.path.join(out_dir, "grabacion.wav")
            sf.write(grab_path, session_audio, SAMPLE_RATE)
            paths["grabacion"] = grab_path

            # 2. Take karaoke (mezcla)
            if karaoke_audio is not None:
                take_path = os.path.join(out_dir, "take.wav")
                sf.write(take_path, self._mezclar(session_audio, karaoke_audio), SAMPLE_RATE)
                paths["take"] = take_path

            # 3. PDF diagnóstico
            if frases:
                pdf_path = os.path.join(out_dir, "diagnostico.pdf")
                self._exportar_pdf(
                    frases      = frases,
                    pdf_path    = pdf_path,
                    session_id  = session_id,
                    plateaus_ref= plateaus_ref or [],
                    bpm         = bpm or 120.0,
                )
                paths["diagnostico"] = pdf_path

            print(f"[EXPORT] {out_dir}")
            return paths

        except Exception as e:
            import traceback
            print(f"[EXPORT ERROR] {e}\n{traceback.format_exc()}")
            return None

    # ── Audio ─────────────────────────────────────────────────────────────────

    def _mezclar(self, voz: np.ndarray, inst: np.ndarray,
                 g_voz: float = 1.0, g_inst: float = 0.6) -> np.ndarray:
        n = max(len(voz), len(inst))
        v = np.pad(voz,  (0, n - len(voz)))
        k = np.pad(inst, (0, n - len(inst)))
        mix  = v * g_voz + k * g_inst
        peak = np.max(np.abs(mix))
        if peak > 0.99:
            mix = mix * (0.99 / peak)
        return mix.astype(np.float32)

    # ── PDF ───────────────────────────────────────────────────────────────────

    def _exportar_pdf(self, frases, pdf_path, session_id,
                      plateaus_ref, bpm):
        beat_s     = 60.0 / bpm
        compas_s   = beat_s * 4          # 4 beats por compás
        todos_pl   = [p for f in frases for p in f.plateaus]
        if not todos_pl:
            return

        t_max = max(p.t_fin for p in todos_pl)
        n_compases = max(1, int(np.ceil(t_max / compas_s)))

        # Rango MIDI visible
        midis = [p.mediana_midi for p in todos_pl]
        midi_min = max(36, int(min(midis)) - 3)
        midi_max = min(84, int(max(midis)) + 3)

        compases_por_pagina = 4
        n_paginas = max(1, int(np.ceil(n_compases / compases_por_pagina)))

        with PdfPages(pdf_path) as pdf:
            # ── Portada ───────────────────────────────────────────────────
            fig, ax = plt.subplots(figsize=(8.5, 11))
            ax.axis('off')
            fig.patch.set_facecolor('#0d0d0d')

            # Métricas globales
            pl_estables = [p for p in todos_pl if p.tipo in ("plateau", "vibrato")]
            cents_prom  = float(np.mean([abs(p.cents) for p in pl_estables])) if pl_estables else 0
            estab_prom  = float(np.mean([p.varianza_f0 for p in pl_estables])) if pl_estables else 0

            from analyzer import calcular_score
            score_global = calcular_score(cents_prom, estab_prom)
            col_score    = SCORE_COLORS.get(score_global, "#aaa")

            ax.text(0.5, 0.88, "VOCAL COACH", ha='center', va='center',
                    fontsize=28, fontweight='bold', color='#7c83fd',
                    transform=ax.transAxes)
            ax.text(0.5, 0.78, session_id, ha='center', va='center',
                    fontsize=11, color='#555', transform=ax.transAxes)

            # Score global grande
            ax.text(0.5, 0.62, score_global, ha='center', va='center',
                    fontsize=72, fontweight='900', color=col_score,
                    transform=ax.transAxes)

            # Métricas
            metricas = [
                ("BPM",       f"{bpm:.0f}"),
                ("Afinación", f"{cents_prom:.1f}¢ prom."),
                ("Estab.",    f"σ={estab_prom:.4f}"),
                ("Frases",    str(len(frases))),
                ("Plateaus",  str(len(pl_estables))),
            ]
            for i, (k, v) in enumerate(metricas):
                x = 0.15 + (i % 3) * 0.35
                y = 0.44 - (i // 3) * 0.08
                ax.text(x, y, f"{k}: ", ha='right', va='center',
                        fontsize=11, color='#555', transform=ax.transAxes)
                ax.text(x, y, v, ha='left', va='center',
                        fontsize=11, color='#eee', transform=ax.transAxes)

            # Score por frase (mini timeline)
            ax.text(0.5, 0.30, "Score por frase", ha='center', va='center',
                    fontsize=10, color='#555', transform=ax.transAxes)
            for i, f in enumerate(frases):
                x = 0.08 + (i % 12) * 0.07
                y = 0.25 - (i // 12) * 0.06
                col = SCORE_COLORS.get(f.score, "#aaa")
                ax.text(x, y, f.score, ha='center', va='center',
                        fontsize=9, fontweight='bold', color=col,
                        transform=ax.transAxes,
                        bbox=dict(boxstyle='round,pad=0.2', facecolor='#1a1a1a',
                                  edgecolor=col, linewidth=0.8))

            # Leyenda tipos
            y_ley = 0.10
            ax.text(0.08, y_ley + 0.03, "Tipos:", ha='left', fontsize=9,
                    color='#555', transform=ax.transAxes)
            tipos_ley = ["plateau","vibrato","inestable","portamento","ornamento","melisma"]
            for i, t in enumerate(tipos_ley):
                x = 0.08 + (i % 3) * 0.30
                y = y_ley - (i // 3) * 0.04
                col = TIPO_COLORS.get(t, "#aaa")
                ax.plot([x - 0.02, x], [y, y], color=col, lw=2,
                        transform=ax.transAxes)
                ax.text(x + 0.01, y, t, ha='left', va='center',
                        fontsize=8, color='#aaa', transform=ax.transAxes)

            pdf.savefig(fig, facecolor='#0d0d0d')
            plt.close(fig)

            # ── Páginas de compases ───────────────────────────────────────
            for pag in range(n_paginas):
                c_ini = pag * compases_por_pagina
                c_fin = min(c_ini + compases_por_pagina, n_compases)
                n_c   = c_fin - c_ini

                fig, axes = plt.subplots(n_c, 1,
                                         figsize=(8.5, 11),
                                         squeeze=False)
                fig.patch.set_facecolor('#0d0d0d')
                fig.subplots_adjust(hspace=0.5, top=0.95, bottom=0.05,
                                    left=0.08, right=0.97)

                for ci in range(n_c):
                    compas_idx = c_ini + ci
                    t_ini_c    = compas_idx * compas_s
                    t_fin_c    = t_ini_c + compas_s
                    ax         = axes[ci][0]

                    self._dibujar_compas(
                        ax, t_ini_c, t_fin_c, compas_idx + 1,
                        todos_pl, plateaus_ref,
                        midi_min, midi_max, beat_s, frases
                    )

                pdf.savefig(fig, facecolor='#0d0d0d')
                plt.close(fig)

    def _dibujar_compas(self, ax, t_ini, t_fin, num,
                         plateaus, plateaus_ref,
                         midi_min, midi_max, beat_s, frases):
        ax.set_facecolor('#0d0d0d')
        ax.set_xlim(t_ini, t_fin)
        ax.set_ylim(midi_min - 0.5, midi_max + 0.5)

        # Líneas de beat
        t = t_ini
        while t <= t_fin:
            ax.axvline(t, color='#1a1a1a', lw=0.5, zorder=0)
            t += beat_s

        # Grid de semitonos
        NOTAS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
        for midi in range(midi_min, midi_max + 1):
            nota = NOTAS[midi % 12]
            col  = '#181818' if '#' in nota else '#141414'
            ax.axhspan(midi - 0.5, midi + 0.5, facecolor=col, zorder=0)
            if nota == 'C':
                ax.axhline(midi, color='#2a2a2a', lw=0.8, zorder=1)
                oct_ = midi // 12 - 1
                ax.text(t_ini, midi, f"C{oct_}", fontsize=6,
                        color='#7c83fd', va='center', ha='left')

        # Referencia (azul semitransparente)
        for p in plateaus_ref:
            if p.get('t_fin', 0) < t_ini or p.get('t_inicio', 0) > t_fin:
                continue
            x1 = max(p['t_inicio'], t_ini)
            x2 = min(p['t_fin'],    t_fin)
            ax.barh(p['mediana_midi'], x2 - x1, left=x1,
                    height=0.35, color='#4a7a9b', alpha=0.4, zorder=2)

        # Plateaus de grabación
        for p in plateaus:
            if p.t_fin < t_ini or p.t_inicio > t_fin:
                continue
            x1    = max(p.t_inicio, t_ini)
            x2    = min(p.t_fin,    t_fin)
            tipo  = p.subtipo_arreglo if (p.fusionado and p.subtipo_arreglo) else p.tipo
            color = TIPO_COLORS.get(tipo, '#aaa')
            alpha = 0.40 if (p.fusionado and p.subtipo_arreglo == 'arreglo_undefined') else \
                    0.70 if p.fusionado or p.tipo == 'inestable' else 1.0
            ax.barh(p.mediana_midi, x2 - x1, left=x1,
                    height=0.5, color=color, alpha=alpha, zorder=3)

        # Score de frases que caen en este compás
        for f in frases:
            if f.t_fin < t_ini or f.t_inicio > t_fin:
                continue
            col = SCORE_COLORS.get(f.score, "#aaa")
            ax.text(f.t_inicio + 0.02, midi_max + 0.2, f.score,
                    fontsize=7, fontweight='bold', color=col, zorder=5)
            for i, fb in enumerate(f.feedback or []):
                ax.text(f.t_inicio + 0.02, midi_max - 0.15 - i * 0.3,
                        fb, fontsize=6, color='#ffeb3b', zorder=5)

        # Etiqueta compás
        ax.set_title(f"Compás {num}", fontsize=8, color='#555',
                     loc='left', pad=2)
        ax.tick_params(colors='#333', labelsize=6)
        for spine in ax.spines.values():
            spine.set_edgecolor('#222')

        # Eje Y: solo notas naturales
        NOTAS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
        yticks = [m for m in range(midi_min, midi_max + 1)
                  if '#' not in NOTAS[m % 12]]
        ax.set_yticks(yticks)
        ax.set_yticklabels(
            [f"{NOTAS[m%12]}{m//12-1}" for m in yticks],
            fontsize=6, color='#444'
        )
        ax.set_xlabel('')


# Singleton
_exporter = None

def get_exporter() -> SessionExporter:
    global _exporter
    if _exporter is None:
        _exporter = SessionExporter()
    return _exporter
