#!/usr/bin/env python3
"""
features_texto.py — Fase 5: extracción robusta de feat_* desde texto + plausibilidad.

Mejora sobre el extractor actual (str.contains ingenuo): detecta NEGACIONES.
'sin cochera', 'no tiene balcón', 'sin apto crédito' NO deben marcar el atributo.
(K&J 2019: "detectar 'cochera' dentro de 'sin cochera' es un error de adquisición".)

Además: chequeos de plausibilidad que MARCAN (no eliminan) observaciones dudosas.
"""
import re
import unicodedata

# Patrones reutilizados del pipeline actual (extensible)
FEAT_PATRONES = {
    'feat_balcon':          r'balc[oó]n|terraza',
    'feat_parrillero':      r'parrillero|parrilla',
    'feat_lavadero':        r'lavadero',
    'feat_amenities':       r'amenities?',
    'feat_patio':           r'\bpatio\b',
    'feat_seguridad':       r'seguridad|porter[ií]a|vigilancia',
    'feat_pileta':          r'pileta|piscina',
    'feat_financiacion':    r'financiaci[oó]n|cr[eé]dito|hipoteca',
    'feat_sum':             r'\bsum\b|sal[oó]n de usos',
    'feat_solarium':        r'solarium',
    'feat_apto_credito':    r'apto cr[eé]dito|apto para cr[eé]dito',
    'feat_vista_rio':       r'vista al r[ií]o|vista r[ií]o|costanera',
    'feat_litoral_gas':     r'gas natural|litoral gas',
    'feat_piso_alto':       r'piso alto|vista panor[aá]mica',
    'feat_a_estrenar':      r'a estrenar|\bestrenar\b',
    'feat_permite_mascotas':r'mascotas|pet friendly',
    'feat_cochera':         r'cochera|garage|garaje',
    'feat_ascensor':        r'ascensor',
    'feat_amoblado':        r'amoblad[oa]|amueblad[oa]',
}

# Términos de negación (aparecen ANTES del atributo, dentro de una ventana corta)
NEGACIONES = r'(?:sin|no|ning[uú]n|ninguna|carece de|no cuenta con|no incluye|no posee|no tiene|falta de|no dispone de)'
VENTANA = 25   # caracteres hacia atrás para buscar negación

def _norm(t: str) -> str:
    return re.sub(r'\s+', ' ', str(t or '').lower()).strip()

def _negado(texto: str, inicio_match: int) -> bool:
    """True si hay una negación en la ventana previa al match (misma cláusula)."""
    ini = max(0, inicio_match - VENTANA)
    ventana = texto[ini:inicio_match]
    # cortar en signos de puntuación fuerte (la negación no cruza cláusulas)
    ventana = re.split(r'[.;,!?]', ventana)[-1]
    return re.search(rf'\b{NEGACIONES}\b[\w\s]*$', ventana) is not None

def extraer_features(texto: str) -> dict:
    """Devuelve {feat_x: 0/1}. Un atributo se marca 1 solo si hay al menos una
    mención NO negada."""
    t = _norm(texto)
    out = {}
    for feat, patron in FEAT_PATRONES.items():
        val = 0
        for m in re.finditer(patron, t):
            if not _negado(t, m.start()):
                val = 1
                break
        out[feat] = val
    return out

# ── Chequeos de plausibilidad (MARCAN, no eliminan) ───────────────────────────
RANGOS = dict(
    precio_usd=(10_000, 2_000_000),
    superficie_m2=(15, 500),
    precio_m2=(300, 6_000),
    ambientes=(1, 12),
)

def chequear_plausibilidad(prop: dict) -> list:
    """Devuelve lista de flags (strings). No elimina nada."""
    flags = []
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    precio = num(prop.get('precio_valor')); sup = num(prop.get('superficie_total_m2') or prop.get('superficie_m2'))
    supc = num(prop.get('superficie_cubierta_m2')); amb = num(prop.get('ambientes'))
    if precio is not None and not (RANGOS['precio_usd'][0] <= precio <= RANGOS['precio_usd'][1]):
        flags.append('precio_fuera_rango')
    if sup is not None and not (RANGOS['superficie_m2'][0] <= sup <= RANGOS['superficie_m2'][1]):
        flags.append('superficie_fuera_rango')
    if precio and sup:
        pm2 = precio / sup
        if not (RANGOS['precio_m2'][0] <= pm2 <= RANGOS['precio_m2'][1]):
            flags.append('precio_m2_fuera_rango')
    if amb is not None and not (RANGOS['ambientes'][0] <= amb <= RANGOS['ambientes'][1]):
        flags.append('ambientes_fuera_rango')
    if sup and supc and supc > sup + 1:
        flags.append('sup_cubierta_mayor_que_total')
    if prop.get('precio_moneda') and prop.get('precio_moneda') != 'USD':
        flags.append('moneda_no_usd')
    return flags
