#!/usr/bin/env python3
"""config.py — Configuración del scraper v2."""
import os
from datetime import datetime, timezone

# Rutas
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
# Carpeta con zonaprop_extractor.py / zonaprop_scraper.py (a reutilizar).
# Si están en esta misma carpeta (repo), se usa BASE_DIR; si no, la ubicación original.
LEGACY_DIR = (BASE_DIR if os.path.exists(os.path.join(BASE_DIR, 'zonaprop_extractor.py'))
              else os.path.abspath(os.path.join(BASE_DIR, '..', 'tasaprop_para_Enrique')))
OUT_DIR    = os.path.join(BASE_DIR, 'salida')
DB_PATH    = os.path.join(OUT_DIR, 'zonaprop_v2.db')
LOG_PATH   = os.path.join(OUT_DIR, 'scraping.log')

# Zona objetivo
# ZonaProp canonicaliza 'rosario-distrito-centro' -> 'rosario-centro-rosario' (misma zona).
ZONA_SLUG     = 'rosario-distrito-centro'   # para bounds / filter_out_of_zone (está mapeado)
ZONA_SLUG_URL = 'rosario-centro-rosario'    # slug canónico para construir las URLs (sin redirect)
ZONA_LABEL = 'Rosario · Distrito Centro'
ANTIGUEDAD_SLUG  = ''
ANTIGUEDAD_LABEL = 'Sin filtro'
AMBIENTES = [
    (1, '1 ambiente',        '1-ambiente'),
    (2, '2 ambientes',       '2-ambientes'),
    (3, '3 ambientes',       '3-ambientes'),
    (4, '4 ambientes',       '4-ambientes'),
    (5, '5 ambientes o más', '5-ambientes-o-mas'),
]

# Robustez
DELAY_DETALLE   = 1.5      # segundos entre requests de detalle (cortesía)
MAX_REINTENTOS  = 3
BACKOFF_BASE    = 5.0      # segundos, exponencial

# ── Particionado por bandas de precio (para superar el tope de ~9 páginas) ────
MAX_PAGINAS = 9           # tope seguro de páginas por consulta (antes del bloqueo)
CAP_SATURACION = 260      # si una banda trae >= esto, se considera saturada -> subdividir
MIN_ANCHO_BANDA = 2000    # USD: no subdividir bandas más angostas que esto
MONEDA = 'dolar'
# Bandas iniciales en USD (se subdividen solas si saturan)
BANDAS_PRECIO = [
    (0, 35000), (35000, 45000), (45000, 55000), (55000, 65000),
    (65000, 80000), (80000, 100000), (100000, 130000), (130000, 180000),
    (180000, 300000), (300000, 10_000_000),
]

def build_url_precio(zona_slug, amb_slug, pmin, pmax):
    """URL de ZonaProp con filtro de banda de precio en USD.
    Formato: departamentos-venta-{zona}-{amb}-{min}-{max}-dolar.html"""
    return (f'https://www.zonaprop.com.ar/departamentos-venta-'
            f'{zona_slug}-{amb_slug}-{int(pmin)}-{int(pmax)}-{MONEDA}.html')

def nuevo_run_id():
    return 'run_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
