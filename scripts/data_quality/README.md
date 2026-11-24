# Calidad de datos

Scripts reproducibles para pasar de la tabla interim a artefactos de auditoría y
EDA sin modificar la fuente raw.

```bash
python scripts/data_quality/construir_tabla_auditoria.py \
  data/interim/zonaprop_v2_candidate.csv.gz \
  data/external/distritos_rosario/distritos_descentralizados_rosario.csv \
  data/interim/zonaprop_v2_auditoria.csv.gz

python scripts/data_quality/construir_dataset_eda.py \
  data/interim/zonaprop_v2_candidate.csv.gz \
  data/interim/zonaprop_v2_auditoria.csv.gz \
  data/processed/zonaprop_v2_eda_v0.csv.gz

python scripts/data_quality/construir_dataset_eda_centro.py \
  data/processed/zonaprop_v2_eda_v0.csv.gz \
  data/processed/zonaprop_v2_eda_centro_v0.csv.gz
```

El primer script no excluye filas. El segundo limita el alcance inicial a target
USD positivo, registra las exclusiones y conserva outliers, faltantes y marcas de
revisión. Los artefactos de datos permanecen fuera de Git.

El tercer script materializa el universo del área de estudio: target USD positivo
y coordenadas dentro del polígono oficial del Distrito Centro. Conserva los
casos geográficos sospechosos con su flag y registra todo lo que queda fuera del
alcance territorial.

`construir_auditoria_direcciones.py` utiliza los caches legacy como entradas de
solo lectura para reconstruir si cada coordenada provino de dirección exacta,
Georef o un fallback a nivel de calle. Produce una cola priorizada y columnas
vacías para registrar la decisión de revisión sin modificar ningún dataset.

`validar_direcciones_georef.py` consulta Georef solo para las direcciones P1 con
calle y altura interpretables. Deduplica queries, persiste cada respuesta para
reanudar y cruza el resultado con los polígonos oficiales. Requiere autorización
explícita porque transmite direcciones al servicio público; nunca modifica el
dataset automáticamente.

`aplicar_validacion_georef.py` crea una versión nueva del dataset Centro usando
solo respuestas Georef resueltas. Conserva coordenadas y distrito legacy en
columnas separadas, registra proveedor y precisión, y nunca sobrescribe la v0.

`enriquecer_barrios_oficiales.py` cruza las coordenadas con la cartografía
municipal de barrios oficiales. Conserva la columna `barrio`, crea una versión
nueva del dataset y separa asignaciones aptas, provisionales, limítrofes y no
resueltas. Interpreta directamente los polígonos GeoJSON en WGS 84 incluidos en
el CSV oficial.

`construir_auditoria_extremos_eda.py` genera una cola priorizada de casos con
precios, superficies, relaciones físicas u otras variables que requieren
revisión. Distingue explícitamente los faltantes de los extremos y agrega campos
vacíos para decisión, evidencia y justificación. Sus umbrales son diagnósticos:
no corrige ni excluye observaciones.

`construir_dataset_eda_auditado.py` aplica un registro explícito de decisiones
sobre columnas nuevas, sin sobrescribir los valores originales. La salida
identifica targets no observables, correcciones confirmadas y casos P0 todavía
pendientes, y recalcula el precio/m² auditado sólo para descripción.

`construir_dataset_eda_v4.py` materializa la muestra analítica una vez cerradas
las auditorías P0 y P1. Exige target observable y unidad comparable, conserva
todas las columnas de la v3, agrega aliases `eda_*` que apuntan exclusivamente a
valores auditados y genera artefactos separados de exclusiones y flujo. La
calidad espacial es una marca adicional: no se exige para el EDA no espacial.

`auditar_duplicados_republicaciones.py` verifica claves exactas, combina una
firma estructural conservadora con descripciones idénticas y genera una cola de
revisión sin fusionar filas. También crea `split_group_id_v1` para corregir el
agrupamiento de calles con nombres numéricos y produce el mapeo que podrá usarse
en validación agrupada.
