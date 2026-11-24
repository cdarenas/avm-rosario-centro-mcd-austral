#!/usr/bin/env python3
"""Construye una tabla de auditoría sin modificar ni excluir la tabla interim."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cargar_poligonos(path):
    distritos = pd.read_csv(path)
    polygons = {}
    for row in distritos.itertuples(index=False):
        geometry = json.loads(row.GEOJSON)['geometry']
        if geometry['type'] != 'Polygon':
            raise ValueError(f"Geometría no soportada: {geometry['type']}")
        polygons[str(row.DISTRITO).upper()] = geometry['coordinates'][0]
    if 'CENTRO' not in polygons:
        raise ValueError('No se encontró el polígono DISTRITO=CENTRO')
    return polygons


def punto_en_poligono(lon, lat, ring):
    """Ray casting sobre WGS84; incluye puntos ubicados sobre el borde."""
    inside = False
    for i in range(len(ring)):
        x1, y1 = ring[i - 1]
        x2, y2 = ring[i]
        cross = (x2 - x1) * (lat - y1) - (y2 - y1) * (lon - x1)
        if abs(cross) < 1e-12 and min(x1, x2) <= lon <= max(x1, x2) and min(y1, y2) <= lat <= max(y1, y2):
            return True
        if ((y1 > lat) != (y2 > lat)):
            cut = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < cut:
                inside = not inside
    return inside


def normalizar_direccion(series):
    return (series.fillna('').astype(str).str.lower()
            .str.replace(r'[^a-záéíóúüñ0-9]+', ' ', regex=True).str.strip())


def construir(input_path, districts_path, output_path, address_threshold=10):
    input_path, districts_path, output_path = map(
        lambda value: Path(value).resolve(), (input_path, districts_path, output_path)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, low_memory=False)
    polygons = cargar_poligonos(districts_path)

    audit = df[[c for c in [
        'property_id', 'posting_id_ultimo', 'url', 'direccion_exacta',
        'direccion_norm', 'precio_ultimo', 'precio_moneda',
        'superficie_total_m2', 'superficie_cubierta_m2', 'ambientes',
        'latitud', 'longitud', 'geo_source', 'id_confianza', 'quality_flags'
    ] if c in df.columns]].copy()
    audit['direccion_auditoria'] = normalizar_direccion(audit['direccion_exacta'])
    audit['geo_disponible'] = audit['latitud'].notna() & audit['longitud'].notna()
    audit['geo_rango_wgs84_valido'] = (
        audit['latitud'].between(-90, 90) & audit['longitud'].between(-180, 180)
    )

    valid = audit['geo_disponible'] & audit['geo_rango_wgs84_valido']
    def distrito_oficial(lon, lat):
        for district, ring in polygons.items():
            if punto_en_poligono(lon, lat, ring):
                return district
        return 'FUERA_MUNICIPIO'

    audit['geo_distrito_oficial'] = pd.Series(pd.NA, index=audit.index, dtype='string')
    audit.loc[valid, 'geo_distrito_oficial'] = [
        distrito_oficial(lon, lat)
        for lon, lat in zip(audit.loc[valid, 'longitud'], audit.loc[valid, 'latitud'])
    ]
    audit['geo_en_distrito_centro_oficial'] = audit['geo_distrito_oficial'].eq('CENTRO')
    audit.loc[~valid, 'geo_en_distrito_centro_oficial'] = pd.NA

    coord_cols = ['latitud', 'longitud']
    counts = audit.loc[valid].groupby(coord_cols).size().rename('geo_coord_n_registros')
    address_counts = (audit.loc[valid].groupby(coord_cols)['direccion_auditoria']
                      .nunique().rename('geo_coord_n_direcciones'))
    audit = audit.join(counts, on=coord_cols).join(address_counts, on=coord_cols)
    audit[['geo_coord_n_registros', 'geo_coord_n_direcciones']] = audit[
        ['geo_coord_n_registros', 'geo_coord_n_direcciones']
    ].fillna(0).astype(int)
    audit['geo_coordenada_compartida_sospechosa'] = (
        audit['geo_coord_n_direcciones'] >= address_threshold
    )

    def geo_level(row):
        if not row.geo_disponible:
            return 'G0_sin_coordenadas'
        if not row.geo_rango_wgs84_valido:
            return 'G1_rango_invalido'
        if not bool(row.geo_en_distrito_centro_oficial):
            return 'G1_fuera_poligono_oficial'
        if row.geo_coordenada_compartida_sospechosa:
            return 'G1_coordenada_compartida_sospechosa'
        # La base legacy no conserva proveedor/precisión: nunca asignar calidad alta.
        return 'G2_dentro_poligono_procedencia_legacy'

    audit['geo_nivel_calidad'] = audit.apply(geo_level, axis=1)
    flags = audit['quality_flags'].fillna('')
    audit['target_usd_positivo'] = (
        audit['precio_moneda'].eq('USD') & audit['precio_ultimo'].gt(0)
    )
    audit['error_estructural_a_revisar'] = (
        flags.str.contains('superficie_fuera_rango|sup_cubierta_mayor_que_total|ambientes_fuera_rango')
    )
    audit['outlier_precio_a_revisar'] = flags.str.contains(
        'precio_fuera_rango|precio_m2_fuera_rango'
    )
    audit['identidad_a_revisar'] = audit['id_confianza'].eq('baja')
    audit['apto_eda_target_preliminar'] = audit['target_usd_positivo']
    audit['apto_eda_espacial_preliminar'] = (
        audit['target_usd_positivo']
        & audit['geo_en_distrito_centro_oficial'].fillna(False)
        & ~audit['geo_coordenada_compartida_sospechosa']
    )

    def motivos(row):
        values = []
        if not row.target_usd_positivo: values.append('target_no_usd_o_no_positivo')
        if row.error_estructural_a_revisar: values.append('inconsistencia_estructural')
        if row.outlier_precio_a_revisar: values.append('outlier_precio')
        if row.identidad_a_revisar: values.append('identidad_legacy')
        if row.geo_nivel_calidad != 'G2_dentro_poligono_procedencia_legacy':
            values.append(row.geo_nivel_calidad)
        return '|'.join(values)

    audit['motivos_revision'] = audit.apply(motivos, axis=1)
    audit['requiere_revision'] = audit['motivos_revision'].ne('')
    audit.to_csv(output_path, index=False, compression='gzip' if output_path.name.endswith('.gz') else None)

    summary = {
        'artifact': output_path.name,
        'created_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source_artifact_sha256': sha256(input_path),
        'official_districts_sha256': sha256(districts_path),
        'rows': int(len(audit)),
        'excluded_rows': 0,
        'address_reuse_threshold': address_threshold,
        'geo_quality_counts': audit['geo_nivel_calidad'].value_counts().sort_index().to_dict(),
        'official_district_counts': audit['geo_distrito_oficial'].fillna('SIN_COORDENADAS').value_counts().to_dict(),
        'requires_review': int(audit['requiere_revision'].sum()),
        'preliminary_target_eda': int(audit['apto_eda_target_preliminar'].sum()),
        'preliminary_spatial_eda': int(audit['apto_eda_espacial_preliminar'].sum()),
        'warning': 'Aptitud preliminar; no constituye la tabla processed final.',
    }
    summary_path = output_path.with_suffix(output_path.suffix + '.summary.json')
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Tabla interim .csv o .csv.gz')
    parser.add_argument('districts', help='CSV oficial con columna GEOJSON')
    parser.add_argument('output', help='Tabla de auditoría .csv o .csv.gz')
    parser.add_argument('--address-reuse-threshold', type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(construir(args.input, args.districts, args.output,
                               args.address_reuse_threshold),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
