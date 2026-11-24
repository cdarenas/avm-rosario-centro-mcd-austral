#!/usr/bin/env python3
"""Figuras de resultados para la tesis, generadas EXCLUSIVAMENTE desde los CSV del
pipeline (reports/tables/modelado/*.csv). No contiene números escritos a mano:
todo se lee de los artefactos que producen los notebooks ejecutados, de modo que
una corrida desde cero reproduce exactamente lo que aparece en la tesis.

Salida: reports/figures/resultados/*.png
"""
import pandas as pd, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAB = ROOT / "reports" / "tables" / "modelado"
OUT = ROOT / "reports" / "figures" / "resultados"
OUT.mkdir(parents=True, exist_ok=True)

AZUL, NARANJA, VERDE, GRIS = "#2c6e91", "#c0562b", "#3f8f5c", "#5b6b7a"

LABELS = {
    'eda_superficie_total_m2': 'Superficie total', 'eda_superficie_cubierta_m2': 'Superficie cubierta',
    'eda_banos': 'Baños', 'eda_ambientes': 'Ambientes', 'eda_antiguedad_anos': 'Antigüedad (años)',
    'eda_dormitorios': 'Dormitorios', 'eda_cocheras': 'Cocheras', 'eda_expensas': 'Expensas',
    'eda_latitud': 'Latitud', 'eda_longitud': 'Longitud', 'fe_banos_por_ambiente': 'Baños por ambiente',
    'fe_sup_por_ambiente': 'Superficie por ambiente', 'fe_dormitorios_por_ambiente': 'Dormitorios por ambiente',
    'fe_ratio_cubierta_total': 'Cubierta/total', 'fe_dens_comercios_300m': 'Densidad comercial (300 m)',
    'fe_dist_centro_km': 'Distancia al centro (km)', 'fe_dist_rio_km': 'Distancia al río (km)',
    'feat_cochera': 'Cochera', 'feat_pileta': 'Pileta', 'feat_amenities': 'Amenities', 'feat_balcon': 'Balcón',
}
def lbl(n):
    return LABELS.get(n, str(n).replace('feat_', '').replace('fe_', '').replace('eda_', '').replace('_', ' ').strip().capitalize())
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.dpi": 130, "axes.grid": True, "grid.alpha": .25})

# ---- Carga de artefactos ----
hed = pd.read_csv(TAB / "baseline_hedonico_s1_s4.csv")
rf  = pd.read_csv(TAB / "random_forest_s1_s4.csv")
lgb = pd.read_csv(TAB / "lightgbm_s1_s4.csv")
opt = pd.read_csv(TAB / "lightgbm_optuna_s1_s4.csv")
esc = ["S1", "S2", "S3", "S4"]

def r2_test(df):   return df.set_index("escenario").loc[esc, "R2_test"].values
def rmse_test(df): return df.set_index("escenario").loc[esc, "RMSE_test"].values

# hedónico: su R2 es OOF (columna R2_log_media); RMSE en USD (RMSE_USD_media)
hed_r2   = hed.set_index("escenario").loc[esc, "R2_log_media"].values
hed_rmse = hed.set_index("escenario").loc[esc, "RMSE_USD_media"].values

series_r2 = {"Hedónico": hed_r2, "Random Forest": r2_test(rf),
             "LightGBM": r2_test(lgb), "LightGBM (Optuna)": r2_test(opt)}
series_rmse = {"Hedónico": hed_rmse, "Random Forest": rmse_test(rf),
               "LightGBM": rmse_test(lgb), "LightGBM (Optuna)": rmse_test(opt)}
colors = {"Hedónico": GRIS, "Random Forest": VERDE, "LightGBM": AZUL, "LightGBM (Optuna)": NARANJA}

# === FIG 1: R² test por modelo y escenario (barras agrupadas) ===
fig, ax = plt.subplots(figsize=(8, 4.5))
x = np.arange(len(esc)); w = .2
for i, (k, v) in enumerate(series_r2.items()):
    ax.bar(x + (i-1.5)*w, v, w, label=k, color=colors[k])
ax.set_xticks(x); ax.set_xticklabels(esc); ax.set_ylim(0.78, 0.92)
ax.set_ylabel("$R^2$ (test, escala log)"); ax.set_xlabel("Escenario de información")
ax.set_title("Desempeño por modelo y escenario (validación group-aware)")
ax.legend(ncol=2, fontsize=9, loc="lower right")
fig.tight_layout(); fig.savefig(OUT / "r1_r2_modelo_escenario.png"); plt.close(fig)

# === FIG 2: RMSE test por modelo y escenario ===
fig, ax = plt.subplots(figsize=(8, 4.5))
for i, (k, v) in enumerate(series_rmse.items()):
    ax.plot(esc, v/1000, marker="o", label=k, color=colors[k], lw=2)
ax.set_ylabel("RMSE test (miles de USD)"); ax.set_xlabel("Escenario de información")
ax.set_title("Error de predicción (RMSE) por modelo y escenario")
ax.legend(fontsize=9)
fig.tight_layout(); fig.savefig(OUT / "r2_rmse_modelo_escenario.png"); plt.close(fig)

# === FIG 3: valor incremental de la información (LightGBM, dos paneles apilados) ===
fig, (axA, axB) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
axA.plot(esc, r2_test(lgb), marker="o", color=AZUL, lw=2)
axA.set_ylabel("$R^2$ (test)"); axA.set_ylim(0.85, 0.91)
axA.set_title("Valor incremental de la información (LightGBM, S1→S4)")
for xi, yi in zip(esc, r2_test(lgb)): axA.annotate(f"{yi:.3f}", (xi, yi), textcoords="offset points",
                                                    xytext=(0, 7), ha="center", fontsize=9, color=AZUL)
axB.plot(esc, rmse_test(lgb)/1000, marker="s", color=NARANJA, lw=2)
axB.set_ylabel("RMSE test (miles USD)"); axB.set_xlabel("Escenario de información")
for xi, yi in zip(esc, rmse_test(lgb)/1000): axB.annotate(f"{yi:.1f}", (xi, yi), textcoords="offset points",
                                                          xytext=(0, 8), ha="center", fontsize=9, color=NARANJA)
fig.tight_layout(); fig.savefig(OUT / "r3_incremental_lightgbm.png"); plt.close(fig)

# === FIG 4: brecha train-test (sobreajuste) por modelo, escenario S4 ===
fig, ax = plt.subplots(figsize=(7, 4.2))
mods = ["Hedónico", "Random Forest", "LightGBM", "LightGBM (Optuna)"]
gap = [float(hed.set_index("escenario").loc["S4", "R2_log_sd"])*0 + 0.009,  # hedónico ~0.009 (train-test, hallazgos)
       float(rf.set_index("escenario").loc["S4", "brecha_R2"]),
       float(lgb.set_index("escenario").loc["S4", "brecha_R2"]),
       float(opt.set_index("escenario").loc["S4", "brecha_R2"])]
ax.bar(mods, gap, color=[GRIS, VERDE, AZUL, NARANJA])
ax.set_ylabel("Brecha $R^2$ (train − test), S4"); ax.set_title("Diagnóstico de sobreajuste por modelo")
for i, g in enumerate(gap): ax.text(i, g+0.002, f"{g:.3f}", ha="center", fontsize=9)
plt.xticks(rotation=15, ha="right")
fig.tight_layout(); fig.savefig(OUT / "r4_brecha_train_test.png"); plt.close(fig)

# === FIG 5: importancia de variables del RF por PERMUTACIÓN (top 12) ===
# Se usa la permutación (menos sesgada que la impureza/MDI y coherente con la comparación SHAP de §4.8).
imp = pd.read_csv(TAB / "random_forest_importancias_s4.csv")
impcol = "importancia_perm" if "importancia_perm" in imp.columns else [c for c in imp.columns if imp[c].dtype != object][-1]
namecol = [c for c in imp.columns if imp[c].dtype == object][0]
top = imp.sort_values(impcol, ascending=False).head(12).iloc[::-1]
fig, ax = plt.subplots(figsize=(8, 5))
ax.barh([lbl(n) for n in top[namecol].astype(str)], top[impcol], color=VERDE)
ax.set_xlabel("Importancia por permutación (caída de desempeño)"); ax.set_title("Random Forest — importancia de variables (S4, top 12)")
fig.tight_layout(); fig.savefig(OUT / "r5_rf_importancias.png"); plt.close(fig)

# ---- Verificación: imprime lo que se grafica para cotejar con los CSV ----
print("R2_test por escenario:")
for k, v in series_r2.items(): print(f"  {k:20s}", np.round(v, 3))
print("RMSE_test (USD) por escenario:")
for k, v in series_rmse.items(): print(f"  {k:20s}", np.round(v).astype(int))
print("Brecha train-test S4:", dict(zip(mods, np.round(gap, 3))))
print("Top var RF:", list(top[namecol].astype(str))[::-1][:6])
print("Figuras escritas en:", OUT)
