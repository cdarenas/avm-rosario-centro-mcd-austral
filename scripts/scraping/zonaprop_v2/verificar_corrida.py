#!/usr/bin/env python3
"""
verificar_corrida.py — Verificación de calidad de la base del scraper (Fase 6).
Ejecuta los chequeos del checklist sobre salida/zonaprop_v2.db.

Uso:  python verificar_corrida.py
"""
import sqlite3, os
import config as C
import features_texto as F

def linea(t): print('\n' + '='*64 + f'\n{t}\n' + '='*64)

def main(db=None):
    db = db or C.DB_PATH
    if not os.path.exists(db):
        print('No existe la base:', db); return
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    q = lambda s, p=(): con.execute(s, p).fetchone()[0]

    linea('1) VOLUMEN Y TRAZABILIDAD')
    print('capturas    :', q('SELECT COUNT(*) FROM capturas'))
    print('propiedades :', q('SELECT COUNT(*) FROM propiedades'))
    print('exclusiones :', q('SELECT COUNT(*) FROM exclusiones'))
    print('runs        :', q('SELECT COUNT(*) FROM runs'))
    print('\n  consistencia de runs:')
    run_cols = {r[1] for r in con.execute('PRAGMA table_info(runs)')}
    status_expr = "COALESCE(r.status,'legacy')" if 'status' in run_cols else "'legacy'"
    for run_id, stored, actual, status in con.execute(f"""
        SELECT r.run_id, r.n_capturas, COUNT(c.id), {status_expr}
        FROM runs r LEFT JOIN capturas c ON c.run_id=r.run_id
        GROUP BY r.run_id ORDER BY r.started_at
    """):
        marca = 'OK' if stored == actual else 'REVISAR'
        print(f'  {run_id}: stored={stored} actual={actual} status={status} [{marca}]')

    linea('2) IDENTIDAD Y REPUBLICACIONES')
    npost = q('SELECT COUNT(DISTINCT posting_id) FROM capturas')
    nprop = q('SELECT COUNT(*) FROM propiedades')
    nbld  = q('SELECT COUNT(DISTINCT building_cluster_id) FROM propiedades')
    print(f'posting_id distintos : {npost}')
    print(f'property_id (propiedades): {nprop}')
    print(f'building_cluster distintos: {nbld}')
    if npost:
        print(f'diferencia property/posting (legacy): {(1-nprop/npost)*100:.1f}%')
    for conf,n in con.execute("SELECT id_confianza, COUNT(*) FROM propiedades GROUP BY id_confianza"):
        print(f'  confianza {conf}: {n}')
    multi = q("""
        SELECT COUNT(*) FROM (
          SELECT property_id FROM capturas GROUP BY property_id
          HAVING COUNT(DISTINCT posting_id)>1
        )
    """)
    print(f'  property_id con múltiples posting_id: {multi}')
    capture_cols = {r[1] for r in con.execute('PRAGMA table_info(capturas)')}
    if 'republication_candidate_id' in capture_cols:
        candidates = q("""
            SELECT COUNT(*) FROM (
              SELECT republication_candidate_id FROM capturas
              WHERE republication_candidate_id IS NOT NULL
              GROUP BY republication_candidate_id
              HAVING COUNT(DISTINCT posting_id)>1
            )
        """)
        print(f'  grupos candidatos a republicación: {candidates}')

    linea('3) COORDENADAS')
    for src,n in con.execute("SELECT COALESCE(geo_source,'null'), COUNT(*) FROM propiedades GROUP BY geo_source"):
        print(f'  {src}: {n}')
    cols = {r[1] for r in con.execute('PRAGMA table_info(propiedades)')}
    if {'geo_provider', 'geo_precision'} <= cols:
        print('  proveedor / precisión:')
        for provider, precision, n in con.execute("""
            SELECT COALESCE(geo_provider,'null'), COALESCE(geo_precision,'null'), COUNT(*)
            FROM propiedades GROUP BY geo_provider, geo_precision ORDER BY COUNT(*) DESC
        """):
            print(f'    {provider:12s} {precision:20s}: {n}')
    inc = q("SELECT COUNT(*) FROM propiedades WHERE in_distrito_centro=1")
    fuera = q("SELECT COUNT(*) FROM propiedades WHERE in_distrito_centro=0")
    print(f'  dentro del Distrito Centro: {inc} | fuera: {fuera}')

    linea('4) PRECIOS Y CONSISTENCIA')
    for m,n in con.execute("SELECT COALESCE(precio_moneda,'null'), COUNT(*) FROM propiedades GROUP BY precio_moneda"):
        print(f'  moneda {m}: {n}')
    r = con.execute("SELECT MIN(precio_ultimo), AVG(precio_ultimo), MAX(precio_ultimo) FROM propiedades WHERE precio_ultimo>0 AND precio_moneda='USD'").fetchone()
    print(f'  precio USD (solo USD)  min={r[0]} avg={r[1]:.0f} max={r[2]}' if r[0] else '  sin precios USD')
    print('  moneda no USD:', q("SELECT COUNT(*) FROM propiedades WHERE precio_moneda<>'USD'"))
    print('  USD fuera de rango:', q("""
        SELECT COUNT(*) FROM propiedades
        WHERE precio_moneda='USD' AND (precio_ultimo<10000 OR precio_ultimo>2000000)
    """))
    print('  propiedades con cambios de precio:', q("SELECT COUNT(*) FROM propiedades WHERE cambios_precio>0"))

    linea('5) FALTANTES (campos clave)')
    campos = ['superficie_total_m2','ambientes','banos','antiguedad','expensas_valor','direccion_exacta','descripcion_completa']
    for c in campos:
        nul = q(f"SELECT COUNT(*) FROM propiedades WHERE {c} IS NULL")
        print(f'  {c:22s} nulos: {nul}/{nprop} ({nul/max(nprop,1)*100:.1f}%)')

    linea('6) FEATURES DE TEXTO (feat_*) — prevalencia (extractor robusto)')
    descs = [r[0] for r in con.execute("SELECT descripcion_completa FROM propiedades WHERE descripcion_completa IS NOT NULL")]
    if descs:
        acc = {k:0 for k in F.FEAT_PATRONES}
        for d in descs:
            for k,v in F.extraer_features(d).items(): acc[k]+=v
        for k in sorted(acc, key=lambda x:-acc[x]):
            if acc[k]: print(f'  {k:22s} {acc[k]:5d} ({acc[k]/len(descs)*100:.0f}%)')

    linea('7) PLAUSIBILIDAD (marcas, no exclusiones)')
    rows = con.execute("SELECT precio_ultimo, superficie_total_m2, superficie_cubierta_m2, ambientes, precio_moneda FROM propiedades").fetchall()
    from collections import Counter
    cnt = Counter()
    for pr in rows:
        prop = dict(precio_valor=pr[0], superficie_total_m2=pr[1], superficie_cubierta_m2=pr[2], ambientes=pr[3], precio_moneda=pr[4])
        for fl in F.chequear_plausibilidad(prop): cnt[fl]+=1
    if cnt:
        for fl,n in cnt.most_common(): print(f'  {fl}: {n}')
    else:
        print('  sin flags de plausibilidad')

    linea('8) EXCLUSIONES por motivo')
    for mot,n in con.execute("SELECT motivo, COUNT(*) FROM exclusiones GROUP BY motivo ORDER BY 2 DESC"):
        print(f'  {mot}: {n}')

    linea('9) TEMPORALIDAD')
    multi_run = q("""
        SELECT COUNT(*) FROM (
          SELECT posting_id FROM capturas GROUP BY posting_id
          HAVING COUNT(DISTINCT run_id)>1
        )
    """)
    print('  posting_id observados en más de una corrida:', multi_run)
    print('  propiedades con cambios de precio:', q(
        'SELECT COUNT(*) FROM propiedades WHERE cambios_precio>0'
    ))
    con.close()

if __name__ == '__main__':
    import sys
    main(sys.argv[1] if len(sys.argv)>1 else None)
