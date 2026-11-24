#!/usr/bin/env python3
"""Asigna barrios oficiales mediante point-in-polygon sin alterar la fuente."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


SOURCE_NAME = "Municipalidad de Rosario - Barrios oficiales"
SOURCE_VERSION = "2025-10-28"
EPSILON = 1e-10


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


def point_on_segment(x: float, y: float, a: list, b: list) -> bool:
    ax, ay = a
    bx, by = b
    cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
    if abs(cross) > EPSILON:
        return False
    return (
        min(ax, bx) - EPSILON <= x <= max(ax, bx) + EPSILON
        and min(ay, by) - EPSILON <= y <= max(ay, by) + EPSILON
    )


def point_in_ring(x: float, y: float, ring: list) -> str:
    """Devuelve outside, inside o boundary para un anillo GeoJSON."""
    inside = False
    for i in range(len(ring) - 1):
        a, b = ring[i], ring[i + 1]
        if point_on_segment(x, y, a, b):
            return "boundary"
        ax, ay = a
        bx, by = b
        if (ay > y) != (by > y):
            intersection_x = (bx - ax) * (y - ay) / (by - ay) + ax
            if x < intersection_x:
                inside = not inside
    return "inside" if inside else "outside"


def point_in_polygon(x: float, y: float, rings: list) -> str:
    outer = point_in_ring(x, y, rings[0])
    if outer != "inside":
        return outer
    for hole in rings[1:]:
        result = point_in_ring(x, y, hole)
        if result == "boundary":
            return "boundary"
        if result == "inside":
            return "outside"
    return "inside"


def geometry_parts(geometry: dict) -> list[list]:
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    raise ValueError(f"Geometría no soportada: {geometry['type']}")


def load_neighborhoods(path: Path) -> list[dict]:
    source = pd.read_csv(path)
    required = {"MSLINK", "BARRIO", "GEOJSON"}
    if not required.issubset(source.columns):
        raise ValueError(f"Faltan columnas: {sorted(required - set(source.columns))}")
    neighborhoods = []
    for row in source.itertuples(index=False):
        feature = json.loads(row.GEOJSON)
        parts = geometry_parts(feature["geometry"])
        coordinates = [point for polygon in parts for ring in polygon for point in ring]
        neighborhoods.append(
            {
                "mslink": row.MSLINK,
                "name": row.BARRIO,
                "parts": parts,
                "bbox": (
                    min(point[0] for point in coordinates),
                    min(point[1] for point in coordinates),
                    max(point[0] for point in coordinates),
                    max(point[1] for point in coordinates),
                ),
            }
        )
    return neighborhoods


def locate(x: float, y: float, neighborhoods: list[dict]) -> list[tuple[dict, str]]:
    matches = []
    for neighborhood in neighborhoods:
        xmin, ymin, xmax, ymax = neighborhood["bbox"]
        if not (xmin - EPSILON <= x <= xmax + EPSILON and ymin - EPSILON <= y <= ymax + EPSILON):
            continue
        results = [point_in_polygon(x, y, polygon) for polygon in neighborhood["parts"]]
        if "boundary" in results:
            matches.append((neighborhood, "boundary"))
        elif "inside" in results:
            matches.append((neighborhood, "inside"))
    return matches


def enrich(input_path: Path, polygons_path: Path, output_path: Path, audit_path: Path) -> dict:
    paths = [Path(value).resolve() for value in (input_path, polygons_path, output_path, audit_path)]
    input_path, polygons_path, output_path, audit_path = paths
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path, low_memory=False)
    if df["property_id"].duplicated().any():
        raise ValueError("property_id debe ser único")
    neighborhoods = load_neighborhoods(polygons_path)
    spatial_ok = boolean(df["apto_eda_espacial_preliminar"])

    assignments = []
    for row, is_spatial_ok in zip(df.itertuples(index=False), spatial_ok):
        try:
            lat, lon = float(row.latitud), float(row.longitud)
        except (TypeError, ValueError):
            assignments.append((pd.NA, pd.NA, "coordenada_invalida", 0))
            continue
        matches = locate(lon, lat, neighborhoods)
        if not matches:
            assignments.append((pd.NA, pd.NA, "sin_asignacion", 0))
            continue
        boundary = any(result == "boundary" for _, result in matches)
        if len(matches) > 1:
            names = " | ".join(sorted({match[0]["name"] for match in matches}))
            links = " | ".join(str(match[0]["mslink"]) for match in matches)
            state = "limite_o_superposicion" if boundary else "superposicion_poligonos"
            assignments.append((names, links, state, len(matches)))
            continue
        neighborhood, result = matches[0]
        if result == "boundary":
            state = "limite_barrial"
        elif is_spatial_ok:
            state = "asignado_coordenada_apta"
        else:
            state = "asignado_coordenada_pendiente"
        assignments.append((neighborhood["name"], neighborhood["mslink"], state, 1))

    assigned = pd.DataFrame(
        assignments,
        columns=["barrio_oficial_geo", "barrio_oficial_mslink", "barrio_geo_estado", "barrio_geo_n_coincidencias"],
        index=df.index,
    )
    enriched = pd.concat([df, assigned], axis=1)
    enriched["barrio_geo_fuente"] = SOURCE_NAME
    enriched["barrio_geo_version"] = SOURCE_VERSION
    enriched["barrio_geo_apto_eda_preliminar"] = enriched["barrio_geo_estado"].eq(
        "asignado_coordenada_apta"
    )

    compression = {"method": "gzip", "mtime": 0} if output_path.name.endswith(".gz") else None
    enriched.to_csv(output_path, index=False, compression=compression)

    audit = (
        enriched.groupby(["barrio_oficial_geo", "barrio_geo_estado"], dropna=False)
        .size()
        .rename("n_propiedades")
        .reset_index()
        .sort_values(["barrio_geo_estado", "n_propiedades"], ascending=[True, False])
    )
    audit.to_csv(audit_path, index=False)

    states = enriched["barrio_geo_estado"].value_counts(dropna=False).to_dict()
    manifest = {
        "artifact": output_path.name,
        "artifact_sha256": sha256(output_path),
        "stage": "processed_eda_enriched_neighborhoods_v1",
        "input_artifact": input_path.name,
        "input_sha256": sha256(input_path),
        "polygons_artifact": polygons_path.name,
        "polygons_sha256": sha256(polygons_path),
        "rows": int(len(enriched)),
        "input_columns": int(df.shape[1]),
        "output_columns": int(enriched.shape[1]),
        "unique_property_id": int(enriched["property_id"].nunique()),
        "assignment_states": {str(key): int(value) for key, value in states.items()},
        "neighborhoods_assigned": int(enriched["barrio_oficial_geo"].nunique(dropna=True)),
        "audit_artifact": audit_path.name,
        "audit_sha256": sha256(audit_path),
        "original_neighborhood_column_modified": False,
        "input_modified": False,
        "warning": "Las asignaciones con coordenada pendiente no son aptas todavía para EDA territorial."
    }
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("polygons", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("audit", type=Path)
    args = parser.parse_args()
    print(json.dumps(enrich(args.input, args.polygons, args.output, args.audit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
