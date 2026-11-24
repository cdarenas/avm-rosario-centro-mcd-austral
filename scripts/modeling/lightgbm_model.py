#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# LightGBM (gradient boosting) sobre escenarios S1→S4, con CV group-aware ANIDADA.
# Comparable de forma pareada con el hedónico y el Random Forest (mismas
# particiones, mismo target log, mismo preprocesamiento one-hot).
#
# Protocolo:
#   · mismas particiones group-aware (GroupKFold por building_cluster_id);
#   · preprocessing DENTRO del fold (imputación + one-hot);
#   · CV ANIDADA: hiperparámetros por búsqueda aleatoria (RandomizedSearchCV) con
#     CV interna group-aware dentro del train de cada fold externo → test sin fuga;
#   · se reportan métricas de ENTRENAMIENTO y TEST por escenario (sesgo–varianza);
#   · target log1p(precio_usd); métricas retransformadas a USD.
#
# Entrada : data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz
# Salidas : reports/tables/modelado/lightgbm_s1_s4.csv            (train+test por escenario)
#           reports/tables/modelado/lightgbm_importancias_s4.csv (importancias)
#
# Uso:  python3 scripts/modeling/lightgbm_model.py
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import randint, uniform, loguniform
from sklearn.model_selection import GroupKFold, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from lightgbm import LGBMRegressor

ROOT = Path(__file__).resolve().parents[2]
MATRIZ = ROOT / "data" / "processed" / "zonaprop_v2_matriz_modelado_centro.csv.gz"
OUT_PERF = ROOT / "reports" / "tables" / "modelado" / "lightgbm_s1_s4.csv"
OUT_IMP = ROOT / "reports" / "tables" / "modelado" / "lightgbm_importancias_s4.csv"
N_OUT, N_IN, SEED, N_ITER = 5, 3, 42, 60

S1 = ["eda_superficie_total_m2", "eda_superficie_cubierta_m2", "eda_ambientes", "eda_dormitorios",
      "eda_banos", "eda_cocheras", "eda_toilette", "eda_antiguedad_anos", "eda_antiguedad_estado",
      "eda_disposicion", "eda_orientacion", "eda_tipo_operacion", "eda_expensas",
      "fe_ratio_cubierta_total", "fe_sup_por_ambiente", "fe_banos_por_ambiente",
      "fe_dormitorios_por_ambiente", "fe_tiene_cochera", "fe_expensas_informadas"]
S2 = ["barrio_oficial_geo", "eda_latitud", "eda_longitud"]
S3 = ["fe_dist_centro_km", "fe_dist_rio_km", "fe_dist_espacio_verde_km", "fe_dens_comercios_300m"]
CAT = {"eda_antiguedad_estado", "eda_disposicion", "eda_orientacion", "eda_tipo_operacion", "barrio_oficial_geo"}

# distribución de búsqueda (RandomizedSearch) sobre los hiperparámetros clave del boosting
DIST = {
    "m__n_estimators": randint(300, 1400),
    "m__learning_rate": loguniform(0.01, 0.15),
    "m__num_leaves": randint(15, 90),
    "m__max_depth": randint(3, 14),
    "m__min_child_samples": randint(5, 70),
    "m__subsample": uniform(0.6, 0.4),         # 0.6–1.0 (bagging por filas)
    "m__colsample_bytree": uniform(0.6, 0.4),  # 0.6–1.0 (submuestreo de columnas)
    "m__reg_lambda": loguniform(1e-3, 20),
    "m__reg_alpha": loguniform(1e-3, 20),
}


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


def lgbm():
    return LGBMRegressor(random_state=SEED, n_jobs=1, subsample_freq=1, verbose=-1)


def search(cols, feat_cols, X, y, g):
    base = Pipeline([("prep", preprocesador(cols, feat_cols)), ("m", lgbm())])
    rs = RandomizedSearchCV(base, DIST, n_iter=N_ITER, cv=GroupKFold(N_IN),
                            scoring="neg_mean_squared_error", random_state=SEED, n_jobs=-1)
    rs.fit(X, y, groups=g)
    return rs.best_estimator_, rs.best_params_


def _met(yv, pv):
    return r2_score(yv, pv), np.sqrt(mean_squared_error(np.expm1(yv), np.expm1(pv)))


def nested(df, cols, feat_cols, y, groups):
    gkf = GroupKFold(N_OUT)
    tr_r2, te_r2, tr_rm, te_rm, te_mae, te_mape = [], [], [], [], [], []
    oof = np.full(len(y), np.nan)
    for tr, te in gkf.split(df, y, groups):
        est, _ = search(cols, feat_cols, df.iloc[tr][cols], y[tr], groups[tr])
        ptr, pte = est.predict(df.iloc[tr][cols]), est.predict(df.iloc[te][cols]); oof[te] = pte
        a, b = _met(y[tr], ptr); c, d = _met(y[te], pte)
        tr_r2.append(a); tr_rm.append(b); te_r2.append(c); te_rm.append(d)
        ytu, ypu = np.expm1(y[te]), np.expm1(pte)
        te_mae.append(mean_absolute_error(ytu, ypu)); te_mape.append(np.mean(np.abs((ytu - ypu) / ytu)) * 100)
    return dict(R2_train=np.mean(tr_r2), R2_test=np.mean(te_r2), R2_test_sd=np.std(te_r2),
                RMSE_train=np.mean(tr_rm), RMSE_test=np.mean(te_rm),
                MAE_test=np.mean(te_mae), MAPE_test=np.mean(te_mape), brecha_R2=np.mean(tr_r2) - np.mean(te_r2)), oof


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
          f"LightGBM · CV ANIDADA {N_OUT}×{N_IN} · RandomizedSearch n_iter={N_ITER}\n")

    filas = []
    for nombre, cols in escen.items():
        res, _ = nested(df, cols, feat_cols, y, groups)
        filas.append({"escenario": nombre, "n_features": len(cols), **res})
        print(f"  {nombre} ({len(cols):>2} feats): R²  train {res['R2_train']:.3f} / test {res['R2_test']:.3f} "
              f"(brecha {res['brecha_R2']:+.3f}) | RMSE train ${res['RMSE_train']:,.0f} / test ${res['RMSE_test']:,.0f} "
              f"| MAPE test {res['MAPE_test']:.1f}%")
    OUT_PERF.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(filas).round(4).to_csv(OUT_PERF, index=False)

    # ── Modelo final S4: búsqueda sobre todo el dataset → importancias ─────────
    cols = escen["S4"]
    est, best = search(cols, feat_cols, df[cols], y, groups)
    print(f"\nMejores hiperparámetros (S4): {best}")
    names = [n.split('__', 1)[-1] for n in est.named_steps["prep"].get_feature_names_out()]
    gain = est.named_steps["m"].booster_.feature_importance(importance_type="gain")
    Xt = est.named_steps["prep"].transform(df[cols])
    perm = permutation_importance(est.named_steps["m"], Xt, y, n_repeats=5, random_state=SEED, n_jobs=-1)
    imp = pd.DataFrame({"feature": names, "importancia_gain": gain / gain.sum(),
                        "importancia_perm": perm.importances_mean}).sort_values("importancia_perm", ascending=False)
    imp.round(5).to_csv(OUT_IMP, index=False)
    print("\nTop-8 por importancia de permutación:")
    for _, r in imp.head(8).iterrows():
        print(f"  {r.feature:<32} perm={r.importancia_perm:.4f}")
    print(f"\nTablas: {OUT_PERF.relative_to(ROOT)} · {OUT_IMP.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
