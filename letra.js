/**
 * LETRA.JS — Silabización y render de letra karaoke
 * Vista teleprompter: línea anterior / actual / siguiente
 * Coloreo por tiempo con barra de carga por sílaba
 */

let _lineas   = [];
let _letraRAF = null;

// ── Silabización ─────────────────────────────────────────────────────────────

function silabizar(palabra) {
  const vocales = /[aeiouáéíóúüAEIOUÁÉÍÓÚÜ]/;
  const sils = [];
  let actual = '';
  for (let i = 0; i < palabra.length; i++) {
    const c = palabra[i], sig = palabra[i+1];
    actual += c;
    if (vocales.test(c) && sig && !vocales.test(sig) && i+2 < palabra.length && vocales.test(palabra[i+2])) {
      sils.push(actual); actual = '';
    } else if (vocales.test(c) && sig && vocales.test(sig)) {
      sils.push(actual); actual = '';
    }
  }
  if (actual) sils.push(actual);
  return sils.length > 0 ? sils : [palabra];
}

function tiemposSilabas(silabas, t_ini, t_fin) {
  const dur  = (t_fin - t_ini) / silabas.length;
  return silabas.map((_, i) => ({ t_ini: t_ini + i * dur, t_fin: t_ini + (i+1) * dur }));
}

function durClass(dur) {
  const beat  = window._beatS || 0.5;
  const beats = dur / beat;
  if (beats < 0.5) return 'dur-corto';
  if (beats < 1.5) return 'dur-medio';
  return 'dur-largo';
}

// ── Preparación de líneas ─────────────────────────────────────────────────────

function prepararLineas(palabras) {
  if (!palabras?.length) return;
  _lineas = [];
  let linea = [];

  for (let i = 0; i < palabras.length; i++) {
    const p   = palabras[i];
    const sig = palabras[i+1];
    const sils   = silabizar(p.word);
    const tSils  = tiemposSilabas(sils, p.start, p.end);
    linea.push({ texto: p.word, silabas: sils, tiempos: tSils, t_ini: p.start, t_fin: p.end });
    const pausa = sig ? sig.start - p.end : 99;
    if (linea.length >= 5 || pausa > 1.0) {
      _lineas.push({ palabras: linea, t_ini: linea[0].t_ini, t_fin: linea[linea.length-1].t_fin });
      linea = [];
    }
  }
  if (linea.length > 0)
    _lineas.push({ palabras: linea, t_ini: linea[0].t_ini, t_fin: linea[linea.length-1].t_fin });
}

// ── Render ────────────────────────────────────────────────────────────────────

function arrancarLetra() {
  document.getElementById('letra-wrap').style.display = 'flex';
  if (_letraRAF) cancelAnimationFrame(_letraRAF);
  _tickLetra();
}

function detenerLetra() {
  if (_letraRAF) { cancelAnimationFrame(_letraRAF); _letraRAF = null; }
  document.getElementById('letra-wrap').style.display = 'none';
}

function _tickLetra() {
  if (!window._audioCtxRef || !window._instrStartTime) {
    _letraRAF = requestAnimationFrame(_tickLetra); return;
  }
  const t = window._audioCtxRef.currentTime - window._instrStartTime;
  _renderLetra(t);
  _letraRAF = requestAnimationFrame(_tickLetra);
}

function _renderLetra(t) {
  if (!_lineas.length) return;

  // Línea actual — mantener última visible en silencio
  let idxCurr = _lineas.findIndex(l => t >= l.t_ini && t < l.t_fin);
  if (idxCurr === -1) {
    const pasadas = _lineas.filter(l => t >= l.t_fin);
    idxCurr = pasadas.length > 0 ? _lineas.indexOf(pasadas[pasadas.length-1]) : 0;
  }

  const prev = _lineas[idxCurr - 1];
  const curr = _lineas[idxCurr];
  const next = _lineas[idxCurr + 1];

  document.getElementById('letra-linea-prev').textContent =
    prev ? prev.palabras.map(p => p.texto).join(' ') : '';
  document.getElementById('letra-linea-next').textContent =
    next ? next.palabras.map(p => p.texto).join(' ') : '';

  const currEl = document.getElementById('letra-linea-curr');
  if (!curr) { currEl.innerHTML = ''; return; }

  // Próxima sílaba para color de duración
  let proxSil = null;
  outer: for (const pal of curr.palabras) {
    for (let i = 0; i < pal.silabas.length; i++) {
      if (pal.tiempos[i].t_ini > t) { proxSil = pal.tiempos[i]; break outer; }
    }
  }

  currEl.innerHTML = curr.palabras.map(pal => {
    const silsHTML = pal.silabas.map((sil, i) => {
      const ts  = pal.tiempos[i];
      const dur = ts.t_fin - ts.t_ini;
      let cls = 'silaba', barraHTML = '';

      if (t >= ts.t_fin) {
        cls += ' pasada';
      } else if (t >= ts.t_ini) {
        cls += ' activa';
        const pct = Math.min(100, ((t - ts.t_ini) / dur) * 100);
        barraHTML = `<div class="silaba-barra-wrap">
          <div class="silaba-barra ${durClass(dur)}" style="width:${pct}%"></div>
        </div>`;
      } else if (proxSil && ts.t_ini === proxSil.t_ini) {
        cls += ` ${durClass(dur)}`;
        barraHTML = `<div class="silaba-barra-wrap">
          <div class="silaba-barra ${durClass(dur)}" style="width:0%"></div>
        </div>`;
      }
      return `<span class="${cls}">${sil}${barraHTML}</span>`;
    }).join('');
    return silsHTML;
  }).join('<span style="display:inline-block;width:6px"></span>');
}
