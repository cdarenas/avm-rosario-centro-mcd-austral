#!/usr/bin/env python3
"""Materializa una versión auditada conservando todos los campos originales."""

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


def normalize_scalar(value):
    if pd.isna(value):
        return None
    return str(value)


def construir(input_path: Path, decisions_path: Path, audit_path: Path, output_path: Path) -> dict:
    input_path, decisions_path, audit_path, output_path = [
        Path(path).resolve() for path in (input_path, decisions_path, audit_path, output_path)
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, low_memory=False)
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    audit = pd.read_csv(audit_path, low_memory=False)
    reviewed_no_change_ids: set[str] = set()
    reviewed_artifact = decisions.get("reviewed_no_change_artifact")
    if reviewed_artifact:
        reviewed_path = decisions_path.parent / reviewed_artifact
        reviewed = pd.read_csv(reviewed_path, low_memory=False)
        if reviewed["property_id"].duplicated().any():
            raise ValueError("property_id duplicado en revisiones sin cambio")
        reviewed_no_change_ids = set(reviewed["property_id"])

    if df["property_id"].duplicated().any():
        raise ValueError("property_id debe ser único")
    indexed = df.set_index("property_id", drop=False)
    known_ids = set(indexed.index)
    target_missing_ids = set(decisions["target_unobservable"]["property_ids"])
    modeling_ineligible = decisions.get("modeling_ineligible", [])
    modeling_ineligible_ids = {item["property_id"] for item in modeling_ineligible}
    spatial_validation = decisions.get("spatial_validation", [])
    spatial_validation_ids = {item["property_id"] for item in spatial_validation}
    if unknown := target_missing_ids - known_ids:
        raise ValueError(f"IDs de target no encontrados: {sorted(unknown)}")
    if unknown := modeling_ineligible_ids - known_ids:
        raise ValueError(f"IDs inelegibles para modelado no encontrados: {sorted(unknown)}")
    if unknown := spatial_validation_ids - known_ids:
        raise ValueError(f"IDs de validación espacial no encontrados: {sorted(unknown)}")
    maximum_placeholder = decisions["target_unobservable"].get("maximum_observed_value", 1_000)
    if not indexed.loc[list(target_missing_ids), "precio_ultimo"].le(maximum_placeholder).all():
        raise ValueError(
            f"Un target marcado como placeholder supera USD {maximum_placeholder:,.0f}"
        )

    result = df.copy()
    result["precio_auditado"] = pd.to_numeric(result["precio_ultimo"], errors="coerce")
    result["antiguedad_auditada"] = result["antiguedad"].astype("string")
    for field in (
        "superficie_total_m2", "superficie_cubierta_m2", "banos", "cocheras",
        "expensas_valor",
    ):
        result[f"{field}_auditado"] = pd.to_numeric(result[field], errors="coerce")
    result["apto_eda_target_auditado"] = True
    result["apto_modelado_preliminar"] = True
    result["motivo_no_apto_modelado"] = ""
    result["auditoria_decisiones_aplicadas"] = ""
    result["auditoria_p0_pendiente"] = False
    result["auditoria_p1_revisado"] = False
    result["auditoria_p1_pendiente"] = False
    result["latitud_auditada"] = pd.to_numeric(
        result.get("latitud", pd.Series(pd.NA, index=result.index)), errors="coerce"
    )
    result["longitud_auditada"] = pd.to_numeric(
        result.get("longitud", pd.Series(pd.NA, index=result.index)), errors="coerce"
    )
    result["distrito_auditado"] = result.get(
        "geo_distrito_oficial", pd.Series(pd.NA, index=result.index)
    ).astype("string")
    result["apto_eda_espacial_auditado"] = result.get(
        "barrio_geo_apto_eda_preliminar", pd.Series(False, index=result.index)
    ).fillna(False).astype(bool)
    result["auditoria_espacial_estado"] = "sin_cambio"
    result_index = result.set_index("property_id", drop=False)

    reason = decisions["target_unobservable"]["reason"]
    result_index.loc[list(target_missing_ids), "precio_auditado"] = pd.NA
    result_index.loc[list(target_missing_ids), "apto_eda_target_auditado"] = False
    result_index.loc[list(target_missing_ids), "auditoria_decisiones_aplicadas"] = reason
    result_index.loc[list(target_missing_ids), "apto_modelado_preliminar"] = False
    result_index.loc[list(target_missing_ids), "motivo_no_apto_modelado"] = reason
    for item in modeling_ineligible:
        property_id = item["property_id"]
        result_index.loc[property_id, "apto_modelado_preliminar"] = False
        result_index.loc[property_id, "motivo_no_apto_modelado"] = item["reason"]
        result_index.loc[property_id, "auditoria_decisiones_aplicadas"] = item["reason"]

    outside_center_count = 0
    for item in spatial_validation:
        property_id = item["property_id"]
        result_index.loc[property_id, "latitud_auditada"] = item["latitud"]
        result_index.loc[property_id, "longitud_auditada"] = item["longitud"]
        result_index.loc[property_id, "distrito_auditado"] = item["distrito"]
        result_index.loc[property_id, "auditoria_espacial_estado"] = item["status"]
        in_center = item["distrito"] == "CENTRO"
        result_index.loc[property_id, "apto_eda_espacial_auditado"] = in_center
        prior = result_index.loc[property_id, "auditoria_decisiones_aplicadas"]
        result_index.loc[property_id, "auditoria_decisiones_aplicadas"] = " | ".join(
            value for value in (prior, item["status"]) if value
        )
        if not in_center:
            outside_center_count += 1
            result_index.loc[property_id, "apto_modelado_preliminar"] = False
            result_index.loc[property_id, "motivo_no_apto_modelado"] = (
                "direccion_validada_fuera_distrito_centro"
            )

    applied_log = []
    for correction in decisions["corrections"]:
        property_id = correction["property_id"]
        field = correction["field"]
        if property_id not in result_index.index:
            raise ValueError(f"ID de corrección no encontrado: {property_id}")
        observed = indexed.loc[property_id, field]
        expected = correction["expected_original"]
        if normalize_scalar(observed) != normalize_scalar(expected):
            raise ValueError(
                f"Valor original inesperado para {property_id}/{field}: {observed!r} != {expected!r}"
            )
        audited_field = {
            "precio_ultimo": "precio_auditado",
            "antiguedad": "antiguedad_auditada",
            "superficie_total_m2": "superficie_total_m2_auditado",
            "superficie_cubierta_m2": "superficie_cubierta_m2_auditado",
            "banos": "banos_auditado",
            "cocheras": "cocheras_auditado",
            "expensas_valor": "expensas_valor_auditado",
        }[field]
        result_index.loc[property_id, audited_field] = correction["corrected_value"]
        prior = result_index.loc[property_id, "auditoria_decisiones_aplicadas"]
        result_index.loc[property_id, "auditoria_decisiones_aplicadas"] = " | ".join(
            value for value in (prior, correction["reason"]) if value
        )
        applied_log.append(correction)

    p0_ids = set(audit.loc[audit["audit_priority"].eq("P0"), "property_id"])
    resolved_ids = (
        target_missing_ids | modeling_ineligible_ids
        | {item["property_id"] for item in decisions["corrections"]}
        | spatial_validation_ids
    )
    pending_ids = p0_ids - resolved_ids
    result_index.loc[list(pending_ids), "auditoria_p0_pendiente"] = True

    p1_ids = set(audit.loc[audit["audit_priority"].eq("P1"), "property_id"])
    if unknown_reviewed := reviewed_no_change_ids - p1_ids:
        raise ValueError(f"Revisiones sin cambio que no son P1: {sorted(unknown_reviewed)}")
    reviewed_p1_ids = p1_ids & (resolved_ids | reviewed_no_change_ids)
    pending_p1_ids = p1_ids - reviewed_p1_ids
    result_index.loc[list(reviewed_p1_ids), "auditoria_p1_revisado"] = True
    result_index.loc[list(pending_p1_ids), "auditoria_p1_pendiente"] = True

    result = result_index.reset_index(drop=True)
    price = pd.to_numeric(result["precio_auditado"], errors="coerce")
    surface = pd.to_numeric(result["superficie_total_m2_auditado"], errors="coerce")
    result["precio_m2_auditado"] = price.div(surface).where(price.notna() & surface.gt(0))
    result["auditoria_version"] = decisions["version"]

    compression = {"method": "gzip", "mtime": 0} if output_path.name.endswith(".gz") else None
    result.to_csv(output_path, index=False, compression=compression)
    manifest = {
        "artifact": output_path.name,
        "artifact_sha256": sha256(output_path),
        "input_artifact": input_path.name,
        "input_sha256": sha256(input_path),
        "decisions_artifact": decisions_path.name,
        "decisions_sha256": sha256(decisions_path),
        "audit_artifact": audit_path.name,
        "audit_sha256": sha256(audit_path),
        "rows": int(len(result)),
        "input_columns": int(df.shape[1]),
        "output_columns": int(result.shape[1]),
        "original_columns_modified": False,
        "target_unobservable": int(len(target_missing_ids)),
        "modeling_ineligible": int((~result["apto_modelado_preliminar"]).sum()),
        "field_corrections_applied": int(len(applied_log)),
        "spatial_validations_applied": int(len(spatial_validation)),
        "spatial_validated_outside_center": int(outside_center_count),
        "spatial_eda_eligible": int(result["apto_eda_espacial_auditado"].sum()),
        "p0_pending": int(len(pending_ids)),
        "p1_reviewed": int(len(reviewed_p1_ids)),
        "p1_reviewed_without_change": int(len(reviewed_no_change_ids)),
        "p1_pending": int(len(pending_p1_ids)),
        "applied_corrections": applied_log,
        "warning": "Versión auditada para EDA; no constituye todavía dataset final de modelado."
    }
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(construir(args.input, args.decisions, args.audit, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
