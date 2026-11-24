#!/usr/bin/env python3
"""Aplica resultados Georef resueltos y deriva el dataset Centro v1."""
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


def construir(dataset_path, validation_path, output_path):
    dataset_path, validation_path, output_path = map(
        lambda value: Path(value).resolve(), (dataset_path, validation_path, output_path)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(dataset_path, low_memory=False)
    validation = pd.read_csv(validation_path, low_memory=False)
    resolved = validation.loc[validation['status'].eq('resuelta'), [
        'property_id', 'query_georef', 'georef_latitud', 'georef_longitud',
        'georef_nomenclatura', 'georef_distrito_oficial', 'validacion_direccion'
    ]].drop_duplicates('property_id')
    if resolved['property_id'].duplicated().any():
        raise ValueError('La validación debe contener una fila resuelta por property_id')

    merged = df.merge(resolved, on='property_id', how='left', validate='one_to_one')
    applied = merged['georef_latitud'].notna() & merged['georef_longitud'].notna()
    merged['geo_latitud_legacy'] = merged['latitud']
    merged['geo_longitud_legacy'] = merged['longitud']
    merged['geo_distrito_legacy'] = merged['geo_distrito_oficial']
    merged['geo_validacion_georef_aplicada'] = applied
    merged.loc[applied, 'latitud'] = merged.loc[applied, 'georef_latitud']
    merged.loc[applied, 'longitud'] = merged.loc[applied, 'georef_longitud']
    merged.loc[applied, 'geo_distrito_oficial'] = merged.loc[
        applied, 'georef_distrito_oficial'
    ]
    merged.loc[applied, 'geo_nivel_calidad'] = 'G3_georef_direccion_validada'
    merged.loc[applied, 'geo_source'] = 'geocoded'
    merged['geo_provider_validado'] = pd.NA
    merged['geo_precision_validada'] = pd.NA
    merged.loc[applied, 'geo_provider_validado'] = 'georef'
    merged.loc[applied, 'geo_precision_validada'] = 'address'
    merged['apto_eda_espacial_preliminar'] = (
        merged['geo_distrito_oficial'].eq('CENTRO')
        & (
            merged['geo_validacion_georef_aplicada']
            | ~merged['geo_coordenada_compartida_sospechosa'].fillna(False)
        )
    )

    center = merged.loc[merged['geo_distrito_oficial'].eq('CENTRO')].copy()
    center['alcance_territorial'] = 'distrito_centro_oficial'
    center['calidad_espacial_preliminar'] = center['apto_eda_espacial_preliminar']
    center.to_csv(output_path, index=False,
                  compression='gzip' if output_path.name.endswith('.gz') else None)

    manifest = {
        'artifact': output_path.name,
        'stage': 'processed_eda_centro_v1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'dataset_v0_sha256': sha256(dataset_path),
        'georef_validation_sha256': sha256(validation_path),
        'input_rows': int(len(df)),
        'georef_resolved_applied': int(applied.sum()),
        'moved_into_center': int((applied & merged['geo_distrito_legacy'].ne('CENTRO')
                                  & merged['geo_distrito_oficial'].eq('CENTRO')).sum()),
        'confirmed_outside_center': int((applied & merged['geo_distrito_oficial'].ne('CENTRO')).sum()),
        'output_rows': int(len(center)),
        'preliminary_spatial_quality_rows': int(center['calidad_espacial_preliminar'].sum()),
        'unresolved_spatial_quality_rows': int((~center['calidad_espacial_preliminar']).sum()),
        'outliers_retained': True,
        'missing_values_imputed': False,
        'warning': 'Apta para EDA; validaciones no resueltas permanecen marcadas.',
    }
    manifest_path = output_path.with_suffix(output_path.suffix + '.manifest.json')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset')
    parser.add_argument('validation')
    parser.add_argument('output')
    args = parser.parse_args()
    print(json.dumps(construir(args.dataset, args.validation, args.output),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
