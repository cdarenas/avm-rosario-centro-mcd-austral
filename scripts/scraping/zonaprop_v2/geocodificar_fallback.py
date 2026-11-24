#!/usr/bin/env python3
"""
geocodificar_fallback.py — Tercera pasada: geocodifica a NIVEL CALLE (sin altura)
las propiedades que aún quedan pendientes. Precisión de cuadra, suficiente para
features espaciales de escala barrial. Usa Georef. Correr al final.

Uso:  python geocodificar_fallback.py
"""
import os
import config as C
import storage, geocode

CACHE_PATH = os.path.join(C.OUT_DIR, 'geocache_calle.csv')

def main():
    con = storage.connect(C.DB_PATH)
    cache = geocode.Cache(CACHE_PATH if os.path.exists(CACHE_PATH) else None)
    cache.path = CACHE_PATH
    geocoder = geocode.GeorefGeocoder()
    print('Fallback a nivel calle (Georef)…')
    ok, fuera, fail = geocode.geocodificar_pendientes(
        con, geocoder, cache, query_fn=geocode.preparar_query_calle,
        precision='street')
    print(f'Fallback calle: ok={ok} (fuera={fuera}) fallidas={fail}')
    geocode.reevaluar_zona(con)
    usab = con.execute("SELECT COUNT(*) FROM propiedades WHERE in_distrito_centro=1").fetchone()[0]
    tot = con.execute("SELECT COUNT(*) FROM propiedades").fetchone()[0]
    print(f'Cobertura usable final: {usab}/{tot} ({usab/tot*100:.0f}%)')
    con.close()

if __name__ == '__main__':
    main()
