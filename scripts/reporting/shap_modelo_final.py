#!/usr/bin/env python3
"""SHAP sobre el MODELO FINAL de PI1 (importado de modelo_final.py: LightGBM one-hot,
notebook 04). Las categóricas one-hot se agregan a su variable de origen para la
importancia global. Guarda figuras y CSV. Fuente única de hiperparámetros."""
import warnings; warnings.filterwarnings("ignore")
import sys, numpy as np, pandas as pd, shap, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts"/"modeling")); import modelo_final as mf
FIG = ROOT/"reports"/"figures"/"shap"; FIG.mkdir(parents=True, exist_ok=True)
TAB = ROOT/"reports"/"tables"/"modelado"

df = mf.cargar_matriz(ROOT); y = mf.target_log(df); cols = mf.columnas_S4(df)
pipe = mf.construir_modelo_final(cols, df).fit(df[cols], y)
names = [n.split("__",1)[-1] for n in pipe.named_steps["prep"].get_feature_names_out()]
Xt = pd.DataFrame(pipe.named_steps["prep"].transform(df[cols]), columns=names)
ex = shap.TreeExplainer(pipe.named_steps["m"])(Xt.values); ex.feature_names = names
base = float(ex.base_values[0])

REN = {"eda_superficie_total_m2":"Superficie total","eda_superficie_cubierta_m2":"Superficie cubierta","eda_ambientes":"Ambientes",
 "eda_banos":"Baños","eda_antiguedad_anos":"Antigüedad","eda_latitud":"Latitud","eda_longitud":"Longitud","barrio_oficial_geo":"Barrio",
 "eda_dormitorios":"Dormitorios","eda_cocheras":"Cocheras","eda_toilette":"Toilette","eda_expensas":"Expensas","eda_disposicion":"Disposición",
 "eda_orientacion":"Orientación","eda_tipo_operacion":"Tipo de operación","fe_sup_por_ambiente":"Superficie por ambiente",
 "fe_banos_por_ambiente":"Baños por ambiente","fe_dormitorios_por_ambiente":"Dormitorios por ambiente","fe_ratio_cubierta_total":"Cubierta/total",
 "fe_tiene_cochera":"Tiene cochera","fe_expensas_informadas":"Expensas informadas","fe_dist_centro_km":"Distancia al centro",
 "fe_dist_rio_km":"Distancia al río","fe_dist_espacio_verde_km":"Distancia a espacio verde","fe_dens_comercios_300m":"Densidad comercial"}
REN.update({c:c.replace("feat_","").replace("_"," ").capitalize() for c in cols if c.startswith("feat_")})
def orig(n):
    for c in mf.CAT:
        if n.startswith(c+"_"): return c
    return n
mean_abs = np.abs(ex.values).mean(0); agg={}
for n,v in zip(names, mean_abs): agg[orig(n)] = agg.get(orig(n),0.0)+v
imp = pd.Series(agg).sort_values(ascending=False); imp.index=[REN.get(i,i) for i in imp.index]
imp.rename("shap_medio_abs").to_csv(TAB/"shap_importancia_s4.csv", header=True)
print(f"base={base:.3f} (log) -> USD {np.expm1(base):,.0f} | casos={ex.values.shape[0]}")
print(imp.head(8).round(4).to_string())

top=imp.head(14)[::-1]
fig,ax=plt.subplots(figsize=(8,5)); ax.barh(top.index,top.values,color="#2c6e91")
ax.set_xlabel("Importancia SHAP (media |aporte|, escala log)"); ax.set_title("SHAP — importancia global (modelo final, S4)")
fig.tight_layout(); fig.savefig(FIG/"s_importancia_bar.png"); plt.close(fig)
ex.feature_names=[REN.get(n,n) for n in names]
shap.plots.beeswarm(ex,max_display=15,show=False); plt.title("SHAP — aportes por variable (beeswarm, modelo final)")
plt.savefig(FIG/"s_importancia_beeswarm.png",bbox_inches="tight"); plt.close()
for col,fn in [("Superficie total","s_dep_superficie"),("Antigüedad","s_dep_antiguedad"),("Baños","s_dep_banos"),("Latitud","s_dep_latitud")]:
    if col in ex.feature_names:
        shap.plots.scatter(ex[:,col],show=False); plt.title(f"SHAP — dependencia: {col}")
        plt.savefig(FIG/f"{fn}.png",bbox_inches="tight"); plt.close()
ytu=np.expm1(y); order=np.argsort(ytu)
for et,i in {"bajo":int(order[int(0.10*len(ytu))]),"medio":int(order[int(0.50*len(ytu))]),"alto":int(order[int(0.90*len(ytu))])}.items():
    shap.plots.waterfall(ex[i],max_display=12,show=False); plt.title(f"Tasación {et} — descomposición SHAP")
    plt.savefig(FIG/f"s_waterfall_{et}.png",bbox_inches="tight"); plt.close()
print("OK figuras+CSV (fuente única modelo_final)")
