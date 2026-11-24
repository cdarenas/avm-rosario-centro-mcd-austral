#!/usr/bin/env python3
"""Audita duplicados exactos, republicaciones candidatas y clusters de edificio."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

SCRAPER_DIR = Path(__file__).resolve().parents[1] / "scraping" / "zonaprop_v2"
sys.path.insert(0, str(SCRAPER_DIR))
import identidad  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).lower()).strip()


def strict_candidate(row) -> str | None:
    prop = {
        "direccion_exacta": row.direccion_exacta,
        "superficie_total_m2": row.eda_superficie_total_m2,
        "superficie_cubierta_m2": row.eda_superficie_cubierta_m2,
        "ambientes": row.ambientes,
        "dormitorios": row.dormitorios,
        "banos": row.eda_banos,
        "antiguedad": row.antiguedad_auditada,
        "orientacion": row.orientacion,
        "disposicion": row.disposicion,
    }
    return identidad.republication_candidate_id(prop)[0]


def signature_value(value):
    if pd.isna(value):
        return "NA"
    if isinstance(value, (int, float)):
        return f"{float(value):.3f}"
    return normalize_text(value)


def exact_signature(row) -> str | None:
    description = normalize_text(row.descripcion_completa)
    if len(description) < 100:
        return None
    values = [
        normalize_text(row.direccion_norm),
        signature_value(row.eda_superficie_total_m2),
        signature_value(row.eda_superficie_cubierta_m2),
        signature_value(row.ambientes),
        signature_value(row.dormitorios),
        signature_value(row.eda_banos),
        description,
    ]
    return "exact_" + hashlib.sha1("|".join(values).encode()).hexdigest()[:16]


def unit_marker(value) -> str:
    text = normalize_text(value)
    patterns = [
        r"\b(?:piso|unidad|dpto|depto|departamento)\s*([0-9a-z-]+)",
        r"\b(\d{1,2})\s*[°º]\s*([a-z0-9-]*)",
        r"\b(\d{1,2})[- ](\d{1,2})\b",
    ]
    found = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            if isinstance(match, tuple):
                found.append("-".join(part for part in match if part))
            else:
                found.append(match)
    return "|".join(found)


def split_group_id_v1(address) -> str:
    """Agrupa por cuadra sin confundir 3/9/27 de Febrero con una altura."""
    normalized = identidad.normalizar_direccion(address or "")
    height = re.search(r"(?<!\d)(\d{3,5})(?!\d)", normalized)
    if height and normalized[:height.start()].strip():
        street = normalized[:height.start()].strip()
        block = (int(height.group(1)) // 100) * 100
        key = f"calle_cuadra::{street}|{block}"
    elif normalized:
        key = f"direccion_sin_altura::{normalized}"
    else:
        key = "sin_direccion"
    return "split_" + hashlib.sha1(key.encode()).hexdigest()[:16]


def construir(input_path: Path, candidates_path: Path, clusters_path: Path, mapping_path: Path,
              report_path: Path,
              decisions_path: Path | None = None) -> dict:
    input_path, candidates_path, clusters_path, mapping_path, report_path = [
        Path(path).resolve() for path in (
            input_path, candidates_path, clusters_path, mapping_path, report_path
        )
    ]
    for path in (candidates_path, clusters_path, mapping_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, low_memory=False)
    if df["property_id"].duplicated().any():
        raise ValueError("La entrada contiene property_id duplicados")

    duplicate_posting = int(df["posting_id_ultimo"].duplicated().sum())
    duplicate_url = int(df["url"].duplicated().sum())
    df["repub_signature_strict"] = [strict_candidate(row) for row in df.itertuples()]
    df["repub_signature_exact"] = [exact_signature(row) for row in df.itertuples()]
    df["unit_marker"] = df["direccion_exacta"].map(unit_marker)
    df["split_group_id_v1"] = df["direccion_exacta"].map(split_group_id_v1)

    strict_counts = df["repub_signature_strict"].value_counts()
    exact_counts = df["repub_signature_exact"].value_counts()
    strict_valid = set(strict_counts[strict_counts.gt(1)].index)
    exact_valid = set(exact_counts[exact_counts.gt(1)].index)
    members = df.loc[
        df["repub_signature_strict"].isin(strict_valid)
        | df["repub_signature_exact"].isin(exact_valid)
    ].copy()

    # Cada señal genera su propio grupo auditable; no se fusionan componentes automáticamente.
    rows = []
    for signal, ids in (("firma_estricta_atributos", strict_valid), ("descripcion_y_atributos_exactos", exact_valid)):
        column = "repub_signature_strict" if signal == "firma_estricta_atributos" else "repub_signature_exact"
        for group_id in sorted(ids):
            group = members.loc[members[column].eq(group_id)].copy()
            markers = {value for value in group["unit_marker"] if value}
            priority = "P0_revisar_posible_republicacion"
            if len(markers) > 1:
                priority = "P1_posibles_unidades_distintas"
            for row in group.itertuples():
                rows.append({
                    "candidate_group_id": group_id,
                    "candidate_signal": signal,
                    "audit_priority": priority,
                    "n_properties_group": int(len(group)),
                    "property_id": row.property_id,
                    "posting_id_ultimo": row.posting_id_ultimo,
                    "url": row.url,
                    "direccion_exacta": row.direccion_exacta,
                    "direccion_norm": row.direccion_norm,
                    "unit_marker": row.unit_marker,
                    "inmobiliaria": row.inmobiliaria,
                    "precio_usd": row.eda_precio_usd,
                    "superficie_total_m2": row.eda_superficie_total_m2,
                    "superficie_cubierta_m2": row.eda_superficie_cubierta_m2,
                    "ambientes": row.ambientes,
                    "dormitorios": row.dormitorios,
                    "banos": row.eda_banos,
                    "first_seen": row.first_seen,
                    "last_seen": row.last_seen,
                    "building_cluster_id": row.building_cluster_id,
                    "split_group_id_v1": row.split_group_id_v1,
                    "decision_revision": "pendiente",
                    "evidencia_revision": "",
                })
    candidates = pd.DataFrame(rows).drop_duplicates(
        ["candidate_group_id", "property_id", "candidate_signal"]
    )
    decision_counts = {}
    if decisions_path:
        decisions = pd.read_csv(decisions_path)
        if decisions["candidate_group_id"].duplicated().any():
            raise ValueError("candidate_group_id duplicado en decisiones")
        candidates = candidates.merge(decisions, on="candidate_group_id", how="left", validate="many_to_one")
        candidates["decision_revision"] = candidates["decision"].fillna("pendiente")
        candidates["evidencia_revision"] = candidates["evidence"].fillna("")
        candidates.drop(columns=["decision", "evidence"], inplace=True)
        decision_counts = (
            candidates.drop_duplicates("candidate_group_id")["decision_revision"].value_counts().to_dict()
        )
    candidates.sort_values(
        ["audit_priority", "candidate_signal", "candidate_group_id", "property_id"], inplace=True
    )
    candidates.to_csv(candidates_path, index=False)

    cluster_rows = []
    for cluster_id, group in df.groupby("split_group_id_v1", sort=True):
        normalized = group["direccion_norm"].dropna().astype(str)
        parseable = normalized.str.contains(r"\d{2,5}", regex=True)
        cluster_rows.append({
            "split_group_id_v1": cluster_id,
            "n_building_cluster_legacy": int(group["building_cluster_id"].nunique()),
            "n_properties": int(len(group)),
            "n_postings": int(group["posting_id_ultimo"].nunique()),
            "n_direcciones_norm": int(group["direccion_norm"].nunique(dropna=True)),
            "direccion_ejemplo": group["direccion_exacta"].dropna().iloc[0] if group["direccion_exacta"].notna().any() else "",
            "precio_min": group["eda_precio_usd"].min(),
            "precio_max": group["eda_precio_usd"].max(),
            "identidades_baja_confianza": int(group["id_confianza"].eq("baja").sum()),
            "direccion_con_altura": bool(parseable.any()),
            "riesgo_split": "alto" if len(group) >= 20 else ("medio" if len(group) >= 5 else "bajo"),
        })
    clusters = pd.DataFrame(cluster_rows).sort_values(
        ["n_properties", "identidades_baja_confianza"], ascending=[False, False]
    )
    clusters.to_csv(clusters_path, index=False)
    cluster_sizes = clusters.set_index("split_group_id_v1")["n_properties"]
    mapping = df[[
        "property_id", "posting_id_ultimo", "direccion_exacta", "direccion_norm",
        "building_cluster_id", "split_group_id_v1", "id_confianza",
    ]].copy()
    mapping["split_group_n_properties"] = mapping["split_group_id_v1"].map(cluster_sizes)
    mapping.to_csv(mapping_path, index=False)

    group_summary = candidates.drop_duplicates(["candidate_signal", "candidate_group_id"])
    manifest = {
        "input_artifact": input_path.name,
        "input_sha256": sha256(input_path),
        "rows": int(len(df)),
        "duplicate_property_id": 0,
        "duplicate_posting_id": duplicate_posting,
        "duplicate_url": duplicate_url,
        "candidate_groups": int(len(group_summary)),
        "candidate_member_rows": int(len(candidates)),
        "strict_signature_groups": int((group_summary["candidate_signal"] == "firma_estricta_atributos").sum()),
        "exact_description_attribute_groups": int((group_summary["candidate_signal"] == "descripcion_y_atributos_exactos").sum()),
        "building_clusters": int(len(clusters)),
        "legacy_building_clusters": int(df["building_cluster_id"].nunique()),
        "clusters_ge_20": int(clusters["n_properties"].ge(20).sum()),
        "max_cluster_size": int(clusters["n_properties"].max()),
        "low_confidence_identity_rows": int(df["id_confianza"].eq("baja").sum()),
        "automatic_merges": 0,
        "split_mapping_artifact": mapping_path.name,
        "split_mapping_sha256": sha256(mapping_path),
        "decision_counts": decision_counts,
        "warning": "Candidatos para revisión y agrupamiento; no implica eliminar ni fusionar observaciones.",
    }
    manifest_path = candidates_path.with_suffix(candidates_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = f"""# Auditoría de duplicados y republicaciones — Centro v4

## Resultado automático

- filas auditadas: {len(df):,};
- `property_id` duplicados: 0;
- `posting_id_ultimo` duplicados: {duplicate_posting};
- URL duplicadas: {duplicate_url};
- grupos candidatos a revisión: {manifest['candidate_groups']};
- filas miembro de esos grupos: {manifest['candidate_member_rows']};
- clusters de edificio/cuadra: {len(clusters):,};
- tamaño máximo de cluster: {manifest['max_cluster_size']};
- identidades legacy de baja confianza: {manifest['low_confidence_identity_rows']:,}.

## Interpretación

No existen duplicados exactos por las claves técnicas disponibles. Las firmas de
republicación son señales para revisión: una descripción idéntica puede pertenecer
a distintas unidades de un mismo desarrollo. No se fusionó ni eliminó ninguna fila.

`building_cluster_id` debe evaluarse como unidad de agrupamiento para los folds,
no como identificador de propiedad física. Los clusters grandes pueden representar
una cuadra, un edificio con muchas unidades o una dirección incompleta.
"""
    report_path.write_text(report, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("clusters", type=Path)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    print(json.dumps(construir(
        args.input, args.candidates, args.clusters, args.mapping, args.report, args.decisions
    ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
