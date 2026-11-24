#!/usr/bin/env python3
"""
geo.py — Consolidación de coordenadas y validación dentro del Distrito Centro.

- consolidar_coordenadas: prioriza lat/long scrapeadas; si faltan/invalidas, deja marca
  para geocodificar por dirección (geopy/Nominatim) en el paso de enriquecimiento.
- en_distrito_centro: validación aproximada por bounding box (reemplazar por polígono real
  cuando se cargue el shapefile del Distrito Centro de Rosario).
"""
# Bounding box aproximado del Distrito Centro de Rosario (ajustar con polígono oficial)
# Box generoso de Rosario central (captura todo el Distrito Centro con margen).
# Como ZonaProp ya filtró por distrito, esto solo sirve para descartar geocodes
# groseramente errados (calles homónimas en otras ciudades).
CENTRO_BBOX = dict(lat_min=-32.990, lat_max=-32.880, lon_min=-60.700, lon_max=-60.600)

def _valida_coord(lat, lon):
    try:
        lat = float(lat); lon = float(lon)
    except (TypeError, ValueError):
        return None, None
    # Rosario está ~ -32.9, -60.6; descartar 0,0 y valores fuera de rango
    if not (-33.2 < lat < -32.7 and -60.9 < lon < -60.4):
        return None, None
    return lat, lon

def consolidar_coordenadas(prop: dict):
    """Devuelve (lat, lon, source). source: 'scraped' | 'pendiente_geocode'."""
    lat, lon = _valida_coord(prop.get('latitud'), prop.get('longitud'))
    if lat is not None:
        return lat, lon, 'scraped'
    return None, None, 'pendiente_geocode'

def en_distrito_centro(lat, lon):
    if lat is None or lon is None:
        return None
    b = CENTRO_BBOX
    return int(b['lat_min'] <= lat <= b['lat_max'] and b['lon_min'] <= lon <= b['lon_max'])
