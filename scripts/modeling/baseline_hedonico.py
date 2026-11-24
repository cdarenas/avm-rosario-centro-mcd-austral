#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Baseline hedónico (OLS) sobre escenarios S1→S4, con CV group-aware.
#
# Respeta el protocolo experimental:
#   · mismas particiones para todos los escenarios (comparación pareada);
#   · agrupamiento: todas las publicaciones de una misma propiedad/edificio en el
#     mismo grupo (group = building_cluster_id) → sin fuga por republicaciones;
#   · preprocessing DENTRO del fold (ColumnTransformer: imputación + one-hot + escala),
#     ajustado solo con el train de cada fold;
#   · target log1p(precio_usd); métricas RMSE/MAE/R² por fold (media ± desvío), en USD.
#
# Entrada : data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz
# Salida  : reports/tables/modelado/baseline_hedonico_s1_s4.csv
#
# Uso:  python3 scripts/modeling/baseline_hedonico.py
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

ROOT = Path(__file__).resolve().parents[2]
MATRIZ = ROOT / "data" / "processed" / "zonaprop_v2_matriz_modelado_centro.csv.gz"
OUT = ROOT / "reports" / "tables" / "modelado" / "baseline_hedonico_s1_s4.csv"
N_FOLDS = 5
SEED = 42

# ── Definición de escenarios (incrementales), según docs/matriz_modelado.md ──
S1 = ["eda_superficie_total_m2", "eda_superficie_cubierta_m2", "eda_ambientes", "eda_dormitorios",
      "eda_banos", "eda_cocheras", "eda_toilette", "eda_antiguedad_anos", "eda_antiguedad_estado",
      "eda_disposicion", "eda_orientacion", "eda_tipo_operacion", "eda_expensas",
      "fe_ratio_cubierta_total", "fe_sup_por_ambiente", "fe_banos_por_ambiente",
      "fe_dormitorios_por_ambiente", "fe_tiene_cochera", "fe_expensas_informadas"]
S2 = ["barrio_oficial_geo", "eda_latitud", "eda_longitud"]
S3 = ["fe_dist_centro_km", "fe_dist_rio_km", "fe_dist_espacio_verde_km", "fe_dens_comercios_300m"]
S4_PREFIX = "feat_"

CATEGORICAS = {"eda_antiguedad_estado", "eda_disposicion", "eda_orientacion",
               "eda_tipo_operacion", "barrio_oficial_geo"}

def preprocesador(cols, feat_cols):
    """ColumnTransformer: categóricas→impute+onehot, binarias→passthrough, numéricas→impute+escala."""
    cat = [c for c in cols if c in CATEGORICAS]
    binz = [c for c in cols if c in feat_cols or c in ("fe_tiene_cochera", "fe_expensas_informadas")]
    num = [c for c in cols if c not in cat and c not in binz]
    return ColumnTransformer([
        ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                          ("oh", OneHotEncoder(handle_unknown="ignore", min_frequency=10))]), cat),
        ("bin", "passthrough", binz),
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                          ("sc", StandardScaler())]), num),
    ], remainder="drop")

def evaluar(df, cols, feat_cols, y, groups):
    gkf = GroupKFold(n_splits=N_FOLDS)
    filas = []
    for tr, te in gkf.split(df, y, groups):
        pipe = Pipeline([("prep", preprocesador(cols, feat_cols)), ("ols", LinearRegression())])
        pipe.fit(df.iloc[tr][cols], y[tr])
        pred_log = pipe.predict(df.iloc[te][cols])
        yt_log, yt_usd = y[te], np.expm1(y[te])
        yp_usd = np.expm1(pred_log)
        filas.append({
            "rmse_log": np.sqrt(mean_squared_error(yt_log, pred_log)),
            "r2_log": r2_score(yt_log, pred_log),
            "rmse_usd": np.sqrt(mean_squared_error(yt_usd, yp_usd)),
            "mae_usd": mean_absolute_error(yt_usd, yp_usd),
            "mape": np.mean(np.abs((yt_usd - yp_usd) / yt_usd)) * 100,
        })
    return pd.DataFrame(filas)

def main():
    df = pd.read_csv(MATRIZ)
    y = np.log1p(pd.to_numeric(df["eda_precio_usd"], errors="coerce").values)
    groups = df["building_cluster_id"].values
    feat_cols = [c for c in df.columns if c.startswith(S4_PREFIX)]

    escenarios = {
        "S1": [c for c in S1 if c in df.columns],
        "S2": [c for c in S1 + S2 if c in df.columns],
        "S3": [c for c in S1 + S2 + S3 if c in df.columns],
        "S4": [c for c in S1 + S2 + S3 if c in df.columns] + feat_cols,
    }
    print(f"Matriz: {len(df):,} avisos · {df['building_cluster_id'].nunique():,} grupos (edificio/cuadra) · "
          f"CV group-aware {N_FOLDS}-fold\n")

    resumen = []
    for nombre, cols in escenarios.items():
        r = evaluar(df, cols, feat_cols, y, groups)
        resumen.append({
            "escenario": nombre, "n_features": len(cols),
            "RMSE_USD_media": r["rmse_usd"].mean(), "RMSE_USD_sd": r["rmse_usd"].std(),
            "MAE_USD_media": r["mae_usd"].mean(),
            "MAPE_media": r["mape"].mean(),
            "R2_log_media": r["r2_log"].mean(), "R2_log_sd": r["r2_log"].std(),
        })
    res = pd.DataFrame(resumen)
    print("Baseline hedónico (OLS) — valor incremental S1→S4 (media ± sd entre folds):\n")
    for _, x in res.iterrows():
        print(f"  {x['escenario']} ({int(x['n_features']):>2} feats): "
              f"RMSE ${x['RMSE_USD_media']:,.0f} ±{x['RMSE_USD_sd']:,.0f} | "
              f"MAE ${x['MAE_USD_media']:,.0f} | MAPE {x['MAPE_media']:.1f}% | "
              f"R²(log) {x['R2_log_media']:.3f} ±{x['R2_log_sd']:.3f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.round(4).to_csv(OUT, index=False)
    print(f"\nTabla: {OUT.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
