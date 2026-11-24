#!/usr/bin/env python3
"""Análisis de errores por segmento de precio (OOF del MODELO FINAL) y métricas por
partición para las tres familias, bajo el protocolo group-aware del Capítulo 4.
El LightGBM es el modelo final (notebook 04, importado de modelo_final.py).
Salidas: metricas_por_fold_s4.csv · error_por_segmento.csv · r6_error_por_segmento.png
"""
import sys, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts"/"modeling")); import modelo_final as mf
TAB = ROOT/"reports"/"tables"/"modelado"; FIG = ROOT/"reports"/"figures"/"resultados"
plt.rcParams.update({"font.size":11,"axes.spines.top":False,"axes.spines.right":False,"figure.dpi":130})
df = mf.cargar_matriz(ROOT); yv = pd.to_numeric(df["eda_precio_usd"],errors="coerce").values.astype(float)
ytil = mf.target_log(df); groups = df["building_cluster_id"].values
cols = mf.columnas_S4(df); X = df[cols]
CAT=[c for c in cols if c in mf.CAT]; BIN=[c for c in cols if c in mf._binarias(df)]; NUM=[c for c in cols if c not in CAT and c not in BIN]
def prep(scale):
    return ColumnTransformer([
        ("num", Pipeline([("i",SimpleImputer(strategy="median"))]+([("s",StandardScaler())] if scale else [])), NUM),
        ("bin", SimpleImputer(strategy="most_frequent"), BIN),
        ("cat", Pipeline([("i",SimpleImputer(strategy="most_frequent")),("o",OneHotEncoder(handle_unknown="ignore",min_frequency=10,sparse_output=False))]), CAT)])
def pipe_hed(): return Pipeline([("p",prep(True)),("m",LinearRegression())])
def pipe_rf():  return Pipeline([("p",prep(False)),("m",RandomForestRegressor(n_estimators=600,max_depth=16,random_state=0,n_jobs=-1))])
def pipe_lgb(): return mf.construir_modelo_final(cols, df)
modelos={"Hedónico":pipe_hed,"Random Forest":pipe_rf,"LightGBM":pipe_lgb}
gkf=GroupKFold(5); filas=[]; oof_lgb=np.zeros(len(yv))
for nombre,fn in modelos.items():
    for k,(tr,va) in enumerate(gkf.split(X,ytil,groups),1):
        pred=fn().fit(X.iloc[tr],ytil[tr]).predict(X.iloc[va])
        filas.append({"modelo":nombre,"fold":k,"R2_log":round(r2_score(ytil[va],pred),4),"RMSE_USD":round(np.sqrt(mean_squared_error(yv[va],np.expm1(pred))))})
        if nombre=="LightGBM": oof_lgb[va]=pred
fold_tab=pd.DataFrame(filas); fold_tab.to_csv(TAB/"metricas_por_fold_s4.csv",index=False)
print(fold_tab.groupby("modelo").agg(R2_medio=("R2_log","mean"),R2_sd=("R2_log","std"),RMSE_medio=("RMSE_USD","mean")).round(3))
pred_usd=np.expm1(oof_lgb)
seg=pd.cut(yv,[0,80000,120000,180000,300000,np.inf],labels=["< 80.000","80.000–120.000","120.000–180.000","180.000–300.000","> 300.000"])
rows=[]
for s in seg.categories:
    m=seg==s; rows.append({"segmento":s,"n":int(m.sum()),"MAE_USD":round(mean_absolute_error(yv[m],pred_usd[m])),
                           "MAPE":round(np.mean(np.abs((yv[m]-pred_usd[m])/yv[m]))*100,1),"sesgo_medio_USD":round(np.mean(pred_usd[m]-yv[m]))})
segt=pd.DataFrame(rows); segt.to_csv(TAB/"error_por_segmento.csv",index=False); print("\n",segt.to_string(index=False))
fig,ax=plt.subplots(figsize=(8,4.5)); ax.bar(range(len(segt)),segt["MAPE"],color="#2c6e91"); ax.set_xticks(range(len(segt))); ax.set_xticklabels(["< 80k","80–120k","120–180k","180–300k","> 300k"])
for i,v in enumerate(segt["MAPE"]): ax.text(i,v+0.3,f"{v:.1f}%",ha="center",fontsize=9)
ax.set(ylabel="MAPE (%)",xlabel="Segmento de precio (USD)",title="Error relativo (MAPE) por segmento — LightGBM final (OOF)")
fig.tight_layout(); fig.savefig(FIG/"r6_error_por_segmento.png"); plt.close(fig)
print("\nR2 OOF LightGBM global:",round(r2_score(ytil,oof_lgb),3))
