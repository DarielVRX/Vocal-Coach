"""
DIAGNÓSTICO — Genera informe global desde frases de la sesión
"""

import numpy as np
from analyzer import Frase, frase_a_dict, DIAG, calcular_score
from pipeline import inferir_escala, calificar, INTERVALOS_ESCALA, nota_en_escala


def generar_diagnostico(frases: list[Frase]) -> dict:
    if not frases:
        return {"frases": [], "diagnostico": None}

    todos_plateaus = [p for f in frases for p in f.plateaus
                      if p.tipo in ("plateau", "vibrato")]

    if not todos_plateaus:
        return {"frases": _serializar_frases(frases), "diagnostico": None}

    cents_vals  = [abs(p.cents) for p in todos_plateaus]
    estab_vals  = [p.varianza_f0 for p in todos_plateaus]
    midis_todos = [p.mediana_midi for p in todos_plateaus]

    cents_prom = float(np.mean(cents_vals))
    estab_prom = float(np.mean(estab_vals))

    escala_global = inferir_escala(midis_todos, DIAG["min_notas_escala"])
    escala_str    = None
    pct_en_escala = None

    if escala_global:
        escala_str = f"{escala_global['tonica']} {escala_global['nombre']}"
        intervalos = INTERVALOS_ESCALA.get(escala_global["nombre"], [])
        en_escala  = [nota_en_escala(m, escala_global["tonica"], intervalos)
                      for m in midis_todos]
        pct_en_escala = round(sum(en_escala) / len(en_escala) * 100, 1) if en_escala else None

    tipo_counts = {}
    for p in [p for f in frases for p in f.plateaus]:
        tipo_counts[p.tipo] = tipo_counts.get(p.tipo, 0) + 1

    cal_global = {
        "afinacion"  : calificar(cents_prom,
                                  DIAG["cents_excelente"], DIAG["cents_ok"], DIAG["cents_malo"]),
        "estabilidad": calificar(estab_prom,
                                  DIAG["estabilidad_ex"], DIAG["estabilidad_ok"],
                                  DIAG["estabilidad_mal"]),
    }

    scores      = {"Excelente": 4, "Ok": 3, "Malo": 2, "Pésimo": 1}
    score_total = sum(scores[v] for v in cal_global.values()) / len(cal_global)
    cal_general = ["Pésimo","Malo","Ok","Excelente"][max(0, min(3, int(score_total)-1))]
    score_global = calcular_score(cents_prom, estab_prom)

    return {
        "frases"     : _serializar_frases(frases),
        "diagnostico": {
            "n_frases"        : len(frases),
            "n_plateaus"      : len(todos_plateaus),
            "escala_dominante": escala_str,
            "escala_confianza": escala_global["confianza"] if escala_global else None,
            "pct_en_escala"   : pct_en_escala,
            "cents_promedio"  : round(cents_prom, 1),
            "estab_promedio"  : round(estab_prom, 4),
            "tipo_counts"     : tipo_counts,
            "cal"             : cal_global,
            "cal_general"     : cal_general,
            "score_global"    : score_global,
        }
    }


def _serializar_frases(frases: list[Frase]) -> list[dict]:
    return [frase_a_dict(f) for f in frases]
