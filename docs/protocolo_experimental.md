# Protocolo experimental

## 1. Objetivo

Establecer un procedimiento común, reproducible y auditable para comparar modelos y escenarios de información en la tesis.

El protocolo deberá permanecer estable durante la comparación principal.

Los análisis exploratorios podrán utilizar procedimientos distintos, pero deberán identificarse explícitamente como exploratorios.

---

# 2. Principio general

Bibliografía
→ hipótesis
→ diseño experimental
→ implementación
→ experimento
→ evidencia
→ análisis estadístico
→ conclusión

---

# 3. Escenarios de información

Se utilizará un esquema incremental de features.

La definición exacta podrá ajustarse después de conocer el dataset, conservando la lógica de incremento informativo.

## S1 — Características estructurales

Información intrínseca del inmueble.

Ejemplos:

- superficie cubierta;
- superficie total;
- ambientes;
- dormitorios;
- baños;
- antigüedad;
- piso;
- cochera;
- características físicas disponibles.

## S2 — Localización

S1 +

- barrio / microzona;
- latitud;
- longitud;
- otras representaciones territoriales no supervisadas.

## S3 — Microlocalización y entorno

S2 +

- distancias a puntos de interés;
- espacios verdes;
- transporte;
- equipamientos;
- otras variables territoriales justificadas.

## S4 — Información enriquecida

S3 +

- variables derivadas del texto;
- amenities detectadas;
- información espacial supervisada si queda metodológicamente justificada.

> **Spatial lag del precio (feature supervisada, por fold).** Candidata central de S4: el promedio
> del precio de los vecinos ponderado por distancia (KNN). Explota la autocorrelación espacial
> detectada en el EDA y es el eje de RQ4 (¿aporta un componente espacial explícito tras las
> covariables?). **Recaudo crítico:** usa el target de los vecinos, así que **debe calcularse dentro
> de cada fold, con precios del *train* únicamente** (transformer del pipeline de modelado), **nunca**
> como columna del dataset — calcularlo globalmente induce fuga de información (ESL §7.10.2). Un
> antecedente propio (notebooks tasaprop) lo calculaba de forma global; acá se corrige a nivel fold.

La composición exacta de cada escenario deberá quedar versionada.

Al avanzar de S1 hacia escenarios territorialmente más ricos se medirá cómo
cambia la autocorrelación espacial de los residuos OOF. El objetivo será
distinguir la información territorial ya capturada por covariables observadas de
la dependencia residual que podría justificar un componente espacial explícito.

---

# 4. Particionado y resampling

## Regla general

Los modelos deben compararse usando las mismas particiones.

## Agrupamiento

Si se detectan múltiples publicaciones correspondientes a una misma propiedad, todas deberán pertenecer al mismo grupo de partición.

## Test final

Se evaluará la conveniencia de reservar un test final independiente.

El tamaño se definirá en función del número de propiedades únicas disponibles.

Si se reserva, se utilizará una sola vez como evaluación final independiente. No
se empleará para seleccionar features, ajustar hiperparámetros, elegir modelos ni
definir transformaciones. Si el test se consulta repetidamente para tomar
decisiones, deja de funcionar como evaluación independiente.

## Cross-validation

El esquema definitivo podrá utilizar:

- K-fold;
- repeated K-fold;
- group-aware CV;
- spatial CV;
- validación temporal.

La selección dependerá de las propiedades del dataset.

No se fijan todavía el número de folds, el uso de repeated CV, spatial CV o
holdout temporal, ni el tamaño del test final.

## Niveles de evaluación

### A. Diagnósticos de training

Se utilizarán para detectar underfitting y overfitting. El desempeño in-sample no
constituirá evidencia principal de generalización.

### B. Cross-validation y OOF

Se utilizarán para:

- comparar modelos;
- realizar tuning;
- evaluar los escenarios S1–S4;
- analizar estabilidad;
- generar predicciones OOF;
- diagnosticar errores fuera de muestra.

### C. Holdout final

Cuando se adopte, proporcionará una evaluación final independiente. No se
utilizará para feature selection, tuning ni selección de modelo.

---

# 5. Preprocessing dentro del fold

Cuando existan transformaciones aprendidas, el objeto evaluado en
cross-validation deberá ser el pipeline completo: preprocessing, feature
engineering aprendido y modelo. Cada operación deberá ajustarse únicamente con
el training del fold correspondiente.

Para cada split:

TRAIN
    ↓
fit preprocessing
    ↓
transform TRAIN
transform VALIDATION
    ↓
fit modelo en TRAIN
    ↓
predict VALIDATION

Está prohibido:

DATASET COMPLETO
    ↓
fit preprocessing
    ↓
cross-validation

cuando el preprocessing aprende parámetros del conjunto de datos.

---

# 6. Features supervisadas

Toda feature que utilice el target deberá calcularse exclusivamente con información disponible en el training correspondiente.

Ejemplos:

- target encoding;
- medias por barrio basadas en precio;
- precio de vecinos;
- spatial lag supervisado.

Para una observación de validación:

feature(x_validation)
=
f(X_train, y_train)

y nunca:

feature(x_validation)
=
f(X_train ∪ X_validation,
  y_train ∪ y_validation)

---

# 7. Modelos

## Hedónico

Baseline interpretable.

La especificación final deberá considerar:

- transformaciones;
- residuos;
- heterocedasticidad;
- multicolinealidad;
- observaciones influyentes;
- variables indicadoras;
- posibles no linealidades;
- interacciones justificadas.

## Random Forest

Modelo ensemble basado en bagging.

Se ajustarán hiperparámetros dentro del esquema de entrenamiento.

## LightGBM

Modelo predictivo central.

Se realizará optimización de hiperparámetros utilizando únicamente información de entrenamiento.

---

# 8. Tuning

El tuning deberá estar separado conceptualmente de la evaluación final.

No se utilizará el conjunto final de test para seleccionar:

- features;
- hiperparámetros;
- transformaciones;
- K espacial;
- arquitectura de escenarios.

El registro de cada búsqueda deberá incluir:

- `search_strategy`;
- `search_space`;
- `seed`;
- número de iteraciones;
- `scoring`;
- folds;
- `best_params`.

Se mantienen como candidatas:

- `GridSearchCV` para espacios pequeños;
- `RandomizedSearchCV` para espacios amplios;
- Optuna para LightGBM, pendiente de justificar y definir.

Una búsqueda excesiva sobre los mismos folds puede sobreajustar el propio proceso
de tuning. La amplitud y repetición de las búsquedas deberán registrarse y
considerarse al interpretar el resultado.

Se distinguirán:

- **hiperparámetros computacionales**, que controlan el ajuste de un algoritmo;
- **decisiones metodológicas**, que definen el problema y el diseño experimental.

La variable objetivo, los feature sets, el diseño espacial y la definición de los
escenarios S1–S4 no se tratarán automáticamente como simples hiperparámetros.

---

# 9. Métricas

Métricas principales:

- RMSE;
- MAE;
- R².

Métricas adicionales podrán incorporarse si aportan información relevante.

Se evaluará la conveniencia de:

- MAPE;
- MedAE;
- error relativo por segmento.

No se interpretará una mejora únicamente por el valor medio.

---

# 10. Comparación entre modelos

Para cada modelo y escenario se registrará:

- métricas por fold;
- media;
- desviación;
- distribución de errores;
- predicciones OOF.

Las comparaciones deberán ser pareadas cuando los modelos hayan sido evaluados sobre los mismos folds.

## Análisis de errores

El análisis de errores utilizará preferentemente predicciones OOF o de validación,
no predicciones in-sample. Como diagnóstico, podrá segmentarse por:

- rango de precio;
- superficie;
- microzona;
- calidad de geocodificación;
- densidad de comparables;
- missingness;
- período temporal.

Estos análisis tendrán finalidad diagnóstica y deberán distinguirse de la
evaluación final independiente.

---

# 11. Estabilidad

Además del desempeño promedio se analizará:

- variabilidad entre folds;
- sensibilidad a la seed;
- sensibilidad a hiperparámetros;
- estabilidad por rango de precios;
- estabilidad territorial;
- estabilidad temporal si corresponde.

---

# 12. Análisis estadístico

Cuando sea adecuado se analizarán las diferencias pareadas entre modelos utilizando las observaciones o resamples comunes.

La elección del procedimiento estadístico se realizará después de definir el esquema final de resampling.

No se asumirá significancia únicamente porque un modelo tenga menor RMSE promedio.

---

# 13. Componente espacial

Se analizará:

1. distribución espacial del target;
2. estructura espacial;
3. calidad y cobertura de la geocodificación;
4. autocorrelación espacial de residuos OOF en cada escenario S1–S4;
5. cambio de la autocorrelación residual al incorporar información territorial;
6. desempeño incremental de features espaciales;
7. desempeño fuera de muestra de cualquier extensión espacial explícita.

La elección de SAR, SEM, KNN espacial, Gaussian Processes, GPBoost u otras
variantes dependerá de esta evidencia. No se incorporará automáticamente un
componente espacial explícito si las covariables observadas ya absorben la
dependencia relevante o si la mejora fuera de muestra no es estable.

La feature de precio de vecinos se evaluará como candidato experimental mediante
una ablación específica. Su cálculo deberá respetar los límites del fold y su
aporte no se extrapolará de Gyger et al. (2026), quienes estudian Gaussian
Processes y GPBoost, no KNN de precios.

## Auditoría de geocodificación

Antes del modelado espacial se registrará, como mínimo:

- proporción de observaciones con ubicación exacta, aproximada, imputada o no
  disponible;
- método y fuente de geocodificación;
- resolución espacial efectiva;
- distribución territorial de cada nivel de calidad;
- sensibilidad de métricas y diagnósticos espaciales a la calidad de ubicación.

Cuando el tamaño y la cobertura lo permitan, se compararán resultados usando
todas las observaciones geocodificadas y el subconjunto con localización exacta.
Esta comparación deberá reconocer que restringir la muestra puede alterar la
cobertura territorial y no constituye por sí sola una estimación libre de sesgo.

---

# 14. Interpretabilidad

Para LightGBM se utilizará SHAP.

Se analizarán:

- importancia global;
- dirección de contribuciones;
- explicaciones locales;
- comportamiento de variables centrales;
- estabilidad de las explicaciones cuando sea posible.

La interpretación deberá limitarse al comportamiento predictivo del modelo.

---

# 15. Registro obligatorio del experimento

Cada ejecución deberá registrar como mínimo:

- experiment_id;
- timestamp;
- git_commit;
- dataset_version;
- target;
- feature_scenario;
- split_strategy;
- folds;
- seed;
- modelo;
- preprocessing;
- hiperparámetros;
- `search_strategy`;
- `search_space`;
- número de iteraciones de búsqueda;
- `scoring`;
- `best_params`;
- métricas por fold;
- métricas agregadas;
- tiempo de ejecución;
- ubicación de predicciones OOF;
- observaciones.

---

# 16. Criterio para aceptar una mejora

Una modificación sólo se considerará una mejora relevante cuando se evalúen conjuntamente:

1. magnitud;
2. variabilidad;
3. estabilidad;
4. generalización;
5. plausibilidad metodológica;
6. ausencia de leakage.

Una diferencia pequeña en una métrica media no será suficiente por sí sola.
