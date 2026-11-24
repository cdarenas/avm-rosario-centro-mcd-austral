# Perfil EDA inicial — ZonaProp Centro v1

Este perfil describe el artefacto sin modificarlo. No se imputaron faltantes, no
se eliminaron outliers y ninguna alerta se convirtió en exclusión automática.

## Alcance

- Observaciones: **9,582**.
- Columnas conservadas: **80**.
- `property_id` únicos: **9,582**.
- Aptas para análisis espacial preliminar: **8,766**.
- Pendientes de validación espacial: **816**.

## Primeras señales

- Precio mediano publicado: **USD 125,000**.
- Precio mediano observado por m²: **USD 1,755.93**.
- Superficie total mediana: **76 m²**.
- Requieren revisión según las banderas existentes: **2,046**.
- Tienen coordenada compartida sospechosa: **913**.
- El texto sugiere que la cochera podría no estar incluida en el precio: **408**. Esta regla es sólo una búsqueda textual inicial.
- Presentan superficie cubierta mayor que la total: **12**.

Los máximos de precio, precio por m², superficie, antigüedad, baños, cocheras y
expensas son extremadamente altos respecto de sus percentiles 99. Deben
investigarse como casos individuales antes de definir reglas de tratamiento.

## Columnas con mayor proporción de faltantes

- `barrio`: 100.00% (9582 filas)
- `geo_precision_validada`: 98.90% (9477 filas)
- `geo_provider_validado`: 98.90% (9477 filas)
- `georef_distrito_oficial`: 98.90% (9477 filas)
- `georef_latitud`: 98.90% (9477 filas)
- `georef_longitud`: 98.90% (9477 filas)
- `georef_nomenclatura`: 98.90% (9477 filas)
- `query_georef`: 98.90% (9477 filas)
- `validacion_direccion`: 98.90% (9477 filas)
- `quality_flags`: 86.99% (8335 filas)

## Uso correcto

Las tablas permiten priorizar auditorías y diseñar visualizaciones. Las
comparaciones territoriales deben usar sólo `apto_eda_espacial_preliminar=True`;
los 816 casos pendientes permanecen en el dataset general y deben informarse por
separado. Este perfil no es todavía una muestra de entrenamiento.
