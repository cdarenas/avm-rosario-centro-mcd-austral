#!/usr/bin/env python3
"""
geocodificar.py — Paso opcional con Nominatim (correr después de Georef/fallback).
Completa lat/lon de las propiedades con geo_source='pendiente_geocode'.

Uso:
    python geocodificar.py
"""
import os
import config as C
import storage, geocode

CACHE_PATH = os.path.join(C.OUT_DIR, 'geocache.csv')
# Semilla opcional: reutilizar el geocodificacion.csv previo si existe
SEMILLA = os.path.join(C.LEGACY_DIR, 'datos', 'geocodificacion.csv')

def main():
    con = storage.connect(C.DB_PATH)
    # cache: usa geocache.csv acumulado; si no existe, siembra con el csv previo
    ruta = CACHE_PATH if os.path.exists(CACHE_PATH) else (SEMILLA if os.path.exists(SEMILLA) else None)
    cache = geocode.Cache(ruta)
    cache.path = CACHE_PATH  # guardará el cache acumulado acá
    print(f'Cache inicial: {len(cache.d):,} direcciones')
    geocoder = geocode.NominatimGeocoder(user_agent='tesis-avm-rosario')
    ok, fuera, fail = geocode.geocodificar_pendientes(
        con, geocoder, cache, precision='address_unverified'
    )
    print(f'Listo. geocodificadas={ok} (fuera_centro={fuera}) fallidas={fail}')
    # reevaluar in_distrito_centro para TODAS con el bounding box corregido
    geocode.reevaluar_zona(con)
    con.close()

if __name__ == '__main__':
    main()
