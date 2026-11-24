# Revisión inicial de casos P0 — Centro v2

Este documento registra propuestas basadas exclusivamente en los campos
capturados. No modifica el dataset ni reemplaza la validación contra la
publicación de origen.

## 1. Precio placeholder — 40 casos

Los títulos muestran valores como `USD 1`, `USD 2`, `USD 10`, `USD 111` o
`USD 123`. Las descripciones presentan inmuebles ordinarios o desarrollos, pero
no contienen un precio alternativo demostrable.

- Propuesta: `target_no_observable`.
- Valor corregido: no inferir.
- Tratamiento futuro: excluir del entrenamiento supervisado si el precio no
  puede recuperarse; conservar en la tabla auditada y documentar el motivo.

## 2. Precio de USD 60.708.000 — 1 caso

- `property_id`: `prop_6d5aad2773c6bd96`.
- Dirección: Necochea al 2000, unidad 06 B.
- `precio_ultimo`: USD 60.708.000.
- Título capturado: `USD 42.342`.
- `precio_min`: USD 42.342.
- Superficie total: 32 m².

El valor máximo es incompatible con el título y genera USD 1.897.125/m². La
publicación activa fue consultada el 21 de agosto de 2026 y muestra USD 42.342,
32 m² totales y 28 m² cubiertos.

- Propuesta: corregir el precio representativo a USD 42.342, conservando
  USD 60.708.000 como valor original anómalo y registrando como evidencia la
  publicación activa y el `precio_min` capturado. La selección del snapshot debe
  quedar documentada.

## 3. Superficies mayores a 1.000 m² — 4 casos

Tres pares total/cubierta son consistentes con pérdida de separador decimal:

| `property_id` | Total capturado | Cubierta capturada | Candidato a total | Candidato a cubierta |
|---|---:|---:|---:|---:|
| `prop_c04276623062bb71` | 267.682 | 9.865 | 267,682 m² | 98,65 m² |
| `prop_f487732a6194d04c` | 6.709 | 5.740 | 67,09 m² | 57,40 m² |
| `prop_073596effa6ba7fb` | 7.746 | 6.183 | 77,46 m² | 61,83 m² |

Las correcciones son plausibles, pero deben cotejarse con el HTML o fuente del
aviso. Para `prop_8c7827e9c53d3ecb` (2.107 m² totales y 77 m² cubiertos) no hay
una transformación inequívoca; debe permanecer pendiente.

Al consultar las URLs el 21 de agosto de 2026, tres avisos ya estaban
finalizados. El de Maipú 900 permanecía activo, pero el propio portal mostraba
7.746 m² totales y 6.183 m² cubiertos, sin aportar el separador perdido. Por
ello, la plausibilidad estadística no basta para confirmar el valor corregido y
debe conservarse la evidencia capturada.

## 4. Superficie cubierta mayor que total — 12 casos

Las descripciones muestran situaciones heterogéneas: posibles campos invertidos,
superficie exclusiva frente a total, balcones/patios omitidos o errores de
parseo. Por ejemplo, Maipú 1036 informa en el texto 89,02 m² exclusivos y 12,61
m² de balcón, mientras los campos capturados son 13 m² totales y 89 m²
cubiertos.

- Propuesta: revisión individual; no adoptar una regla general de intercambio
  entre campos.

Para Maipú 1036 la descripción aporta evidencia suficiente: 89,02 m²
exclusivos y 12,61 m² de balcón y patio. En la versión auditada se registran
89,02 m² cubiertos y 101,63 m² totales, conservando los valores capturados en
las columnas originales. En los otros once casos se conserva la superficie
total cuando es plausible y se lleva la cubierta incompatible a faltante. El
aviso que ofrece un edificio completo queda sin ambas superficies auditadas,
porque mezcla atributos de unidades y del conjunto.

## 5. Antigüedad de 792 años — 1 caso

- `property_id`: `prop_adaaefe3dcd3c7bf`.
- La descripción no informa una antigüedad verificable.
- Propuesta: marcar como error y convertir a faltante sólo en una versión
  auditada, salvo recuperación del dato original.

## 6. Cuarenta baños — 1 caso

- `property_id`: `prop_310af6efd00eced5`.
- La descripción indica un dormitorio principal en suite y un baño completo
  adicional; no respalda cuarenta baños.
- Propuesta: valor candidato `2`, pendiente de cotejo con la ficha estructurada.

La descripción enumera un dormitorio principal en suite y un baño completo
adicional. Se adopta `2` en `banos_auditado`, sin modificar `banos`.

## 7. Más de diez cocheras — 8 casos

Los valores 14, 20, 27 y 50 aparecen en avisos de desarrollos y parecen describir
la cantidad de cocheras del edificio o disponibles en el proyecto. No demuestran
que la unidad publicada incluya esa cantidad.

- Propuesta: no usar esos valores como cocheras de la propiedad.
- Valor corregido: mantener pendiente o faltante, salvo que el texto indique de
  forma inequívoca cuántas cocheras están incluidas en la unidad y en el precio.

Se adopta faltante en `cocheras_auditado` para los ocho casos. La decisión no
afirma que las unidades carezcan de cochera: indica que la cantidad capturada
pertenece al desarrollo y no puede atribuirse a la unidad publicada.

## Próxima acción

Los 67 casos P0 quedaron tratados mediante una corrección respaldada o una
conversión conservadora a faltante en columnas auditadas. No se aplicaron
transformaciones decimales automáticas. Los 40 placeholders de precio se
clasifican como target no observable y se conservan en el dataset. El siguiente
nivel de trabajo es analizar P1 y definir criterios de elegibilidad para el
dataset de modelado, sin confundir el cierre de P0 con ausencia total de problemas.
