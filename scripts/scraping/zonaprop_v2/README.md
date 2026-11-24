# scraper_v2 — Scraper ZonaProp para la tesis (AVM Rosario)

Extracción reproducible de avisos de departamentos del Distrito Centro de
Rosario. Reutiliza el motor de scraping existente (`cloudscraper` + parsing
`__NEXT_DATA__`, dos etapas) y agrega snapshots, trazabilidad, identidad y
controles de calidad para la tesis.

## Módulos

| Archivo | Rol |
|---|---|
| `config.py` | Configuración (zona, ambientes, delays, rutas, run_id). |
| `storage.py` | Esquema SQLite + escritura: `capturas` (snapshots + `capture_date` + JSON crudo), `propiedades` (identidad + coordenadas + historial de precios), `posting_property_map`, `exclusiones`, `runs`. |
| `identidad.py` | Identidad conservadora por `posting_id`, candidatos de republicación para auditoría y `building_cluster_id` para particiones agrupadas. |
| `geo.py` | Consolidación de coordenadas scrapeadas + validación dentro del Distrito Centro. |
| `geocode.py` | Geocodificación con cache y registro de proveedor, precisión y query. |
| `features_texto.py` | Extracción robusta de `feat_*` **con manejo de negaciones** ("sin cochera" ≠ cochera) + chequeos de plausibilidad. |
| `run_scraping_v2.py` | Orquestador: reintentos con backoff, reanudación (`--resume`), logging, rate-limiting. |
| `verificar_corrida.py` | Auditoría de volumen, runs, identidad, coordenadas, precios, faltantes y temporalidad. |
| `construir_dataset_candidato.py` | Exportación interim no destructiva con features y flags de calidad. |
| `exportar_auditoria_identidad.py` | Candidatos de republicación y clusters para revisar antes del splitting. |

## Qué mejora respecto del scraper anterior
- **`capture_date`** por corrida → control temporal y detección de republicaciones/cambios de precio.
- **Identidad conservadora** → cada `posting_id` conserva su propia identidad; las
  coincidencias estructurales solo generan candidatos de republicación auditables.
- **`building_cluster_id`** → permite particiones agrupadas y ayuda a controlar
  leakage entre unidades del mismo edificio o cuadra.
- **Coordenadas persistidas** + procedencia y precisión de geocodificación.
- **`feat_*` con negaciones** → corrige ~121 falsos positivos en el corpus actual (p. ej. apto_credito 4,6%).
- **Exclusiones registradas** con motivo → no se pierden datos en silencio.
- **Snapshots del JSON crudo** → reproducibilidad y re-parseo sin re-scrapear.
- **Robustez:** reintentos, resume, logging, rate-limiting cortés.

## Uso
```bash
cd scripts/scraping/zonaprop_v2
python -m pip install -r requirements.txt
python run_scraping_v2.py            # todos los ambientes
python run_scraping_v2.py 3          # solo 3 ambientes
python run_scraping_v2.py --resume run_YYYYMMDDT...Z   # reanudar

python geocodificar_georef.py
python geocodificar_fallback.py
python geocodificar.py                 # opcional: Nominatim
python verificar_corrida.py
```
Salida en `scraper_v2/salida/zonaprop_v2.db` + `scraping.log`.

Una corrida nueva vuelve a observar avisos activos para construir snapshots
temporales. `--resume` saltea solamente los avisos ya guardados dentro del mismo
`run_id`.

## Dataset candidato

La exportación interim agrega features textuales y flags, pero no elimina filas:

```bash
python construir_dataset_candidato.py \
  salida/zonaprop_v2.db \
  salida/zonaprop_v2_candidate.parquet
```

También puede utilizarse `.csv.gz` cuando `pyarrow` no esté disponible. Se genera
un manifiesto con hash de la base, dimensiones y prevalencia de flags.

Los candidatos de republicación y los clusters se auditan por separado:

```bash
python exportar_auditoria_identidad.py \
  salida/zonaprop_v2.db \
  salida/auditoria_identidad
```

## Estado

La captura inicial del 15–17 de agosto de 2026 fue auditada y se registra en
`data/raw/zonaprop_v2/manifest.json`. La copia legacy contiene 15.966 capturas y
13.594 identidades inferidas. Debe considerarse raw: conserva casos en ARS,
extremos, faltantes, identidades por validar y geocodificación sin granularidad
retroactiva suficiente.

Las correcciones actuales se aplican a corridas futuras. No alteran ni reescriben
la base raw original.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

## Nota
Scraping cortés y con fines académicos (rate-limiting, sin sobrecargar). El target
capturado es **precio de publicación** (oferta), no precio de cierre. Antes de
realizar nuevas capturas deben revisarse las condiciones vigentes del portal y
las pautas institucionales aplicables.
