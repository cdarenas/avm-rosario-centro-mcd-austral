#!/usr/bin/env python3
"""Exporta el MODELO FINAL de PI1 (notebook 04, vía modelo_final.py) como artefacto de
producción (.joblib) para el robot/Raspberry, SIN reentrenar. Incluye el cuantil
conforme (q) para reconstruir el intervalo de predicción, metadatos y un CASO DE
REFERENCIA con predicción e intervalo esperados (para verificar en la Pi).

Salidas en artefactos_produccion/:
  avm_lightgbm_final.joblib    (pipeline completo one-hot + LightGBM + q conforme)
  avm_metadata.json            (modelo, escenario, target, features, q, versiones)
  avm_caso_prueba.json         (input conocido -> predicción e intervalo esperados)
"""
import sys, json, hashlib, numpy as np, pandas as pd
from pathlib import Path
import joblib, sklearn, lightgbm
from sklearn.model_selection import GroupKFold
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts"/"modeling")); import modelo_final as mf
OUT = ROOT/"artefactos_produccion"; OUT.mkdir(exist_ok=True)

df = mf.cargar_matriz(ROOT); y = mf.target_log(df); cols = mf.columnas_S4(df)
groups = df["building_cluster_id"].values

# cuantil conforme q (OOF, mismo esquema que conformal_intervalos.py) -- nivel 90%
oof = np.full(len(y), np.nan)
for tr, va in GroupKFold(5).split(df[cols], y, groups):
    oof[va] = mf.construir_modelo_final(cols, df).fit(df[cols].iloc[tr], y[tr]).predict(df[cols].iloc[va])
alpha = 0.10; res = np.abs(y - oof); n = len(res)
q = float(np.sort(res)[min(int(np.ceil((n+1)*(1-alpha))), n)-1])
pred_oof = np.expm1(oof); yv_all = np.expm1(y)
ape = np.abs(yv_all - pred_oof) / yv_all                           # error porcentual absoluto OOF
mape = float(np.mean(ape) * 100)                                   # referencia (métrica media)
# Rango ORIENTATIVO del robot: percentil del APE OOF (no la media). P80 = "~8 de cada 10
# casos históricos cayeron dentro de este error porcentual". Interpretación empírica clara,
# proporcional al precio. NO es un intervalo de predicción estadístico (eso es el conforme 90%).
ape_pctls = {p: float(np.percentile(ape, p) * 100) for p in (75, 80, 90)}
ROBOT_P = 75                                                       # percentil elegido para el robot
e_robot = ape_pctls[ROBOT_P] / 100                                 # fracción (p.ej. 0.215)
# Banda SIMÉTRICA pred*(1 ± e): mismo % de cobertura empírica que la asimétrica en estos
# datos (el modelo casi no tiene sesgo global: ~47% sobreestima / ~53% subestima), pero con
# un techo más moderado y un mensaje más simple ("± e%"). NO es un intervalo estadístico.
# MAPE + sesgo medio por segmento de precio (chequeo antes de congelar la banda)
_seg = pd.cut(yv_all, [0,80000,120000,180000,300000,np.inf],
              labels=["<80k","80-120k","120-180k","180-300k",">300k"])
seg_check = {}
for s in _seg.categories:
    m = np.asarray(_seg == s)
    seg_check[str(s)] = {"n": int(m.sum()), "mape_pct": round(float(ape[m].mean()*100),1),
                         "ape_p80_pct": round(float(np.percentile(ape[m],80)*100),1),
                         "sesgo_medio_usd": round(float(np.mean(pred_oof[m]-yv_all[m])),0)}

# modelo final entrenado sobre TODA la matriz
pipe = mf.construir_modelo_final(cols, df).fit(df[cols], y)
joblib.dump({"pipeline": pipe, "cols": cols, "target": "log1p(precio_usd)",
             "retransform": "expm1", "conformal_q_log": q, "conformal_nivel": 0.90, "mape_pct": mape,
             "rango_orientativo_percentil": ROBOT_P, "rango_orientativo_ape": e_robot,
             "ape_percentiles_pct": ape_pctls, "best_params": mf.BEST_PARAMS},
            OUT/"avm_lightgbm_final.joblib")

meta = {"model": "LightGBM", "scenario": "S4", "target": "log1p(precio_usd)",
        "inverse_transform": "expm1", "feature_count": len(cols),
        "conformal_q_log": round(q, 4), "conformal_nivel": 0.90, "mape_pct": round(mape, 1),
        "intervalo_conformal_90": "pred_log ± q  ->  [expm1(pred_log - q), expm1(pred_log + q)]  (tesis: garantía 90%)",
        "rango_orientativo": {
            "percentil_ape": ROBOT_P, "ape_pct": round(e_robot*100, 1), "forma": "simetrica",
            "formula": "lower = pred_usd * (1 - e),  upper = pred_usd * (1 + e)   con e = ape_pct/100",
            "interpretacion": f"rango de referencia: ~{ROBOT_P}% de los casos historicos cayeron dentro de este error porcentual (cobertura empirica verificada ~{ROBOT_P}%). NO es un intervalo de prediccion estadistico.",
            "nota": "banda simetrica: cobertura empirica equivalente a la asimetrica porque el modelo casi no tiene sesgo global (~47% sobreestima / ~53% subestima)."},
        "ape_percentiles_pct": {str(k): round(v,1) for k,v in ape_pctls.items()},
        "chequeo_por_segmento": seg_check,
        "categoricas": sorted([c for c in cols if c in mf.CAT]),
        "binarias_texto": sorted([c for c in cols if c.startswith("feat_")]),
        "columnas_entrada": cols,
        "sklearn": sklearn.__version__, "lightgbm": lightgbm.__version__, "version": "1.0"}
json.dump(meta, open(OUT/"avm_metadata.json","w"), ensure_ascii=False, indent=2)

i = int(np.argsort(np.expm1(y))[int(0.50*len(y))])   # propiedad de referencia (precio mediano)
# --- referencia SHAP para la propiedad de prueba (agregada a variables semánticas) ---
import shap
names = [n.split("__",1)[-1] for n in pipe.named_steps["prep"].get_feature_names_out()]
Xt = pipe.named_steps["prep"].transform(df[cols])
_ex = shap.TreeExplainer(pipe.named_steps["m"])(Xt)
REN = {"eda_superficie_total_m2":"superficie_total","eda_superficie_cubierta_m2":"superficie_cubierta","eda_ambientes":"ambientes",
 "eda_dormitorios":"dormitorios","eda_banos":"banos","eda_cocheras":"cocheras","eda_toilette":"toilette","eda_antiguedad_anos":"antiguedad",
 "eda_latitud":"latitud","eda_longitud":"longitud","barrio_oficial_geo":"barrio","eda_expensas":"expensas","eda_disposicion":"disposicion",
 "eda_orientacion":"orientacion","eda_tipo_operacion":"tipo_operacion","fe_sup_por_ambiente":"superficie_por_ambiente",
 "fe_banos_por_ambiente":"banos_por_ambiente","fe_dist_centro_km":"distancia_centro","fe_dist_rio_km":"distancia_rio",
 "fe_dist_espacio_verde_km":"distancia_espacio_verde","fe_dens_comercios_300m":"densidad_comercial","eda_antiguedad_estado":"estado"}
REN.update({c:c.replace("feat_","") for c in cols if c.startswith("feat_")})
def _orig(nm):
    for c in mf.CAT:
        if nm.startswith(c+"_"): return c
    return nm
_agg = {}
for nm,val in zip(names, _ex.values[i]): _agg[_orig(nm)] = _agg.get(_orig(nm),0.0)+float(val)
_top = sorted(_agg.items(), key=lambda kv: abs(kv[1]), reverse=True)[:8]
shap_ref = {"base_value_log": round(float(_ex.base_values[i]),4),
            "top_features": [{"feature": REN.get(k,k), "shap_value": round(v,4),
                              "direction": "increase" if v>0 else "decrease"} for k,v in _top]}

# caso de referencia: input + predicción + intervalo + SHAP esperados
i = int(np.argsort(np.expm1(y))[int(0.50*len(y))])
fila = df[cols].iloc[[i]]; pl = float(pipe.predict(fila)[0])
pred_usd = float(np.expm1(pl)); lo = float(np.expm1(pl-q)); hi = float(np.expm1(pl+q))
caso = {"descripcion": "propiedad de precio mediano del dataset",
        "entrada": {k: (None if pd.isna(v) else (float(v) if isinstance(v,(int,float,np.floating,np.integer)) else str(v)))
                    for k,v in fila.iloc[0].to_dict().items()},
        "prediccion_esperada_usd": round(pred_usd, 2),
        "rango_orientativo_usd": {"metodo": f"percentil {ROBOT_P} del APE (banda simetrica)",
                            "ape_pct": round(e_robot*100,1),
                            "lower": round(pred_usd*(1-e_robot),2), "upper": round(pred_usd*(1+e_robot),2),
                            "nota": f"rango de referencia (~{ROBOT_P}% de los casos), NO intervalo de prediccion estadistico"},
        "intervalo_conformal_90_usd": {"q_log": round(q,4), "lower": round(lo,2), "upper": round(hi,2)},
        "shap_reference": shap_ref,
        "precio_observado_usd": float(np.expm1(y)[i])}
json.dump(caso, open(OUT/"avm_caso_prueba.json","w"), ensure_ascii=False, indent=2)

h = hashlib.md5(open(OUT/"avm_lightgbm_final.joblib","rb").read()).hexdigest()[:12]
print(f"Artefacto: avm_lightgbm_final.joblib (md5 {h}) | q(log)={q:.4f} | MAPE={mape:.1f}%")
print(f"APE percentiles OOF: " + ", ".join(f"P{p}={v:.1f}%" for p,v in ape_pctls.items()))
print(f"Caso de referencia -> predicción USD {pred_usd:,.2f}")
print(f"  Rango orientativo robot (P{ROBOT_P} simetrico, +/-{e_robot*100:.1f}%): [USD {pred_usd*(1-e_robot):,.0f} ; USD {pred_usd*(1+e_robot):,.0f}]")
print(f"  Conformal 90% (tesis):            [USD {lo:,.0f} ; USD {hi:,.0f}]")
print("Chequeo por segmento (mape / ape_p80 / sesgo_medio USD):")
for s,d in seg_check.items():
    print(f"  {s:9s} n={d['n']:4d}  MAPE={d['mape_pct']:4.1f}%  P80={d['ape_p80_pct']:4.1f}%  sesgo={d['sesgo_medio_usd']:+,.0f}")
print(f"sklearn {sklearn.__version__} · lightgbm {lightgbm.__version__}")
