#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# run_pipeline.py — Orquestador reproducible del pipeline (AVM Rosario).
#
# El pipeline es una cadena de artefactos con linaje verificable por hash (cada
# dataset lleva su `*.manifest.json` con el SHA256 de su entrada y de su salida).
#
# Uso:
#   python run_pipeline.py --verify         # verifica hashes de todos los datasets vs. manifiesto
#   python run_pipeline.py --run            # re-ejecuta la cola reproducible (v4→v5→v6) + notebooks
#   python run_pipeline.py --run --from v5  # re-ejecuta desde una etapa
#   python run_pipeline.py --list           # muestra el DAG
#
# Entrada reproducible: v1 (lo previo —scrape y candidato desde la base— es externo).
# Los tramos v1→v4 dependen de artefactos de auditoría y se documentan en docs/PIPELINE.md;
# los tramos v4→v6 y los notebooks se re-ejecutan de forma automática.
# ─────────────────────────────────────────────────────────────────────────────
import argparse, hashlib, json, subprocess, sys, gzip
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "data" / "processed"

def content_sha256(path):
    """Hash del CONTENIDO (CSV descomprimido): verifica reproducibilidad de los DATOS,
    robusto al wrapper gzip y a qué proceso escribió el archivo."""
    raw = open(path, "rb").read()
    data = gzip.decompress(raw) if str(path).endswith(".gz") else raw
    return hashlib.sha256(data).hexdigest()

# ── DAG: orden de las etapas ─────────────────────────────────────────────────
# runnable=True → el orquestador la re-ejecuta; False → documentada (ver docs/PIPELINE.md)
STAGES = [
    {"id": "v1", "output": "data/processed/zonaprop_v2_eda_centro_v1.csv.gz",
     "input": None, "cmd": None, "runnable": False,
     "desc": "Universo EDA Distrito Centro (entrada reproducible del pipeline)"},
    {"id": "v2_barrios", "output": "data/processed/zonaprop_v2_eda_centro_v2_barrios.csv.gz",
     "input": "data/processed/zonaprop_v2_eda_centro_v1.csv.gz",
     "cmd": ["python", "scripts/data_quality/enriquecer_barrios_oficiales.py",
             "data/processed/zonaprop_v2_eda_centro_v1.csv.gz",
             "data/external/barrios_rosario/barrios_oficiales.csv",
             "data/processed/zonaprop_v2_eda_centro_v2_barrios.csv.gz",
             "reports/tables/auditoria_barrios_centro_v2.csv"],
     "runnable": False, "desc": "Enriquecimiento con barrios oficiales (point-in-polygon)"},
    {"id": "v3_auditado", "output": "data/processed/zonaprop_v2_eda_centro_v3_auditado.csv.gz",
     "input": "data/processed/zonaprop_v2_eda_centro_v2_barrios.csv.gz",
     "cmd": None, "runnable": False,
     "desc": "Universo auditado (decisiones P0/P1). Ver docs/PIPELINE.md para los argumentos."},
    {"id": "v4", "output": "data/processed/zonaprop_v2_eda_centro_v4.csv.gz",
     "input": "data/processed/zonaprop_v2_eda_centro_v3_auditado.csv.gz",
     "cmd": None, "runnable": False,
     "desc": "Muestra analítica apta para EDA. Ver docs/PIPELINE.md."},
    {"id": "v5", "output": "data/processed/zonaprop_v2_eda_centro_v5.csv.gz",
     "input": "data/processed/zonaprop_v2_eda_centro_v4.csv.gz",
     "cmd": ["python", "scripts/preprocessing/definir_muestra_temporal.py"],
     "runnable": True, "desc": "Corte temporal ≤ 6 meses (comparabilidad de precios)"},
    {"id": "v6", "output": "data/processed/zonaprop_v2_eda_centro_v6.csv.gz",
     "input": "data/processed/zonaprop_v2_eda_centro_v5.csv.gz",
     "cmd": ["python", "scripts/preprocessing/preprocesar_dataset.py"],
     "runnable": True, "desc": "Preprocesamiento: limpieza row-wise + regularización de nombres"},
    {"id": "pois", "output": "data/external/osm/espacios_verdes.csv",
     "input": None,
     "cmd": ["python", "scripts/feature_engineering/descargar_pois.py"],
     "runnable": False, "optional": True, "desc": "Descarga de POI (OSM) para S3 — correr una vez, requiere red"},
    {"id": "matriz", "output": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "input": "data/processed/zonaprop_v2_eda_centro_v6.csv.gz",
     "cmd": ["python", "scripts/feature_engineering/construir_matriz_modelado.py"],
     "runnable": True, "desc": "Feature engineering: matriz de modelado magra (S1–S4)"},
    {"id": "diccionario", "output": "docs/diccionario_variables.md",
     "input": "data/processed/zonaprop_v2_eda_centro_v6.csv.gz",
     "cmd": ["python", "scripts/data_quality/generar_diccionario_variables.py"],
     "runnable": True, "desc": "Diccionario de variables (124 columnas)"},
    {"id": "nb_eda", "output": "reports/eda_final_centro_v4.html",
     "input": "data/processed/zonaprop_v2_eda_centro_v5.csv.gz",
     "cmd": ["bash", "scripts/eda/exportar_reporte_html.sh"],
     "runnable": True, "desc": "EDA: ejecuta el notebook y exporta el reporte HTML"},
    {"id": "nb_preproc", "output": "notebooks/02_preprocesamiento/01_preprocesamiento_centro_v6.ipynb",
     "input": "data/processed/zonaprop_v2_eda_centro_v5.csv.gz",
     "cmd": ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "notebooks/02_preprocesamiento/01_preprocesamiento_centro_v6.ipynb"],
     "runnable": True, "desc": "Preprocesamiento: ejecuta el notebook"},
    {"id": "nb_fe", "output": "notebooks/03_feature_engineering/01_matriz_modelado_centro.ipynb",
     "input": "data/processed/zonaprop_v2_eda_centro_v6.csv.gz",
     "cmd": ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "notebooks/03_feature_engineering/01_matriz_modelado_centro.ipynb"],
     "runnable": True, "desc": "Feature engineering: ejecuta el notebook"},
    {"id": "baseline", "output": "reports/tables/modelado/baseline_hedonico_s1_s4.csv",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["python", "scripts/modeling/baseline_hedonico.py"],
     "runnable": True, "desc": "Modelado: baseline hedónico (OLS) S1→S4"},
    {"id": "nb_baseline", "output": "notebooks/04_modelado/01_baseline_hedonico.ipynb",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "notebooks/04_modelado/01_baseline_hedonico.ipynb"],
     "runnable": True, "desc": "Modelado: ejecuta el notebook del baseline hedónico"},
    {"id": "regular", "output": "reports/tables/modelado/regularizacion_perf_s4.csv",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["python", "scripts/modeling/regularizacion.py"],
     "runnable": True, "desc": "Modelado: regularización (Ridge/Lasso/ElasticNet) y selección de variables"},
    {"id": "nb_regular", "output": "notebooks/04_modelado/02_regularizacion.ipynb",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "notebooks/04_modelado/02_regularizacion.ipynb"],
     "runnable": True, "desc": "Modelado: ejecuta el notebook de regularización"},
    {"id": "rf", "output": "reports/tables/modelado/random_forest_s1_s4.csv",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["python", "scripts/modeling/random_forest.py"],
     "runnable": True, "desc": "Modelado: Random Forest S1→S4 (tuneo + importancias)"},
    {"id": "nb_rf", "output": "notebooks/04_modelado/03_random_forest.ipynb",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "notebooks/04_modelado/03_random_forest.ipynb"],
     "runnable": True, "desc": "Modelado: ejecuta el notebook de Random Forest"},
    {"id": "lgbm", "output": "reports/tables/modelado/lightgbm_s1_s4.csv",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["python", "scripts/modeling/lightgbm_model.py"],
     "runnable": True, "desc": "Modelado: LightGBM S1→S4 (nested CV + búsqueda + importancias)"},
    {"id": "nb_lgbm", "output": "notebooks/04_modelado/04_lightgbm.ipynb",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "notebooks/04_modelado/04_lightgbm.ipynb"],
     "runnable": True, "desc": "Modelado: ejecuta el notebook de LightGBM"},
    {"id": "lgbm_opt", "output": "reports/tables/modelado/lightgbm_optuna_s1_s4.csv",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["python", "scripts/modeling/lightgbm_optuna.py"],
     "runnable": True, "desc": "Modelado: LightGBM idiomático (nativas + Optuna + early stopping)"},
    {"id": "nb_lgbm_opt", "output": "notebooks/04_modelado/05_lightgbm_optuna.ipynb",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "notebooks/04_modelado/05_lightgbm_optuna.ipynb"],
     "runnable": True, "desc": "Modelado: ejecuta el notebook de LightGBM idiomático (Optuna + SHAP)"},
    {"id": "nb_espacial", "output": "notebooks/05_espacial/01_diagnostico_espacial.ipynb",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "notebooks/05_espacial/01_diagnostico_espacial.ipynb"],
     "runnable": True, "desc": "Diagnóstico espacial: Moran's I sobre residuos + spatial lag (RQ3–RQ4)"},
    {"id": "nb_shap", "output": "notebooks/06_interpretabilidad/01_shap.ipynb",
     "input": "data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz",
     "cmd": ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "notebooks/06_interpretabilidad/01_shap.ipynb"],
     "runnable": True, "desc": "Interpretabilidad: SHAP (global, dependencias, local) sobre el modelo final (RQ5)"},
    {"id": "reportes", "output": "reportes_html/index.html",
     "input": None,
     "cmd": ["python", "scripts/reporting/generar_reportes_html.py"],
     "runnable": True, "desc": "Reportes HTML por etapa (exportación estática para revisar sin ejecutar)"},
]

def verificar():
    print("Verificación de linaje por hash de CONTENIDO (dataset vs. manifiesto):\n")
    ok = True
    for st in STAGES:
        out = ROOT / st["output"]
        man = out.with_name(out.name + ".manifest.json")
        if not out.exists():
            if st.get("optional"):
                print(f"  [pend.]  {st['id']:<12} {st['output']}  (opcional, no descargado)")
            else:
                print(f"  [FALTA]  {st['id']:<12} {st['output']}"); ok = False
            continue
        if not man.exists():
            print(f"  [s/man]  {st['id']:<12} {st['output']}  (sin manifiesto)"); continue
        m = json.loads(man.read_text())
        esperado = m.get("content_sha256") or m.get("artifact_sha256")   # contenido; fallback a hash de archivo
        real = content_sha256(out) if "content_sha256" in m else sha256_file(out)
        estado = "OK  " if esperado == real else "MISMATCH"
        if esperado != real: ok = False
        print(f"  [{estado}] {st['id']:<12} {st['output']}")
    print("\n" + ("✓ Todos los artefactos coinciden con su manifiesto (contenido reproducible)." if ok
                  else "✗ Hay discrepancias — revisar arriba."))
    return ok

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def correr(desde=None):
    activo = desde is None
    for st in STAGES:
        if st["id"] == desde: activo = True
        if not activo: continue
        if not st["runnable"] or st["cmd"] is None:
            if st["input"] is not None:
                print(f"· [documentada] {st['id']}: {st['desc']}  → ver docs/PIPELINE.md")
            continue
        print(f"\n▶ {st['id']}: {st['desc']}")
        r = subprocess.run(st["cmd"], cwd=ROOT)
        if r.returncode != 0:
            print(f"✗ Falló la etapa '{st['id']}'."); sys.exit(1)
    print("\n✓ Cola reproducible ejecutada.")

def listar():
    print("DAG del pipeline (entrada reproducible: v1):\n")
    for st in STAGES:
        flechа = "←" if st["input"] else " "
        marca = "auto" if st["runnable"] else "doc "
        print(f"  [{marca}] {st['id']:<12} {flechа} {Path(st['input']).name if st['input'] else '(raíz)':<40} {st['desc']}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Orquestador reproducible del pipeline AVM Rosario.")
    ap.add_argument("--verify", action="store_true", help="verifica hashes vs. manifiestos")
    ap.add_argument("--run", action="store_true", help="re-ejecuta la cola reproducible + notebooks")
    ap.add_argument("--from", dest="desde", default=None, help="ejecutar desde una etapa (id)")
    ap.add_argument("--list", action="store_true", help="muestra el DAG")
    args = ap.parse_args()
    if args.list: listar()
    elif args.run: correr(args.desde)
    else: verificar()      # por defecto, verificar
