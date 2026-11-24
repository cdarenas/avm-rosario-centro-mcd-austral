#!/usr/bin/env python3
"""Deriva el dataset EDA territorialmente confirmado para el Distrito Centro."""
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


def motivo_fuera_alcance(row):
    if pd.isna(row.get('geo_distrito_oficial')):
        return 'sin_coordenadas_no_validable_territorialmente'
    return f"fuera_distrito_centro_{str(row['geo_distrito_oficial']).lower()}"


def construir(input_path, output_path):
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, low_memory=False)

    if df['property_id'].duplicated().any():
        raise ValueError('property_id debe ser único')
    if not df['apto_eda_target_preliminar'].fillna(False).all():
        raise ValueError('La entrada debe ser el dataset EDA con target validado')

    in_scope = df['geo_distrito_oficial'].eq('CENTRO')
    centro = df.loc[in_scope].copy()
    centro['alcance_territorial'] = 'distrito_centro_oficial'
    centro['calidad_espacial_preliminar'] = centro[
        'apto_eda_espacial_preliminar'
    ].astype(bool)

    exclusions = df.loc[~in_scope, [
        'property_id', 'posting_id_ultimo', 'geo_distrito_oficial',
        'geo_nivel_calidad', 'latitud', 'longitud', 'motivos_revision'
    ]].copy()
    exclusions.insert(0, 'stage', 'eda_centro_v0')
    exclusions.insert(1, 'exclusion_reason', exclusions.apply(motivo_fuera_alcance, axis=1))

    compression = 'gzip' if output_path.name.endswith('.gz') else None
    centro.to_csv(output_path, index=False, compression=compression)
    stem = output_path.name.removesuffix('.csv.gz').removesuffix('.csv')
    exclusion_path = output_path.with_name(f'{stem}_fuera_alcance.csv')
    exclusions.to_csv(exclusion_path, index=False)

    manifest = {
        'artifact': output_path.name,
        'stage': 'processed_eda_centro_v0',
        'created_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source_artifact': input_path.name,
        'source_sha256': sha256(input_path),
        'territorial_rule': 'geo_distrito_oficial == CENTRO',
        'input_rows': int(len(df)),
        'output_rows': int(len(centro)),
        'outside_scope_rows': int(len(exclusions)),
        'outside_scope_reasons': exclusions['exclusion_reason'].value_counts().to_dict(),
        'preliminary_spatial_quality_rows': int(centro['calidad_espacial_preliminar'].sum()),
        'suspicious_coordinate_rows_retained': int(
            centro['geo_coordenada_compartida_sospechosa'].sum()
        ),
        'outliers_retained': True,
        'missing_values_imputed': False,
        'warning': 'Apta para EDA del área de estudio; aún no es dataset final de modelado.',
    }
    manifest_path = output_path.with_suffix(output_path.suffix + '.manifest.json')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Dataset EDA v0')
    parser.add_argument('output', help='Salida .csv o .csv.gz para Distrito Centro')
    args = parser.parse_args()
    print(json.dumps(construir(args.input, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
