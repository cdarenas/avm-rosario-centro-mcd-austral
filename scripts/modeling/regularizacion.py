#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Regularización y selección de variables (Ridge / Lasso / ElasticNet) sobre S4.
#
# Objetivo: identificar qué atributos APORTAN al modelo y cuáles son redundantes,
# usando regresión penalizada (ISL cap. 6; ESL cap. 3), y contrastar su desempeño
# fuera de muestra contra el OLS del baseline.
#
# Respeta el protocolo experimental:
#   · mismas particiones group-aware (GroupKFold por building_cluster_id) que el baseline;
#   · preprocessing DENTRO del fold (imputación + one-hot + estandarización);
#   · el hiperparámetro de penalización (alpha, l1_ratio) se tunea con CV INTERNA
#     group-aware (nested CV) → sin fuga por selección de modelo (ESL §7.10);
#   · target log1p(precio_usd); métricas retransformadas a USD.
#
# Entrada : data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz
# Salidas : reports/tables/modelado/regularizacion_perf_s4.csv       (performance OOF)
#           reports/tables/modelado/regularizacion_seleccion_s4.csv  (features que sobreviven)
#
# Uso:  python3 scripts/modeling/regularizacion.py
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

ROOT = Path(__file__).resolve().parents[2]
MATRIZ = ROOT / "data" / "processed" / "zonaprop_v2_matriz_modelado_centro.csv.gz"
OUT_PERF = ROOT / "reports" / "tables" / "modelado" / "regularizacion_perf_s4.csv"
OUT_SEL = ROOT / "reports" / "tables" / "modelado" / "regularizacion_seleccion_s4.csv"
N_OUT, N_IN, SEED = 5, 4, 42

S1 = ["eda_superficie_total_m2", "eda_superficie_cubierta_m2", "eda_ambientes", "eda_dormitorios",
      "eda_banos", "eda_cocheras", "eda_toilette", "eda_antiguedad_anos", "eda_antiguedad_estado",
      "eda_disposicion", "eda_orientacion", "eda_tipo_operacion", "eda_expensas",
      "fe_ratio_cubierta_total", "fe_sup_por_ambiente", "fe_banos_por_ambiente",
      "fe_dormitorios_por_ambiente", "fe_tiene_cochera", "fe_expensas_informadas"]
S2 = ["barrio_oficial_geo", "eda_latitud", "eda_longitud"]
S3 = ["fe_dist_centro_km", "fe_dist_rio_km", "fe_dist_espacio_verde_km", "fe_dens_comercios_300m"]
CAT = {"eda_antiguedad_estado", "eda_disposicion", "eda_orientacion", "eda_tipo_operacion", "barrio_oficial_geo"}

# grillas de penalización (sobre matriz estandarizada)
A_L1 = np.logspace(-4, 0, 25)      # Lasso / ElasticNet
A_L2 = np.logspace(-2, 4, 25)      # Ridge
L1R = [0.2, 0.5, 0.8]              # ElasticNet


def preprocesador(cols, feat_cols):
    """Imputa + one-hot (sin escalar acá); el escalado global va después para penalizar de forma justa."""
    cat = [c for c in cols if c in CAT]
    binz = [c for c in cols if c in feat_cols or c in ("fe_tiene_cochera", "fe_expensas_informadas")]
    num = [c for c in cols if c not in cat and c not in binz]
    return ColumnTransformer([
        ("cat", Pipeline([("i", SimpleImputer(strategy="most_frequent")),
                          ("o", OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse_output=False))]), cat),
        ("bin", SimpleImputer(strategy="most_frequent"), binz),
        ("num", SimpleImputer(strategy="median"), num),
    ], remainder="drop")


def pipe(cols, feat_cols, model):
    return Pipeline([("prep", preprocesador(cols, feat_cols)),
                     ("sc", StandardScaler()), ("m", model)])


def tune(cols, feat_cols, base, grid, Xtr, ytr, gtr):
    gs = GridSearchCV(pipe(cols, feat_cols, base), grid, cv=GroupKFold(N_IN),
                      scoring="neg_mean_squared_error", n_jobs=-1)
    gs.fit(Xtr, ytr, groups=gtr)
    return gs.best_estimator_, gs.best_params_


def oof_eval(df, cols, feat_cols, y, groups, base, grid):
    """Nested CV: alpha tuneado en train de cada fold; métricas OOF en USD."""
    gkf = GroupKFold(N_OUT)
    filas, n_nz = [], []
    for tr, te in gkf.split(df, y, groups):
        if grid is None:
            est = pipe(cols, feat_cols, base).fit(df.iloc[tr][cols], y[tr])
        else:
            est, _ = tune(cols, feat_cols, base, grid, df.iloc[tr][cols], y[tr], groups[tr])
        p = est.predict(df.iloc[te][cols])
        ytu, ypu = np.expm1(y[te]), np.expm1(p)
        filas.append(dict(rmse_usd=np.sqrt(mean_squared_error(ytu, ypu)),
                          mae_usd=mean_absolute_error(ytu, ypu),
                          mape=np.mean(np.abs((ytu - ypu) / ytu)) * 100,
                          r2_log=r2_score(y[te], p)))
        coef = getattr(est.named_steps["m"], "coef_", None)
        n_nz.append(int(np.sum(np.abs(coef) > 1e-8)) if coef is not None else np.nan)
    r = pd.DataFrame(filas)
    return dict(RMSE_USD=r.rmse_usd.mean(), RMSE_sd=r.rmse_usd.std(), MAE_USD=r.mae_usd.mean(),
                MAPE=r.mape.mean(), R2_log=r.r2_log.mean(), R2_sd=r.r2_log.std(),
                n_coef_nz=np.nanmean(n_nz))


def nombres(prep):
    return [n.split("__", 1)[-1] for n in prep.get_feature_names_out()]


def main():
    df = pd.read_csv(MATRIZ)
    y = np.log1p(pd.to_numeric(df["eda_precio_usd"], errors="coerce").values)
    groups = df["building_cluster_id"].values
    feat_cols = [c for c in df.columns if c.startswith("feat_")]
    cols = [c for c in S1 + S2 + S3 if c in df.columns] + feat_cols
    print(f"Matriz: {len(df):,} avisos · {df['building_cluster_id'].nunique():,} grupos · "
          f"escenario S4 con {len(cols)} columnas de entrada\n")

    # ── 1. Performance OOF: OLS vs. penalizados ────────────────────────────────
    modelos = {
        "OLS": (LinearRegression(), None),
        "Ridge": (Ridge(), {"m__alpha": A_L2}),
        "Lasso": (Lasso(max_iter=20000, tol=1e-3), {"m__alpha": A_L1}),
        "ElasticNet": (ElasticNet(max_iter=20000, tol=1e-3), {"m__alpha": A_L1, "m__l1_ratio": L1R}),
    }
    perf = {}
    for nombre, (base, grid) in modelos.items():
        perf[nombre] = oof_eval(df, cols, feat_cols, y, groups, base, grid)
        x = perf[nombre]
        print(f"  {nombre:<11} RMSE ${x['RMSE_USD']:,.0f} ±{x['RMSE_sd']:,.0f} | MAE ${x['MAE_USD']:,.0f} | "
              f"MAPE {x['MAPE']:.1f}% | R²(log) {x['R2_log']:.3f} | coef≠0 {x['n_coef_nz']:.0f}")
    pd.DataFrame(perf).T.to_csv(OUT_PERF)

    # ── 2. Selección con Lasso: alpha por CV group-aware sobre todo el dataset ──
    gs = GridSearchCV(pipe(cols, feat_cols, Lasso(max_iter=20000, tol=1e-3)),
                      {"m__alpha": A_L1}, cv=GroupKFold(N_OUT),
                      scoring="neg_mean_squared_error", n_jobs=-1)
    gs.fit(df[cols], y, groups=groups)
    alpha = gs.best_params_["m__alpha"]
    best = gs.best_estimator_
    names = nombres(best.named_steps["prep"])
    coef_full = best.named_steps["m"].coef_
    print(f"\nLasso α* (CV group-aware) = {alpha:.5g} · {int((np.abs(coef_full) > 1e-8).sum())}/{len(names)} coef ≠ 0")

    # ── 3. Estabilidad: frecuencia de selección por fold (α* fijo) ─────────────
    # el one-hot puede diferir por fold (categorías infrecuentes) → se alinea por NOMBRE
    gkf = GroupKFold(N_OUT)
    freq_map = {n: 0 for n in names}
    for tr, _ in gkf.split(df, y, groups):
        est = pipe(cols, feat_cols, Lasso(alpha=alpha, max_iter=20000, tol=1e-3)).fit(df.iloc[tr][cols], y[tr])
        nm = nombres(est.named_steps["prep"])
        for n, c in zip(nm, est.named_steps["m"].coef_):
            if n in freq_map and abs(c) > 1e-8:
                freq_map[n] += 1
    freq = np.array([freq_map[n] for n in names])

    sel = pd.DataFrame({"feature": names, "coef_lasso": coef_full,
                        "abs_coef": np.abs(coef_full), "freq_folds": freq.astype(int),
                        "seleccionada": np.abs(coef_full) > 1e-8}).sort_values(
        ["seleccionada", "abs_coef"], ascending=[False, False])
    OUT_SEL.parent.mkdir(parents=True, exist_ok=True)
    sel.to_csv(OUT_SEL, index=False)
    n_sel = int(sel.seleccionada.sum())
    print(f"\nVariables que SOBREVIVEN al Lasso (α*): {n_sel} · descartadas (coef=0): {len(sel) - n_sel}")
    print(f"Tablas: {OUT_PERF.relative_to(ROOT)} · {OUT_SEL.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
