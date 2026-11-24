#!/usr/bin/env python3
"""Exporta tablas de revisión manual para identidades y clusters de edificios."""
import argparse
import pathlib
import sqlite3

import pandas as pd


MERGES_SQL = """
SELECT
  c.property_id,
  COUNT(DISTINCT c.posting_id) AS n_postings,
  GROUP_CONCAT(DISTINCT c.posting_id) AS posting_ids,
  COUNT(*) AS n_capturas,
  p.id_confianza,
  p.direccion_exacta,
  p.superficie_total_m2,
  p.superficie_cubierta_m2,
  p.ambientes,
  p.dormitorios,
  p.banos,
  p.antiguedad,
  p.orientacion,
  p.disposicion,
  MIN(c.precio_valor) AS precio_min_capturado,
  MAX(c.precio_valor) AS precio_max_capturado
FROM capturas c
JOIN propiedades p ON p.property_id=c.property_id
GROUP BY c.property_id
HAVING COUNT(DISTINCT c.posting_id)>1
ORDER BY n_postings DESC, n_capturas DESC
"""

REPUBLICATION_CANDIDATES_SQL = """
SELECT
  c.republication_candidate_id,
  COUNT(DISTINCT c.posting_id) AS n_postings,
  GROUP_CONCAT(DISTINCT c.posting_id) AS posting_ids,
  COUNT(*) AS n_capturas,
  MIN(p.direccion_exacta) AS direccion_ejemplo,
  MIN(p.superficie_total_m2) AS superficie_total_min,
  MAX(p.superficie_total_m2) AS superficie_total_max,
  MIN(c.precio_valor) AS precio_min_capturado,
  MAX(c.precio_valor) AS precio_max_capturado
FROM capturas c
JOIN propiedades p ON p.property_id=c.property_id
WHERE c.republication_candidate_id IS NOT NULL
GROUP BY c.republication_candidate_id
HAVING COUNT(DISTINCT c.posting_id)>1
ORDER BY n_postings DESC, n_capturas DESC
"""


CLUSTERS_SQL = """
SELECT
  building_cluster_id,
  COUNT(*) AS n_propiedades,
  COUNT(DISTINCT direccion_norm) AS n_direcciones,
  MIN(direccion_exacta) AS direccion_ejemplo,
  MIN(precio_ultimo) AS precio_min,
  MAX(precio_ultimo) AS precio_max,
  SUM(CASE WHEN id_confianza='baja' THEN 1 ELSE 0 END) AS identidades_baja_confianza
FROM propiedades
GROUP BY building_cluster_id
ORDER BY n_propiedades DESC
"""


def exportar(db_path, output_dir):
    db_path = pathlib.Path(db_path).resolve()
    output_dir = pathlib.Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    capture_cols = {row[1] for row in con.execute('PRAGMA table_info(capturas)')}
    merge_sql = (
        REPUBLICATION_CANDIDATES_SQL
        if 'republication_candidate_id' in capture_cols
        else MERGES_SQL
    )
    merges = pd.read_sql_query(merge_sql, con)
    clusters = pd.read_sql_query(CLUSTERS_SQL, con)
    con.close()
    merge_path = output_dir / 'property_merges_review.csv'
    cluster_path = output_dir / 'building_clusters_review.csv'
    merges.to_csv(merge_path, index=False)
    clusters.to_csv(cluster_path, index=False)
    return merge_path, cluster_path, len(merges), len(clusters)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('database', help='Ruta a zonaprop_v2.db')
    parser.add_argument('output_dir', help='Directorio para CSV de auditoría')
    args = parser.parse_args()
    merge_path, cluster_path, n_merges, n_clusters = exportar(
        args.database, args.output_dir
    )
    print(f'Fusiones a revisar: {n_merges} -> {merge_path}')
    print(f'Clusters a revisar: {n_clusters} -> {cluster_path}')


if __name__ == '__main__':
    main()
