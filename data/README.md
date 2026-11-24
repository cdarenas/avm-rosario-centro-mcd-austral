# Datos

Este directorio sigue un flujo de datos por etapas:

- `raw/`: copia inmutable de los datos originales.
- `external/`: fuentes externas o de terceros.
- `interim/`: resultados parciales de limpieza y transformación.
- `processed/`: conjuntos listos para análisis o modelado.

Registrar aquí, para cada fuente, su procedencia, fecha de descarga, responsable,
licencia o restricciones de uso y el script necesario para reproducirla.

Los datos no se versionan por defecto. Antes de incorporar un archivo, verificar
que no contenga información personal, sensible o sujeta a restricciones.

## ZonaProp v2

La fuente raw y su huella reproducible están documentadas en
`raw/zonaprop_v2/`. La primera tabla candidata se genera localmente en
`interim/zonaprop_v2_candidate.csv.gz`, junto con un manifiesto JSON, mediante
`scripts/scraping/zonaprop_v2/construir_dataset_candidato.py`.

La auditoría y las reglas de seguridad vigentes se registran en
`docs/calidad_datos_zonaprop_v2.md`. Ningún archivo de `interim/` debe
interpretarse como dataset final de modelado.

La cartografía municipal usada para validar coordenadas se documenta en
`external/distritos_rosario/`. Las tablas locales de auditoría y EDA se generan
con los scripts de `scripts/data_quality/`; sus manifiestos y registros de
exclusión acompañan siempre a los artefactos, aunque los datos no se versionen.

## Excepción de versionado para revisión académica

Se versiona de manera explícita
`processed/zonaprop_v2_eda_centro_v1.csv.gz`, sin reducir columnas ni modificar
su contenido, para compartir el avance con el director de tesis. Su manifiesto
acompañante registra hash, dimensiones, procedencia y estado de calidad.

Debe interpretarse como una versión preliminar y parcialmente depurada: conserva
faltantes, outliers, columnas de trazabilidad y casos pendientes. Su publicación
no implica que las reglas de limpieza o el universo final de modelado estén
cerrados.

Esta excepción alcanza únicamente a esa versión identificada. No habilita el
versionado automático de raw, tablas interim, caches, exclusiones, versiones
anteriores ni futuros datasets processed. Cada nueva versión deberá evaluarse y
autorizarse por separado.

## Enriquecimiento territorial por barrios

La cartografía de `external/barrios_rosario/` permite derivar el barrio oficial
mediante cruce point-in-polygon. La columna original `barrio` no se sobrescribe.
La versión `processed/zonaprop_v2_eda_centro_v2_barrios.csv.gz` agrega la
nomenclatura oficial, fuente, versión y estado de asignación. Sólo los registros
con `barrio_geo_apto_eda_preliminar=True` deben usarse inicialmente en análisis
comparativos por barrio.

La versión `processed/zonaprop_v2_eda_centro_v3_auditado.csv.gz` conserva esas
87 columnas y agrega campos auditados según
`config/auditoria_p0_decisiones_v1.json`. Los originales nunca se sobrescriben:
la v3 identifica 70 targets no observables, aplica 75 correcciones respaldadas
y cierra los 67 casos P0 y los 364 casos P1 sin pendientes.

La versión `processed/zonaprop_v2_eda_centro_v4.csv.gz` es la muestra analítica
para EDA: contiene 9.498 unidades con target observable y comparables con un
departamento individual del Distrito Centro. Conserva las 108 columnas de la
v3 y agrega variables consolidadas `eda_*`; no imputa ni winsoriza. Para mapas y
análisis territoriales debe aplicarse `apto_eda_espacial_v4`, que identifica
8.711 observaciones. Esta versión todavía no define folds ni constituye el
dataset final de modelado.
