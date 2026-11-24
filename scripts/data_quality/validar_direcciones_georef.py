#!/usr/bin/env python3
"""Valida direcciones prioritarias con Georef y polígonos oficiales de Rosario."""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from construir_tabla_auditoria import cargar_poligonos, punto_en_poligono

GEOREF_URL = 'https://apis.datos.gob.ar/georef/api/direcciones'


def preparar_query_georef(query):
    """Conserva calle y primera altura; evita enviar piso/departamento."""
    value = str(query or '').split(',')[0].strip()
    # Los cruces y direcciones sin altura no son resolubles por este endpoint.
    if '&' in value:
        return ''
    matches = list(re.finditer(r'(?<![A-Za-zÁÉÍÓÚÜÑáéíóúüñ\d])(\d{2,5})(?!\d)', value))
    if not matches:
        return ''
    match = matches[0]
    street = value[:match.start()].strip()
    if not street:
        return ''
    return f'{street} {match.group(1)}'


def distrito(lon, lat, polygons):
    for name, ring in polygons.items():
        if punto_en_poligono(lon, lat, ring):
            return name
    return 'FUERA_MUNICIPIO'


def consultar(query, timeout=20):
    params = {
        'direccion': query, 'provincia': 'santa fe',
        'localidad': 'rosario', 'max': 1,
    }
    request = Request(
        f'{GEOREF_URL}?{urlencode(params)}',
        headers={'User-Agent': 'tesis-avm-rosario/1.0 (investigacion academica)'},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    results = (payload or {}).get('direcciones') or []
    if not results:
        return {'status': 'no_encontrada'}
    first = results[0]
    location = first.get('ubicacion') or {}
    if location.get('lat') is None or location.get('lon') is None:
        return {'status': 'sin_coordenadas'}
    return {
        'status': 'resuelta',
        'georef_latitud': float(location['lat']),
        'georef_longitud': float(location['lon']),
        'georef_nomenclatura': first.get('nomenclatura'),
        'georef_calle': (first.get('calle') or {}).get('nombre'),
        'georef_altura': first.get('altura'),
    }


def validar(audit_path, districts_path, cache_path, output_path, delay=0.35):
    audit = pd.read_csv(audit_path, low_memory=False)
    priority = audit.loc[
        audit['prioridad_revision'].eq('P1_regeocodificar_direccion_exacta')
    ].copy()
    priority['query_georef'] = priority['query_exacta'].map(preparar_query_georef)
    queries = sorted(set(priority.loc[priority['query_georef'].ne(''), 'query_georef']))
    polygons = cargar_poligonos(districts_path)
    cache_path, output_path = Path(cache_path), Path(output_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = {}
    if cache_path.exists():
        cache = {
            row['query_georef']: row
            for row in pd.read_csv(cache_path).to_dict('records')
        }

    for index, query in enumerate(queries, 1):
        if query in cache:
            continue
        try:
            result = consultar(query)
        except Exception as exc:
            result = {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'}
        result['query_georef'] = query
        if result['status'] == 'resuelta':
            result['georef_distrito_oficial'] = distrito(
                result['georef_longitud'], result['georef_latitud'], polygons
            )
        cache[query] = result
        pd.DataFrame(cache.values()).sort_values('query_georef').to_csv(cache_path, index=False)
        if index % 25 == 0:
            print(f'[{index}/{len(queries)}] consultas procesadas', flush=True)
        time.sleep(delay)

    results = pd.DataFrame(cache.values()) if cache else pd.DataFrame(columns=['query_georef'])
    validation = priority.merge(results, on='query_georef', how='left')
    validation.loc[validation['query_georef'].eq(''), 'status'] = 'sin_calle_altura_parseable'
    validation['validacion_direccion'] = 'pendiente'
    resolved = validation['status'].eq('resuelta')
    validation.loc[resolved & validation['georef_distrito_oficial'].eq('CENTRO'),
                   'validacion_direccion'] = 'confirmar_centro_corregir_coordenada'
    validation.loc[resolved & validation['georef_distrito_oficial'].ne('CENTRO'),
                   'validacion_direccion'] = 'confirmar_fuera_centro'
    validation.to_csv(output_path, index=False,
                      compression='gzip' if output_path.name.endswith('.gz') else None)
    summary = {
        'input_priority_rows': int(len(priority)),
        'unique_queries_sent': int(len(queries)),
        'status_counts': validation['status'].fillna('sin_resultado').value_counts().to_dict(),
        'validation_counts': validation['validacion_direccion'].value_counts().to_dict(),
        'resolved_district_counts': validation.loc[resolved, 'georef_distrito_oficial'].value_counts().to_dict(),
        'warning': 'Resultados de validación; no se aplicaron cambios al dataset.',
    }
    summary_path = output_path.with_suffix(output_path.suffix + '.summary.json')
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audit')
    parser.add_argument('districts')
    parser.add_argument('cache')
    parser.add_argument('output')
    parser.add_argument('--delay', type=float, default=0.35)
    args = parser.parse_args()
    summary = validar(args.audit, args.districts, args.cache, args.output, args.delay)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
