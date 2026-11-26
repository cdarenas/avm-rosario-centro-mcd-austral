# Decisión metodológica: agrupamiento y esquema de partición

> Documento de trazabilidad. Registra la evidencia empírica y el razonamiento detrás de la estrategia de
> particionado adoptada en la tesis (validación cruzada *group-aware*). Sustenta §3.3 y §3.6 de la
> metodología y la subsección de robustez del Capítulo 4.

## 1. Planteo del problema

El particionado debe controlar **dos dependencias distintas**, que conviene no confundir:

1. **Republicaciones.** Un mismo departamento reaparece en varios avisos (reposteos, o publicaciones
   simultáneas de distintas inmobiliarias). Si dos publicaciones de la misma unidad quedan una en train y
   otra en test, el modelo puede "memorizar" el precio → fuga de información.
2. **Dependencia espacial / de edificio.** Unidades *distintas* de la misma cuadra o edificio comparten
   atributos latentes (antigüedad, calidad constructiva, amenities, microubicación, a veces el mismo texto o
   inmobiliaria) y precios autocorrelacionados. Su reparto entre train y test también infla el desempeño.

La duda que originó este análisis: agrupar por cuadra reúne propiedades distintas en un mismo grupo; ¿eso
sesga la muestra o hace perder poder de generalización, al dejar folds sin información de una cuadra?

## 2. Evidencia empírica (sobre `zonaprop_v2_matriz_modelado_centro`, 4.765 avisos)

### 2.1 Los grupos reúnen mayormente unidades DISTINTAS, no duplicados

`building_cluster_id`: 1.377 grupos (media 3,46 avisos/grupo; mediana 2; máx. 53; 631 grupos de 1 aviso;
746 de más de uno). Dentro de los 746 grupos con más de un aviso:

- 87,7 % varía más de 5 m² en superficie total (solo 4,6 % tiene superficie idéntica);
- 55,8 % difiere en dormitorios; 53,6 % difiere en baños;
- 78,8 % varía más de 20 % en precio (solo 5,1 % con precio casi idéntico).

**Conclusión:** `building_cluster_id` es un *proxy* de cuadra/edificio, **no** un identificador de unidad
física. Un grupo de 5 son mayormente 5 departamentos distintos del mismo edificio, no una propiedad
publicada 5 veces. Por lo tanto: (a) no hay sobreponderación relevante por republicación; (b) deduplicar a
"una fila por grupo" destruiría observaciones legítimas.

### 2.2 Las republicaciones literales son escasas y no identificables por atributos

La auditoría por firma estructural + descripción exacta (ver `calidad_datos_zonaprop_v2.md`) halló ~3
republicaciones confirmadas y ~1 probable sobre 14 grupos candidatos (31 filas); no se fusionó ni eliminó
ninguna observación. Una regla laxa por atributos (misma tipología + superficie ±2 m² + precio ±3 %) marca
911 avisos (19 %), pero son mayormente **falsos positivos**: edificios con muchas unidades de tipología
idéntica a precio parecido. Sin piso/unidad ni fotos, la identidad física no es recuperable de forma fiable.

**Conclusión:** construir un `property_cluster_id` por atributos sería frágil (umbrales arbitrarios,
fusionaría unidades distintas) y desproporcionado (≈4 casos). No se construye.

### 2.3 Sensibilidad del desempeño al esquema de partición

Mismo modelo (`HistGradientBoostingRegressor`, 300 iteraciones, lr 0,05) y mismas variables; target log1p;
validación cruzada de 5 particiones; métricas OOF (RMSE en USD retransformado).

| Esquema de partición | grupos | R² (log) | RMSE (USD) |
|---|---|---|---|
| KFold aleatorio (por aviso) — referencia | — | 0,9125 | 36.138 |
| GroupKFold cuadra/edificio (`building_cluster_id`) — **principal** | 1.377 | 0,8952 | 41.019 |
| GroupKFold celda espacial ~500 m | 89 | 0,8919 | 42.654 |

- KFold → cuadra: **−0,0172 de R² / +4.881 USD de RMSE** ⇒ el KFold ingenuo es optimista por dependencia local.
- cuadra → celda ~500 m: **−0,0033 de R²** ⇒ diferencia marginal; el agrupamiento por cuadra ya absorbe la
  mayor parte de la dependencia espacial y no es, a su vez, materialmente optimista.

### 2.4 Balance entre folds (GroupKFold cuadra, k=5)

| fold | n | grupos | precio mediano (USD) | superficie mediana | barrio top |
|---|---|---|---|---|---|
| 1 | 953 | 275 | 115.000 | 70,0 | 56,2 % |
| 2 | 953 | 275 | 130.000 | 76,0 | 64,6 % |
| 3 | 953 | 275 | 120.000 | 77,0 | 59,7 % |
| 4 | 953 | 276 | 112.000 | 71,0 | 58,4 % |
| 5 | 953 | 276 | 110.000 | 70,0 | 60,2 % |

Balance razonable en tamaño, precio, superficie y composición por barrio. El grupo máximo (53 avisos) es
apenas el 1,1 % de la muestra: no domina ningún fold. La pérdida de eficiencia por agrupar es, por lo tanto,
despreciable en la práctica (1.377 grupos ⇒ ~275 por fold).

## 3. Modelo vs. estimación (respuesta a la duda de generalización)

El agrupamiento **no reduce la capacidad del modelo desplegado**: el AVM final se entrena con todas las
observaciones —todas las cuadras incluidas—. El agrupamiento solo gobierna cómo se **estima** el error. Lo
que cambia es el escenario medido:

- **KFold aleatorio** estima: predecir un aviso nuevo en una cuadra con comparables ya vistos.
- **GroupKFold por cuadra** estima: predecir en una cuadra **no observada** en el entrenamiento (tarea más
  exigente, acorde a un uso robusto del avalúo).

Que el costo de la tarea exigente sea pequeño (≈0,017 de R²) evidencia que el modelo generaliza por
**localización continua + atributos estructurales**, no por identidad de cuadra: ante una cuadra ausente,
interpola desde coordenadas, distancias, barrio y densidad. No queda "a ciegas".

## 4. Decisión adoptada

1. **Conservar todos los avisos** (sin deduplicar): son unidades genuinas; deduplicar perdería información
   real y el peso de las ~4 republicaciones es despreciable.
2. **No construir un identificador de unidad física** por atributos (frágil y desproporcionado).
3. **Protocolo principal:** `GroupKFold` sobre `building_cluster_id`, presentado honestamente como
   agrupamiento de **cuadra/edificio** (validación espacial suave), del cual el control de republicaciones
   es un caso particular cubierto.
4. **Reportar la partición aleatoria como referencia** (cota optimista) y la **celda espacial como
   robustez** (cota exigente). El desempeño esperado en operación queda acotado entre la aleatoria y la
   agrupada; la brecha pequeña vuelve la decisión de bajo riesgo numérico.
5. **Auditar el balance entre folds** (hecho; §2.4).

## 5. Material listo para el Capítulo 4 (subsección "Robustez de la partición")

> El diseño experimental adopta como protocolo principal la validación cruzada agrupada por cuadra/edificio.
> Para dimensionar el efecto de esta elección se contrastaron tres esquemas de partición de severidad
> creciente, con un mismo modelo y un mismo conjunto de variables (Cuadro). El paso de la partición
> aleatoria a la agrupada por cuadra reduce el $R^2$ en aproximadamente 0,017 (unos 4.900 dólares de RMSE),
> lo que sugiere que la partición aleatoria sobreestima el desempeño al dejar unidades muy próximas a ambos
> lados de la partición. El paso posterior a una partición por celdas espaciales más gruesas añade una
> diferencia marginal (≈0,003), lo que indicaría que el agrupamiento por cuadra ya absorbe la mayor parte de
> la dependencia local. La lectura conjunta sería que el desempeño esperado en operación se ubica entre la
> cota optimista (cuadra ya observada) y la exigente (cuadra no observada), y que el modelo tendería a
> generalizar a partir de la localización continua y los atributos estructurales más que de la identidad de
> cada cuadra. El balance entre folds (tamaño, precio, superficie y composición por barrio) no evidencia
> desequilibrios que comprometan la comparación.

## 6. Referencias de respaldo

- Hastie, Tibshirani & Friedman (2017), *The Elements of Statistical Learning*, §7.10 (validación cruzada y
  fuga de información).
- Kuhn & Johnson (2016), *Applied Predictive Modeling* (agrupamiento en resampling).
- Roberts et al. (2017), *Ecography* (validación con estructura espacial/agrupada; block CV).

## 7. Reproducibilidad

Las cifras de §2 se obtienen sobre `data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz`
(target `eda_precio_usd` en log1p; grupo `building_cluster_id`; celda espacial por redondeo de
lat/lon a ~0,005°). Modelo de referencia: `HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05)`.
