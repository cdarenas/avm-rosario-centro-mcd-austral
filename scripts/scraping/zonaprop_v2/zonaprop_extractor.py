#!/usr/bin/env python3
"""
JOSHUA — Agente de Extracción de Propiedades · ZonaProp

Uso:
    python zonaprop_tui.py

Dependencias adicionales:
    pip install rich questionary
"""

# Suprimir warnings de dependencias (ej. requests/charset_normalizer)
# antes de cualquier import para evitar output inesperado en la TUI.
import warnings
warnings.filterwarnings("ignore")

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime


# ─── Verificar dependencias ──────────────────────────────────────────────────

def _check_deps():
    missing = []
    for pkg, imp in [("rich", "rich"), ("questionary", "questionary"),
                     ("cloudscraper", "cloudscraper"), ("pandas", "pandas"),
                     ("beautifulsoup4", "bs4"), ("lxml", "lxml")]:
        try:
            __import__(imp)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"\n  [!] Dependencias faltantes: {', '.join(missing)}")
        print(f"  Instalá con:  pip install {' '.join(missing)}\n")
        sys.exit(1)

_check_deps()

# ─── Imports ─────────────────────────────────────────────────────────────────

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.columns import Columns
from rich.progress import (Progress, SpinnerColumn, TextColumn,
                            BarColumn, TaskProgressColumn, TimeElapsedColumn)
from rich.align import Align
from rich.rule import Rule
from rich.layout import Layout
from rich.live import Live
from rich import box as rbox
import questionary
from questionary import Style as QStyle
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from zonaprop_scraper import ZonapropScraper


# ─── Constantes ──────────────────────────────────────────────────────────────

VERSION = "1.0.0"

ZONAS = {
    "Rosario · Distrito Norte":    "rosario-distrito-norte",
    "Rosario · Distrito Noroeste": "rosario-distrito-noroeste",
    "Rosario · Distrito Oeste":    "rosario-distrito-oeste",
    "Rosario · Distrito Centro":   "rosario-distrito-centro",
    "Rosario · Distrito Sudoeste": "rosario-distrito-sudoeste",
    "Rosario · Distrito Sur":      "rosario-distrito-sur",
}

AMBIENTES_OPTS = [
    "1 ambiente",
    "2 ambientes",
    "3 ambientes",
    "4 ambientes",
    "5 ambientes o más",
]

AMBIENTES_SLUG = {
    "1 ambiente":        "1-ambiente",
    "2 ambientes":       "2-ambientes",
    "3 ambientes":       "3-ambientes",
    "4 ambientes":       "4-ambientes",
    "5 ambientes o más": "5-ambientes-o-mas",
}

ANTIGUEDAD_OPTS = [
    "Sin filtro",
    "Desde hoy",
    "Desde ayer",
    "Última semana",
    "Últimos 15 días",
    "Últimos 30 días",
    "Últimos 45 días",
]

# Slugs verificados contra URLs reales de ZonaProp (testeados uno a uno).
ANTIGUEDAD_SLUG = {
    "Sin filtro":      "",
    "Desde hoy":       "-publicado-hace-menos-de-1-dia",
    "Desde ayer":      "-publicado-hace-menos-de-2-dias",
    "Última semana":   "-publicado-hace-menos-de-1-semana",
    "Últimos 15 días": "-publicado-hace-menos-de-15-dias",
    "Últimos 30 días": "-publicado-hace-menos-de-1-mes",
    "Últimos 45 días": "-publicado-hace-menos-de-45-dias",
}

FORMATO_OPTS = ["CSV", "JSON", "CSV + JSON"]

# Bounding boxes por zona: (lat_min, lat_max, lon_min, lon_max)
# Basado en los límites reales de los distritos municipales de Rosario.
# Se aplica una tolerancia de ±0.005° (~500 m) para no filtrar propiedades
# ubicadas exactamente en el borde de un distrito.
ZONA_BOUNDS = {
    "rosario-distrito-norte":    (-32.900, -32.810, -60.760, -60.610),
    "rosario-distrito-noroeste": (-32.920, -32.835, -60.800, -60.635),
    "rosario-distrito-oeste":    (-33.035, -32.900, -60.800, -60.625),
    "rosario-distrito-centro":   (-32.960, -32.885, -60.670, -60.575),
    "rosario-distrito-sudoeste": (-33.030, -32.930, -60.680, -60.610),
    "rosario-distrito-sur":      (-33.045, -32.975, -60.745, -60.575),
}

# ─── Colores ─────────────────────────────────────────────────────────────────

GREEN       = "bright_green"
DIM_GREEN   = "green"
DARK_GREEN  = "dark_green"
BG          = "on black"


# ─── Polígonos de distritos (coordenadas SVG 400×415 px) ─────────────────────
# Extraídos del SVG oficial de distritos de Rosario.
# Las curvas Bézier están aproximadas como segmentos rectos intermedios.

_POLY = {
    # path65153 (#51bdaa) — franja norte, límite con Santa Fe
    "rosario-distrito-norte": [
        (235.3, 166.8),
        (165.7,  77.8),
        (112.7,  95.0),
        ( 77.7,  94.7),
        ( 85.6,  77.9),
        ( 79.0,  78.0),
        ( 79.2,  57.2),
        ( 62.1,  57.2),
        ( 62.1,  32.4),
        (230.7,  32.1),
        (232.5,  49.6),
        (232.7,  73.0),
        (237.7,  90.5),
        (242.6, 100.7),
        (246.3, 110.3),
        (251.1, 120.8),
        (258.3, 131.6),
        (262.4, 138.7),
        (266.4, 145.5),
        (270.4, 151.2),
        (274.9, 157.7),
        (280.7, 162.3),
        (287.0, 165.3),
        (298.3, 170.4),
    ],
    # path66078 (#a68fbd) — sector noroeste (interior norte)
    "rosario-distrito-noroeste": [
        ( 31.9,  77.8),
        ( 69.4, 137.7),
        ( 94.2, 144.8),
        ( 92.7, 148.3),
        ( 86.2, 163.8),
        ( 79.7, 170.1),
        ( 69.4, 180.0),
        ( 61.8, 189.2),
        ( 49.0, 197.5),
        ( 90.0, 197.3),
        ( 90.0, 203.9),
        (138.5, 203.9),
        (138.7, 207.2),
        (164.1, 207.2),
        (164.1, 199.1),
        (217.1, 200.8),
        (216.6, 173.9),
        (249.8, 183.8),
        (165.1,  78.3),
    ],
    # path64243 (#fbbd81) — franja central costera (Río Paraná)
    "rosario-distrito-centro": [
        (350.5, 261.5),
        (350.9, 255.2),
        (349.3, 248.8),
        (348.3, 241.8),
        (346.0, 235.7),
        (342.5, 224.0),
        (336.1, 215.6),
        (333.5, 201.3),
        (327.4, 190.4),
        (316.7, 184.9),
        (307.1, 177.4),
        (302.7, 173.8),
        (298.5, 170.6),
        (235.8, 167.2),
        (249.8, 183.8),
        (217.0, 174.5),
        (217.1, 201.2),
        (271.0, 214.0),
        (262.2, 257.5),
        (302.2, 267.8),
        (307.1, 250.3),
    ],
    # path67874 (#fde18b) — sector oeste (interior central-sur)
    "rosario-distrito-oeste": [
        ( 89.7, 203.9),
        ( 90.0, 236.1),
        (142.5, 236.1),
        (135.2, 275.2),
        (149.3, 330.7),
        (159.3, 331.0),
        (168.0, 350.0),
        (177.0, 369.0),
        (193.0, 390.0),
        (201.0, 403.3),
        (215.4, 393.7),
        (218.9, 274.2),
        (226.9, 248.8),
        (262.1, 257.4),
        (270.9, 214.0),
        (216.7, 200.8),
        (176.5, 199.4),
        (164.0, 198.9),
        (164.0, 206.9),
        (138.3, 206.9),
        (138.3, 204.0),
    ],
    # path68779 (#f99e7e) — sector sudoeste (interior sur)
    "rosario-distrito-sudoeste": [
        (215.6, 393.7),
        (218.8, 274.3),
        (226.9, 248.8),
        (271.9, 260.0),
        (259.7, 305.7),
        (285.5, 335.7),
        (274.3, 381.6),
        (270.3, 380.9),
        (266.4, 379.6),
        (246.2, 381.5),
        (225.0, 384.1),
        (220.9, 388.1),
        (218.1, 392.4),
    ],
    # path69684 (#7389c1) — franja sur costera (Río Paraná)
    "rosario-distrito-sur": [
        (274.4, 381.3),
        (285.5, 335.6),
        (259.8, 305.7),
        (271.9, 260.0),
        (302.3, 267.8),
        (307.0, 250.2),
        (350.5, 261.3),
        (352.3, 290.0),
        (352.3, 315.1),
        (348.8, 329.1),
        (339.0, 333.0),
        (332.1, 334.2),
        (318.0, 344.0),
        (311.3, 353.2),
        (300.0, 362.0),
        (294.1, 367.7),
        (282.0, 375.0),
    ],
}

# Nombre de cada distrito (para etiqueta centrada en el mapa)
_POLY_LABEL = {
    "rosario-distrito-norte":    "NORTE",
    "rosario-distrito-noroeste": "NOROESTE",
    "rosario-distrito-oeste":    "OESTE",
    "rosario-distrito-centro":   "CENTRO",
    "rosario-distrito-sudoeste": "SUDOESTE",
    "rosario-distrito-sur":      "SUR",
}


# ─── Motor de renderizado de polígonos ───────────────────────────────────────

def _point_in_polygon(px: float, py: float, polygon: list) -> bool:
    """Ray-casting: True si (px, py) está dentro del polígono."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and \
                (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _render_district(points: list, max_cols: int = 44, max_rows: int = 20,
                     label: str = "") -> tuple:
    """
    Rasteriza el polígono sobre una grilla de texto.
    Compensa el aspect ratio del terminal (caracteres ~2× más altos que anchos).

    Devuelve (filas: list[str], cols: int, rows: int).
    Caracteres usados:
      '·' → borde del polígono   (bright_green)
      '░' → relleno interior     (dark_green)
      ' ' → exterior             (sin estilo)
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    svg_w = max_x - min_x
    svg_h = max_y - min_y

    # Aspecto visual real de la figura vs. aspecto de los chars (~0.5)
    CHAR_ASPECT = 0.5
    vis_ratio   = svg_w / svg_h

    cols = max_cols
    rows = max(4, int(cols * CHAR_ASPECT / vis_ratio))
    if rows > max_rows:
        rows = max_rows
        cols = max(4, min(max_cols, int(rows * vis_ratio / CHAR_ASPECT)))

    grid = [[' '] * cols for _ in range(rows)]

    def tc(x): return int((x - min_x) / svg_w * (cols - 1))
    def tr(y): return int((y - min_y) / svg_h * (rows - 1))

    def _line(c0, r0, c1, r1):
        dx = abs(c1 - c0); dy = abs(r1 - r0)
        sc = 1 if c0 < c1 else -1
        sr = 1 if r0 < r1 else -1
        err = dx - dy
        while True:
            if 0 <= c0 < cols and 0 <= r0 < rows:
                grid[r0][c0] = '·'
            if c0 == c1 and r0 == r1:
                break
            e2 = 2 * err
            if e2 > -dy: err -= dy; c0 += sc
            if e2 <  dx: err += dx; r0 += sr

    n = len(points)
    for i in range(n):
        _line(tc(points[i][0]),         tr(points[i][1]),
              tc(points[(i+1) % n][0]), tr(points[(i+1) % n][1]))

    # Relleno interior
    for row in range(rows):
        for col in range(cols):
            if grid[row][col] == ' ':
                sx = min_x + (col / (cols - 1)) * svg_w
                sy = min_y + (row / (rows - 1)) * svg_h
                if _point_in_polygon(sx, sy, points):
                    grid[row][col] = '░'

    # Etiqueta del distrito centrada en la fila media
    if label:
        mid_r = rows // 2
        interior = [c for c in range(cols) if grid[mid_r][c] != ' ']
        if interior:
            c0 = interior[0]; c1 = interior[-1]
            lbl = f' {label} '
            if len(lbl) <= (c1 - c0 + 1):
                off = c0 + (c1 - c0 + 1 - len(lbl)) // 2
                for k, ch in enumerate(lbl):
                    if 0 <= off + k < cols and grid[mid_r][off + k] != '·':
                        grid[mid_r][off + k] = ch

    return [''.join(r) for r in grid], cols, rows


# ─── Mapa ASCII estilo WarGames ───────────────────────────────────────────────

def zona_ascii_map(zona_slug: str) -> Text:
    """
    Dibuja la forma real del distrito seleccionado al estilo WOPR/WarGames (1983).
    Muestra el polígono del distrito con relleno ░, borde ·, nombre centrado
    y coordenadas cardinales alrededor del mapa.
    """
    t = Text(no_wrap=True)

    poly   = _POLY.get(zona_slug)
    label  = _POLY_LABEL.get(zona_slug, "")
    bounds = ZONA_BOUNDS.get(zona_slug)

    if not poly or not bounds:
        # Fallback: texto con coordenadas si no hay polígono
        t.append(f"  {label}\n", style=f"bold {GREEN}")
        if bounds:
            lat_min, lat_max, lon_min, lon_max = bounds
            t.append(
                f"  N {lat_max:.3f}°  S {lat_min:.3f}°  "
                f"O {lon_min:.3f}°  E {lon_max:.3f}°\n",
                style=DIM_GREEN,
            )
        return t

    lat_min, lat_max, lon_min, lon_max = bounds
    art, map_w, map_h = _render_district(poly, label=label)
    mid = map_h // 2

    LEFT_W = 14   # ancho de la columna izquierda (etiquetas O/lat)

    # ── Latitud norte (encabezado) ─────────────────────────────────────────
    n_lbl = f"N  {lat_max:.3f}°"
    t.append(f"{'':>{LEFT_W}}  {n_lbl:^{map_w}}\n", style=DIM_GREEN)

    # ── Filas del mapa ─────────────────────────────────────────────────────
    for i, row in enumerate(art):
        # Columna izquierda: lon O en fila media, espacios en las demás
        if i == mid:
            left_lbl = f"O {lon_min:.3f}°"
            t.append(f"{left_lbl:>{LEFT_W}}  ", style=DIM_GREEN)
        else:
            t.append(f"{'':>{LEFT_W}}  ", style=DIM_GREEN)

        # Renderizar cada carácter con su estilo
        for ch in row:
            if ch == '·':
                t.append(ch, style=f"bold {GREEN}")
            elif ch == '░':
                t.append(ch, style=DARK_GREEN)
            elif ch == ' ':
                t.append(ch)
            else:
                # Texto del label del distrito
                t.append(ch, style=f"bold {GREEN}")

        # Columna derecha: lon E en fila media + río en todas las filas
        if i == mid:
            t.append(f"  {lon_max:.3f}° E", style=DIM_GREEN)
        t.append("  ≋≋\n", style=DARK_GREEN)

    # ── Latitud sur (pie) ──────────────────────────────────────────────────
    s_lbl = f"S  {lat_min:.3f}°"
    t.append(f"{'':>{LEFT_W}}  {s_lbl:^{map_w}}\n", style=DIM_GREEN)

    # ── Etiqueta del río ───────────────────────────────────────────────────
    t.append(
        f"{'≋≋  RÍO PARANÁ':>{LEFT_W + map_w + 6}}\n",
        style=DARK_GREEN,
    )

    return t


# ─── Estilo questionary (retro verde terminal) ────────────────────────────────

Q_STYLE = QStyle([
    ("qmark",       "fg:#00ff41 bold"),
    ("question",    "fg:#c8ffc8 bold"),
    ("answer",      "fg:#00ff41 bold"),
    ("pointer",     "fg:#00ff41 bold"),
    ("highlighted", "fg:#00ff41 bold"),
    ("selected",    "fg:#39ff14"),
    ("separator",   "fg:#1a3a1a"),
    ("instruction", "fg:#4a7a4a italic"),
    ("text",        "fg:#a0ffa0"),
    ("disabled",    "fg:#2a5a2a italic"),
])


# ─── ASCII Art JOSHUA (ANSI Shadow font) ─────────────────────────────────────

LOGO = r"""
     ██╗ ██████╗ ███████╗██╗  ██╗██╗   ██╗ █████╗
     ██║██╔═══██╗██╔════╝██║  ██║██║   ██║██╔══██╗
     ██║██║   ██║███████╗███████║██║   ██║███████║
██   ██║██║   ██║╚════██║██╔══██║██║   ██║██╔══██║
╚█████╔╝╚██████╔╝███████║██║  ██║╚██████╔╝██║  ██║
 ╚════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝"""

SUBTITLE = "by Grupo 3  ·  MCD  ·  Universidad Austral"


def make_logo_text() -> Text:
    """Logo JOSHUA con subtítulo institucional en letra pequeña/tenue."""
    t = Text(no_wrap=True)
    t.append(LOGO, style=f"bold {GREEN}")
    t.append(f"\n{'':>12}{SUBTITLE}", style=f"dim {DIM_GREEN} italic")
    return t


# ─── Console ─────────────────────────────────────────────────────────────────

console = Console()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def timestamp_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


def build_url(zona_slug: str, ambientes_slug: str, antiguedad_slug: str) -> str:
    base = f"https://www.zonaprop.com.ar/departamentos-venta-{zona_slug}-{ambientes_slug}"
    if antiguedad_slug:
        base += antiguedad_slug
    return base + ".html"


# ─── Localizador geográfico por barrio/distrito ───────────────────────────────

# Intento de importar geopandas (dependencia opcional).
# Si no está disponible, el enriquecimiento se omite sin romper el flujo.
try:
    import geopandas as _gpd
    from shapely.geometry import Point as _Point
    _GEO_AVAILABLE = True
except ImportError:
    _GEO_AVAILABLE = False


class RosarioLocator:
    """
    Enriquece cada propiedad con su barrio oficial y distrito municipal
    usando el GeoJSON de polígonos de Rosario.

    Usa geopandas + índice espacial STRtree para consultas rápidas,
    y procesamiento por lotes (sjoin) para datasets completos.

    Si geopandas no está instalado, todos los métodos devuelven None/None
    sin lanzar excepciones.
    """

    # ── Mapeo slug de zona → nombre corto de distrito ─────────────────────────
    _SLUG_TO_DISTRITO: dict = {
        "rosario-distrito-norte":    "Norte",
        "rosario-distrito-noroeste": "Noroeste",
        "rosario-distrito-oeste":    "Oeste",
        "rosario-distrito-centro":   "Centro",
        "rosario-distrito-sudoeste": "Sudoeste",
        "rosario-distrito-sur":      "Sur",
    }

    # ── Alias de ZonaProp → nombre canónico del GeoJSON ───────────────────────
    # ZonaProp usa nombres populares/comerciales que no siempre coinciden
    # con los nombres oficiales del GeoJSON municipal.
    ZONAPROP_ALIAS: dict = {
        "Abasto":                         "Barrio del Abasto",
        "Agote":                          "Luis Agote",
        "Lourdes":                        "Nuestra Sra. de Lourdes",
        "Nuestra Señora de Lourdes":      "Nuestra Sra. de Lourdes",
        "Nuestra Sra. de la Guardia":     "Nuestra Sra. de la Guardia",
        "La Guardia":                     "Nuestra Sra. de la Guardia",
        "Gral. José de San Martín":       "Gral. José de San Martín",
        "General José de San Martín":     "Gral. José de San Martín",
        "España y Hospitales":            "España y Hospitales",
        "Esteban Echeverría":             "Esteban Echeverría",
        "Luis Agote":                     "Luis Agote",
        "Alberto Olmedo":                 "Alberto Olmedo",
    }

    # ── Barrios populares que NO están en el GeoJSON → distrito directo ────────
    # Nombres usados por ZonaProp, portales inmobiliarios o vecinos, que no
    # corresponden a barrios oficiales del mapa municipal.
    EXTRA_BARRIOS: dict = {
        # ── Norte ─────────────────────────────────────────────────────────────
        "Arroyito":          "Norte",
        "La Florida":        "Norte",
        "Alberdi":           "Norte",   # también en GeoJSON pero por si acaso
        # ── Noroeste ──────────────────────────────────────────────────────────
        "Fisherton":         "Noroeste",
        "Belgrano":          "Noroeste",
        # ── Centro ────────────────────────────────────────────────────────────
        "Pichincha":         "Centro",  # borde Centro/Sur; convencionalmente Centro
        "Echesortu":         "Centro",  # zona de Bv. Oroño, catalogado como Centro
        "República":         "Centro",
        "Lourdes":           "Centro",
        # ── Oeste ─────────────────────────────────────────────────────────────
        "Empalme Graneros":  "Noroeste",
        "Ludueña":           "Noroeste",
        # ── Sur ───────────────────────────────────────────────────────────────
        "Saladillo":         "Sur",
        "Echevarría":        "Sur",
    }

    # Mapeo completo barrio (GeoJSON) → distrito municipal.
    # Basado en los nombres exactos del archivo rosario_barrios.geojson.
    BARRIO_TO_DISTRITO: dict = {
        # ── NORTE ─────────────────────────────────────────────────────────────
        "Alberdi":                         "Norte",
        "Domingo Faustino Sarmiento":      "Norte",
        "Lisandro de la Torre":            "Norte",

        # ── NOROESTE ──────────────────────────────────────────────────────────
        "Belgrano":                        "Noroeste",
        "Celedonio Escalada":              "Noroeste",
        'Docente "Hermanas Cossettini"':   "Noroeste",
        "Fisherton":                       "Noroeste",
        "José Ignacio Rucci":              "Noroeste",
        "La Cerámica y Cuyo":             "Noroeste",
        "Larrea y Empalme Graneros":       "Noroeste",
        "Ludueña Sur y Norte":            "Noroeste",
        "Parque Field":                    "Noroeste",

        # ── CENTRO ────────────────────────────────────────────────────────────
        "Alberto Olmedo":                  "Centro",
        "Barrio del Abasto":              "Centro",
        "Centro":                          "Centro",
        "Luis Agote":                      "Centro",
        "Nuestra Sra. de Lourdes":        "Centro",
        "Nuestra Sra. de la Guardia":     "Centro",
        "República de la 6 ta.":          "Centro",

        # ── OESTE ─────────────────────────────────────────────────────────────
        "Antártida Argentina":            "Oeste",
        "Azcuenaga":                       "Oeste",
        "Bella Vista":                     "Oeste",
        "Cinco Esquinas":                  "Oeste",
        "Godoy":                           "Oeste",
        "Jorge Cura":                      "Oeste",
        "Las Malvinas":                    "Oeste",
        "Latinoamerica":                   "Oeste",
        "Parque Casado":                   "Oeste",
        "Remedios Escalada de San Martín": "Oeste",
        "Tango":                           "Oeste",
        "Triangulo y Moderno":            "Oeste",
        "Urquiza":                         "Oeste",
        "Victoria Walsh":                  "Oeste",

        # ── SUDOESTE ──────────────────────────────────────────────────────────
        "14 de Octubre":                   "Sudoeste",
        "17 de agosto":                    "Sudoeste",
        "Alvear":                          "Sudoeste",
        "Gral. Las Heras":                "Sudoeste",
        "Las Flores":                      "Sudoeste",
        "Matheu":                          "Sudoeste",
        "Presidente Roque Saenz Peña":    "Sudoeste",

        # ── SUR ───────────────────────────────────────────────────────────────
        "España y Hospitales":            "Sur",
        "Esteban Echeverría":             "Sur",
        "Gral. José de San Martín":       "Sur",
        "Mercedes de San Martín":         "Sur",
        "Saladillo Sud":                   "Sur",
        "Tiro Suizo":                      "Sur",
        "Villa Manuelita":                 "Sur",
    }

    def __init__(self, geojson_path: str):
        self._ready = False
        if not _GEO_AVAILABLE:
            return
        try:
            gdf = _gpd.read_file(geojson_path)
            # Asegura CRS geográfico estándar (lat/lon WGS84)
            if gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")
            else:
                gdf = gdf.to_crs("EPSG:4326")
            # Conserva solo las columnas necesarias para reducir memoria
            self._barrios = gdf[["BARRIO", "geometry"]].copy()
            self._ready = True
        except Exception as e:
            console.print(f"  [yellow]⚠  RosarioLocator: no se pudo cargar {geojson_path}: {e}[/yellow]")

    @property
    def available(self) -> bool:
        return self._ready

    # ── Consulta individual ────────────────────────────────────────────────────

    def get_location(self, lat, lon) -> tuple:
        """
        Devuelve (barrio, distrito) para una coordenada.
        Usa el índice espacial STRtree de geopandas para eficiencia.
        """
        if not self._ready:
            return None, None
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            return None, None

        point = _Point(lon_f, lat_f)
        # sindex.query devuelve índices de geometrías cuyo bounding-box
        # intersecta con el punto; luego filtramos con contains exacto.
        candidates = self._barrios.sindex.query(point, predicate="within")
        if len(candidates):
            barrio = self._barrios.iloc[candidates[0]]["BARRIO"]
            return barrio, self.BARRIO_TO_DISTRITO.get(barrio)
        return None, None

    # ── Procesamiento en lote (mucho más rápido para datasets completos) ────────

    def enrich_props(self, props: list) -> list:
        """
        Agrega los campos 'barrio_geo' y 'distrito' a cada propiedad.

        Estrategia:
        - Construye un GeoDataFrame con todos los puntos válidos de una vez.
        - Realiza un spatial join vectorizado contra los polígonos de barrios.
        - Aplica el mapping barrio → distrito en memoria (O(1) por propiedad).
        - Las propiedades sin coordenadas o fuera de Rosario quedan como None.

        Retorna la lista original con los campos nuevos añadidos in-place.
        """
        if not self._ready:
            for p in props:
                p.setdefault("barrio_geo", None)
                p.setdefault("distrito",   None)
            return props

        # Recolectar índices y coordenadas válidas
        valid: list[tuple[int, float, float]] = []
        for i, p in enumerate(props):
            try:
                lat = float(p["latitud"])
                lon = float(p["longitud"])
                if -34 <= lat <= -32 and -61 <= lon <= -60:   # bbox Rosario
                    valid.append((i, lat, lon))
            except (KeyError, TypeError, ValueError):
                pass

        # Pre-setear None para todos; los válidos se sobreescriben abajo
        for p in props:
            p["barrio_geo"] = None
            p["distrito"]   = None

        if not valid:
            return props

        indices, lats, lons = zip(*valid)

        # Construir GeoDataFrame de puntos
        gdf_pts = _gpd.GeoDataFrame(
            {"prop_idx": list(indices)},
            geometry=[_Point(lon, lat) for lat, lon in zip(lats, lons)],
            crs="EPSG:4326",
        )

        # Spatial join: cada punto queda asociado al polígono que lo contiene
        try:
            joined = _gpd.sjoin(
                gdf_pts,
                self._barrios,
                how="left",
                predicate="within",
            )
        except Exception:
            # Fallback a consulta individual si sjoin falla
            for i, lat, lon in valid:
                barrio, distrito = self.get_location(lat, lon)
                props[i]["barrio_geo"] = barrio
                props[i]["distrito"]   = distrito
            return props

        # sjoin puede producir múltiples filas por punto si hay polígonos
        # solapados; tomamos el primero para cada prop_idx.
        seen: set = set()
        for _, row in joined.iterrows():
            idx = int(row["prop_idx"])
            if idx in seen:
                continue
            seen.add(idx)
            barrio = row.get("BARRIO")
            if barrio and str(barrio) != "nan":
                props[idx]["barrio_geo"] = barrio
                props[idx]["distrito"]   = self.BARRIO_TO_DISTRITO.get(barrio)

        return props

    # ── Enriquecimiento basado en texto (fallback sin coordenadas) ─────────────

    @classmethod
    def barrio_from_text(cls, ubicacion: str) -> tuple:
        """
        Intenta determinar (barrio_texto, distrito) a partir del campo
        'ubicacion_completa' o 'barrio' devuelto por ZonaProp.

        Estrategia:
        1. Busca explícitamente "Distrito X" en el texto → distrito directo.
        2. Extrae el primer token (antes de la primera coma) como candidato
           a nombre de barrio.
        3. Normaliza y busca en BARRIO_TO_DISTRITO (exacto), luego en
           ZONAPROP_ALIAS → BARRIO_TO_DISTRITO, luego en EXTRA_BARRIOS.

        Returns:
            (barrio_texto: str | None, distrito: str | None)
        """
        if not ubicacion:
            return None, None

        text = str(ubicacion).strip()

        # ── 1. Búsqueda de "Distrito X" explícito en el string ────────────────
        import re as _re
        distrito_explicit = None
        for slug, dist_name in cls._SLUG_TO_DISTRITO.items():
            if dist_name.lower() in text.lower():
                # Verifica que sea un match semántico real (no sólo una substr)
                pattern = r'\bDistrito\s+' + dist_name
                if _re.search(pattern, text, _re.IGNORECASE):
                    distrito_explicit = dist_name
                    break

        # ── 2. Primer token como candidato de barrio ──────────────────────────
        candidate = text.split(',')[0].strip()

        # ── 3. Intentar resolver el barrio ────────────────────────────────────
        def _lookup(name: str):
            """Busca name en los dicts de mapeo; devuelve (nombre_canon, distrito)."""
            # Exacto en GeoJSON
            if name in cls.BARRIO_TO_DISTRITO:
                return name, cls.BARRIO_TO_DISTRITO[name]
            # Alias ZonaProp → canónico
            canon = cls.ZONAPROP_ALIAS.get(name)
            if canon and canon in cls.BARRIO_TO_DISTRITO:
                return canon, cls.BARRIO_TO_DISTRITO[canon]
            # Extra (no en GeoJSON pero conocido)
            if name in cls.EXTRA_BARRIOS:
                return name, cls.EXTRA_BARRIOS[name]
            return None, None

        barrio_name, distrito = _lookup(candidate)

        # Si no encontramos por el primer token, intentar tokens adicionales
        if barrio_name is None:
            parts = [p.strip() for p in text.split(',')]
            for part in parts[1:3]:    # segundo y tercer token, si los hay
                barrio_name, distrito = _lookup(part)
                if barrio_name:
                    break

        # Si tenemos distrito explícito del texto y no del barrio, usarlo
        if distrito is None and distrito_explicit:
            distrito = distrito_explicit

        return barrio_name or (candidate if candidate else None), distrito

    @classmethod
    def enrich_from_text(cls, props: list) -> list:
        """
        Enriquece con barrio_texto y distrito las propiedades que NO tienen
        coordenadas (barrio_geo es None).  Usa únicamente el campo
        'ubicacion_completa' o 'barrio' presentes en cada propiedad.

        Llamar después de enrich_props() para cubrir los casos sin lat/lon.
        """
        for p in props:
            # Solo actuar si aún sin asignación geográfica
            if p.get("barrio_geo") is not None:
                continue

            # Intentar con 'barrio' (viene del JSON cuando __NEXT_DATA__ funciona)
            barrio_raw = p.get("barrio") or p.get("ubicacion_completa") or ""
            barrio_txt, distrito = cls.barrio_from_text(barrio_raw)

            p["barrio_geo"] = barrio_txt
            if p.get("distrito") is None:
                p["distrito"] = distrito

        return props


def filter_out_of_zone(props: list, zona_slug: str) -> tuple:
    """
    Elimina propiedades que están fuera de la zona buscada.
    ZonaProp mezcla avisos patrocinados de otras zonas en los resultados.

    Estrategia (en orden de prioridad):
    1. Bounding-box geográfico: usa latitud/longitud cuando están disponibles.
    2. Distrito textual: si la propiedad ya tiene 'distrito' asignado (por
       enrich_from_text), compara contra el distrito esperado de la zona.
    3. Sin datos: se conserva (beneficio de la duda).

    Tolerancia bounding-box: ±0.005° (~500 m) en los bordes de zona.

    Returns:
        (propiedades_válidas, cantidad_eliminadas)
    """
    bounds = ZONA_BOUNDS.get(zona_slug)
    if not bounds:
        return props, 0   # Zona no mapeada → sin filtro

    lat_min, lat_max, lon_min, lon_max = bounds
    TOLERANCE = 0.005     # ~500 metros de margen

    # Nombre de distrito esperado para esta zona (ej. "Centro")
    expected_distrito = RosarioLocator._SLUG_TO_DISTRITO.get(zona_slug)

    filtered, removed = [], 0

    for prop in props:
        lat = prop.get("latitud")
        lon = prop.get("longitud")

        # ── Estrategia 1: filtrar por coordenadas ─────────────────────────────
        if lat is not None and lon is not None:
            try:
                lat_f, lon_f = float(lat), float(lon)
                in_bounds = (
                    (lat_min - TOLERANCE) <= lat_f <= (lat_max + TOLERANCE) and
                    (lon_min - TOLERANCE) <= lon_f <= (lon_max + TOLERANCE)
                )
                if in_bounds:
                    filtered.append(prop)
                else:
                    removed += 1
            except (TypeError, ValueError):
                filtered.append(prop)
            continue

        # ── Estrategia 2: filtrar por distrito textual ────────────────────────
        prop_distrito = prop.get("distrito")
        if prop_distrito is not None and expected_distrito is not None:
            if prop_distrito.lower() == expected_distrito.lower():
                filtered.append(prop)
            else:
                removed += 1
            continue

        # ── Estrategia 3: sin datos → conservar ──────────────────────────────
        filtered.append(prop)

    return filtered, removed


# ─── Pantalla de bienvenida ───────────────────────────────────────────────────

def show_welcome():
    """Pantalla de inicio estilo WarGames."""
    clear()

    # ── Logo ──
    logo_panel = Panel(
        Align.center(make_logo_text()),
        border_style=DIM_GREEN,
        padding=(0, 4),
    )
    console.print(logo_panel)

    # ── Info panels ──
    left = Table.grid(padding=(0, 1))
    left.add_column(style=DIM_GREEN, width=18)
    left.add_column(style=f"bold {GREEN}")
    left.add_row("Sistema  :", "Extracción de Propiedades")
    left.add_row("Fuente   :", "ZonaProp.com.ar")
    left.add_row("Versión  :", f"v{VERSION}")
    left.add_row("Tipo     :", "Departamentos en Venta")
    left.add_row("Ciudad   :", "Rosario, Argentina")

    right = Table.grid(padding=(0, 1))
    right.add_column(style=DIM_GREEN, width=22)
    right.add_column(style=f"{GREEN}")
    right.add_row(f"[dim]{timestamp_str()}[/dim]", "Sistema iniciado")
    right.add_row(f"[dim]{timestamp_str()}[/dim]", "Módulos cargados")
    right.add_row(f"[dim]{timestamp_str()}[/dim]", "Listo para configurar")
    right.add_row("", "")
    right.add_row(f"[dim green]>[/dim green] [dim]Comandos disponibles:[/dim]", "")
    right.add_row(f"  [bold green]run[/bold green]", "[dim]iniciar scraping[/dim]")
    right.add_row(f"  [bold green]salir[/bold green]", "[dim]terminar sesión[/dim]")

    console.print(
        Panel(
            Columns([
                Panel(left,  border_style=DARK_GREEN, padding=(0, 2), expand=True),
                Panel(right, border_style=DARK_GREEN, padding=(0, 2), expand=True),
            ]),
            border_style=DIM_GREEN,
            padding=(0, 1),
        )
    )

    # ── Bottom bar ──
    console.print(
        Panel(
            f"[dim green]  run[/dim green] [dim]·[/dim] [dim green]salir[/dim green]"
            f"[dim]                          "
            f"Escribí [/dim][bold green]run[/bold green][dim] para iniciar[/dim]",
            border_style=DARK_GREEN,
            padding=(0, 2),
        )
    )


# ─── Wizard de configuración ──────────────────────────────────────────────────

def run_wizard() -> dict:
    """
    Guía al usuario a través de los parámetros de búsqueda.
    Retorna un dict con toda la configuración.
    """
    config = {}

    console.print()
    console.print(
        Panel(
            f"[bold {GREEN}]  Configuración de búsqueda[/bold {GREEN}]\n"
            f"  [dim green]Usá las flechas ↑↓ para navegar · Enter para confirmar[/dim green]",
            border_style=DARK_GREEN,
            padding=(0, 2),
        )
    )
    console.print()

    # ── Zona ──────────────────────────────────────────────────────────────────
    zona_label = questionary.select(
        "  Zona de búsqueda:",
        choices=list(ZONAS.keys()),
        style=Q_STYLE,
        use_shortcuts=False,
    ).ask()
    if zona_label is None:
        raise KeyboardInterrupt

    config["zona_label"] = zona_label
    config["zona_slug"]  = ZONAS[zona_label]

    # ── Ambientes ─────────────────────────────────────────────────────────────
    ambientes = questionary.select(
        "  Cantidad de ambientes:",
        choices=AMBIENTES_OPTS,
        style=Q_STYLE,
    ).ask()
    if ambientes is None:
        raise KeyboardInterrupt

    config["ambientes"]       = ambientes
    config["ambientes_slug"]  = AMBIENTES_SLUG[ambientes]

    # ── Antigüedad ────────────────────────────────────────────────────────────
    antiguedad = questionary.select(
        "  Antigüedad de publicación:",
        choices=ANTIGUEDAD_OPTS,
        style=Q_STYLE,
    ).ask()
    if antiguedad is None:
        raise KeyboardInterrupt

    config["antiguedad"]      = antiguedad
    config["antiguedad_slug"] = ANTIGUEDAD_SLUG[antiguedad]

    # ── Formato de salida ─────────────────────────────────────────────────────
    formato = questionary.select(
        "  Formato del archivo de salida:",
        choices=FORMATO_OPTS,
        style=Q_STYLE,
    ).ask()
    if formato is None:
        raise KeyboardInterrupt

    config["formato"] = formato

    # ── Ruta de salida ────────────────────────────────────────────────────────
    default_path = str(Path(__file__).parent)
    ruta_raw = questionary.text(
        "  Directorio de salida:",
        default=default_path,
        style=Q_STYLE,
        validate=lambda p: True if p.strip() else "Ingresá una ruta válida.",
    ).ask()
    if ruta_raw is None:
        raise KeyboardInterrupt

    config["ruta"] = ruta_raw.strip()

    # ── Construir URL ─────────────────────────────────────────────────────────
    config["url"] = build_url(
        config["zona_slug"],
        config["ambientes_slug"],
        config["antiguedad_slug"],
    )

    return config


# ─── Pantalla de confirmación ─────────────────────────────────────────────────

def show_config_summary(config: dict):
    """Muestra tabla resumen de la configuración seleccionada."""
    table = Table(
        box=rbox.SIMPLE_HEAVY,
        border_style=DARK_GREEN,
        show_header=False,
        padding=(0, 2),
    )
    table.add_column(style=DIM_GREEN, width=26)
    table.add_column(style=f"bold {GREEN}")

    table.add_row("Zona",                   config.get("zona_label", "—"))
    table.add_row("Tipo de propiedad",      "[dim green]Departamento (fijo)[/dim green]")
    table.add_row("Ambientes",              config.get("ambientes", "—"))
    table.add_row("Antigüedad publicación", config.get("antiguedad", "—"))
    table.add_row("Formato de salida",      config.get("formato", "—"))
    table.add_row("Directorio de salida",   f"[italic]{config.get('ruta', '—')}[/italic]")
    table.add_row("", "")
    table.add_row(
        "URL generada",
        Text(config.get("url", ""), style=f"dim {GREEN}", overflow="fold"),
    )

    console.print(
        Panel(
            table,
            title=f"[bold {GREEN}]  Parámetros de búsqueda[/bold {GREEN}]",
            border_style=DIM_GREEN,
            padding=(0, 1),
        )
    )


def confirm_and_run(config: dict) -> bool:
    """Muestra resumen y pide confirmación antes de ejecutar."""
    console.print()
    show_config_summary(config)

    # Mapa ASCII estilo WarGames de los distritos de Rosario
    zona_slug = config.get("zona_slug", "")
    if zona_slug in ZONA_BOUNDS:
        console.print(
            Panel(
                zona_ascii_map(zona_slug),
                title=f"[bold {GREEN}]  Zona de búsqueda · Rosario[/bold {GREEN}]",
                border_style=DARK_GREEN,
                padding=(0, 2),
            )
        )

    console.print()

    answer = questionary.confirm(
        "  ¿Confirmar e iniciar el scraping?",
        default=True,
        style=Q_STYLE,
    ).ask()

    return bool(answer)


# ─── Ejecución del scraper ────────────────────────────────────────────────────

def run_scraping(config: dict) -> list:
    """Ejecuta el scraper con display de progreso en tiempo real."""
    console.print()
    bounds = ZONA_BOUNDS.get(config.get("zona_slug", ""))
    bounds_str = ""
    if bounds:
        lat_min, lat_max, lon_min, lon_max = bounds
        bounds_str = (
            f"\n\n  [dim green]Límites:[/dim green]  "
            f"N {lat_max:.4f}°  S {lat_min:.4f}°  "
            f"E {lon_max:.4f}°  O {lon_min:.4f}°"
        )

    console.print(
        Panel(
            f"[bold {GREEN}]  Iniciando scraping...[/bold {GREEN}]\n\n"
            f"  [dim green]URL :[/dim green]  [green]{config['url']}[/green]\n"
            f"  [dim green]Zona:[/dim green]  {config['zona_label']}\n"
            f"  [dim green]Amb :[/dim green]  {config['ambientes']}\n"
            f"  [dim green]Pub :[/dim green]  {config['antiguedad']}"
            f"{bounds_str}",
            title=f"[bold {GREEN}]▶  EJECUTANDO[/bold {GREEN}]",
            border_style=DIM_GREEN,
            padding=(0, 2),
        )
    )
    console.print()

    scraper     = ZonapropScraper()
    all_props   = []
    page        = 1
    total_known = None

    with Progress(
        SpinnerColumn(spinner_name="dots2", style=f"bold {GREEN}"),
        TextColumn(f"[{GREEN}]{{task.description}}"),
        BarColumn(bar_width=36, style=DARK_GREEN, complete_style=f"bold {GREEN}"),
        TaskProgressColumn(style=DIM_GREEN),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:

        task = progress.add_task("Conectando...", total=None)

        base_url = scraper.parse_base_url(config["url"])

        reintentos_pag = 0            # reintentos del bloqueo en la página actual
        max_pag = config.get("max_paginas")   # límite de páginas por consulta (particionado)
        while True:
            try:
                if max_pag and page > max_pag:
                    break
                progress.update(
                    task,
                    description=(
                        f"Página [bold]{page}[/bold] · "
                        f"[bold green]{len(all_props)}[/bold green] propiedades"
                    ),
                )
                properties, soup = scraper.scrape_page(base_url, page)

                if not properties:
                    break

                all_props.extend(properties)

                total = scraper.get_total_listings(soup)
                if total and total_known is None:
                    total_known = total
                    progress.update(task, total=total)

                if total_known:
                    progress.update(task, completed=min(len(all_props), total_known))

                if total_known and len(all_props) >= total_known:
                    break

                page += 1
                reintentos_pag = 0
                time.sleep(4)

            except Exception as e:
                msg = str(e)
                es_bloqueo = ('403' in msg or '429' in msg or 'Forbidden' in msg
                              or 'Too Many' in msg)
                if es_bloqueo and reintentos_pag < 4:
                    reintentos_pag += 1
                    espera = 15 * (2 ** (reintentos_pag - 1))   # 15, 30, 60, 120 s
                    console.print(
                        f"  [yellow]⚠[/yellow]  Bloqueo en pág. {page} "
                        f"({msg[:50]}). Reintento {reintentos_pag}/4 en {espera}s…"
                    )
                    time.sleep(espera)
                    continue                     # reintenta la MISMA página
                console.print(f"  [yellow]⚠[/yellow]  Error en página {page}: {e}")
                break

        progress.update(
            task,
            completed=len(all_props) if not total_known else total_known,
            total=len(all_props) if not total_known else total_known,
            description=f"[bold green]✓  Scraping completado[/bold green]",
        )

    return all_props


# ─── Guardar resultados ───────────────────────────────────────────────────────

def save_results(props: list, config: dict):
    """Guarda los resultados en el formato elegido y retorna paths + DataFrame."""
    if not props:
        return {}, pd.DataFrame()

    df         = pd.DataFrame(props)
    output_dir = Path(config["ruta"])
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp  = datetime.now().strftime("%Y-%m-%d_%H-%M")
    zona_tag   = config["zona_slug"].replace("rosario-", "").replace("-", "_")
    amb_tag    = config["ambientes_slug"].replace("-", "_")
    base_name  = f"joshua_{zona_tag}_{amb_tag}_{timestamp}"

    saved = {}
    fmt   = config["formato"]

    if "CSV" in fmt:
        path = output_dir / f"{base_name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        saved["CSV"] = str(path)

    if "JSON" in fmt:
        path = output_dir / f"{base_name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(props, f, ensure_ascii=False, indent=2)
        saved["JSON"] = str(path)

    return saved, df


# ─── Pantalla de resultados ───────────────────────────────────────────────────

def show_results(props: list, saved: dict, df: "pd.DataFrame", config: dict, n_filtered: int = 0, n_dupes: int = 0):
    """Muestra estadísticas del dataset y paths de los archivos generados."""
    if not props:
        console.print(
            Panel(
                f"[yellow]⚠  No se encontraron propiedades para los parámetros seleccionados.[/yellow]\n"
                f"[dim green]  Verificá la URL o intentá con otros filtros.[/dim green]",
                border_style="yellow",
                title=f"[yellow]  Sin resultados[/yellow]",
            )
        )
        return

    # ── Estadísticas ──────────────────────────────────────────────────────────
    stats = Table(box=rbox.SIMPLE, show_header=False, padding=(0, 2))
    stats.add_column(style=DIM_GREEN, width=26)
    stats.add_column(style=f"bold {GREEN}")

    stats.add_row("Total propiedades únicas", str(len(props)))
    if n_dupes > 0:
        stats.add_row("Duplicados eliminados", f"[yellow]{n_dupes}[/yellow]")
    if n_filtered > 0:
        stats.add_row("Fuera de zona (eliminadas)", f"[yellow]{n_filtered}[/yellow]")
    stats.add_row("Columnas extraídas", str(len(df.columns)))

    if "precio_valor" in df.columns:
        prices = df["precio_valor"].dropna()
        if not prices.empty:
            stats.add_row("Precio promedio",  f"USD {prices.mean():,.0f}")
            stats.add_row("Precio mínimo",    f"USD {prices.min():,.0f}")
            stats.add_row("Precio máximo",    f"USD {prices.max():,.0f}")

    if "superficie_total_m2" in df.columns:
        sup = df["superficie_total_m2"].dropna()
        if not sup.empty:
            stats.add_row("Superficie prom.", f"{sup.mean():.0f} m²")

    if "publicadora_nombre" in df.columns:
        n_pub = df["publicadora_nombre"].nunique()
        stats.add_row("Inmobiliarias únicas", str(n_pub))

    if "titulo_real" in df.columns:
        n_det = df["titulo_real"].notna().sum()
        stats.add_row("Propiedades con detalle", f"[green]{n_det}[/green]")
    if "orientacion" in df.columns:
        stats.add_row(
            "Orientación más común",
            str(df["orientacion"].mode().iloc[0]) if not df["orientacion"].dropna().empty else "—",
        )
    if "disposicion" in df.columns:
        stats.add_row(
            "Disposición más común",
            str(df["disposicion"].mode().iloc[0]) if not df["disposicion"].dropna().empty else "—",
        )

    # ── Archivos ──────────────────────────────────────────────────────────────
    files_lines = []
    for fmt, path in saved.items():
        files_lines.append(
            f"  [dim green]{fmt}[/dim green]  →  [bold green]{path}[/bold green]"
        )
    files_text = "\n".join(files_lines) if files_lines else "[dim]—[/dim]"

    console.print()
    console.print(
        Panel(
            Columns([
                Panel(
                    stats,
                    title=f"[bold {GREEN}]  Estadísticas[/bold {GREEN}]",
                    border_style=DARK_GREEN, expand=True,
                ),
                Panel(
                    f"[bold {GREEN}]Archivos generados:[/bold {GREEN}]\n\n{files_text}",
                    title=f"[bold {GREEN}]  Dataset guardado[/bold {GREEN}]",
                    border_style=DARK_GREEN, expand=True,
                ),
            ]),
            title=f"[bold {GREEN}]✓  SCRAPING FINALIZADO[/bold {GREEN}]",
            border_style=DIM_GREEN,
        )
    )

    # ── Vista previa ──────────────────────────────────────────────────────────
    # Columnas base + columnas de detalle (solo aparecen si el enriquecimiento se ejecutó)
    _base_cols = [
        "posting_id", "tipo_operacion", "precio_texto", "ubicacion_completa",
        "barrio_geo", "distrito",
        "superficie_total_m2", "ambientes", "banos", "expensas_valor",
        "cocheras", "dormitorios",
    ]
    _detail_cols = [
        "titulo_real", "fecha_publicacion", "orientacion", "disposicion",
        "inmobiliaria", "telefono_parcial", "whatsapp",
    ]
    preview_cols = [c for c in _base_cols + _detail_cols if c in df.columns]

    if preview_cols:
        console.print()
        console.print(
            Rule(f"[dim green]  Vista previa del dataset (primeras 3 filas)  [/dim green]",
                 style=DARK_GREEN)
        )
        console.print()

        prev = Table(
            box=rbox.SIMPLE_HEAVY,
            border_style=DARK_GREEN,
            header_style=f"bold {DIM_GREEN}",
            show_header=True,
        )
        for col in preview_cols:
            prev.add_column(col, max_width=22, overflow="fold",
                            style=DIM_GREEN, no_wrap=False)

        for _, row in df.head(3).iterrows():
            prev.add_row(*[str(row.get(c, ""))[:22] for c in preview_cols])

        console.print(prev)
        console.print()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    try:
        # ── Bienvenida ────────────────────────────────────────────────────────
        show_welcome()
        console.print()

        # ── Prompt de comando inicial ─────────────────────────────────────────
        cmd = questionary.text(
            "  Escribe una orden:",
            style=Q_STYLE,
            validate=lambda v: True,
        ).ask()

        if cmd is None or cmd.strip().lower() in ("salir", "exit", "quit", "q"):
            clear()
            console.print(f"\n  [{GREEN}]Hasta luego.[/{GREEN}]\n")
            return

        if cmd.strip().lower() not in ("run", "iniciar", "start", ""):
            console.print(
                f"\n  [yellow]Comando no reconocido.[/yellow] "
                f"Escribí [bold green]run[/bold green] para iniciar.\n"
            )
            time.sleep(1.5)

        # ── Wizard de configuración ───────────────────────────────────────────
        clear()
        console.print(
            Panel(
                make_logo_text(),
                border_style=DARK_GREEN,
                padding=(0, 4),
            )
        )
        console.print(
            Rule(f"[dim green]  Configuración de búsqueda  [/dim green]",
                 style=DARK_GREEN)
        )

        config = run_wizard()

        # ── Confirmación ──────────────────────────────────────────────────────
        clear()
        console.print(
            Panel(
                make_logo_text(),
                border_style=DARK_GREEN,
                padding=(0, 4),
            )
        )

        if not confirm_and_run(config):
            console.print(f"\n  [dim green]Operación cancelada.[/dim green]\n")
            return

        # ── Scraping ──────────────────────────────────────────────────────────
        props = run_scraping(config)

        # ── Enriquecimiento geográfico (barrio + distrito) ─────────────────────
        # IMPORTANTE: debe correr ANTES del filtro de zona para que
        # filter_out_of_zone pueda usar el campo 'distrito' cuando no hay coords.
        if props:
            geojson_path = Path(__file__).parent / "rosario_barrios.geojson"
            if geojson_path.exists():
                if not _GEO_AVAILABLE:
                    console.print(
                        "  [dim yellow]ℹ  Enriquecimiento geográfico desactivado "
                        "(instalá geopandas y shapely para activarlo).[/dim yellow]\n"
                    )
                else:
                    locator = RosarioLocator(str(geojson_path))
                    if locator.available:
                        with console.status(
                            f"  [dim green]Geolocalizando {len(props)} propiedades…[/dim green]",
                            spinner="dots",
                        ):
                            props = locator.enrich_props(props)
                        n_geo = sum(
                            1 for p in props if p.get("barrio_geo") is not None
                        )
                        console.print(
                            f"  [dim green]✓  Geolocalización:[/dim green] "
                            f"[green]{n_geo}/{len(props)}[/green] propiedades "
                            f"asignadas a barrio y distrito.\n"
                        )

            # Enriquecimiento por texto para propiedades sin coordenadas.
            # Cubre el caso habitual de scraping HTML (sin __NEXT_DATA__).
            n_sin_geo = sum(1 for p in props if p.get("barrio_geo") is None)
            if n_sin_geo > 0:
                props = RosarioLocator.enrich_from_text(props)
                n_texto = sum(
                    1 for p in props if p.get("barrio_geo") is not None
                ) - (len(props) - n_sin_geo)
                if n_texto > 0:
                    console.print(
                        f"  [dim green]✓  Barrio/distrito por texto:[/dim green] "
                        f"[green]{n_texto}[/green] propiedades asignadas "
                        f"desde ubicacion_completa.\n"
                    )

        # ── Filtro geográfico ─────────────────────────────────────────────────
        # Corre DESPUÉS del enriquecimiento para poder usar 'distrito' como
        # criterio de filtrado cuando no hay coordenadas disponibles.
        n_filtered = 0
        if props:
            props, n_filtered = filter_out_of_zone(props, config["zona_slug"])
            if n_filtered > 0:
                console.print(
                    f"\n  [yellow]⚠  Filtro de zona:[/yellow] "
                    f"[yellow]{n_filtered} propiedad(es) fuera de "
                    f"{config['zona_label']} eliminada(s)[/yellow] "
                    f"([dim green]{len(props)} propiedades válidas[/dim green])\n"
                )

        # ── Deduplicación por posting_id ──────────────────────────────────────
        n_dupes = 0
        if props:
            seen, deduped = set(), []
            for p in props:
                pid = p.get("posting_id")
                if pid is None or pid not in seen:
                    deduped.append(p)
                    if pid is not None:
                        seen.add(pid)
            n_dupes = len(props) - len(deduped)
            props = deduped
            if n_dupes > 0:
                console.print(
                    f"  [yellow]⚠  Deduplicación:[/yellow] "
                    f"[yellow]{n_dupes} publicación(es) duplicada(s) eliminada(s)[/yellow] "
                    f"([dim green]{len(props)} propiedades únicas[/dim green])\n"
                )

        # ── Enriquecimiento de detalle (opcional) ─────────────────────────────
        n_enriched = 0
        if props:
            n_with_url = sum(1 for p in props if p.get('url'))
            if n_with_url > 0:
                secs  = int(n_with_url * 1.5)
                mins  = secs // 60
                segs  = secs % 60
                t_str = f"{mins} min {segs} s" if mins else f"{segs} s"

                console.print(
                    Panel(
                        f"  [dim green]Enriquecimiento de detalle disponible.[/dim green]\n\n"
                        f"  Visita la página de cada propiedad y agrega:\n"
                        f"  [green]título real · fecha publicación · descripción completa\n"
                        f"  dirección exacta · lat/lon · orientación · disposición\n"
                        f"  luminoso · toilette · inmobiliaria · teléfono · WhatsApp\n"
                        f"  superficie cubierta · fotos HD[/green]\n\n"
                        f"  [dim]Propiedades a procesar: [bold]{n_with_url}[/bold] · "
                        f"Tiempo estimado: [bold]{t_str}[/bold][/dim]",
                        title=f"[bold {GREEN}]▶  DETALLE[/bold {GREEN}]",
                        border_style=DIM_GREEN,
                        padding=(0, 2),
                    )
                )
                console.print()

                do_enrich = questionary.confirm(
                    "  ¿Enriquecer dataset con datos de detalle?",
                    default=False,
                    style=Q_STYLE,
                ).ask()

                if do_enrich:
                    from zonaprop_scraper import ZonapropDetailScraper
                    detail_scraper = ZonapropDetailScraper(delay=1.5)

                    with Progress(
                        SpinnerColumn(spinner_name="dots2", style=f"bold {GREEN}"),
                        TextColumn(f"[{GREEN}]{{task.description}}"),
                        BarColumn(bar_width=36, style=DARK_GREEN, complete_style=f"bold {GREEN}"),
                        TaskProgressColumn(style=DIM_GREEN),
                        TimeElapsedColumn(),
                        console=console,
                        transient=False,
                    ) as progress:
                        task = progress.add_task(
                            f"Enriqueciendo…", total=n_with_url
                        )

                        def _on_progress(current, total):
                            progress.update(
                                task,
                                completed=current,
                                description=(
                                    f"Detalle [bold]{current}[/bold]/"
                                    f"[bold]{total}[/bold]"
                                ),
                            )

                        props = detail_scraper.enrich(props, on_progress=_on_progress)
                        progress.update(
                            task,
                            completed=n_with_url,
                            description=f"[bold green]✓  Enriquecimiento completado[/bold green]",
                        )

                    n_enriched = sum(1 for p in props if p.get('titulo_real'))
                    console.print(
                        f"\n  [dim green]✓  Detalle:[/dim green] "
                        f"[green]{n_enriched}/{len(props)}[/green] propiedades "
                        f"enriquecidas con datos de la página de detalle.\n"
                    )

        # ── Guardar ───────────────────────────────────────────────────────────
        if props:
            saved, df = save_results(props, config)
        else:
            saved, df = {}, pd.DataFrame()

        # ── Resultados ────────────────────────────────────────────────────────
        show_results(props, saved, df, config, n_filtered, n_dupes)

        # ── Cierre ────────────────────────────────────────────────────────────
        console.print(
            Panel(
                f"[dim green]  Sesión finalizada · {timestamp_str()}[/dim green]  "
                f"[dim]Presioná Enter para cerrar.[/dim]",
                border_style=DARK_GREEN,
            )
        )
        input()

    except KeyboardInterrupt:
        clear()
        console.print(f"\n  [{GREEN}]Hasta luego.[/{GREEN}]\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
