#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Definición de la muestra analítica por ventana temporal (comparabilidad de precios)
#
#   Entrada : data/processed/zonaprop_v2_eda_centro_v4.csv.gz
#             fecha de publicación (datePosted) desde la base del scraper
#   Salida  : data/interim/publicacion_fechas_por_property.csv.gz   (repro sin la base)
#             data/processed/zonaprop_v2_eda_centro_v5.csv.gz        (muestra ≤ 6 meses)
#             reports/tables/muestra_temporal/deriva_precio_por_antiguedad.csv (evidencia)
#
# Motivación: un aviso viejo refleja el mercado de su época, no el actual. Se comprobó
# que en unidades comparables (mismo barrio/ambientes/superficie) el precio/m² deriva
# ~+20% a partir de los 6 meses (listings "rancios" sobrevaluados). Para garantizar la
# comparabilidad temporal del target se restringe la muestra a avisos de ≤ 6 meses.
#
# Uso:  python3 scripts/preprocessing/definir_muestra_temporal.py
#       (si el intermedio de fechas ya existe, no se necesita la base del scraper)
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path
import os, sqlite3
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
V4   = ROOT / "data" / "processed" / "zonaprop_v2_eda_centro_v4.csv.gz"
V5   = ROOT / "data" / "processed" / "zonaprop_v2_eda_centro_v5.csv.gz"
INTERIM = ROOT / "data" / "interim" / "publicacion_fechas_por_property.csv.gz"
EVID = ROOT / "reports" / "tables" / "muestra_temporal" / "deriva_precio_por_antiguedad.csv"
# Base del scraper (fuera del repo; sólo se usa si falta el intermedio de fechas).
DB = Path(os.environ.get("SCRAPER_DB",
     "/Users/u633076/Desktop/TrabajoFinal/scraper_v2/salida/zonaprop_v2.db"))
UMBRAL_MESES = 6
DIAS = int(round(UMBRAL_MESES * 30.44))

import hashlib, json, datetime, gzip
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _content_sha256(path):
    """Hash del CONTENIDO (CSV descomprimido): reproducible sin importar el wrapper gzip ni el escritor."""
    raw = open(path, "rb").read()
    data = gzip.decompress(raw) if str(path).endswith(".gz") else raw
    return hashlib.sha256(data).hexdigest()

def escribir_manifiesto(salida, entrada, stage, in_shape, out_shape, extra=None):
    """Manifiesto de linaje: hash de contenido in/out, filas/cols, decisiones."""
    man = {
        "artifact": salida.name, "artifact_sha256": _sha256(salida),
        "content_sha256": _content_sha256(salida),
        "stage": stage,
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "input_artifact": entrada.name, "input_sha256": _sha256(entrada),
        "input_content_sha256": _content_sha256(entrada),
        "input_rows": int(in_shape[0]), "output_rows": int(out_shape[0]),
        "input_columns": int(in_shape[1]), "output_columns": int(out_shape[1]),
    }
    if extra:
        man.update(extra)
    (salida.parent / (salida.name + ".manifest.json")).write_text(
        json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    return man["artifact_sha256"]

def fechas_publicacion() -> pd.DataFrame:
    """property_id -> fecha_publicacion (datePosted más antigua observada)."""
    if INTERIM.exists():
        print(f"· fechas de publicación: usando intermedio {INTERIM.relative_to(ROOT)}")
        return pd.read_csv(INTERIM, parse_dates=["fecha_publicacion"])
    if not DB.exists():
        raise SystemExit(f"No existe el intermedio ni la base del scraper ({DB}). "
                         "Definí SCRAPER_DB o generá el intermedio.")
    print(f"· fechas de publicación: extrayendo de la base {DB}")
    con = sqlite3.connect(DB)
    cap = pd.read_sql("SELECT property_id, fecha_publicacion FROM capturas", con)
    con.close()
    cap["fecha_publicacion"] = pd.to_datetime(cap["fecha_publicacion"], errors="coerce", utc=True)
    fp = (cap.dropna(subset=["fecha_publicacion"])
             .groupby("property_id")["fecha_publicacion"].min().reset_index())
    INTERIM.parent.mkdir(parents=True, exist_ok=True)
    fp.to_csv(INTERIM, index=False)
    print(f"  intermedio guardado: {INTERIM.relative_to(ROOT)} ({len(fp):,} property_id)")
    return fp

def main():
    df = pd.read_csv(V4)
    v4_shape = df.shape
    fp = fechas_publicacion()
    fp["fecha_publicacion"] = pd.to_datetime(fp["fecha_publicacion"], utc=True)
    df = df.merge(fp, on="property_id", how="left")

    # Antigüedad del aviso = captura (first_seen) − fecha de publicación (datePosted)
    fs = pd.to_datetime(df["first_seen"], errors="coerce", utc=True)
    df["antiguedad_aviso_dias"] = (fs - df["fecha_publicacion"]).dt.days

    cob = df["fecha_publicacion"].notna().mean() * 100
    print(f"\nCobertura de fecha_publicacion en v4: {cob:.1f}%  ({df['fecha_publicacion'].notna().sum():,}/{len(df):,})")

    # ── Evidencia: deriva del precio/m² por antigüedad (justifica el corte) ──────
    b = pd.cut(df["antiguedad_aviso_dias"]/30.44, [0,3,6,12,24,1e4],
               labels=["0-3m","3-6m","6-12m","12-24m",">24m"])
    ev = (df.assign(_b=b).groupby("_b", observed=True)
            .agg(n=("eda_precio_m2","size"), pm2_mediana=("eda_precio_m2","median"))
            .assign(vs_0_3m=lambda d: (d.pm2_mediana/d.pm2_mediana.iloc[0]*100).round(0)))
    ev["pm2_mediana"] = ev["pm2_mediana"].round(0)
    EVID.parent.mkdir(parents=True, exist_ok=True)
    ev.to_csv(EVID)
    print("\nDeriva del precio/m² por antigüedad del aviso (evidencia del corte):")
    print(ev.to_string())

    # ── Filtro de muestra: ≤ 6 meses (excluye avisos sin fecha) ──────────────────
    keep = df["antiguedad_aviso_dias"].le(DIAS)
    v5 = df[keep].copy()
    print(f"\nCorte ≤ {UMBRAL_MESES} meses ({DIAS} días):")
    print(f"  v4:                 {len(df):,}")
    print(f"  sin fecha (excl.):  {int(df['antiguedad_aviso_dias'].isna().sum()):,}")
    print(f"  > {UMBRAL_MESES} meses (excl.):  {int((~keep & df['antiguedad_aviso_dias'].notna()).sum()):,}")
    print(f"  v5 (≤ {UMBRAL_MESES} meses):     {len(v5):,}  ({len(v5)/len(df)*100:.0f}%)")

    v5.to_csv(V5, index=False, compression={"method": "gzip", "mtime": 0})
    escribir_manifiesto(
        V5, V4, "processed_muestra_temporal_centro_v5", v4_shape, v5.shape,
        extra={"criterio": f"antiguedad_aviso_dias <= {DIAS} dias (~{UMBRAL_MESES} meses)",
               "filas_excluidas_sin_fecha": int(df["antiguedad_aviso_dias"].isna().sum()),
               "filas_excluidas_mayor_umbral": int((~keep & df["antiguedad_aviso_dias"].notna()).sum()),
               "columnas_agregadas": ["fecha_publicacion", "antiguedad_aviso_dias"],
               "fuente_fecha": "data/interim/publicacion_fechas_por_property.csv.gz",
               "imputation_applied": False, "winsorization_applied": False,
               "warning": "Muestra acotada temporalmente (<=6 meses) para comparabilidad de precios."})
    print(f"\nMuestra analítica escrita: {V5.relative_to(ROOT)}  "
          f"({len(v5):,} filas · {v5.shape[1]} columnas)")

if __name__ == "__main__":
    main()
