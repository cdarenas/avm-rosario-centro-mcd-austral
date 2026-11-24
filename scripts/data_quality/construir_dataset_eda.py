#!/usr/bin/env python3
"""Genera una primera tabla EDA trazable; conserva outliers y registra exclusiones."""
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


def construir(candidate_path, audit_path, output_path):
    candidate_path, audit_path, output_path = map(
        lambda value: Path(value).resolve(), (candidate_path, audit_path, output_path)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidate = pd.read_csv(candidate_path, low_memory=False)
    audit = pd.read_csv(audit_path, low_memory=False)
    audit_fields = [
        'property_id', 'geo_distrito_oficial', 'geo_nivel_calidad',
        'geo_coord_n_registros', 'geo_coord_n_direcciones',
        'geo_coordenada_compartida_sospechosa', 'motivos_revision',
        'requiere_revision', 'apto_eda_target_preliminar',
        'apto_eda_espacial_preliminar'
    ]
    if candidate['property_id'].duplicated().any() or audit['property_id'].duplicated().any():
        raise ValueError('property_id debe ser único en candidate y audit')
    merged = candidate.merge(audit[audit_fields], on='property_id', how='left', validate='one_to_one')
    if merged['apto_eda_target_preliminar'].isna().any():
        raise ValueError('Hay propiedades sin correspondencia en la tabla de auditoría')

    exclusions = merged.loc[~merged['apto_eda_target_preliminar'], [
        'property_id', 'posting_id_ultimo', 'precio_ultimo', 'precio_moneda',
        'motivos_revision'
    ]].copy()
    exclusions.insert(0, 'stage', 'eda_v0')
    exclusions.insert(1, 'exclusion_reason', 'target_no_usd_o_no_positivo')
    eda = merged.loc[merged['apto_eda_target_preliminar']].copy()

    compression = 'gzip' if output_path.name.endswith('.gz') else None
    eda.to_csv(output_path, index=False, compression=compression)
    exclusion_path = output_path.with_name(output_path.name.replace('.csv.gz', '') + '_exclusiones.csv')
    exclusions.to_csv(exclusion_path, index=False)
    manifest = {
        'artifact': output_path.name,
        'stage': 'processed_eda_v0',
        'created_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'candidate_sha256': sha256(candidate_path),
        'audit_sha256': sha256(audit_path),
        'input_rows': int(len(merged)),
        'output_rows': int(len(eda)),
        'excluded_rows': int(len(exclusions)),
        'exclusion_reasons': exclusions['exclusion_reason'].value_counts().to_dict(),
        'requires_review_retained': int(eda['requiere_revision'].sum()),
        'preliminary_spatial_rows': int(eda['apto_eda_espacial_preliminar'].sum()),
        'outliers_retained': True,
        'missing_values_imputed': False,
        'warning': 'Apta para EDA descriptivo; no apta todavía para entrenamiento final.',
    }
    manifest_path = output_path.with_suffix(output_path.suffix + '.manifest.json')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate')
    parser.add_argument('audit')
    parser.add_argument('output')
    args = parser.parse_args()
    print(json.dumps(construir(args.candidate, args.audit, args.output),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
