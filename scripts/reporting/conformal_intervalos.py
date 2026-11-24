#!/usr/bin/env python3
"""Intervalos de predicción por conformal (exploratorio) sobre el MODELO FINAL de PI1
(notebook 04, importado de modelo_final.py), usando las predicciones fuera de muestra
(OOF) como scores de no-conformidad. Reporta cobertura empírica (global y por segmento)
y amplitud. Reproducible y consistente con el modelo final.
Salidas: reports/tables/modelado/conformal_cobertura.csv · reports/figures/resultados/r7_intervalos.png
"""
import sys, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.model_selection import GroupKFold
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts"/"modeling")); import modelo_final as mf
TAB = ROOT/"reports"/"tables"/"modelado"; FIG = ROOT/"reports"/"figures"/"resultados"
AZUL, NARANJA = "#2c6e91", "#c0562b"
plt.rcParams.update({"font.size":11,"axes.spines.top":False,"axes.spines.right":False,"figure.dpi":130})
df = mf.cargar_matriz(ROOT); yv = pd.to_numeric(df["eda_precio_usd"],errors="coerce").values.astype(float)
ytil = mf.target_log(df); groups = df["building_cluster_id"].values
cols = mf.columnas_S4(df); X = df[cols]
oof = np.full(len(yv), np.nan)
for tr,va in GroupKFold(5).split(X, ytil, groups):
    oof[va] = mf.construir_modelo_final(cols, df).fit(X.iloc[tr], ytil[tr]).predict(X.iloc[va])
alpha=0.10; res=np.abs(ytil-oof); n=len(res); k=int(np.ceil((n+1)*(1-alpha))); q=np.sort(res)[min(k,n)-1]
lo=np.expm1(oof-q); hi=np.expm1(oof+q); dentro=(yv>=lo)&(yv<=hi)
cob=dentro.mean()*100; amp=np.median((hi-lo)/np.expm1(oof))*100
print(f"[modelo final] q(log)={q:.3f} | cobertura={cob:.1f}% | ancho mediano ±{amp/2:.0f}%")
print("NOTA: mismos OOF para calibrar y evaluar -> NO es validación independiente.")
seg=pd.cut(yv,[0,80000,120000,180000,300000,np.inf],labels=["< 80k","80–120k","120–180k","180–300k","> 300k"])
rows=[{"segmento":"GLOBAL","n":n,"cobertura_%":round(cob,1),"ancho_rel_%":round(amp)}]
for s in seg.categories:
    m=seg==s; rows.append({"segmento":s,"n":int(m.sum()),"cobertura_%":round(dentro[m].mean()*100,1),"ancho_rel_%":round(np.median((hi[m]-lo[m])/np.expm1(oof[m]))*100)})
cov=pd.DataFrame(rows); cov.to_csv(TAB/"conformal_cobertura.csv",index=False); print(cov.to_string(index=False))
fig,ax=plt.subplots(figsize=(8,4.5)); sub=cov[cov.segmento!="GLOBAL"]
ax.bar(sub["segmento"],sub["cobertura_%"],color=AZUL); ax.axhline(90,color=NARANJA,ls="--",lw=1.8,label="nivel nominal 90 %")
for i,v in enumerate(sub["cobertura_%"]): ax.text(i,v+0.6,f"{v:.0f}%",ha="center",fontsize=9)
ax.set(ylim=(0,105),ylabel="Cobertura empírica (%)",xlabel="Segmento de precio (USD)",title="Cobertura de los intervalos (90 %) por segmento"); ax.legend()
fig.tight_layout(); fig.savefig(FIG/"r7_intervalos.png"); plt.close(fig); print("figura ->",FIG/"r7_intervalos.png")
