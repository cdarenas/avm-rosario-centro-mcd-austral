#!/usr/bin/env python3
"""Especificación ÚNICA del modelo final de PI1 (notebook 04_lightgbm.ipynb):
LightGBM con codificación one-hot y la configuración hallada por búsqueda aleatoria
(RandomizedSearchCV). Todo análisis dependiente del modelo final —SHAP, conformal,
errores por segmento, función de estimación y el artefacto de producción— importa
esta especificación para garantizar consistencia (mismos hiperparámetros, mismo S4,
mismo preprocesamiento).
"""
import numpy as np, pandas as pd
from pathlib import Path
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from lightgbm import LGBMRegressor

SEED = 42
# Hiperparámetros del modelo final (RandomizedSearchCV, notebook 04) — R2(test)=0,902
BEST_PARAMS = dict(colsample_bytree=0.8604, learning_rate=0.0117, max_depth=10,
                   min_child_samples=34, n_estimators=1105, num_leaves=16,
                   reg_alpha=0.0061, reg_lambda=0.0061, subsample=0.7217)
CAT = {"eda_antiguedad_estado", "eda_disposicion", "eda_orientacion", "eda_tipo_operacion", "barrio_oficial_geo"}

def cargar_matriz(root):
    return pd.read_csv(Path(root) / "data" / "processed" / "zonaprop_v2_matriz_modelado_centro.csv.gz")

def columnas_S4(df):
    feat = [c for c in df.columns if c.startswith("feat_")]
    S1 = ["eda_superficie_total_m2","eda_superficie_cubierta_m2","eda_ambientes","eda_dormitorios","eda_banos",
          "eda_cocheras","eda_toilette","eda_antiguedad_anos","eda_antiguedad_estado","eda_disposicion",
          "eda_orientacion","eda_tipo_operacion","eda_expensas","fe_ratio_cubierta_total","fe_sup_por_ambiente",
          "fe_banos_por_ambiente","fe_dormitorios_por_ambiente","fe_tiene_cochera","fe_expensas_informadas"]
    S2 = ["barrio_oficial_geo","eda_latitud","eda_longitud"]
    S3 = [c for c in ["fe_dist_centro_km","fe_dist_rio_km","fe_dist_espacio_verde_km","fe_dens_comercios_300m"] if c in df.columns]
    return [c for c in S1 + S2 + S3 if c in df.columns] + feat

def _binarias(df):
    feat = [c for c in df.columns if c.startswith("feat_")]
    return set(feat) | {"fe_tiene_cochera", "fe_expensas_informadas"}

def preprocesador(cols, df):
    binc = _binarias(df)
    cat = [c for c in cols if c in CAT]; binz = [c for c in cols if c in binc]
    num = [c for c in cols if c not in cat and c not in binz]
    return ColumnTransformer([
        ("cat", Pipeline([("i", SimpleImputer(strategy="most_frequent")),
                          ("o", OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse_output=False))]), cat),
        ("bin", SimpleImputer(strategy="most_frequent"), binz),
        ("num", SimpleImputer(strategy="median"), num)], remainder="drop")

def construir_modelo_final(cols, df):
    """Pipeline completo (preprocesamiento one-hot + LightGBM final)."""
    return Pipeline([("prep", preprocesador(cols, df)),
                     ("m", LGBMRegressor(random_state=SEED, n_jobs=-1, subsample_freq=1, verbose=-1, **BEST_PARAMS))])

def target_log(df):
    return np.log1p(pd.to_numeric(df["eda_precio_usd"], errors="coerce").values)
