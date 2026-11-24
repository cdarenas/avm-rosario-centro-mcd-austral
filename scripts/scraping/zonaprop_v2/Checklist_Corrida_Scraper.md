# Checklist — corrida real del scraper (Fase 6)

Guía para ejecutar y **verificar la calidad** de la primera corrida sobre ZonaProp antes de pasar al EDA.

## A. Antes de correr

- [ ] **Dependencias:** `pip install cloudscraper beautifulsoup4 lxml pandas geopy pyarrow`.
- [ ] `zonaprop_extractor.py` y `zonaprop_scraper.py` presentes en este directorio.
- [ ] **Revisar `config.py`:** zona (`rosario-distrito-centro`), `DELAY_DETALLE` (cortesía, ≥1,5 s), rutas de salida.
- [ ] **Espacio en disco** para la DB y los snapshots crudos.
- [ ] **Corrida de prueba primero:** `python run_scraping_v2.py 1` (solo 1 ambiente) para confirmar que el sitio responde, no hay bloqueo de Cloudflare, y la DB se escribe bien. Recién después, la corrida completa.

## B. Durante la corrida

- [ ] Seguir `salida/scraping.log`: avisos scrapeados, fuera de zona, exclusiones y errores de red por ambiente.
- [ ] Sin bloqueos de Cloudflare (si aparecen, subir el delay).
- [ ] Si se corta: **reanudar** con `python run_scraping_v2.py --resume run_YYYYMMDDT...Z` (no reprocesa lo ya capturado).

## C. Después — verificación de calidad de `zonaprop_v2.db`

### 1. Volumen y trazabilidad
- [ ] Nº de `capturas`, `propiedades`, `exclusiones` y `runs`. ¿Volumen esperable? (referencia previa: ~13k–17k avisos en el Centro).
- [ ] `runs`: `started_at`/`finished_at` completos; sin corridas colgadas.
- [ ] Los contadores almacenados de cada run coinciden con sus filas reales.

### 2. Identidad y republicaciones
- [ ] Verificar que cada `posting_id` mantenga un `property_id` estable entre corridas.
- [ ] Auditar grupos de `republication_candidate_id`; no fusionarlos automáticamente.
- [ ] `building_cluster_id` únicos (edificios/cuadras).
- [ ] Distribución `id_confianza` (`posting` en corridas nuevas; valores legacy documentados).
- [ ] Spot-check: tomar 2–3 `building_cluster_id` con varias unidades y confirmar que son deptos distintos (no falsos merges).

### 3. Coordenadas (la brecha crítica)
- [ ] Cobertura por `geo_source`, `geo_provider` y `geo_precision`.
- [ ] Correr la geocodificación de respaldo y volver a medir; no asumir cobertura total.
- [ ] % con `in_distrito_centro = 1`; revisar los `= 0` (posibles errores de geocodificación).

### 4. Precios y consistencia
- [ ] `precio_moneda`: 100% USD (o registrar mezcla).
- [ ] Rango y mediana de `precio_valor` y `precio_m2`; comparar con referencia (mediana ~USD 108k, ~1.650/m²).
- [ ] `cambios_precio`: cuántas propiedades registraron cambios entre capturas.

### 5. Faltantes
- [ ] % de nulos por campo clave (superficie, ambientes, baños, antigüedad, expensas, dirección).
- [ ] Separar **ausencia estructural** (p. ej. sin cochera) de faltante real, según la taxonomía.

### 6. Features de texto (`feat_*`)
- [ ] Prevalencia de cada `feat_*` (con `features_texto.extraer_features`).
- [ ] Spot-check de negaciones: descripciones con "sin cochera"/"no apto crédito" → el flag debe ser 0.

### 7. Plausibilidad (marcas, no exclusiones)
- [ ] Correr `features_texto.chequear_plausibilidad` sobre las propiedades: cuántas y qué flags (`precio_fuera_rango`, `superficie_fuera_rango`, `precio_m2_fuera_rango`, `sup_cubierta_mayor_que_total`).
- [ ] Revisar los casos marcados: ¿errores de dato o propiedades legítimamente extraordinarias? (no eliminar automáticamente).

### 8. Exclusiones
- [ ] Revisar `exclusiones` por motivo (`sin_precio`, `fuera_de_zona`, `sin_posting_id`). ¿Se pierde algo recuperable?

### 9. Temporal
- [ ] `capture_date` consistente en toda la corrida; `fecha_publicacion` con cobertura razonable.
- [ ] Una corrida nueva vuelve a observar postings activos; `--resume` solo evita duplicados del mismo run.

## D. Criterio "listo para EDA"
- [ ] Volumen suficiente y sin errores sistemáticos en el log.
- [ ] Cobertura y precisión de coordenadas cuantificadas; pertenencia territorial auditada.
- [ ] Precios coherentes (USD, rango razonable) y plausibilidad revisada.
- [ ] Candidatos de republicación y `building_cluster_id` verificados (base para el group-aware split).

---
El dataset candidato debe conservar los flags y un manifiesto antes de cualquier
decisión de exclusión o imputación.
