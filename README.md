# AVM Rosario — Distrito Centro

Modelo de valuación automática (**AVM**) interpretable para el **precio de publicación de departamentos** del Distrito Centro de Rosario, basado en *gradient boosting* (LightGBM) y explicabilidad (SHAP).

Este repositorio contiene el código, los datos y los notebooks necesarios para **reproducir los resultados** de la tesis de maestría:

> *Predicción interpretable del precio de publicación de departamentos: un modelo de valuación automática (AVM) basado en gradient boosting y explicabilidad para el Distrito Centro de Rosario.*
> Autor: Cristian Daniel Arenas · Director: Enrique Gabriel Baquela
> Maestría en Explotación de Datos y Gestión del Conocimiento — Universidad Austral.

## Requisitos

Python 3.10 o superior. Instalación de dependencias:

```bash
pip install -r requirements.txt
```

## Reproducción

```bash
python run_pipeline.py --list      # muestra el DAG de etapas
python run_pipeline.py --verify    # verifica los hashes de contenido de los datasets
python run_pipeline.py --run       # re-ejecuta el pipeline (datos -> matriz -> modelos -> notebooks)
```

## Estructura

```text
.
├── run_pipeline.py        # orquestador reproducible del pipeline (DAG con hashes)
├── requirements.txt
├── config/                # configuración del proyecto
├── scripts/
│   ├── scraping/          # scraper de avisos + geocodificación
│   ├── preprocessing/     # limpieza y preprocesamiento (v4 -> v6)
│   ├── feature_engineering/ # construcción de la matriz de modelado
│   ├── data_quality/      # auditorías y enriquecimiento (barrios oficiales)
│   ├── modeling/          # hedónico, regularización, Random Forest, LightGBM, SHAP
│   ├── eda/               # análisis exploratorio
│   └── reporting/         # generación de tablas y figuras de resultados
├── notebooks/             # pipeline paso a paso (EDA, preproc, FE, modelado, espacial, SHAP, errores, conformal)
├── data/
│   ├── external/          # fuentes de terceros (barrios oficiales, POI de OSM)
│   ├── interim/           # salidas intermedias del scraper
│   └── processed/         # cadena de datasets v0->v6 + matriz de modelado (con manifiestos de hash)
├── reports/
│   ├── tables/            # tablas de resultados (coinciden con las de la tesis)
│   └── figures/           # figuras de resultados
└── docs/                  # documentación técnica (PIPELINE, diccionario de variables, protocolo)
```

## Datos

`data/processed/` incluye la cadena completa de datasets (`v0` → `v6`) y la **matriz de modelado final** (`zonaprop_v2_matriz_modelado_centro.csv.gz`), cada uno acompañado de un manifiesto con el hash de su contenido. Las **fotografías** de los avisos no se incluyen (no son necesarias para reproducir los resultados del documento).

## Reproducibilidad

Cada artefacto de datos conserva un manifiesto con el hash de contenido de su entrada y su salida; `python run_pipeline.py --verify` valida el linaje de extremo a extremo.
