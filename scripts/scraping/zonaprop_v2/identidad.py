#!/usr/bin/env python3
"""
identidad.py — Identidad de propiedad y agrupamiento por edificio (v2, dos niveles).

Problema de fondo: ZonaProp enmascara la altura exacta ("Entre Ríos al 400" = cuadra
400-499). Por eso NO se puede identificar la unidad con certeza. Dos deptos distintos
del mismo edificio pueden compartir superficie y ambientes.

Solución de dos niveles (evita tanto el leakage como la pérdida de observaciones):

  1) property_id (CONSERVADOR): identidad estable por posting_id. No fusiona
     publicaciones diferentes sin revisión.

  2) building_cluster_id (LAXO): agrupa todos los avisos de la misma cuadra/edificio.
     Uso: group-aware splitting (train/test). Conservador y seguro contra leakage,
     SIN colapsar unidades distintas. Dos deptos distintos del mismo edificio quedan
     como observaciones separadas pero en el mismo fold.

  3) republication_candidate_id: firma rica de dirección y atributos. Identifica
     candidatos a republicación para auditar, pero no fusiona observaciones.
"""
import hashlib
import re
import unicodedata

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

_ABREV = {
    r'\bbv\.?\b': 'boulevard', r'\bblvd\.?\b': 'boulevard', r'\bbulevar\b': 'boulevard',
    r'\bav\.?\b': 'avenida', r'\bavda\.?\b': 'avenida',
    r'\bpje\.?\b': 'pasaje', r'\bcalle\b': '',
    r'\bnro\.?\b': '', r'\bn°\b': '', r'\bnº\b': '', r'\b#\b': '', r'\bal\b': '',
}

def normalizar_direccion(direccion: str) -> str:
    if not direccion:
        return ''
    s = _strip_accents(str(direccion).lower()).replace(',', ' ')
    for pat, rep in _ABREV.items():
        s = re.sub(pat, rep, s)
    s = re.sub(r'\b(rosario|santa fe|argentina|distrito centro|centro)\b', ' ', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def _cuadra(dir_norm: str):
    """Extrae calle + cuadra (centena). 'entre rios 437' -> ('entre rios', 400)."""
    m = re.search(r'(\d{2,5})', dir_norm)
    if not m:
        return dir_norm, None
    altura = int(m.group(1))
    calle = dir_norm[:m.start()].strip()
    cuadra = (altura // 100) * 100
    return calle, cuadra

def building_cluster_id(prop: dict) -> tuple:
    """Nivel LAXO: calle + cuadra. Para group-aware splitting. Devuelve (id, metodo)."""
    dir_norm = normalizar_direccion(prop.get('direccion_exacta') or prop.get('ubicacion_completa') or '')
    calle, cuadra = _cuadra(dir_norm)
    if calle and cuadra is not None:
        clave = f"bld::{calle}|cuadra::{cuadra}"
        met = 'calle+cuadra'
    elif calle:
        clave = f"bld::{calle}"
        met = 'solo_calle'
    else:
        clave = f"bld_posting::{prop.get('posting_id')}"
        met = 'sin_direccion'
    return 'bld_' + hashlib.sha1(clave.encode()).hexdigest()[:16], met

def _norm_attr(x, kind='num'):
    if x is None: return 'na'
    if kind == 'num':
        try: return str(round(float(x)))
        except (TypeError, ValueError): return 'na'
    return _strip_accents(str(x).lower().strip()) or 'na'

def property_id(prop: dict) -> tuple:
    """
    Identidad conservadora por posting_id. Devuelve (id, método, confianza).
    """
    posting_id = str(prop.get('posting_id'))
    pid = 'prop_' + hashlib.sha1(f"posting::{posting_id}".encode()).hexdigest()[:16]
    return pid, 'posting_id (sin fusión automática)', 'posting'


def republication_candidate_id(prop: dict) -> tuple:
    """Firma de candidatos a republicación; no debe usarse para colapsar filas."""
    dir_norm = normalizar_direccion(prop.get('direccion_exacta') or '')
    calle, cuadra = _cuadra(dir_norm)
    # Atributos discriminantes
    attrs = [
        _norm_attr(prop.get('superficie_total_m2')),
        _norm_attr(prop.get('superficie_cubierta_m2')),
        _norm_attr(prop.get('ambientes')),
        _norm_attr(prop.get('dormitorios')),
        _norm_attr(prop.get('banos')),
        _norm_attr(prop.get('antiguedad'), 'txt'),
        _norm_attr(prop.get('orientacion'), 'txt'),
        _norm_attr(prop.get('disposicion'), 'txt'),
    ]
    n_conocidos = sum(1 for a in attrs if a != 'na')
    # Merge estricto solo si hay dirección-cuadra Y suficientes atributos conocidos (>=5 de 8)
    if calle and cuadra is not None and n_conocidos >= 5:
        clave = f"prop::{calle}|{cuadra}|" + '|'.join(attrs)
        candidate_id = 'repub_' + hashlib.sha1(clave.encode()).hexdigest()[:16]
        return candidate_id, 'dir-cuadra+>=5 attrs', 'candidato'
    return None, 'evidencia insuficiente', 'sin_candidato'
