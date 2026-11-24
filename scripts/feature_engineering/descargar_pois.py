#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Descarga de puntos de interés (POI) para el enriquecimiento de S3.
#
# Fuente: OpenStreetMap vía Overpass API (WGS84, incluye plazas; licencia ODbL).
# Se ejecuta UNA vez, en una máquina con red (no requiere librerías extra).
#
# Salidas (versionadas en data/external/ con README):
#   data/external/osm/espacios_verdes.csv   (nombre, lat, lon)
#   data/external/osm/comercios.csv         (lat, lon)
#
# Uso:  python3 scripts/feature_engineering/descargar_pois.py
#
# Nota: los datos oficiales de la Municipalidad (Datos Abiertos: "Parques y paseos",
# padrones municipales) pueden usarse como validación/reemplazo posterior. Se eligió OSM
# por ser más granular a nivel plaza y por accesibilidad (API estable en WGS84).
# ─────────────────────────────────────────────────────────────────────────────
import json, csv, datetime, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "external" / "osm"
# Overpass suele devolver 504/429 en el endpoint principal: probamos varios mirrors con reintentos.
OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
# bounding box del Distrito Centro (S, W, N, E)
BBOX = "-32.99,-60.71,-32.91,-60.60"

def overpass(query, intentos=3):
    data = urllib.parse.urlencode({"data": query}).encode()
    ultimo = None
    for ep in OVERPASS_ENDPOINTS:
        for i in range(intentos):
            try:
                req = urllib.request.Request(ep, data=data, headers={"User-Agent": "tesis-avm-rosario/1.0"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.loads(r.read().decode())
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError) as e:
                ultimo = e
                time.sleep(6 * (i + 1))   # backoff: 6s, 12s, 18s
        print(f"  · {ep} no respondió ({ultimo}); probando otro mirror…")
    raise SystemExit(f"Overpass no respondió en ningún mirror (último: {ultimo}). "
                     "Reintentá en unos minutos (el servicio suele saturarse).")

def puntos(elementos):
    for e in elementos:
        if "lat" in e and "lon" in e:
            yield e
        elif "center" in e:
            yield {**e, "lat": e["center"]["lat"], "lon": e["center"]["lon"]}

def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # espacios verdes (parques, jardines, plazas)
    q_verde = (f'[out:json][timeout:120];('
               f'nwr["leisure"~"^(park|garden|nature_reserve|pitch)$"]({BBOX});'
               f'nwr["place"="square"]({BBOX}););out center;')
    verdes = list(puntos(overpass(q_verde)["elements"]))
    with open(OUT / "espacios_verdes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["nombre", "lat", "lon"])
        for e in verdes:
            w.writerow([e.get("tags", {}).get("name", ""), e["lat"], e["lon"]])
    print(f"espacios_verdes.csv: {len(verdes)} elementos")

    # comercios (cualquier shop)
    q_com = f'[out:json][timeout:120];nwr["shop"]({BBOX});out center;'
    comercios = list(puntos(overpass(q_com)["elements"]))
    with open(OUT / "comercios.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["lat", "lon"])
        for e in comercios:
            w.writerow([e["lat"], e["lon"]])
    print(f"comercios.csv: {len(comercios)} elementos")

    (OUT / "README.md").write_text(
        f"# POI (OpenStreetMap) — enriquecimiento de S3\n\n"
        f"Descargado el {datetime.date.today()} vía Overpass API para el bounding box del "
        f"Distrito Centro ({BBOX}).\n\n"
        f"- `espacios_verdes.csv` — parques, jardines y plazas (`leisure`, `place=square`).\n"
        f"- `comercios.csv` — locales comerciales (`shop=*`).\n\n"
        f"Fuente: © OpenStreetMap contributors, licencia ODbL. Alternativa oficial: Datos Abiertos "
        f"de la Municipalidad de Rosario ('Parques y paseos', padrones municipales).\n", encoding="utf-8")
    print(f"Listo → {OUT.relative_to(ROOT)}/")

if __name__ == "__main__":
    main()
