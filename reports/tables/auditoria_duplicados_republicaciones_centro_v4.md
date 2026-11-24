# Auditoría de duplicados y republicaciones — Centro v4

## Resultado automático

- filas auditadas: 9,498;
- `property_id` duplicados: 0;
- `posting_id_ultimo` duplicados: 0;
- URL duplicadas: 0;
- grupos candidatos a revisión: 14;
- filas miembro de esos grupos: 31;
- clusters de edificio/cuadra: 1,812;
- tamaño máximo de cluster: 109;
- identidades legacy de baja confianza: 1,142.

## Interpretación

No existen duplicados exactos por las claves técnicas disponibles. Las firmas de
republicación son señales para revisión: una descripción idéntica puede pertenecer
a distintas unidades de un mismo desarrollo. No se fusionó ni eliminó ninguna fila.

`building_cluster_id` debe evaluarse como unidad de agrupamiento para los folds,
no como identificador de propiedad física. Los clusters grandes pueden representar
una cuadra, un edificio con muchas unidades o una dirección incompleta.

## Revisión de los 14 grupos candidatos

| Decisión | Grupos |
|---|---:|
| Republicación confirmada | 3 |
| Republicación probable | 1 |
| Unidades distintas confirmadas | 1 |
| Unidades distintas del mismo desarrollo | 5 |
| No resuelto | 4 |

Las tres republicaciones confirmadas corresponden a pares con posting distinto
pero mismo precio, dirección, atributos y descripción específica de la unidad.
La republicación probable corresponde a Balcarce 572/576: las superficies y la
tipología prácticamente coinciden, pero sólo un aviso identifica piso y unidad.

Los cuatro grupos no resueltos se conservan separados. No se deduplican porque
los avisos no permiten distinguir con certeza entre republicación y unidades
equivalentes del mismo edificio.

## Corrección para agrupamiento de folds

El cluster legacy interpreta incorrectamente nombres de calles que comienzan con
un número, como `3 de Febrero`, `9 de Julio` o `27 de Febrero`. Se construyó
`split_group_id_v1`, que busca una altura de tres o más dígitos y, cuando no la
encuentra, usa la intersección normalizada completa.

- clusters legacy: 1.875;
- clusters corregidos para splitting: 1.812;
- clusters corregidos con 20 o más publicaciones: 94;
- tamaño máximo: 109 propiedades;
- 32 grupos corregidos reúnen más de un cluster legacy.

La tabla `grupos_split_centro_v4.csv` contiene el mapeo de las 9.498
observaciones. Esta clave es una propuesta conservadora para mantener juntas las
unidades cercanas durante la validación; su efecto sobre tamaño y balance de los
folds deberá diagnosticarse antes de adoptarla definitivamente.
