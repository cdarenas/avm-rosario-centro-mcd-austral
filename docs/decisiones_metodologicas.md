# Decisiones metodológicas

## Propósito

Registrar de forma trazable las decisiones metodológicas de la tesis, distinguiendo entre:

- decisiones adoptadas;
- hipótesis de investigación;
- decisiones pendientes de validación empírica;
- riesgos metodológicos identificados.

Toda modificación relevante deberá quedar documentada junto con su justificación bibliográfica y, cuando corresponda, con la evidencia experimental que la sustenta.

---

# 1. Decisiones adoptadas

## 1.1 Problema de investigación

Se desarrollará y evaluará un modelo automatizado de valuación inmobiliaria (AVM) para estimar el precio publicado de departamentos en venta del Distrito Centro de Rosario.

El objetivo es combinar capacidad predictiva, reproducibilidad e interpretabilidad.

Referencia principal:
- Plan de Trabajo Final de la tesis.

## 1.2 Variable objetivo

La variable objetivo será inicialmente el precio publicado de venta expresado en USD.

Debe mantenerse explícita la distinción entre:
- precio publicado;
- precio de cierre de una operación.

Los datos disponibles provienen de avisos inmobiliarios y, por lo tanto, no permiten interpretar directamente las predicciones como precios efectivos de transacción.

## 1.3 Modelos principales

Se compararán como mínimo:

1. modelo hedónico / regresión lineal como baseline interpretable;
2. Random Forest;
3. LightGBM como modelo predictivo central.

La comparación deberá realizarse bajo un protocolo experimental común.

## 1.4 Preprocessing

Se distinguirán dos conceptos:

- **pipeline científico de la tesis**: secuencia completa que conecta pregunta de
  investigación, datos, particionado, preprocessing, feature engineering,
  entrenamiento, evaluación e interpretación;
- **`sklearn.Pipeline`**: herramienta de implementación que permite encapsular y
  ejecutar de forma reproducible una parte del pipeline científico.

El pipeline científico no se reduce a una clase de software. A su vez, el uso de
`sklearn.Pipeline` no garantiza por sí solo la validez del diseño experimental.

Todo preprocessing cuyos parámetros se aprendan de los datos deberá ajustarse exclusivamente con las observaciones de entrenamiento correspondientes.

Esto incluye, entre otros:

- imputación;
- escalado;
- encoding supervisado;
- selección de variables;
- transformaciones guiadas por datos;
- generación de features dependientes del target;
- estadísticas espaciales basadas en precios.

Siempre que sea técnicamente razonable, el preprocessing, el feature engineering
aprendido y el modelo se evaluarán como un pipeline completo dentro de cada fold.
Una transformación que aprende parámetros a partir del dataset forma parte del
entrenamiento, aunque no utilice directamente el target, y deberá respetar los
límites del fold.

El preprocessing podrá ser diferente según el paradigma del modelo.

Se contemplan pipelines específicos por modelo:

- `HedonicPipeline`;
- `RandomForestPipeline`;
- `LightGBMPipeline`.

Comparabilidad entre modelos no implica preprocessing idéntico. Exige mantener,
en la medida de lo posible, las mismas observaciones, folds, variable objetivo y
métricas.

Como propuesta de implementación, las operaciones aprendidas se construirán con
transformadores compatibles con `fit`/`transform`; se utilizarán
`ColumnTransformer` y `Pipeline` cuando corresponda, y se encapsularán en
transformadores propios aquellas operaciones de feature engineering que aprendan
parámetros. La arquitectura concreta deberá adecuarse a cada modelo y al dataset.

## 1.5 Evaluación

La evaluación deberá realizarse fuera de muestra.

Los modelos comparados utilizarán, en la medida de lo posible:

- las mismas observaciones;
- las mismas particiones;
- los mismos folds;
- la misma variable objetivo;
- las mismas métricas.

Se conservarán predicciones out-of-fold (OOF) cuando sean necesarias para comparaciones y análisis posteriores.

## 1.6 Data leakage

La prevención de data leakage es un requisito transversal del pipeline.

Especial atención deberá prestarse a:

- imputación;
- target encoding;
- selección de features;
- generación de variables espaciales;
- cálculo de comparables;
- duplicados o republicaciones de una misma propiedad.

El feature engineering aprendido a partir de los datos también forma parte del
entrenamiento. Sus parámetros, estadísticas o reglas no podrán estimarse usando
observaciones de validación o test.

## 1.7 Unidad de independencia

El `listing_id` no se asumirá automáticamente como unidad estadísticamente independiente.

Se investigará la existencia de republicaciones de una misma propiedad y, si es necesario, se construirá un identificador de propiedad física o grupo equivalente para evitar contaminación entre train y validation/test.

## 1.8 Interpretabilidad

Se utilizará SHAP como herramienta central para explicar las predicciones del modelo LightGBM.

La interpretación deberá distinguir entre:

- asociación económica;
- contribución predictiva;
- importancia de una variable;
- causalidad.

No se interpretarán valores SHAP como efectos causales.

## 1.9 Normas APA

La redacción de la tesis deberá ajustarse a las Normas APA 7 durante todo el
proceso de escritura, sin excepciones. Esta exigencia alcanza, como mínimo, al
marco teórico, estado del arte, metodología, resultados, discusión, conclusiones,
tablas, figuras, citas y lista de referencias.

La conformidad con APA no se dejará para la corrección final. Cada sección deberá
verificarse al ser redactada y volver a controlarse antes de integrarse en una
versión entregable. La fuente normativa local se conserva en
`references/normas/Normas  APA 2020, 7 ed.pdf`.

Ningún capítulo se considerará listo para revisión o entrega si contiene citas
sin referencia, referencias no citadas, datos bibliográficos sin verificar o
elementos formales que no hayan sido contrastados con la norma.

## 1.10 Notación matemática en la escritura

El marco teórico y la metodología incorporarán notación matemática cuando resulte
necesaria para expresar con precisión definiciones, relaciones, supuestos,
funciones objetivo, modelos, métricas o procedimientos.

La notación matemática complementará la explicación conceptual y no la
reemplazará. Cada ecuación relevante deberá:

- estar introducida y explicada en el texto;
- definir sus símbolos, índices, parámetros y unidades;
- mantener una notación consistente entre capítulos;
- aclarar los supuestos bajo los cuales se utiliza;
- vincularse con la fuente bibliográfica correspondiente cuando provenga de la
  literatura;
- relacionarse explícitamente con su aplicación en la tesis.

No se agregarán fórmulas de manera ornamental ni se forzará su uso en apartados
donde una explicación conceptual sea suficiente. La decisión de formalizar un
concepto dependerá de si la notación mejora su precisión, verificabilidad o
reproducibilidad.

## 1.11 Cohesión y conectores lógicos

La redacción deberá hacer explícitas las relaciones de causa, consecuencia,
contraste, concesión, condición, comparación, ejemplificación y síntesis cuando
sean necesarias para seguir el argumento.

Los conectores se elegirán por su función lógica y no como recursos ornamentales.
Su uso no deberá exagerar la fuerza de la evidencia: una asociación no se
presentará como causalidad ni una diferencia descriptiva como conclusión
demostrada. Durante la revisión se consultará la guía disponible en
`references/escritura_academica/guia_conectores_logicos.md` y, ante dudas, las
fuentes externas allí registradas.

---

# 2. Hipótesis de investigación

## H1 — Machine learning vs. baseline hedónico

Los modelos basados en árboles, particularmente LightGBM, podrían mejorar la capacidad predictiva respecto del modelo hedónico debido a su capacidad para representar relaciones no lineales e interacciones.

La magnitud y estabilidad de esa mejora deberán demostrarse empíricamente.

## H2 — Valor incremental de la información territorial

La incorporación de variables de localización y microlocalización podría mejorar la capacidad predictiva respecto de un modelo basado únicamente en características estructurales del inmueble.

## H3 — Información espacial

Los precios inmobiliarios del área de estudio podrían presentar dependencia espacial.

La incorporación de información espacial explícita podría aportar capacidad predictiva adicional.

## H4 — Dependencia espacial residual

Incluso después de incorporar variables observadas de localización, podría persistir autocorrelación espacial en los residuos.

Gyger et al. (2026) muestran que las covariables espaciales observadas pueden
capturar una parte sustancial de la variación territorial y, al mismo tiempo, que
un componente espacial explícito puede aprovechar dependencia residual no
utilizada por modelos independientes. En consecuencia, la necesidad de modelar
espacialidad explícita se evaluará después de incorporar las covariables
territoriales disponibles, no antes.

## H5 — Texto de los avisos

Las variables derivadas del texto de las publicaciones podrían aportar información incremental no contenida completamente en los campos estructurados.

---

# 3. Decisiones pendientes de validación empírica

No se consideran adoptadas hasta obtener evidencia.

## Variable objetivo

- precio USD vs. log(precio USD);
- procedimiento de retransformation si se modela log-precio.

Si se utiliza `log(price)`, deberán tratarse explícitamente la interpretación del
modelo, el cálculo de métricas en la escala original y el posible sesgo de
retransformación al volver a expresar las predicciones como precios.

## Outliers

- reglas de detección;
- tratamiento;
- winsorización;
- exclusión;
- análisis de sensibilidad.

## Missing values

- estrategia final por tipo de variable;
- uso de categorías explícitas;
- imputación;
- indicadores de missingness.

## Preprocessing específico por modelo

- necesidad y método de scaling para cada modelo;
- representación de variables categóricas para cada modelo;
- configuración exacta de los transformadores y pipelines.

## Features espaciales

Pendiente decidir:

- KNN de precios como candidato experimental, no como componente garantizado;
- promedio o mediana de vecinos;
- distancia máxima;
- número K;
- weighting por distancia;
- microzonas;
- spatial lag;
- variables de proximidad;
- calidad de geolocalización.

Toda feature supervisada espacial deberá construirse sin utilizar el target de la observación evaluada.

El aporte de una feature de precio de vecinos deberá demostrarse mediante una
comparación fuera de muestra y sin leakage. Gyger et al. (2026) no evalúan esta
feature en particular: su evidencia respalda la relevancia potencial de modelar
dependencia espacial residual, mientras que la elección de KNN, Gaussian
Processes u otra estrategia permanece abierta.

## Modelo espacial hedónico

No se adopta de antemano SAR.

Se evaluará primero:

1. modelo hedónico;
2. estructura espacial de precios;
3. autocorrelación espacial residual;
4. necesidad de una extensión espacial.

SAR, SEM u otras especificaciones serán candidatas únicamente si la evidencia las justifica.

La misma regla se aplicará a Gaussian Processes, GPBoost y otras extensiones
espaciales explícitas. Su incorporación estará condicionada a evidencia de
dependencia espacial residual y a una mejora fuera de muestra estable luego de
considerar covariables territoriales observadas.

## Estrategia de validación

Pendiente definir con el dataset:

- tamaño del test final;
- repeated CV;
- group-aware CV;
- spatial CV;
- holdout temporal;
- combinación de estas estrategias.

Tampoco se fijan todavía el número de folds ni la estrategia final de
holdout/resampling.

## Hiperparámetros

No se fijarán hiperparámetros definitivos antes de los experimentos.

## Decisiones no transferidas automáticamente de California Housing

La lectura del ejemplo de California Housing de Géron aporta patrones de diseño,
no valores o técnicas que deban adoptarse sin validación. Por lo tanto, no se
adoptan automáticamente:

- imputación por mediana;
- `StandardScaler`;
- `MinMaxScaler`;
- one-hot encoding para todos los modelos;
- cross-validation de 10 folds;
- partición de test del 20 %;
- estrategia de estratificación utilizada en ese ejemplo;
- KNN espacial;
- clustering espacial;
- ratios específicos del dataset de California.

Cada alternativa deberá justificarse según el problema, los datos y el protocolo
experimental de esta tesis.

---

# 4. Riesgos metodológicos

## Leakage espacial

El uso de precios de propiedades vecinas puede generar leakage si una observación participa directa o indirectamente en la construcción de su propio predictor.

## Duplicados y republicaciones

Una misma propiedad publicada varias veces puede aparecer en distintos folds y producir estimaciones optimistas.

## Sesgo de selección

Los avisos disponibles representan la oferta publicada en portales y no necesariamente todo el mercado inmobiliario.

## Precio publicado vs. precio de transacción

El target corresponde a precio de oferta.

Las conclusiones deberán limitarse a ese universo.

## Dependencia temporal

Los precios pueden cambiar durante el período de recolección.

Será necesario evaluar si la dimensión temporal afecta la comparabilidad de observaciones.

## Calidad de geocodificación

La precisión de latitud/longitud puede variar entre publicaciones y afectar features de distancia y dependencia espacial.

Antes de utilizar features espaciales se auditarán la disponibilidad, precisión y
procedencia de las coordenadas. Cuando existan ubicaciones exactas, aproximadas o
imputadas, se registrará esa calidad y se realizarán análisis de sensibilidad. La
evidencia de Gyger et al. (2026) muestra que la información espacial imputada
puede aportar poco valor o introducir ruido, y que restringir el análisis a
ubicaciones exactas también puede modificar la cobertura espacial de la muestra.

---

# 5. Regla de actualización

Una decisión pasará de "pendiente" a "adoptada" únicamente cuando:

1. exista una justificación metodológica;
2. se haya implementado sin leakage;
3. haya sido evaluada bajo el protocolo experimental;
4. exista evidencia suficiente sobre magnitud y estabilidad del efecto.
