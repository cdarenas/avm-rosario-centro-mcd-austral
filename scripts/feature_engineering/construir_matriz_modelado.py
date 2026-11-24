#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Feature engineering (v6 → matriz de modelado).
#
# Produce una MATRIZ DE MODELADO MAGRA: target + predictores candidatos + claves de
# split + variables espaciales. NO arrastra columnas de auditoría/trazabilidad: la
# trazabilidad la provee el linaje del pipeline (v1→v6 + manifiestos); cualquier valor
# se rastrea con un join por `property_id` a v6.
#
# Features creadas (determinísticas y por fila → sin fuga; imputación/encoding van por fold):
#   · texto: regeneración de feat_* desde `descripcion_limpia` (saneada)
#   · ratios: cubierta/total, superficie/ambiente, baños/ambiente, dormitorios/ambiente
#   · indicadores de "informado": tiene_cochera, expensas_informadas
#   · microlocalización: distancia al centro (Monumento a la Bandera) y al río Paraná (aprox.)
#
# Predictores organizados por escenarios incrementales S1–S4 (Gutiérrez): ver docs/matriz_modelado.md
#
# Entrada : data/processed/zonaprop_v2_eda_centro_v6.csv.gz
# Salida  : data/processed/zonaprop_v2_matriz_modelado_centro.csv.gz  (+ manifiesto)
#           docs/matriz_modelado.md
#
# Uso:  python3 scripts/feature_engineering/construir_matriz_modelado.py
# ─────────────────────────────────────────────────────────────────────────────
import sys, hashlib, json, datetime, gzip
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
V6 = ROOT / "data" / "processed" / "zonaprop_v2_eda_centro_v6.csv.gz"
MATRIZ = ROOT / "data" / "processed" / "zonaprop_v2_matriz_modelado_centro.csv.gz"
DOC = ROOT / "docs" / "matriz_modelado.md"

sys.path.insert(0, str(ROOT / "scripts" / "scraping" / "zonaprop_v2"))
from features_texto import extraer_features  # regenerar feat_* desde texto limpio

# Punto de referencia del centro: Monumento a la Bandera (Rosario)
CENTRO = (-32.9477, -60.6304)
# Segmento aproximado de la costa del Paraná frente al Distrito Centro (N → S)
RIO_N, RIO_S = (-32.9200, -60.6350), (-32.9750, -60.6150)

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _content_sha256(path):
    raw = open(path, "rb").read()
    data = gzip.decompress(raw) if str(path).endswith(".gz") else raw
    return hashlib.sha256(data).hexdigest()

def escribir_manifiesto(salida, entrada, stage, in_shape, out_shape, extra=None):
    man = {"artifact": salida.name, "artifact_sha256": _sha256(salida),
           "content_sha256": _content_sha256(salida), "stage": stage,
           "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "input_artifact": entrada.name, "input_sha256": _sha256(entrada),
           "input_content_sha256": _content_sha256(entrada),
           "input_rows": int(in_shape[0]), "output_rows": int(out_shape[0]),
           "input_columns": int(in_shape[1]), "output_columns": int(out_shape[1])}
    if extra: man.update(extra)
    (salida.parent / (salida.name + ".manifest.json")).write_text(
        json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")

def _haversine(lat, lon, lat0, lon0):
    R = 6371.0
    lat, lon, lat0, lon0 = map(np.radians, [lat, lon, lat0, lon0])
    d = np.sin((lat0-lat)/2)**2 + np.cos(lat)*np.cos(lat0)*np.sin((lon0-lon)/2)**2
    return 2 * R * np.arcsin(np.sqrt(d))

def _dist_a_segmento(lat, lon, a, b):
    """Distancia (km) de cada punto al segmento a–b, en proyección local plana (suficiente a escala barrial)."""
    kx = 111.320 * np.cos(np.radians(lat.mean()))  # km por grado de longitud
    ky = 110.574                                    # km por grado de latitud
    px, py = (lon - a[1]) * kx, (lat - a[0]) * ky
    bx, by = (b[1] - a[1]) * kx, (b[0] - a[0]) * ky
    t = np.clip((px*bx + py*by) / (bx*bx + by*by), 0, 1)
    return np.hypot(px - t*bx, py - t*by)

def main():
    df = pd.read_csv(V6)
    in_shape = df.shape
    fe = {}  # log

    # ── 1. Texto: regenerar feat_* desde descripcion_limpia ──────────────────
    feats_regen = df["descripcion_limpia"].fillna("").map(extraer_features).apply(pd.Series)
    if "feat_litoral_gas" in feats_regen.columns:
        feats_regen = feats_regen.rename(columns={"feat_litoral_gas": "feat_gas_natural"})
    feat_cols = list(feats_regen.columns)
    # delta vs. los feat_ existentes (validación del efecto del saneo)
    comunes = [c for c in feat_cols if c in df.columns]
    fe["feat_celdas_cambiadas"] = int(sum((df[c].fillna(0).astype(int) != feats_regen[c].astype(int)).sum() for c in comunes))
    for c in feat_cols:
        df[c] = feats_regen[c].astype(int)

    # ── 2. Ratios (sin usar el precio → no circulares) ───────────────────────
    st = pd.to_numeric(df["eda_superficie_total_m2"], errors="coerce")
    sc = pd.to_numeric(df["eda_superficie_cubierta_m2"], errors="coerce")
    amb = pd.to_numeric(df["eda_ambientes"], errors="coerce")
    df["fe_ratio_cubierta_total"] = (sc / st).where(lambda x: x <= 1.05)   # >1 es error
    df["fe_sup_por_ambiente"] = st / amb.replace(0, np.nan)
    df["fe_banos_por_ambiente"] = pd.to_numeric(df["eda_banos"], errors="coerce") / amb.replace(0, np.nan)
    df["fe_dormitorios_por_ambiente"] = pd.to_numeric(df["eda_dormitorios"], errors="coerce") / amb.replace(0, np.nan)

    # ── 3. Indicadores de "informado" (ausencia estructural, sin imputar) ────
    df["fe_tiene_cochera"] = (pd.to_numeric(df["eda_cocheras"], errors="coerce").fillna(0) > 0).astype(int)
    df["fe_expensas_informadas"] = df["eda_expensas"].notna().astype(int)

    # ── 4. Microlocalización (determinística desde coordenadas) ──────────────
    lat = pd.to_numeric(df["eda_latitud"], errors="coerce")
    lon = pd.to_numeric(df["eda_longitud"], errors="coerce")
    df["fe_dist_centro_km"] = _haversine(lat, lon, *CENTRO).round(3)
    df["fe_dist_rio_km"] = _dist_a_segmento(lat, lon, RIO_N, RIO_S).round(3)   # aprox. (refinar con geometría)

    # S3 externas (OSM) — solo si los POI fueron descargados (scripts/feature_engineering/descargar_pois.py)
    OSM = ROOT / "data" / "external" / "osm"
    lat0 = float(np.nanmean(lat)); _kx = 111.320 * np.cos(np.radians(lat0)); _ky = 110.574
    _xy = lambda la, lo: (np.asarray(lo, float) * _kx, np.asarray(la, float) * _ky)
    px, py = _xy(lat.values, lon.values)
    s3_ext = []
    if (OSM / "espacios_verdes.csv").exists():
        g = pd.read_csv(OSM / "espacios_verdes.csv"); gx, gy = _xy(g["lat"], g["lon"])
        df["fe_dist_espacio_verde_km"] = np.array([np.min(np.hypot(gx - x, gy - y)) for x, y in zip(px, py)]).round(3)
        s3_ext.append("fe_dist_espacio_verde_km")
    if (OSM / "comercios.csv").exists():
        c = pd.read_csv(OSM / "comercios.csv"); cx, cy = _xy(c["lat"], c["lon"])
        df["fe_dens_comercios_300m"] = np.array([int(np.sum(np.hypot(cx - x, cy - y) <= 0.3)) for x, y in zip(px, py)])
        s3_ext.append("fe_dens_comercios_300m")
    fe["s3_externas"] = s3_ext
    if s3_ext:
        chk = df[["fe_dist_centro_km", "fe_dist_rio_km"] + s3_ext].corr().loc[s3_ext, ["fe_dist_centro_km", "fe_dist_rio_km"]]
        print("Correlación de las S3 externas con las base (redundancia):\n" + chk.round(2).to_string())
    else:
        print("S3 externas: sin POI descargado (correr descargar_pois.py). Se omiten por ahora.")

    # ── 5. Ensamblar la matriz magra por rol / escenario ─────────────────────
    target = ["eda_precio_usd", "eda_precio_m2"]
    claves = ["property_id", "building_cluster_id"]
    auditoria_seg = ["geo_nivel_calidad"]                       # segmentación, NO predictor
    # Escenarios incrementales (protocolo_experimental.md): S2 = S1+…, S3 = S2+…, S4 = S3+…
    s1 = ["eda_superficie_total_m2", "eda_superficie_cubierta_m2", "eda_ambientes",
          "eda_dormitorios", "eda_banos", "eda_cocheras", "eda_toilette",
          "eda_antiguedad_anos", "eda_antiguedad_estado", "eda_disposicion", "eda_orientacion",
          "eda_tipo_operacion", "eda_expensas",
          "fe_ratio_cubierta_total", "fe_sup_por_ambiente", "fe_banos_por_ambiente",
          "fe_dormitorios_por_ambiente", "fe_tiene_cochera", "fe_expensas_informadas"]
    s2 = ["barrio_oficial_geo", "eda_latitud", "eda_longitud"]
    s3 = ["fe_dist_centro_km", "fe_dist_rio_km"] + s3_ext
    s4 = feat_cols
    orden = target + claves + auditoria_seg + s1 + s2 + s3 + s4
    matriz = df[orden].copy()
    matriz["fe_version"] = 1
    out_shape = matriz.shape
    matriz.to_csv(MATRIZ, index=False, compression={"method": "gzip", "mtime": 0})

    escribir_manifiesto(MATRIZ, V6, "processed_matriz_modelado_centro", in_shape, out_shape,
        extra={"features_creadas": ["feat_* (regeneradas desde texto limpio)",
                                    "fe_ratio_cubierta_total", "fe_sup_por_ambiente",
                                    "fe_banos_por_ambiente", "fe_dormitorios_por_ambiente",
                                    "fe_tiene_cochera", "fe_expensas_informadas",
                                    "fe_dist_centro_km", "fe_dist_rio_km"],
               "columnas_trazabilidad_descartadas": int(in_shape[1] - out_shape[1] + 9),
               "nota": "Matriz magra: trazabilidad via linaje del pipeline (join por property_id a v6).",
               "imputation_applied": False, "encoding_applied": False, "winsorization_applied": False,
               "warning": "Predictores CANDIDATOS. La seleccion final se hace por fold (S1-S4)."})

    # ── Doc de la matriz ─────────────────────────────────────────────────────
    def bloque(titulo, cols, nota=""):
        L = [f"\n### {titulo}\n"]
        if nota: L.append(nota + "\n")
        L.append("| variable | tipo | completitud |"); L.append("|---|---|---:|")
        for c in cols:
            L.append(f"| `{c}` | {matriz[c].dtype} | {matriz[c].notna().mean()*100:.0f}% |")
        return L
    D = [f"# Matriz de modelado — Distrito Centro\n",
         f"*{out_shape[0]:,} filas · {out_shape[1]} columnas · deriva de `{V6.name}` (ver linaje en su manifiesto)*\n",
         "Dataset **magro** que consume el modelo: target + predictores candidatos + claves + espacial. "
         "La trazabilidad la provee el pipeline (v1→v6 + manifiestos); las columnas de auditoría **no** se "
         "arrastran. La **selección final** de predictores se hace por *fold* en el modelado (no a priori), "
         "para evitar fuga de información (ESL §7.10.2; Kuhn & Johnson).\n"]
    D += bloque("Target", target)
    D += bloque("Claves (split *group-aware*, no predictores)", claves)
    D += bloque("Auditoría / segmentación (no predictor)", auditoria_seg)
    D.append("\n> **Escenarios incrementales** (`docs/protocolo_experimental.md`): cada escenario **suma** "
             "sus columnas a las del anterior — S2 = S1+S2, S3 = S1+S2+S3, S4 = todo —, para medir el "
             "**valor incremental** de cada grupo de información (Gutiérrez, RQ2).\n")
    D += bloque("S1 — Características estructurales", s1,
                "Atributos físicos del inmueble (incluye disposición y orientación) y ratios/indicadores derivados.")
    D += bloque("S2 — Localización (S1 + …)", s2,
                "Barrio oficial y coordenadas (representación territorial no supervisada).")
    D += bloque("S3 — Microlocalización y entorno (S2 + …)", s3,
                "Distancias a puntos de interés (centro, río). **A ampliar** con espacios verdes, transporte y equipamientos (fuentes externas).")
    D += bloque("S4 — Información enriquecida (S3 + …)", s4,
                "Atributos binarios derivados del texto (amenities, etc.).")
    DOC.write_text("\n".join(D), encoding="utf-8")

    print(f"Matriz de modelado: {MATRIZ.relative_to(ROOT)}  ({out_shape[0]:,} filas · {out_shape[1]} columnas)")
    print(f"  (v6 tenía {in_shape[1]} columnas → matriz magra con {out_shape[1]})")
    print(f"  feat_ regeneradas desde texto limpio · celdas cambiadas vs. original: {fe['feat_celdas_cambiadas']:,}")
    print(f"doc: {DOC.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
