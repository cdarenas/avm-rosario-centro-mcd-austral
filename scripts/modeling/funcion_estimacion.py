#!/usr/bin/env python3
"""Anexo D — Función de estimación: precio + explicación (Objetivo específico 4).

Entrena el MODELO FINAL de PI1 (LightGBM one-hot, notebook 04, importado de
modelo_final.py) sobre toda la matriz de modelado y expone `tasar(i)`, que para una
propiedad devuelve el precio estimado en dólares junto con la descomposición SHAP de
su valuación. Guarda, además, un waterfall de ejemplo. Mismo modelo que el Capítulo 4.
"""
import sys, numpy as np, pandas as pd, shap, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts"/"modeling")); import modelo_final as mf
OUT = ROOT/"reports"/"figures"/"shap"; OUT.mkdir(parents=True, exist_ok=True)

df = mf.cargar_matriz(ROOT); y = mf.target_log(df)
cols = mf.columnas_S4(df)
pipe = mf.construir_modelo_final(cols, df).fit(df[cols], y)
names = [n.split("__",1)[-1] for n in pipe.named_steps["prep"].get_feature_names_out()]
Xt = pipe.named_steps["prep"].transform(df[cols])
ex = shap.TreeExplainer(pipe.named_steps["m"])(Xt); ex.feature_names = names

REN = {"eda_superficie_total_m2":"Superficie total","eda_superficie_cubierta_m2":"Superficie cubierta",
 "eda_ambientes":"Ambientes","eda_dormitorios":"Dormitorios","eda_banos":"Baños","eda_cocheras":"Cocheras",
 "eda_toilette":"Toilette","eda_antiguedad_anos":"Antigüedad (años)","eda_antiguedad_estado":"Estado",
 "eda_disposicion":"Disposición","eda_orientacion":"Orientación","eda_tipo_operacion":"Tipo de operación",
 "eda_expensas":"Expensas","fe_sup_por_ambiente":"Superficie por ambiente","fe_banos_por_ambiente":"Baños por ambiente",
 "barrio_oficial_geo":"Barrio","eda_latitud":"Latitud","eda_longitud":"Longitud","fe_dist_centro_km":"Distancia al centro (km)"}
def lbl(n): return REN.get(n, n.replace("feat_","").replace("fe_","").replace("eda_","").replace("_"," ").capitalize())
def orig(n):
    for c in mf.CAT:
        if n.startswith(c+"_"): return c
    return n

def tasar(i, top=6):
    """Precio estimado (USD) + principales aportes SHAP (agregados por variable) de la propiedad i."""
    precio = float(np.expm1(pipe.predict(df[cols].iloc[[i]]))[0])
    agg = {}
    for n,v in zip(names, ex.values[i]): agg[orig(n)] = agg.get(orig(n),0.0)+v
    contrib = pd.Series({lbl(k):v for k,v in agg.items()}).sort_values(key=abs, ascending=False)
    return precio, contrib.head(top)

if __name__ == "__main__":
    ytu = np.expm1(y); i = int(np.argsort(ytu)[int(0.50*len(ytu))])
    precio, aportes = tasar(i)
    print("=== Ejemplo de tasación (propiedad de precio mediano) ===")
    print(f"Precio observado : USD {ytu[i]:,.0f}")
    print(f"Precio estimado  : USD {precio:,.0f}")
    print(f"Valor base (valor esperado del modelo, ~mediana del mercado): USD {float(np.expm1(ex.base_values[i])):,.0f}")
    print("Principales aportes a la estimación (escala log):")
    for k,v in aportes.items(): print(f"  {k:28s} {v:+.3f}")
    exi = ex[i]; exi.feature_names = [lbl(n) for n in names]
    shap.plots.waterfall(exi, max_display=10, show=False)
    plt.title("Anexo D — Función de estimación: descomposición de una tasación")
    plt.tight_layout(); plt.savefig(OUT/"anexoD_waterfall_ejemplo.png", bbox_inches="tight"); plt.close()
    print("Figura:", OUT/"anexoD_waterfall_ejemplo.png")
