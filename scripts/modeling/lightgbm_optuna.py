#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# LightGBM idiomático: categóricas NATIVAS + Optuna (TPE) + early stopping.
# Evaluación con CV group-aware ANIDADA (Optuna dentro del train de cada fold).
# Comparable con el LightGBM baseline (notebook 04) y el resto de los modelos.
#
# Entrada : data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz
# Salida  : reports/tables/modelado/lightgbm_optuna_s1_s4.csv  (train+test por escenario)
#
# Uso:  python3 scripts/modeling/lightgbm_optuna.py
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path
import numpy as np
import pandas as pd
import optuna
from optuna.samplers import TPESampler
from lightgbm import LGBMRegressor, early_stopping, log_evaluation
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_squared_error, r2_score

optuna.logging.set_verbosity(optuna.logging.WARNING)
ROOT = Path(__file__).resolve().parents[2]
MATRIZ = ROOT / "data" / "processed" / "zonaprop_v2_matriz_modelado_centro.csv.gz"
OUT = ROOT / "reports" / "tables" / "modelado" / "lightgbm_optuna_s1_s4.csv"
SEED, N_IN, N_TRIALS = 42, 3, 40

S1 = ["eda_superficie_total_m2","eda_superficie_cubierta_m2","eda_ambientes","eda_dormitorios",
      "eda_banos","eda_cocheras","eda_toilette","eda_antiguedad_anos","eda_antiguedad_estado",
      "eda_disposicion","eda_orientacion","eda_tipo_operacion","eda_expensas",
      "fe_ratio_cubierta_total","fe_sup_por_ambiente","fe_banos_por_ambiente",
      "fe_dormitorios_por_ambiente","fe_tiene_cochera","fe_expensas_informadas"]
S2 = ["barrio_oficial_geo","eda_latitud","eda_longitud"]
S3 = ["fe_dist_centro_km","fe_dist_rio_km","fe_dist_espacio_verde_km","fe_dens_comercios_300m"]
CAT = {"eda_antiguedad_estado","eda_disposicion","eda_orientacion","eda_tipo_operacion","barrio_oficial_geo"}
FIJOS = dict(objective="regression", n_estimators=3000, random_state=SEED, n_jobs=-1, subsample_freq=1, verbose=-1)
CB = [early_stopping(50, verbose=False), log_evaluation(0)]


def espacio(t):
    return dict(learning_rate=t.suggest_float("learning_rate", 0.005, 0.2, log=True),
                num_leaves=t.suggest_int("num_leaves", 15, 128),
                max_depth=t.suggest_int("max_depth", 3, 14),
                min_child_samples=t.suggest_int("min_child_samples", 5, 80),
                subsample=t.suggest_float("subsample", 0.6, 1.0),
                colsample_bytree=t.suggest_float("colsample_bytree", 0.6, 1.0),
                reg_alpha=t.suggest_float("reg_alpha", 1e-3, 20, log=True),
                reg_lambda=t.suggest_float("reg_lambda", 1e-3, 20, log=True))


def diseno(df, cols):
    X = pd.DataFrame(index=df.index)
    for c in cols:
        X[c] = df[c].astype("category") if c in CAT else pd.to_numeric(df[c], errors="coerce")
    return X


def tunear(X, y, g, n_trials=N_TRIALS):
    def obj(trial):
        p = {**FIJOS, **espacio(trial)}; sc = []
        for a, b in GroupKFold(N_IN).split(X, y, g):
            m = LGBMRegressor(**p).fit(X.iloc[a], y[a], eval_set=[(X.iloc[b], y[b])], callbacks=CB)
            sc.append(mean_squared_error(y[b], m.predict(X.iloc[b])))
        return float(np.mean(sc))
    st = optuna.create_study(direction="minimize", sampler=TPESampler(seed=SEED))
    st.optimize(obj, n_trials=n_trials, show_progress_bar=False)
    return st.best_params


def ajustar(X, y, g, params):
    a, b = next(iter(GroupKFold(5).split(X, y, g)))
    m = LGBMRegressor(**FIJOS, **params).fit(X.iloc[a], y[a], eval_set=[(X.iloc[b], y[b])], callbacks=CB)
    return m, a


def nested(df, cols, y, groups):
    X = diseno(df, cols); gkf = GroupKFold(5)
    tr_r2=[];te_r2=[];tr_rm=[];te_rm=[];te_mape=[]
    for tr, te in gkf.split(X, y, groups):
        best = tunear(X.iloc[tr], y[tr], groups[tr])
        m, itr = ajustar(X.iloc[tr], y[tr], groups[tr], best)
        ptr = m.predict(X.iloc[tr].iloc[itr]); pte = m.predict(X.iloc[te])
        tr_r2.append(r2_score(y[tr][itr], ptr)); te_r2.append(r2_score(y[te], pte))
        tr_rm.append(np.sqrt(mean_squared_error(np.expm1(y[tr][itr]), np.expm1(ptr))))
        te_rm.append(np.sqrt(mean_squared_error(np.expm1(y[te]), np.expm1(pte))))
        ytu, ypu = np.expm1(y[te]), np.expm1(pte); te_mape.append(np.mean(np.abs((ytu-ypu)/ytu))*100)
    return dict(R2_train=np.mean(tr_r2), R2_test=np.mean(te_r2), RMSE_train=np.mean(tr_rm),
                RMSE_test=np.mean(te_rm), MAPE_test=np.mean(te_mape), brecha_R2=np.mean(tr_r2)-np.mean(te_r2))


def main():
    df = pd.read_csv(MATRIZ)
    y = np.log1p(pd.to_numeric(df["eda_precio_usd"], errors="coerce").values)
    groups = df["building_cluster_id"].values
    feat = [c for c in df.columns if c.startswith("feat_")]
    escen = {"S1": [c for c in S1 if c in df.columns],
             "S2": [c for c in S1+S2 if c in df.columns],
             "S3": [c for c in S1+S2+S3 if c in df.columns],
             "S4": [c for c in S1+S2+S3 if c in df.columns] + feat}
    print(f"Matriz: {len(df):,} avisos · {df['building_cluster_id'].nunique():,} grupos · "
          f"LightGBM idiomático · Optuna n_trials={N_TRIALS} · nested 5×{N_IN}\n")
    filas = []
    for nombre, cols in escen.items():
        r = nested(df, cols, y, groups)
        filas.append({"escenario": nombre, "n_features": len(cols), **r})
        print(f"  {nombre} ({len(cols):>2} feats): R² train {r['R2_train']:.3f} / test {r['R2_test']:.3f} "
              f"(brecha {r['brecha_R2']:+.3f}) | RMSE test ${r['RMSE_test']:,.0f} | MAPE {r['MAPE_test']:.1f}%")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(filas).round(4).to_csv(OUT, index=False)
    print(f"\nTabla: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
