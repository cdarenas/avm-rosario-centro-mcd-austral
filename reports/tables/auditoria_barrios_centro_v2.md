# Auditoría de asignación de barrios — Centro v2

El cruce point-in-polygon asignó un barrio oficial municipal a las 9.582
propiedades. No se detectaron coordenadas fuera de los polígonos, asignaciones
múltiples ni puntos exactamente sobre límites barriales.

## Estado de asignación

- 8.766 propiedades: barrio asignado y coordenada apta para EDA espacial
  preliminar.
- 816 propiedades: barrio asignado de manera provisional porque la coordenada
  continúa pendiente de validación.

La asignación provisional no resuelve el problema de calidad de coordenadas. Por
lo tanto, `barrio_geo_apto_eda_preliminar` es la bandera que debe utilizarse para
comparaciones territoriales iniciales.

## Distribución apta para EDA territorial

| Barrio oficial | Propiedades |
|---|---:|
| CENTRO | 5.209 |
| ALBERTO OLMEDO | 872 |
| NTRA SRA DE LOURDES | 752 |
| DEL ABASTO | 594 |
| REPUBLICA DE LA 6TA | 552 |
| ECHESORTU | 429 |
| LUIS AGOTE | 229 |
| ESPAÑA Y HOSPITALES | 70 |
| JORGE CURA | 23 |
| PARQUE CASADO | 17 |
| LUDUEÑA SUR Y NORTE | 15 |
| LATINOAMERICA | 4 |

Los barrios con muy pocas observaciones no deben compararse mediante rankings
simples sin informar el tamaño muestral y la incertidumbre. El predominio de
CENTRO también debe considerarse al interpretar resultados agregados.

La tabla CSV acompañante desagrega cada barrio según el estado de la coordenada.
