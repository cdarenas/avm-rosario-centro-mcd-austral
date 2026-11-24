# Revisión P1 — Centro v3

## Propósito

Registrar la revisión de los 364 casos P1 sin convertir los percentiles p01 y
p99 en reglas automáticas de exclusión. Un valor extremo puede ser un inmueble
legítimo; sólo se modifica cuando existe evidencia de error, placeholder o
mezcla de atributos.

## Primera criba de alta severidad

Se revisaron 13 propiedades seleccionadas por alguno de estos criterios
diagnósticos:

- precio hasta USD 10.000;
- superficie total hasta 5 m²;
- precio por m² menor a USD 100 o mayor a USD 10.000;
- expensas mayores a ARS 2.000.000.

Estos umbrales se utilizaron únicamente para priorizar la revisión.

### Decisiones aplicadas

- Dos precios (`USD 1.111` y `USD 2.000`) se clasificaron como target no
  observable porque no existe un valor alternativo demostrable.
- Un precio de `USD 1.500.000` se corrigió a `USD 90.000`; la descripción del
  aviso informa explícitamente ese valor. Su superficie total se corrigió de
  65 m² a 53 m² por la misma fuente.
- Cinco propiedades con superficie total igual a 1 m² quedaron con superficie
  auditada faltante. No se infirió una superficie desde dormitorios o ambientes.
- Un aviso con 20 m² totales y cubiertos se corrigió a 81 m² totales y 65 m²
  cubiertos, valores explícitos en la descripción.
- Un aviso de tres dormitorios asociado a un desarrollo quedó sin superficies
  auditadas: los 40/36 m² capturados no pueden atribuirse inequívocamente a la
  unidad ofrecida.
- Tres valores de expensas entre ARS 11.111.100 y ARS 111.111.000 quedaron como
  faltantes auditados por ser incompatibles con los avisos y carecer de un valor
  alternativo verificable.

## Estado

- P1 totales: 364.
- P1 revisados: 364.
- P1 revisados con conservación de valores: 275.
- P1 pendientes: 0.
- P0 pendientes: 0.

## Revisión de extremos aislados

Se conservaron sin cambios 267 observaciones mediante reglas multivariadas
trazables:

- superficies menores a 24 m² con hasta dos ambientes y hasta un dormitorio;
- superficies mayores a 266 m² con al menos tres ambientes y dos dormitorios;
- precios fuera de p01–p99 con precio por m² dentro del intervalo central;
- expensas aisladas de hasta ARS 1.000.000 en unidades compatibles.
- precios por m² bajos entre USD 300 y el p01, con precio total de al menos
  USD 25.000 y sin alertas adicionales;
- precios por m² altos entre el p99 y USD 5.000, con superficie mínima coherente
  por dormitorio y sin alertas territoriales, de cochera o expensas.

Estas observaciones continúan siendo extremos. La decisión registrada es que no
existe evidencia suficiente para tratarlas como errores.

Dos excepciones no se conservaron automáticamente:

- expensas de ARS 1.111.110 con patrón placeholder, convertidas a faltante
  auditado;
- una publicación de Cerrito 575 que ofrece un galpón y dos departamentos. Se
  conserva para EDA, pero queda como no apta preliminarmente para modelar un
  departamento individual.

## Revisión focalizada de precio por m²

La lectura de las publicaciones permitió aplicar estas decisiones adicionales:

- corregir siete superficies con valores explícitos en las descripciones;
- clasificar como no comparables un edificio completo, un local comercial, dos
  casas, una casa dividida en unidades y dos planes/cesiones sin posesión;
- reemplazar un anticipo de USD 15.000 por el precio contado explícito de
  USD 45.500;
- llevar a faltante superficies que pertenecían a otra tipología dentro de un
  aviso de desarrollo o que no podían reconstruirse sin inferencia.

Los precios por m² conservados siguen siendo extremos reales. No se recortaron
ni winsorizaron.

## Publicaciones sin superficie

Se revisaron los 29 P1 con superficie faltante:

- 28 avisos con precios entre USD 15.000 y USD 24.570 corresponden a desarrollos
  multitipología, anticipos, planes o una cochera. Al no identificar en conjunto
  unidad, superficie y precio total, el target se clasificó como no observable;
- un aviso de USD 623.000 conserva el precio para EDA, pero queda fuera
  preliminarmente del modelado porque agrupa unidades de 2, 3 y 4 dormitorios y
  no informa la superficie asociada al precio.

La superficie no fue imputada manualmente a partir del número de ambientes.

## Validación espacial con fuente oficial

Se consultó la API Georef para los casos que combinaban una
alerta extrema con coordenadas sospechosas. Se conservaron las coordenadas
originales y se añadieron campos auditados:

- 16 propiedades fueron confirmadas dentro del Distrito
  Centro y recibieron coordenadas auditadas;
- cinco direcciones fueron confirmadas fuera del alcance: tres en Distrito
  Norte, una en Oeste y una en Sur. Se conservan para trazabilidad, pero quedan
  como no aptas preliminarmente para modelar el Distrito Centro;
- tres cruces se ubicaron mediante alturas equivalentes verificadas en Georef;
- el aviso de Ovidio Lagos y el río se vinculó con el mismo edificio identificado
  como Aristóbulo del Valle 2799 dentro del dataset;
- Avellaneda y Génova se confirmó en Arroyito/Distrito Norte, pero su coordenada
  auditada permanece faltante para no atribuir precisión no demostrada.

## Cierre de P1

Los 18 casos finales se cerraron con estas decisiones:

- cinco cocheras estructuradas se llevaron a faltante auditado porque la
  descripción indica expresamente que se comercializan aparte del precio;
- ocho extremos se conservaron sin cambios por coherencia entre precio,
  superficie, tipología, amenities y texto de la publicación;
- cinco casos territoriales recibieron una decisión espacial trazable.

No quedan casos P0 ni P1 pendientes. Estar fuera de p01–p99 no fue motivo
suficiente para corregir, excluir o winsorizar una observación.
