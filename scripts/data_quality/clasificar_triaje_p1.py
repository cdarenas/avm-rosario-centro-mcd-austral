#!/usr/bin/env python3
"""Clasifica casos P1 para revisión; no corrige ni excluye observaciones."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


SINGLE_COHERENT_FLAGS = {
    "precio_fuera_p01_p99",
    "superficie_fuera_p01_p99",
    "expensas_mayor_p99",
}


def classify(row: pd.Series) -> tuple[str, str]:
    if bool(row["auditoria_p1_revisado"]):
        return "revisado_con_decision", "Decisión ya registrada en la versión auditada"

    flags = set(str(row["audit_flags"]).split(" | "))
    if len(flags) == 1 and next(iter(flags)) in SINGLE_COHERENT_FLAGS:
        return (
            "candidato_extremo_legitimo",
            "Alerta percentilar aislada; revisar aviso y conservar si precio, superficie y tipo son coherentes",
        )
    if "superficie_faltante" in flags:
        return (
            "revisar_superficie_faltante",
            "Buscar superficie en descripción; si no existe, conservar faltante y definir elegibilidad para modelado",
        )
    if "precio_m2_fuera_p01_p99" in flags:
        return (
            "revisar_precio_m2",
            "Contrastar precio y superficie con descripción, tipología y barrio; no winsorizar automáticamente",
        )
    if "coordenada_pendiente" in flags:
        return (
            "revisar_componente_espacial",
            "Resolver dirección/coordenada antes de usar variables territoriales",
        )
    if "cochera_posiblemente_no_incluida" in flags:
        return (
            "revisar_cochera",
            "Determinar si la cochera está incluida en la unidad y en el precio",
        )
    return (
        "revisar_extremos_combinados",
        "Existen alertas simultáneas; revisar coherencia multivariable y fuente",
    )


def no_change_candidates(p1: pd.DataFrame) -> pd.DataFrame:
    """Selecciona extremos aislados coherentes; la excepción se mantiene explícita."""
    flag = p1["audit_flags"]
    surface = pd.to_numeric(p1["superficie_total_m2_auditado"], errors="coerce")
    rooms = pd.to_numeric(p1["ambientes"], errors="coerce")
    bedrooms = pd.to_numeric(p1["dormitorios"], errors="coerce")
    expenses = pd.to_numeric(p1["expensas_valor"], errors="coerce")
    price = pd.to_numeric(p1["precio_auditado"], errors="coerce")
    price_m2 = pd.to_numeric(p1["precio_m2_auditado"], errors="coerce")
    eligible = p1["apto_modelado_preliminar"].fillna(False).astype(bool)
    coherent_small = flag.eq("superficie_fuera_p01_p99") & surface.lt(24) & rooms.le(2) & bedrooms.fillna(0).le(1)
    coherent_large = flag.eq("superficie_fuera_p01_p99") & surface.gt(266) & rooms.ge(3) & bedrooms.ge(2)
    coherent_price = flag.eq("precio_fuera_p01_p99")
    coherent_expenses = flag.eq("expensas_mayor_p99") & expenses.le(1_000_000)
    coherent_low_price_m2 = (
        flag.eq("precio_m2_fuera_p01_p99")
        & price_m2.between(300, 551.365671641791, inclusive="left")
        & price.ge(25_000)
    )
    coherent_high_price_m2 = (
        flag.isin([
            "precio_m2_fuera_p01_p99",
            "precio_fuera_p01_p99 | precio_m2_fuera_p01_p99",
        ])
        & price_m2.between(3571.4285714285716, 5_000, inclusive="both")
        & surface.div(bedrooms.where(bedrooms.gt(0), 1)).ge(25)
    )
    coherent_joint_extremes = (
        flag.isin([
            "precio_fuera_p01_p99 | superficie_fuera_p01_p99",
            "precio_fuera_p01_p99 | superficie_fuera_p01_p99 | expensas_mayor_p99",
            "superficie_fuera_p01_p99 | expensas_mayor_p99",
            "superficie_fuera_p01_p99 | precio_m2_fuera_p01_p99",
        ])
        & price_m2.between(300, 3571.4285714285716, inclusive="both")
        & expenses.fillna(0).le(1_350_000)
    )
    coherent_joint_high_price_m2 = (
        flag.eq("precio_fuera_p01_p99 | superficie_fuera_p01_p99 | precio_m2_fuera_p01_p99")
        & price_m2.between(3571.4285714285716, 5_000, inclusive="both")
        & surface.div(bedrooms.where(bedrooms.gt(0), 1)).ge(25)
    )
    selected = p1.loc[
        eligible & (
            coherent_small | coherent_large | coherent_price | coherent_expenses
            | coherent_low_price_m2 | coherent_high_price_m2
            | coherent_joint_extremes | coherent_joint_high_price_m2
        )
    ].copy()
    selected["reason"] = "extremo_percentilar_aislado_coherente"
    selected["evidence"] = selected.apply(
        lambda row: (
            f"Alerta aislada {row['audit_flags']}; precio={row['precio_auditado']}, "
            f"superficie={row['superficie_total_m2_auditado']}, "
            f"precio_m2={row['precio_m2_auditado']}, ambientes={row['ambientes']}, "
            f"dormitorios={row['dormitorios']}, expensas={row['expensas_valor']}"
        ),
        axis=1,
    )
    selected["review_version"] = "1.0"
    return selected[["property_id", "reason", "evidence", "review_version"]]


def construir(
    audit_path: Path, dataset_path: Path, output_path: Path,
    reviewed_output_path: Path | None = None,
) -> dict:
    audit = pd.read_csv(audit_path, low_memory=False)
    dataset = pd.read_csv(dataset_path, low_memory=False)
    p1 = audit.loc[audit["audit_priority"].eq("P1")].copy()
    status = dataset[[
        "property_id", "auditoria_p1_revisado", "auditoria_p1_pendiente",
        "precio_auditado", "superficie_total_m2_auditado", "precio_m2_auditado",
        "apto_modelado_preliminar",
    ]]
    p1 = p1.merge(status, on="property_id", how="left", validate="one_to_one")
    classified = p1.apply(classify, axis=1, result_type="expand")
    p1[["triaje_grupo", "triaje_accion"]] = classified
    p1["triaje_version"] = "1.0"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    p1.to_csv(output_path, index=False)
    no_change = no_change_candidates(p1)
    if reviewed_output_path is not None:
        reviewed_output_path.parent.mkdir(parents=True, exist_ok=True)
        no_change.to_csv(reviewed_output_path, index=False)
    summary = {
        "rows": int(len(p1)),
        "reviewed": int(p1["auditoria_p1_revisado"].sum()),
        "pending": int(p1["auditoria_p1_pendiente"].sum()),
        "reviewed_without_change_candidates": int(len(no_change)),
        "group_counts": {k: int(v) for k, v in p1["triaje_grupo"].value_counts().items()},
        "warning": "Clasificación para priorizar revisión; no implica corrección, exclusión ni winsorización.",
    }
    output_path.with_suffix(output_path.suffix + ".manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reviewed-output", type=Path)
    args = parser.parse_args()
    print(json.dumps(
        construir(args.audit, args.dataset, args.output, args.reviewed_output),
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    main()
