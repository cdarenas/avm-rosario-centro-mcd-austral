#!/usr/bin/env python3
"""Construye la muestra analítica EDA v4 desde la versión auditada completa."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def construir(input_path: Path, output_path: Path, exclusions_path: Path, flow_path: Path) -> dict:
    input_path, output_path, exclusions_path, flow_path = [
        Path(path).resolve() for path in (input_path, output_path, exclusions_path, flow_path)
    ]
    for path in (output_path, exclusions_path, flow_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    source = pd.read_csv(input_path, low_memory=False)
    if source["property_id"].duplicated().any():
        raise ValueError("property_id debe ser único")
    if source["auditoria_p0_pendiente"].fillna(False).any():
        raise ValueError("No se puede construir v4 con casos P0 pendientes")
    if source["auditoria_p1_pendiente"].fillna(False).any():
        raise ValueError("No se puede construir v4 con casos P1 pendientes")

    target_ok = source["apto_eda_target_auditado"].fillna(False).astype(bool)
    comparable = source["apto_modelado_preliminar"].fillna(False).astype(bool)
    included = target_ok & comparable

    exclusions = source.loc[~included, [
        "property_id", "posting_id_ultimo", "url", "direccion_exacta",
        "precio_ultimo", "precio_auditado", "distrito_auditado",
        "apto_eda_target_auditado", "apto_modelado_preliminar",
        "motivo_no_apto_modelado", "auditoria_decisiones_aplicadas",
    ]].copy()
    exclusions["motivo_exclusion_eda_v4"] = exclusions["motivo_no_apto_modelado"].where(
        exclusions["motivo_no_apto_modelado"].astype("string").str.len().fillna(0).gt(0),
        "target_no_observable",
    )

    result = source.loc[included].copy()
    result["incluido_eda_v4"] = True
    result["motivo_exclusion_eda_v4"] = ""
    result["apto_eda_espacial_v4"] = (
        result["apto_eda_espacial_auditado"].fillna(False).astype(bool)
        & result["distrito_auditado"].eq("CENTRO")
        & result["latitud_auditada"].notna()
        & result["longitud_auditada"].notna()
    )
    consolidated = {
        "eda_precio_usd": "precio_auditado",
        "eda_superficie_total_m2": "superficie_total_m2_auditado",
        "eda_superficie_cubierta_m2": "superficie_cubierta_m2_auditado",
        "eda_banos": "banos_auditado",
        "eda_cocheras": "cocheras_auditado",
        "eda_expensas": "expensas_valor_auditado",
        "eda_latitud": "latitud_auditada",
        "eda_longitud": "longitud_auditada",
        "eda_distrito": "distrito_auditado",
        "eda_precio_m2": "precio_m2_auditado",
    }
    for output_column, audited_column in consolidated.items():
        result[output_column] = result[audited_column]
    result["eda_version"] = "4.0"

    flow = pd.DataFrame([
        {
            "orden": 1,
            "etapa": "universo_auditado_v3",
            "observaciones": int(len(source)),
            "excluidas_en_etapa": 0,
        },
        {
            "orden": 2,
            "etapa": "target_observable",
            "observaciones": int(target_ok.sum()),
            "excluidas_en_etapa": int((~target_ok).sum()),
        },
        {
            "orden": 3,
            "etapa": "unidad_comparable_distrito_centro",
            "observaciones": int(included.sum()),
            "excluidas_en_etapa": int((target_ok & ~comparable).sum()),
        },
        {
            "orden": 4,
            "etapa": "subconjunto_espacial_apto",
            "observaciones": int(result["apto_eda_espacial_v4"].sum()),
            "excluidas_en_etapa": int((~result["apto_eda_espacial_v4"]).sum()),
        },
    ])

    compression = {"method": "gzip", "mtime": 0}
    result.to_csv(output_path, index=False, compression=compression)
    exclusions.to_csv(exclusions_path, index=False)
    flow.to_csv(flow_path, index=False)

    manifest = {
        "artifact": output_path.name,
        "artifact_sha256": sha256(output_path),
        "stage": "processed_eda_centro_v4_analitica",
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_artifact": input_path.name,
        "input_sha256": sha256(input_path),
        "input_rows": int(len(source)),
        "output_rows": int(len(result)),
        "input_columns": int(source.shape[1]),
        "output_columns": int(result.shape[1]),
        "source_columns_removed": False,
        "target_observable": int(target_ok.sum()),
        "excluded_target_unobservable": int((~target_ok).sum()),
        "excluded_non_comparable_or_outside_scope": int((target_ok & ~comparable).sum()),
        "spatial_eda_eligible": int(result["apto_eda_espacial_v4"].sum()),
        "spatial_eda_not_eligible": int((~result["apto_eda_espacial_v4"]).sum()),
        "exclusions_artifact": exclusions_path.name,
        "exclusions_sha256": sha256(exclusions_path),
        "flow_artifact": flow_path.name,
        "flow_sha256": sha256(flow_path),
        "filters": ["apto_eda_target_auditado", "apto_modelado_preliminar"],
        "imputation_applied": False,
        "winsorization_applied": False,
        "warning": "Muestra apta para EDA; todavía no define folds ni dataset final de modelado.",
    }
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("exclusions", type=Path)
    parser.add_argument("flow", type=Path)
    args = parser.parse_args()
    print(json.dumps(
        construir(args.input, args.output, args.exclusions, args.flow),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
