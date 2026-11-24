#!/usr/bin/env python3
"""reevaluar.py — Recalcula in_distrito_centro con el bounding box actual y limpia
geocodes groseramente errados (sin red). Correr tras ajustar el box."""
import config as C
import storage, geocode

def main():
    con = storage.connect(C.DB_PATH)
    antes = con.execute("SELECT COUNT(*) FROM propiedades WHERE geo_source='geocoded'").fetchone()[0]
    geocode.reevaluar_zona(con)
    usables = con.execute("SELECT COUNT(*) FROM propiedades WHERE in_distrito_centro=1").fetchone()[0]
    pend = con.execute("SELECT COUNT(*) FROM propiedades WHERE geo_source='pendiente_geocode'").fetchone()[0]
    print(f'geocoded antes: {antes} | coords usables (in_centro=1): {usables} | pendientes: {pend}')
    con.close()

if __name__ == '__main__':
    main()
