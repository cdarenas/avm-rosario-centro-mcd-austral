# Auditoría de extremos y anomalías — Centro v2

La cola contiene 2.018 propiedades con al menos una señal diagnóstica. Ninguna
fue corregida ni excluida automáticamente.

## Prioridades

| Prioridad | Casos | Interpretación |
|---|---:|---|
| P0 | 67 | anomalía fuerte; revisión manual inmediata |
| P1 | 364 | extremo estadístico o expensas altas; revisar después de P0 |
| P2 | 1.587 | faltante, texto ambiguo o coordenada pendiente |

Las prioridades pueden superponerse con varias banderas; cada propiedad aparece
una sola vez en la tabla y conserva todos sus motivos.

## Señales principales

| Señal | Casos |
|---|---:|
| Coordenada pendiente | 816 |
| Superficie faltante | 520 |
| Cochera posiblemente no incluida | 408 |
| Precio fuera de p01–p99 | 176 |
| Precio/m² fuera de p01–p99 | 175 |
| Superficie fuera de p01–p99 | 157 |
| Precio placeholder hasta USD 1.000 | 40 |
| Expensas superiores a p99 | 27 |
| Superficie cubierta mayor que total | 12 |
| Cocheras superiores a 10 | 8 |
| Superficie superior a 1.000 m² | 4 |
| Precio superior a diez veces p99 | 1 |
| Antigüedad superior a 150 años | 1 |
| Baños superiores a 10 | 1 |

## Uso

La revisión debe completar `decision`, `valor_corregido`, `evidencia`,
`justificacion`, `revisado_por` y `fecha_revision`. Las decisiones admisibles se
definirán antes de iniciar la carga manual; los umbrales de esta tabla sólo
priorizan casos y no constituyen reglas finales de preprocesamiento.
