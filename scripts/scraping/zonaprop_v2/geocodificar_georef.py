#!/usr/bin/env python3
"""
geocodificar_georef.py — Primera pasada de geocodificación con la API Georef
(oficial argentina). Procesa las propiedades que quedaron 'pendiente_geocode'.

Uso:  python geocodificar_georef.py
"""
import os
import config as C
import storage, geocode

CACHE_PATH = os.path.join(C.OUT_DIR, 'geocache_georef.csv')

def main():
    con = storage.connect(C.DB_PATH)
    cache = geocode.Cache(CACHE_PATH if os.path.exists(CACHE_PATH) else None)
    cache.path = CACHE_PATH
    print(f'Cache Georef inicial: {len(cache.d):,}')
    geocoder = geocode.GeorefGeocoder()
    ok, fuera, fail = geocode.geocodificar_pendientes(
        con, geocoder, cache, precision='address'
    )
    print(f'Georef: ok={ok} (rechazadas fuera={fuera}) fallidas={fail}')
    geocode.reevaluar_zona(con)
    usab = con.execute("SELECT COUNT(*) FROM propiedades WHERE in_distrito_centro=1").fetchone()[0]
    tot = con.execute("SELECT COUNT(*) FROM propiedades").fetchone()[0]
    print(f'Cobertura usable: {usab}/{tot} ({usab/tot*100:.0f}%)')
    con.close()

if __name__ == '__main__':
    main()
