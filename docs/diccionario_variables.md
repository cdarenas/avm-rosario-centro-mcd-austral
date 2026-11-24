# Diccionario de variables — muestra analítica del Distrito Centro (v5)

*124 columnas · 4,765 filas · dataset `data/processed/zonaprop_v2_eda_centro_v5.csv.gz`*

## Convención de nombres

El dataset conserva **tres capas** para trazabilidad; para el análisis y el modelo se usa siempre la capa analítica:

| Capa | Sufijo/prefijo | Rol |
|---|---|---|
| Cruda | *(sin sufijo)* | Valor original del scraper. Trazabilidad. |
| Auditada | `*_auditado/a` | Valor validado en la auditoría. Trazabilidad. |
| **Analítica** | **`eda_*`** | **Versión final lista para análisis/modelo. USAR.** |
| **Texto** | **`feat_*`** | **Atributo binario extraído de la descripción. USAR.** |

> **Nota:** la convención `eda_*` está aplicada de forma **incompleta**: variables como `ambientes`, `dormitorios`, `antiguedad`, `disposicion` y `orientacion` se usan **crudas** (no tienen versión `eda_`). Regularizar esta convención es una tarea de la etapa de *feature engineering*.


## Estructurales, target y categóricas (crudas)  (21)

| Variable | Tipo | Completitud | Descripción |
|---|---|---:|---|
| `ambientes` | int64 | 100% | **Predictor.** Cantidad de ambientes (1–12). Se usa crudo (sin versión `eda_`). |
| `antiguedad` | object | 94% | **Predictor.** Antigüedad del inmueble (años + categorías 'a estrenar'/'en construcción'). Campo **sucio** (mezcla tipos, valores imposibles): sanear en FE. |
| `banos` | float64 | 97% | Cantidad de baños (crudo, previo a auditoría). |
| `cocheras` | float64 | 26% | Cantidad de cocheras (crudo). |
| `descripcion_completa` | object | 100% | Texto libre del aviso. **Trae HTML/boilerplate del portal** y leyenda legal: sanear antes de features de texto. |
| `disposicion` | object | 79% | **Predictor.** Disposición: Frente / Contrafrente / Lateral / Interno. |
| `dormitorios` | float64 | 78% | **Predictor.** Cantidad de dormitorios (crudo). |
| `expensas_valor` | float64 | 33% | Expensas crudas (ARS). |
| `inmobiliaria` | object | 100% | Inmobiliaria/publicadora. |
| `orientacion` | object | 70% | **Predictor.** Orientación (N/S/E/O y combinaciones). |
| `precio_m2_observado` | float64 | 98% | Precio/m² observado (crudo). |
| `precio_max` | float64 | 100% | Precio máximo observado entre capturas. |
| `precio_min` | float64 | 100% | Precio mínimo observado entre capturas. |
| `precio_moneda` | object | 100% | Moneda del precio crudo (USD/ARS). |
| `precio_ultimo` | float64 | 100% | Precio de la última captura (crudo, en la moneda de `precio_moneda`). |
| `superficie_cubierta_m2` | float64 | 92% | Superficie cubierta (m²) cruda. |
| `superficie_total_m2` | float64 | 98% | Superficie total (m²) cruda, previa a auditoría. |
| `tipo_operacion` | object | 100% | PROPERTY (unidad individual) vs DEVELOPMENT (emprendimiento/pozo). |
| `titulo` | object | 100% | Título del aviso (crudo). |
| `toilette` | float64 | 20% | Cantidad de toilettes (crudo). |
| `url` | object | 100% | URL del aviso. |

## Analítica — lista para el modelo (`eda_*`)  (11)

| Variable | Tipo | Completitud | Descripción |
|---|---|---:|---|
| `eda_banos` | float64 | 97% | Cantidad de baños, auditada. |
| `eda_cocheras` | float64 | 26% | Cantidad de cocheras, auditada (NA = sin cochera, ausencia estructural). |
| `eda_distrito` | object | 100% | Distrito asignado (constante = CENTRO en esta muestra). |
| `eda_expensas` | float64 | 33% | Expensas mensuales (ARS), parseadas y auditadas. |
| `eda_latitud` | float64 | 100% | Latitud (WGS84) validada contra cartografía oficial. |
| `eda_longitud` | float64 | 100% | Longitud (WGS84) validada contra cartografía oficial. |
| `eda_precio_m2` | float64 | 97% | Valor unitario derivado: `eda_precio_usd` / superficie total. |
| `eda_precio_usd` | float64 | 100% | **Target.** Precio de publicación en USD, normalizado y auditado. Escala del modelo (log recomendada). |
| `eda_superficie_cubierta_m2` | float64 | 91% | Superficie cubierta (m²), auditada. |
| `eda_superficie_total_m2` | float64 | 97% | Superficie total (m²), auditada y lista para análisis. |
| `eda_version` | float64 | 100% | Metadato: versión del esquema EDA. |

## Texto — atributos de la descripción (`feat_*`)  (19)

| Variable | Tipo | Completitud | Descripción |
|---|---|---:|---|
| `feat_a_estrenar` | int64 | 100% | Presencia de 'a estrenar' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_amenities` | int64 | 100% | Presencia de 'amenities' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_amoblado` | int64 | 100% | Presencia de 'amoblado' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_apto_credito` | int64 | 100% | Presencia de 'apto credito' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_ascensor` | int64 | 100% | Presencia de 'ascensor' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_balcon` | int64 | 100% | Presencia de 'balcon' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_cochera` | int64 | 100% | Presencia de 'cochera' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_financiacion` | int64 | 100% | Presencia de 'financiacion' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_lavadero` | int64 | 100% | Presencia de 'lavadero' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_litoral_gas` | int64 | 100% | Conexión a **gas natural** (regex `gas natural|litoral gas`). Renombrar a `gas_natural` en FE. |
| `feat_parrillero` | int64 | 100% | Presencia de 'parrillero' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_patio` | int64 | 100% | Presencia de 'patio' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_permite_mascotas` | int64 | 100% | Presencia de 'permite mascotas' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_pileta` | int64 | 100% | Presencia de 'pileta' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_piso_alto` | int64 | 100% | Presencia de 'piso alto' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_seguridad` | int64 | 100% | Presencia de 'seguridad' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_solarium` | int64 | 100% | Presencia de 'solarium' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_sum` | int64 | 100% | Presencia de 'sum' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |
| `feat_vista_rio` | int64 | 100% | Presencia de 'vista rio' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones. |

## Identidad y trazabilidad  (6)

| Variable | Tipo | Completitud | Descripción |
|---|---|---:|---|
| `building_cluster_id` | object | 100% | Agrupamiento por calle-cuadra (proxy de edificio). Uso: *group-aware splitting*. |
| `cambios_precio` | int64 | 100% | N.º de cambios de precio observados entre capturas. |
| `id_confianza` | object | 100% | Nivel de confianza de la identidad de propiedad. |
| `n_capturas` | int64 | 100% | N.º de veces que se capturó el aviso (republicaciones/actualizaciones). |
| `posting_id_ultimo` | int64 | 100% | `posting_id` del último aviso capturado de la propiedad. |
| `property_id` | object | 100% | Identidad conservadora por `posting_id` (no fusiona publicaciones). Deduplicación. |

## Temporal / captura  (4)

| Variable | Tipo | Completitud | Descripción |
|---|---|---:|---|
| `antiguedad_aviso_dias` | float64 | 100% | Antigüedad del aviso = captura − publicación (días). Base del corte ≤ 6 meses. |
| `fecha_publicacion` | object | 100% | Fecha de publicación original del aviso (datePosted), recuperada de la base del scraper. |
| `first_seen` | object | 100% | Primer timestamp en que se capturó el aviso. |
| `last_seen` | object | 100% | Último timestamp en que se capturó el aviso. |

## Localización / geolocalización  (34)

| Variable | Tipo | Completitud | Descripción |
|---|---|---:|---|
| `apto_eda_espacial_preliminar` | bool | 100% | — |
| `apto_eda_espacial_v4` | bool | 100% | Flag final: apto para el análisis espacial. |
| `apto_eda_target_preliminar` | bool | 100% | — |
| `barrio` | float64 | 0% | Campo de barrio del portal (vacío en esta muestra; se usa el barrio oficial por cruce espacial). |
| `barrio_geo_apto_eda_preliminar` | bool | 100% | — |
| `barrio_geo_estado` | object | 100% | — |
| `barrio_geo_fuente` | object | 100% | — |
| `barrio_geo_n_coincidencias` | int64 | 100% | — |
| `barrio_geo_version` | object | 100% | — |
| `barrio_oficial_geo` | object | 100% | **Barrio oficial** asignado por *point-in-polygon* contra la cartografía municipal. |
| `barrio_oficial_mslink` | int64 | 100% | Identificador (MSLINK) del barrio oficial en la cartografía. |
| `direccion_exacta` | object | 100% | — |
| `direccion_norm` | object | 100% | — |
| `geo_coord_n_direcciones` | int64 | 100% | N.º de direcciones distintas que comparten la coordenada. |
| `geo_coord_n_registros` | int64 | 100% | N.º de avisos que comparten exactamente la coordenada. |
| `geo_coordenada_compartida_sospechosa` | bool | 100% | Flag: coordenada compartida sospechosa (nivel G1). |
| `geo_distrito_legacy` | object | 100% | Versión *legacy* (procedencia previa de la geolocalización). Trazabilidad. |
| `geo_distrito_oficial` | object | 100% | Distrito oficial asignado por cruce espacial. |
| `geo_latitud_legacy` | float64 | 100% | Versión *legacy* (procedencia previa de la geolocalización). Trazabilidad. |
| `geo_longitud_legacy` | float64 | 100% | Versión *legacy* (procedencia previa de la geolocalización). Trazabilidad. |
| `geo_nivel_calidad` | object | 100% | **Calidad de geolocalización** (G1 compartida sospechosa / G2 dentro del polígono / G3 georef). Auditoría y segmentación (idea de `geolocation_quality`, Gyger et al. 2026). |
| `geo_precision_validada` | object | 1% | — |
| `geo_provider_validado` | object | 1% | — |
| `geo_source` | object | 100% | Fuente de la geolocalización. |
| `geo_validacion_georef_aplicada` | bool | 100% | — |
| `georef_distrito_oficial` | object | 1% | — |
| `georef_latitud` | float64 | 1% | — |
| `georef_longitud` | float64 | 1% | — |
| `georef_nomenclatura` | object | 1% | — |
| `in_distrito_centro` | float64 | 100% | Indicador: la coordenada cae dentro del Distrito Centro. |
| `latitud` | float64 | 100% | Latitud cruda (previa a auditoría). |
| `longitud` | float64 | 100% | Longitud cruda. |
| `query_georef` | object | 1% | — |
| `validacion_direccion` | object | 1% | — |

## Auditada — trazabilidad (`*_auditado`)  (13)

| Variable | Tipo | Completitud | Descripción |
|---|---|---:|---|
| `antiguedad_auditada` | object | 94% | Versión **auditada** de `antiguedad` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `apto_eda_espacial_auditado` | bool | 100% | Versión **auditada** de `apto_eda_espacial` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `apto_eda_target_auditado` | bool | 100% | Versión **auditada** de `apto_eda_target` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `banos_auditado` | float64 | 97% | Versión **auditada** de `banos` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `cocheras_auditado` | float64 | 26% | Versión **auditada** de `cocheras` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `distrito_auditado` | object | 100% | Versión **auditada** de `distrito` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `expensas_valor_auditado` | float64 | 33% | Versión **auditada** de `expensas_valor` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `latitud_auditada` | float64 | 100% | Versión **auditada** de `latitud` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `longitud_auditada` | float64 | 100% | Versión **auditada** de `longitud` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `precio_auditado` | float64 | 100% | Versión **auditada** de `precio` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `precio_m2_auditado` | float64 | 97% | Versión **auditada** de `precio_m2` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `superficie_cubierta_m2_auditado` | float64 | 91% | Versión **auditada** de `superficie_cubierta_m2` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |
| `superficie_total_m2_auditado` | float64 | 97% | Versión **auditada** de `superficie_total_m2` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad. |

## Flags y metadatos de auditoría  (16)

| Variable | Tipo | Completitud | Descripción |
|---|---|---:|---|
| `alcance_territorial` | object | 100% | — |
| `apto_modelado_preliminar` | bool | 100% | — |
| `auditoria_decisiones_aplicadas` | object | 1% | Metadato/estado de la auditoría (fase P0/P1, versión). |
| `auditoria_espacial_estado` | object | 100% | Metadato/estado de la auditoría (fase P0/P1, versión). |
| `auditoria_p0_pendiente` | bool | 100% | Metadato/estado de la auditoría (fase P0/P1, versión). |
| `auditoria_p1_pendiente` | bool | 100% | Metadato/estado de la auditoría (fase P0/P1, versión). |
| `auditoria_p1_revisado` | bool | 100% | Metadato/estado de la auditoría (fase P0/P1, versión). |
| `auditoria_version` | float64 | 100% | Metadato/estado de la auditoría (fase P0/P1, versión). |
| `calidad_espacial_preliminar` | bool | 100% | — |
| `incluido_eda_v4` | bool | 100% | — |
| `motivo_exclusion_eda_v4` | float64 | 0% | — |
| `motivo_no_apto_modelado` | float64 | 0% | — |
| `motivos_revision` | object | 16% | — |
| `n_quality_flags` | int64 | 100% | — |
| `quality_flags` | object | 9% | — |
| `requiere_revision` | bool | 100% | — |