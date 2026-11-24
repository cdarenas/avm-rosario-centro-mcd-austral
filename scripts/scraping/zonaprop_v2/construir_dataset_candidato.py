#!/usr/bin/env python3
"""Construye una tabla interim auditable sin excluir observaciones.

Agrega features de texto y flags de calidad a la tabla de propiedades. No imputa,
no elimina outliers y no decide la unidad estadística final.
"""
import argparse
import hashlib
import json
import pathlib
import sqlite3
from datetime import datetime, timezone

import pandas as pd

import features_texto as F


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def construir(db_path, output_path):
    db_path = pathlib.Path(db_path).resolve()
    output_path = pathlib.Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    df = pd.read_sql_query('SELECT * FROM propiedades', con)
    con.close()

    descriptions = df['descripcion_completa'].fillna('')
    text_features = pd.DataFrame(
        (F.extraer_features(value) for value in descriptions), index=df.index
    )
    df = pd.concat([df, text_features], axis=1)

    def flags(row):
        def value_or_none(name):
            value = row.get(name)
            return None if pd.isna(value) else value

        prop = {
            'precio_valor': value_or_none('precio_ultimo'),
            'precio_moneda': value_or_none('precio_moneda'),
            'superficie_total_m2': value_or_none('superficie_total_m2'),
            'superficie_cubierta_m2': value_or_none('superficie_cubierta_m2'),
            'ambientes': value_or_none('ambientes'),
        }
        values = F.chequear_plausibilidad(prop)
        if pd.isna(row.get('latitud')) or pd.isna(row.get('longitud')):
            values.append('sin_coordenadas')
        # Solo el valor legacy "baja" representa una fusión incierta. La identidad
        # conservadora "posting" es una decisión de diseño, no un defecto del dato.
        if row.get('id_confianza') == 'baja':
            values.append('identidad_baja_confianza')
        return '|'.join(sorted(set(values)))

    df['quality_flags'] = df.apply(flags, axis=1)
    df['n_quality_flags'] = df['quality_flags'].map(
        lambda value: 0 if not value else len(value.split('|'))
    )
    df['precio_m2_observado'] = (
        df['precio_ultimo'] / df['superficie_total_m2'].where(
            df['superficie_total_m2'] > 0
        )
    )
    if output_path.name.endswith('.csv.gz'):
        df.to_csv(output_path, index=False, compression='gzip')
    elif output_path.suffix == '.parquet':
        try:
            df.to_parquet(output_path, index=False)
        except ImportError as exc:
            raise RuntimeError(
                'La salida Parquet requiere pyarrow. Instale requirements.txt '
                'o utilice una ruta terminada en .csv.gz.'
            ) from exc
    else:
        raise ValueError('La salida debe terminar en .parquet o .csv.gz')

    flag_counts = {}
    for value in df['quality_flags']:
        for flag in filter(None, value.split('|')):
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    metadata = {
        'artifact': output_path.name,
        'artifact_stage': 'interim_candidate',
        'created_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source_database': db_path.name,
        'source_database_sha256': sha256(db_path),
        'rows': int(len(df)),
        'columns': int(len(df.columns)),
        'quality_flag_counts': dict(sorted(flag_counts.items())),
        'excluded_rows': 0,
        'warning': (
            'Tabla candidata no apta para modelado final: conserva valores extremos, '
            'monedas no USD, identidades pendientes de auditoría y geocodificación heterogénea.'
        ),
    }
    metadata_path = output_path.with_suffix(output_path.suffix + '.manifest.json')
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('database', help='Ruta a zonaprop_v2.db')
    parser.add_argument('output', help='Ruta de salida .parquet o .csv.gz')
    args = parser.parse_args()
    metadata = construir(args.database, args.output)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
