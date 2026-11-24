#!/usr/bin/env python3
"""Genera el perfil tabular inicial del dataset ZonaProp Centro v1.

El análisis es descriptivo: no imputa, recorta, corrige ni excluye observaciones.
Las banderas de calidad se usan para segmentar resultados, no para modificar la
fuente compartida.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


NUMERICAS_RELEVANTES = [
    "precio_ultimo",
    "precio_m2_observado",
    "superficie_total_m2",
    "superficie_cubierta_m2",
    "ambientes",
    "dormitorios",
    "banos",
    "cocheras",
    "antiguedad",
    "expensas_valor",
    "latitud",
    "longitud",
]

CATEGORICAS_RELEVANTES = [
    "precio_moneda",
    "barrio",
    "disposicion",
    "orientacion",
    "id_confianza",
    "geo_source",
    "geo_nivel_calidad",
    "geo_distrito_oficial",
    "alcance_territorial",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _boolean(series: pd.Series) -> pd.Series:
    """Normaliza booleanos conservando faltantes como False para segmentación."""
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype("string").str.lower().isin({"true", "1", "1.0", "si", "sí"})


def perfil_completitud(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in df.columns:
        series = df[column]
        non_empty = series.notna()
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            non_empty &= series.astype("string").str.strip().ne("")
        present = int(non_empty.sum())
        rows.append(
            {
                "columna": column,
                "dtype_inferido": str(series.dtype),
                "n_presentes": present,
                "n_faltantes": int(len(df) - present),
                "pct_faltantes": round(100 * (len(df) - present) / len(df), 2),
                "n_unicos_no_nulos": int(series[non_empty].nunique(dropna=True)),
            }
        )
    return pd.DataFrame(rows).sort_values(["pct_faltantes", "columna"], ascending=[False, True])


def perfil_numerico(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in NUMERICAS_RELEVANTES:
        if column not in df:
            continue
        values = pd.to_numeric(df[column], errors="coerce")
        valid = values.dropna()
        quantiles = valid.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        rows.append(
            {
                "variable": column,
                "n": int(valid.size),
                "faltantes": int(values.isna().sum()),
                "media": valid.mean(),
                "desvio": valid.std(),
                "min": valid.min(),
                "p01": quantiles.get(0.01, np.nan),
                "p05": quantiles.get(0.05, np.nan),
                "p25": quantiles.get(0.25, np.nan),
                "mediana": quantiles.get(0.5, np.nan),
                "p75": quantiles.get(0.75, np.nan),
                "p95": quantiles.get(0.95, np.nan),
                "p99": quantiles.get(0.99, np.nan),
                "max": valid.max(),
                "n_no_positivos": int((valid <= 0).sum()),
            }
        )
    return pd.DataFrame(rows).round(3)


def perfil_categorico(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    frames = []
    for column in CATEGORICAS_RELEVANTES:
        if column not in df:
            continue
        values = df[column].astype("string").fillna("<FALTANTE>").replace("", "<VACIO>")
        counts = values.value_counts(dropna=False).head(top_n)
        frame = counts.rename_axis("valor").reset_index(name="n")
        frame.insert(0, "variable", column)
        frame["pct_total"] = (100 * frame["n"] / len(df)).round(2)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def segmentos_calidad(df: pd.DataFrame) -> pd.DataFrame:
    espacial = _boolean(df["apto_eda_espacial_preliminar"])
    revision = _boolean(df["requiere_revision"])
    target = _boolean(df["apto_eda_target_preliminar"])
    segmentos = {
        "universo_completo": pd.Series(True, index=df.index),
        "target_preliminar_apto": target,
        "espacial_preliminar_apto": espacial,
        "espacial_pendiente": ~espacial,
        "requiere_revision": revision,
        "sin_revision_requerida": ~revision,
    }
    rows = []
    for name, mask in segmentos.items():
        prices = pd.to_numeric(df.loc[mask, "precio_ultimo"], errors="coerce")
        sqm = pd.to_numeric(df.loc[mask, "precio_m2_observado"], errors="coerce")
        rows.append(
            {
                "segmento": name,
                "n": int(mask.sum()),
                "pct_total": round(100 * mask.mean(), 2),
                "precio_mediana_usd": prices.median(),
                "precio_m2_mediana_usd": sqm.median(),
                "precio_n_validos": int(prices.notna().sum()),
                "precio_m2_n_validos": int(sqm.notna().sum()),
            }
        )
    return pd.DataFrame(rows).round(2)


def alertas(df: pd.DataFrame) -> pd.DataFrame:
    numeric = {c: pd.to_numeric(df[c], errors="coerce") for c in NUMERICAS_RELEVANTES if c in df}
    descriptions = df["descripcion_completa"].astype("string").fillna("").str.lower()
    rules = {
        "superficie_total_no_positiva": numeric["superficie_total_m2"] <= 0,
        "superficie_cubierta_mayor_total": numeric["superficie_cubierta_m2"] > numeric["superficie_total_m2"],
        "precio_m2_no_positivo": numeric["precio_m2_observado"] <= 0,
        "coordenadas_faltantes": numeric["latitud"].isna() | numeric["longitud"].isna(),
        "coordenada_compartida_sospechosa": _boolean(df["geo_coordenada_compartida_sospechosa"]),
        "requiere_revision": _boolean(df["requiere_revision"]),
        "espacial_preliminar_pendiente": ~_boolean(df["apto_eda_espacial_preliminar"]),
        "texto_indica_cochera_no_incluida": descriptions.str.contains(
            r"cochera.{0,45}(?:no (?:est[aá] )?incluida|aparte|adicional)", regex=True
        ),
    }
    return pd.DataFrame(
        {
            "alerta": name,
            "n": int(mask.fillna(False).sum()),
            "pct_total": round(100 * mask.fillna(False).mean(), 2),
            "accion": "auditar; no corregir ni excluir automáticamente",
        }
        for name, mask in rules.items()
    ).sort_values("n", ascending=False)


def construir_reporte(input_path: Path, output_dir: Path) -> dict:
    input_path = input_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, low_memory=False)

    if df.empty:
        raise ValueError("El dataset no contiene filas")
    if "property_id" not in df:
        raise ValueError("Falta la clave property_id")

    tables = {
        "completitud_columnas.csv": perfil_completitud(df),
        "resumen_numerico.csv": perfil_numerico(df),
        "frecuencias_categoricas.csv": perfil_categorico(df),
        "segmentos_calidad.csv": segmentos_calidad(df),
        "alertas_calidad.csv": alertas(df),
    }
    for name, table in tables.items():
        table.to_csv(output_dir / name, index=False)

    spatial_ok = _boolean(df["apto_eda_espacial_preliminar"])
    manifest = {
        "analysis": "eda_inicial_zonaprop_centro_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_artifact": input_path.name,
        "input_sha256": sha256(input_path),
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "unique_property_id": int(df["property_id"].nunique()),
        "duplicate_property_id": int(df["property_id"].duplicated().sum()),
        "spatial_preliminary_ok": int(spatial_ok.sum()),
        "spatial_pending": int((~spatial_ok).sum()),
        "mutates_input": False,
        "imputes_missing": False,
        "removes_outliers": False,
        "tables": list(tables),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    numeric = tables["resumen_numerico.csv"].set_index("variable")
    alerts_table = tables["alertas_calidad.csv"].set_index("alerta")
    missing = tables["completitud_columnas.csv"].head(10)
    missing_lines = "\n".join(
        f"- `{row.columna}`: {row.pct_faltantes:.2f}% ({row.n_faltantes} filas)"
        for row in missing.itertuples()
    )
    report = f"""# Perfil EDA inicial — ZonaProp Centro v1

Este perfil describe el artefacto sin modificarlo. No se imputaron faltantes, no
se eliminaron outliers y ninguna alerta se convirtió en exclusión automática.

## Alcance

- Observaciones: **{len(df):,}**.
- Columnas conservadas: **{df.shape[1]}**.
- `property_id` únicos: **{df['property_id'].nunique():,}**.
- Aptas para análisis espacial preliminar: **{int(spatial_ok.sum()):,}**.
- Pendientes de validación espacial: **{int((~spatial_ok).sum()):,}**.

## Primeras señales

- Precio mediano publicado: **USD {numeric.loc['precio_ultimo', 'mediana']:,.0f}**.
- Precio mediano observado por m²: **USD {numeric.loc['precio_m2_observado', 'mediana']:,.2f}**.
- Superficie total mediana: **{numeric.loc['superficie_total_m2', 'mediana']:,.0f} m²**.
- Requieren revisión según las banderas existentes: **{int(alerts_table.loc['requiere_revision', 'n']):,}**.
- Tienen coordenada compartida sospechosa: **{int(alerts_table.loc['coordenada_compartida_sospechosa', 'n']):,}**.
- El texto sugiere que la cochera podría no estar incluida en el precio: **{int(alerts_table.loc['texto_indica_cochera_no_incluida', 'n']):,}**. Esta regla es sólo una búsqueda textual inicial.
- Presentan superficie cubierta mayor que la total: **{int(alerts_table.loc['superficie_cubierta_mayor_total', 'n']):,}**.

Los máximos de precio, precio por m², superficie, antigüedad, baños, cocheras y
expensas son extremadamente altos respecto de sus percentiles 99. Deben
investigarse como casos individuales antes de definir reglas de tratamiento.

## Columnas con mayor proporción de faltantes

{missing_lines}

## Uso correcto

Las tablas permiten priorizar auditorías y diseñar visualizaciones. Las
comparaciones territoriales deben usar sólo `apto_eda_espacial_preliminar=True`;
los 816 casos pendientes permanecen en el dataset general y deben informarse por
separado. Este perfil no es todavía una muestra de entrenamiento.
"""
    (output_dir / "README.md").write_text(report, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(construir_reporte(args.input, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
