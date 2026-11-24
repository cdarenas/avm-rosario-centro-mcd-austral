#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Random Forest sobre escenarios S1→S4, con CV group-aware ANIDADA (nested CV).
# Comparable de forma pareada con el baseline hedónico (mismas particiones, target log).
#
# Respeta el protocolo experimental:
#   · mismas particiones group-aware (GroupKFold por building_cluster_id);
#   · preprocessing DENTRO del fold (imputación + one-hot; los árboles NO
#     requieren estandarización);
#   · CV ANIDADA: los hiperparámetros se eligen por CV interna group-aware DENTRO
#     del train de cada fold externo → estimación de test sin sesgo optimista por
#     selección de modelo (ESL §7.10.2);
#   · se reportan métricas de ENTRENAMIENTO y de TEST por escenario (diagnóstico
#     de sesgo–varianza / sobreajuste);
#   · target log1p(precio_usd); métricas retransformadas a USD.
#
# Entrada : data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz
# Salidas : reports/tables/modelado/random_forest_s1_s4.csv           (train+test por escenario)
#           reports/tables/modelado/random_forest_importancias_s4.csv (importancias)
#
# Uso:  python3 scripts/modeling/random_forest.py
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

ROOT = Path(__file__).resolve().parents[2]
MATRIZ = ROOT / "data" / "processed" / "zonaprop_v2_matriz_modelado_centro.csv.gz"
OUT_PERF = ROOT / "reports" / "tables" / "modelado" / "random_forest_s1_s4.csv"
OUT_IMP = ROOT / "reports" / "tables" / "modelado" / "random_forest_importancias_s4.csv"
N_OUT, N_IN, SEED = 5, 3, 42
N_TREES = 600

S1 = ["eda_superficie_total_m2", "eda_superficie_cubierta_m2", "eda_ambientes", "eda_dormitorios",
      "eda_banos", "eda_cocheras", "eda_toilette", "eda_antiguedad_anos", "eda_antiguedad_estado",
      "eda_disposicion", "eda_orientacion", "eda_tipo_operacion", "eda_expensas",
      "fe_ratio_cubierta_total", "fe_sup_por_ambiente", "fe_banos_por_ambiente",
      "fe_dormitorios_por_ambiente", "fe_tiene_cochera", "fe_expensas_informadas"]
S2 = ["barrio_oficial_geo", "eda_latitud", "eda_longitud"]
S3 = ["fe_dist_centro_km", "fe_dist_rio_km", "fe_dist_espacio_verde_km", "fe_dens_comercios_300m"]
CAT = {"eda_antiguedad_estado", "eda_disposicion", "eda_orientacion", "eda_tipo_operacion", "barrio_oficial_geo"}

# búsqueda exhaustiva sobre los hiperparámetros de mayor impacto (n_estimators fijo alto)
GRID = {"m__max_features": ["sqrt", 0.33, 0.5, 0.7],
        "m__max_depth": [None, 16, 24],
        "m__min_samples_leaf": [1, 2, 5]}


def preprocesador(cols, feat_cols):
    cat = [c for c in cols if c in CAT]
    binz = [c for c in cols if c in feat_cols or c in ("fe_tiene_cochera", "fe_expensas_informadas")]
    num = [c for c in cols if c not in cat and c not in binz]
    return ColumnTransformer([
        ("cat", Pipeline([("i", SimpleImputer(strategy="most_frequent")),
                          ("o", OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse_output=False))]), cat),
        ("bin", SimpleImputer(strategy="most_frequent"), binz),
        ("num", SimpleImputer(strategy="median"), num),
    ], remainder="drop")


def pipe_search(cols, feat_cols):
    """RF con n_jobs=1 para que la paralelización la maneje GridSearchCV."""
    return Pipeline([("prep", preprocesador(cols, feat_cols)),
                     ("m", RandomForestRegressor(n_estimators=N_TREES, random_state=SEED, n_jobs=1))])


def _met(yv, pv):
    return r2_score(yv, pv), np.sqrt(mean_squared_error(np.expm1(yv), np.expm1(pv)))


def nested(df, cols, feat_cols, y, groups):
    """CV anidada: tuneo dentro del train de cada fold externo; devuelve train y test."""
    gkf = GroupKFold(N_OUT)
    tr_r2, te_r2, tr_rmse, te_rmse, te_mae, te_mape, params = [], [], [], [], [], [], []
    oof = np.full(len(y), np.nan)
    for tr, te in gkf.split(df, y, groups):
        gs = GridSearchCV(pipe_search(cols, feat_cols), GRID, cv=GroupKFold(N_IN),
                          scoring="neg_mean_squared_error", n_jobs=-1)
        gs.fit(df.iloc[tr][cols], y[tr], groups=groups[tr])
        est = gs.best_estimator_; params.append(gs.best_params_)
        ptr, pte = est.predict(df.iloc[tr][cols]), est.predict(df.iloc[te][cols]); oof[te] = pte
        r2tr, rmtr = _met(y[tr], ptr); r2te, rmte = _met(y[te], pte)
        tr_r2.append(r2tr); te_r2.append(r2te); tr_rmse.append(rmtr); te_rmse.append(rmte)
        ytu, ypu = np.expm1(y[te]), np.expm1(pte)
        te_mae.append(mean_absolute_error(ytu, ypu)); te_mape.append(np.mean(np.abs((ytu - ypu) / ytu)) * 100)
    res = dict(R2_train=np.mean(tr_r2), R2_test=np.mean(te_r2), R2_test_sd=np.std(te_r2),
               RMSE_train=np.mean(tr_rmse), RMSE_test=np.mean(te_rmse),
               MAE_test=np.mean(te_mae), MAPE_test=np.mean(te_mape), brecha_R2=np.mean(tr_r2) - np.mean(te_r2))
    return res, oof, params


def main():
    df = pd.read_csv(MATRIZ)
    y = np.log1p(pd.to_numeric(df["eda_precio_usd"], errors="coerce").values)
    groups = df["building_cluster_id"].values
    feat_cols = [c for c in df.columns if c.startswith("feat_")]
    escen = {
        "S1": [c for c in S1 if c in df.columns],
        "S2": [c for c in S1 + S2 if c in df.columns],
        "S3": [c for c in S1 + S2 + S3 if c in df.columns],
        "S4": [c for c in S1 + S2 + S3 if c in df.columns] + feat_cols,
    }
    print(f"Matriz: {len(df):,} avisos · {df['building_cluster_id'].nunique():,} grupos · "
          f"RF({N_TREES}) · CV ANIDADA {N_OUT}×{N_IN} group-aware\n")

    filas = []
    for nombre, cols in escen.items():
        res, _, params = nested(df, cols, feat_cols, y, groups)
        filas.append({"escenario": nombre, "n_features": len(cols), **res})
        print(f"  {nombre} ({len(cols):>2} feats): R²  train {res['R2_train']:.3f} / test {res['R2_test']:.3f} "
              f"(brecha {res['brecha_R2']:+.3f}) | RMSE train ${res['RMSE_train']:,.0f} / test ${res['RMSE_test']:,.0f} "
              f"| MAPE test {res['MAPE_test']:.1f}%")
    OUT_PERF.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(filas).round(4).to_csv(OUT_PERF, index=False)

    # ── Modelo final S4: tuneo sobre todo el dataset → importancias ────────────
    cols = escen["S4"]
    gs = GridSearchCV(pipe_search(cols, feat_cols), GRID, cv=GroupKFold(N_OUT),
                      scoring="neg_mean_squared_error", n_jobs=-1).fit(df[cols], y, groups=groups)
    est = gs.best_estimator_
    print(f"\nHiperparámetros del modelo final (S4): {gs.best_params_}")
    names = [n.split('__', 1)[-1] for n in est.named_steps["prep"].get_feature_names_out()]
    Xt = est.named_steps["prep"].transform(df[cols])
    perm = permutation_importance(est.named_steps["m"], Xt, y, n_repeats=5, random_state=SEED, n_jobs=-1)
    imp = pd.DataFrame({"feature": names, "importancia_mdi": est.named_steps["m"].feature_importances_,
                        "importancia_perm": perm.importances_mean}).sort_values("importancia_perm", ascending=False)
    imp.round(5).to_csv(OUT_IMP, index=False)
    print(f"\nTop-8 por importancia de permutación:")
    for _, r in imp.head(8).iterrows():
        print(f"  {r.feature:<32} perm={r.importancia_perm:.4f}")
    print(f"\nTablas: {OUT_PERF.relative_to(ROOT)} · {OUT_IMP.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
