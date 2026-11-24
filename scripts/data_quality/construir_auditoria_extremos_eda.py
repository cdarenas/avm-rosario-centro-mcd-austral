#!/usr/bin/env python3
"""Construye una cola de auditoría de extremos sin corregir ni excluir filas."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def boolean(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype("string").str.lower().isin({"true", "1", "1.0", "si", "sí"})


def construir(input_path: Path, output_path: Path) -> dict:
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, low_memory=False)

    precio = pd.to_numeric(df["precio_ultimo"], errors="coerce")
    superficie = pd.to_numeric(df["superficie_total_m2"], errors="coerce")
    cubierta = pd.to_numeric(df["superficie_cubierta_m2"], errors="coerce")
    precio_m2 = pd.to_numeric(df["precio_m2_observado"], errors="coerce")
    antiguedad = pd.to_numeric(df["antiguedad"], errors="coerce")
    banos = pd.to_numeric(df["banos"], errors="coerce")
    cocheras = pd.to_numeric(df["cocheras"], errors="coerce")
    expensas = pd.to_numeric(df["expensas_valor"], errors="coerce")

    p_price = precio.quantile([0.01, 0.99])
    p_surface = superficie.quantile([0.01, 0.99])
    p_price_m2 = precio_m2.quantile([0.01, 0.99])
    p_expenses = expensas.quantile(0.99)
    text = (
        df["titulo"].fillna("").astype(str)
        + " "
        + df["descripcion_completa"].fillna("").astype(str)
    ).str.lower()

    flags = pd.DataFrame(index=df.index)
    flags["precio_placeholder_hasta_1000"] = precio.le(1_000)
    flags["precio_fuera_p01_p99"] = precio.lt(p_price.loc[0.01]) | precio.gt(p_price.loc[0.99])
    flags["precio_mayor_10x_p99"] = precio.gt(10 * p_price.loc[0.99])
    flags["superficie_faltante"] = superficie.isna()
    flags["superficie_fuera_p01_p99"] = superficie.notna() & (
        superficie.lt(p_surface.loc[0.01]) | superficie.gt(p_surface.loc[0.99])
    )
    flags["superficie_mayor_1000"] = superficie.gt(1_000)
    flags["cubierta_mayor_total"] = cubierta.notna() & superficie.notna() & cubierta.gt(superficie)
    flags["precio_m2_fuera_p01_p99"] = precio_m2.notna() & (
        precio_m2.lt(p_price_m2.loc[0.01]) | precio_m2.gt(p_price_m2.loc[0.99])
    )
    flags["antiguedad_mayor_150"] = antiguedad.gt(150)
    flags["banos_mayor_10"] = banos.gt(10)
    flags["cocheras_mayor_10"] = cocheras.gt(10)
    flags["expensas_mayor_p99"] = expensas.gt(p_expenses)
    flags["cochera_posiblemente_no_incluida"] = text.str.contains(
        r"cochera.{0,45}(?:no (?:est[aá] )?incluida|aparte|adicional)", regex=True
    )
    flags["coordenada_pendiente"] = ~boolean(df["apto_eda_espacial_preliminar"])

    selected = flags.any(axis=1)
    p0 = (
        flags["precio_placeholder_hasta_1000"]
        | flags["precio_mayor_10x_p99"]
        | flags["superficie_mayor_1000"]
        | flags["cubierta_mayor_total"]
        | flags["antiguedad_mayor_150"]
        | flags["banos_mayor_10"]
        | flags["cocheras_mayor_10"]
    )
    p1 = flags[
        ["precio_fuera_p01_p99", "superficie_fuera_p01_p99", "precio_m2_fuera_p01_p99", "expensas_mayor_p99"]
    ].any(axis=1)
    priority = pd.Series("P2", index=df.index)
    priority.loc[p1] = "P1"
    priority.loc[p0] = "P0"

    base_columns = [
        "property_id", "posting_id_ultimo", "url", "direccion_exacta",
        "barrio_oficial_geo", "barrio_geo_estado", "precio_ultimo",
        "precio_moneda", "superficie_total_m2", "superficie_cubierta_m2",
        "precio_m2_observado", "ambientes", "dormitorios", "banos",
        "cocheras", "antiguedad", "expensas_valor",
    ]
    audit = df.loc[selected, base_columns].copy()
    audit.insert(0, "audit_priority", priority.loc[selected])
    audit.insert(1, "audit_flags", flags.loc[selected].apply(
        lambda row: " | ".join(row.index[row].tolist()), axis=1
    ))
    audit["descripcion_extracto"] = df.loc[selected, "descripcion_completa"].fillna("").str.replace(
        r"\s+", " ", regex=True
    ).str.slice(0, 300)
    audit["decision"] = ""
    audit["valor_corregido"] = ""
    audit["evidencia"] = ""
    audit["justificacion"] = ""
    audit["revisado_por"] = ""
    audit["fecha_revision"] = ""
    audit = audit.sort_values(["audit_priority", "precio_ultimo"], ascending=[True, False])
    audit.to_csv(output_path, index=False)

    counts = flags.sum().astype(int).to_dict()
    manifest = {
        "artifact": output_path.name,
        "artifact_sha256": sha256(output_path),
        "input_artifact": input_path.name,
        "input_sha256": sha256(input_path),
        "input_rows": int(len(df)),
        "audit_rows": int(len(audit)),
        "priority_counts": {str(k): int(v) for k, v in audit["audit_priority"].value_counts().sort_index().items()},
        "flag_counts": counts,
        "diagnostic_thresholds": {
            "precio_p01": float(p_price.loc[0.01]),
            "precio_p99": float(p_price.loc[0.99]),
            "superficie_p01": float(p_surface.loc[0.01]),
            "superficie_p99": float(p_surface.loc[0.99]),
            "precio_m2_p01": float(p_price_m2.loc[0.01]),
            "precio_m2_p99": float(p_price_m2.loc[0.99]),
            "expensas_p99": float(p_expenses),
        },
        "automatic_corrections": 0,
        "automatic_exclusions": 0,
        "warning": "Los umbrales priorizan revisión; no constituyen reglas finales de limpieza."
    }
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(construir(args.input, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
