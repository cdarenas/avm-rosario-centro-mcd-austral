#!/usr/bin/env python3
"""Reconstruye procedencia geográfica legacy y prioriza revisión por dirección."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

SCRAPER_DIR = Path(__file__).resolve().parents[1] / 'scraping' / 'zonaprop_v2'
sys.path.insert(0, str(SCRAPER_DIR))
import geocode  # noqa: E402


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cargar_cache(path):
    frame = pd.read_csv(path)
    return {
        str(row.query).lower().strip(): (round(row.lat, 6), round(row.lon, 6))
        for row in frame.itertuples()
    }


def extraer_altura(query):
    match = re.search(r'(?<!\d)(\d{2,5})(?!\d)', query or '')
    return int(match.group(1)) if match else pd.NA


def construir(dataset_path, cache_exacta_path, cache_georef_path,
              cache_calle_path, output_path):
    dataset_path, output_path = Path(dataset_path).resolve(), Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(dataset_path, low_memory=False)
    scope = (
        (df['geo_distrito_oficial'].notna() & df['geo_distrito_oficial'].ne('CENTRO'))
        | df['geo_coordenada_compartida_sospechosa'].fillna(False)
    )
    review = df.loc[scope, [
        'property_id', 'posting_id_ultimo', 'url', 'direccion_exacta',
        'latitud', 'longitud', 'geo_distrito_oficial', 'geo_nivel_calidad',
        'geo_coord_n_registros', 'geo_coord_n_direcciones',
        'geo_coordenada_compartida_sospechosa'
    ]].copy()

    exact = cargar_cache(cache_exacta_path)
    georef = cargar_cache(cache_georef_path)
    street = cargar_cache(cache_calle_path)

    review['query_exacta'] = review['direccion_exacta'].map(geocode.preparar_query)
    review['query_calle'] = review['direccion_exacta'].map(geocode.preparar_query_calle)
    review['calle_altura_parseada'] = review['query_exacta'].map(extraer_altura).astype('Int64')

    def provenance(row):
        coord = (round(row.latitud, 6), round(row.longitud, 6))
        exact_query = row.query_exacta.lower()
        street_query = row.query_calle.lower()
        hits = []
        if georef.get(exact_query) == coord:
            hits.append('georef_exacta')
        if exact.get(exact_query) == coord:
            hits.append('nominatim_exacta')
        if street.get(street_query) == coord:
            hits.append('nominatim_calle')
        return '|'.join(hits) or 'match_solo_por_coordenada'

    review['geo_procedencia_reconstruida'] = review.apply(provenance, axis=1)

    def priority(row):
        source = row.geo_procedencia_reconstruida
        if 'nominatim_calle' in source or source == 'match_solo_por_coordenada':
            return 'P1_regeocodificar_direccion_exacta'
        if row.geo_distrito_oficial != 'CENTRO':
            return 'P2_validar_direccion_fuera_centro'
        return 'P3_validar_coordenada_compartida'

    review['prioridad_revision'] = review.apply(priority, axis=1)
    review['decision_revision'] = 'pendiente'
    review['observacion_revision'] = ''
    review.sort_values(
        ['prioridad_revision', 'geo_coord_n_direcciones', 'direccion_exacta'],
        ascending=[True, False, True], inplace=True
    )
    review.to_csv(output_path, index=False,
                  compression='gzip' if output_path.name.endswith('.gz') else None)
    summary = {
        'artifact': output_path.name,
        'dataset_sha256': sha256(dataset_path),
        'cache_sha256': {
            'nominatim_exacta': sha256(cache_exacta_path),
            'georef_exacta': sha256(cache_georef_path),
            'nominatim_calle': sha256(cache_calle_path),
        },
        'rows': int(len(review)),
        'unique_addresses': int(review['direccion_exacta'].nunique()),
        'parsed_street_number_rows': int(review['calle_altura_parseada'].notna().sum()),
        'provenance_counts': review['geo_procedencia_reconstruida'].value_counts().to_dict(),
        'priority_counts': review['prioridad_revision'].value_counts().to_dict(),
        'decisions': ['confirmar_centro', 'confirmar_fuera_centro', 'corregir_coordenada', 'no_resuelto'],
    }
    summary_path = output_path.with_suffix(output_path.suffix + '.summary.json')
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset')
    parser.add_argument('cache_exacta')
    parser.add_argument('cache_georef')
    parser.add_argument('cache_calle')
    parser.add_argument('output')
    args = parser.parse_args()
    print(json.dumps(construir(args.dataset, args.cache_exacta, args.cache_georef,
                               args.cache_calle, args.output),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
