# Pipeline reproducible — AVM Distrito Centro (Rosario)

Este documento describe la **cadena de procesamiento de datos** de la tesis, de forma que
cualquiera pueda **reproducir los mismos resultados a partir de la versión 1 del dataset**.

## Principios de reproducibilidad

- **Linaje verificable por hash.** Cada dataset `zonaprop_v2_eda_centro_vN.csv.gz` lleva un
  `*.manifest.json` con su **SHA256**, el del **artefacto de entrada**, filas/columnas y las
  decisiones aplicadas. La cadena de hashes permite verificar que cada eslabón proviene exactamente
  del anterior.
- **Bytes determinísticos.** Los `.csv.gz` se escriben con `gzip mtime=0`, de modo que re-ejecutar
  una etapa produce **bytes idénticos** (mismo hash), no solo los mismos datos.
- **Entrada reproducible = v1.** El paso previo (scraping y construcción del *candidato* desde la
  base del scraper) depende de datos crudos que **no se versionan** (tamaño/privacidad), como
  recomienda *cookiecutter-data-science* (raw inmutable). Por eso la reproducción pública arranca en
  **v1**, que sí está en el repositorio.
- **Sin fuga de información.** El preprocesamiento a nivel dataset es determinístico y *row-wise*; la
  imputación, el *encoding* y el escalado se aprenden **por fold** en el modelado (ver
  `reports/preprocesamiento_centro_v6.md`, §"Prevención de fuga de información").

## Orquestador

```bash
pip install -r requirements.txt

python run_pipeline.py --verify        # verifica que cada dataset coincide con su manifiesto (hash)
python run_pipeline.py --list          # muestra el DAG
python run_pipeline.py --run           # re-ejecuta la cola reproducible (v5→v6) + diccionario + notebooks
python run_pipeline.py --run --from v5 # re-ejecuta desde una etapa
```

`--verify` es la comprobación de integridad de todo el linaje. `--run` re-ejecuta automáticamente las
etapas `[auto]`; las etapas `[doc]` (v1→v4) se corren manualmente con los comandos de más abajo,
porque dependen de artefactos de auditoría producidos en fases interactivas.

## DAG del pipeline

| Etapa | Modo | Input → Output | Script / Notebook |
|---|---|---|---|
| **v1** | doc (raíz) | — → `v1.csv.gz` | universo EDA del Distrito Centro |
| **v2_barrios** | doc | `v1` → `v2_barrios` | `scripts/data_quality/enriquecer_barrios_oficiales.py` |
| **v3_auditado** | doc | `v2_barrios` → `v3_auditado` | `scripts/data_quality/construir_dataset_eda_auditado.py` |
| **v4** | doc | `v3_auditado` → `v4` | `scripts/data_quality/construir_dataset_eda_v4.py` |
| **v5** | **auto** | `v4` → `v5` | `scripts/preprocessing/definir_muestra_temporal.py` |
| **v6** | **auto** | `v5` → `v6` | `scripts/preprocessing/preprocesar_dataset.py` |
| diccionario | auto | `v6` → `docs/diccionario_variables.md` | `scripts/data_quality/generar_diccionario_variables.py` |
| EDA (muestra de modelado, 4.765) | auto | `v6` → `reports/eda_final_centro.html` + `reports/figures/eda_final/`, `reports/tables/eda_final/` | `scripts/eda/eda_final_centro_v4.py` · notebook: `notebooks/01_eda/04_eda_final_centro_v4.ipynb` (lee `v5`) |
| Preprocesamiento | auto | `v5` → `v6` + reporte | `notebooks/02_preprocesamiento/01_preprocesamiento_centro_v6.ipynb` |

> **Notebooks y scripts producen lo mismo.** Cada etapa `auto` tiene una versión *script* (para el
> orquestador) y, cuando aplica, una versión *notebook* (narrada, ejecutable y visible en GitHub sin
> descargar nada). Ambas escriben el mismo artefacto con `gzip mtime=0`, así que su hash coincide.

## Comandos por etapa

**Cola automática** (la corre `run_pipeline.py --run`):

```bash
python scripts/preprocessing/definir_muestra_temporal.py     # v4 → v5  (corte temporal ≤ 6 meses)
python scripts/preprocessing/preprocesar_dataset.py          # v5 → v6  (limpieza + nombres)
python scripts/data_quality/generar_diccionario_variables.py # v6 → diccionario
bash   scripts/eda/exportar_reporte_html.sh                  # ejecuta el notebook de EDA y exporta el HTML
jupyter nbconvert --to notebook --execute --inplace \
        notebooks/02_preprocesamiento/01_preprocesamiento_centro_v6.ipynb
```

**Tramo de auditoría** (v1→v4, `[doc]`): son scripts `argparse` con I/O explícito. Los dos primeros
argumentos son siempre *input* y (según el caso) los artefactos auxiliares; el último, *output*.

```bash
# v1 → v2_barrios  (input, polígonos, output, tabla de auditoría)
python scripts/data_quality/enriquecer_barrios_oficiales.py \
    data/processed/zonaprop_v2_eda_centro_v1.csv.gz \
    data/external/barrios_rosario/barrios_oficiales.csv \
    data/processed/zonaprop_v2_eda_centro_v2_barrios.csv.gz \
    reports/tables/auditoria_barrios_centro_v2.csv

# v2_barrios → v3_auditado  (input, decisiones, auditoría, output)
#   decisiones: config/auditoria_p0_decisiones_v1.json ; revisión P1: config/auditoria_p1_sin_cambio_v1.csv
python scripts/data_quality/construir_dataset_eda_auditado.py --help   # ver el orden exacto de argumentos

# v3_auditado → v4  (input, output, exclusiones, flujo)
python scripts/data_quality/construir_dataset_eda_v4.py \
    data/processed/zonaprop_v2_eda_centro_v3_auditado.csv.gz \
    data/processed/zonaprop_v2_eda_centro_v4.csv.gz \
    reports/tables/exclusiones_eda_centro_v4.csv \
    reports/tables/flujo_muestra_eda_centro_v4.csv
```

> Las tablas de auditoría (extremos, triaje P1, republicaciones, clusters de edificio) se generan con
> los scripts `scripts/data_quality/construir_auditoria_*.py`, `clasificar_triaje_p1.py` y
> `auditar_duplicados_republicaciones.py`. El orden y los argumentos exactos de cada uno se consultan
> con `--help`; su salida alimenta la etapa `v3_auditado`.

## Verificación

Tras cualquier re-ejecución:

```bash
python run_pipeline.py --verify
```

debe reportar **OK** para v1…v6 (cada dataset coincide con el hash de su manifiesto). Un `MISMATCH`
indica que la etapa produjo un artefacto distinto al registrado —hay que investigar la causa antes de
seguir—.

## Modelado (ya en el DAG)

- **`baseline`** → `scripts/modeling/baseline_hedonico.py`: OLS hedónico sobre escenarios S1→S4 con
  CV *group-aware*; tabla `reports/tables/modelado/baseline_hedonico_s1_s4.csv` y notebook
  `notebooks/04_modelado/01_baseline_hedonico.ipynb`.
- **`regular`** → `scripts/modeling/regularizacion.py`: Ridge/Lasso/ElasticNet sobre S4 (nested CV para
  el $\lambda$) y selección de variables; tablas `regularizacion_perf_s4.csv` /
  `regularizacion_seleccion_s4.csv` y notebook `notebooks/04_modelado/02_regularizacion.ipynb`.

## Reportes (ya en el DAG)

- **`reportes`** → `scripts/reporting/generar_reportes_html.py`: exporta los notebooks **ejecutados** a
  HTML autocontenido en `reportes_html/` (uno por etapa) y regenera `reportes_html/index.html` como
  portada, para compartir con el director sin necesidad de ejecutar nada. Para sumar un notebook nuevo,
  agregar una entrada a la lista `REPORTES` del script: el HTML y la tarjeta del índice se generan solos.

## Etapas siguientes (a incorporar al DAG)

- **Modelos flexibles**: Random Forest y LightGBM sobre las mismas particiones (comparación pareada
  hedónico vs. ML, RQ1), *spatial lag* por fold y diagnóstico espacial de residuos (Moran's I),
  interpretabilidad con SHAP.
