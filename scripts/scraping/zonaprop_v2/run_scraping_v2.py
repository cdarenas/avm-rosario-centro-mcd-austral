#!/usr/bin/env python3
"""
run_scraping_v2.py — Orquestador del scraper v2 (Fase 2).

Reutiliza el motor existente (cloudscraper + parsing __NEXT_DATA__, dos etapas) y le agrega
lo que exige la tesis:
  - capture_date por corrida (snapshot); historial de precios y republicaciones.
  - property_id (estricto) + building_cluster_id (group-aware split).
  - coordenadas persistidas + marca de geocodificación pendiente.
  - robustez: reintentos con backoff, reanudación (resume), logging, rate-limiting cortés.
  - exclusiones registradas con motivo (no perder datos en silencio).

Uso:
    python run_scraping_v2.py            # todos los ambientes
    python run_scraping_v2.py 3          # solo 3 ambientes
    python run_scraping_v2.py --resume RUN_ID   # reanudar una corrida
"""
import os, sys, time, json, hashlib, logging, argparse

import config as C
sys.path.insert(0, C.LEGACY_DIR)   # reutilizar zonaprop_extractor / zonaprop_scraper
import storage, identidad, geo

# ── logging ───────────────────────────────────────────────────────────────────
os.makedirs(C.OUT_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler(C.LOG_PATH), logging.StreamHandler()]
)
log = logging.getLogger('scraper_v2')

def _content_hash(prop: dict) -> str:
    campos = [prop.get(k) for k in ('precio_valor','precio_moneda','superficie_total_m2',
              'ambientes','banos','descripcion_completa','direccion_exacta')]
    return hashlib.sha1('|'.join(str(x) for x in campos).encode()).hexdigest()[:16]

def _con_reintentos(fn, *a, **kw):
    """Ejecuta fn con reintentos exponenciales."""
    for intento in range(1, C.MAX_REINTENTOS + 1):
        try:
            return fn(*a, **kw)
        except Exception as e:
            espera = C.BACKOFF_BASE * (2 ** (intento - 1))
            log.warning(f'Fallo (intento {intento}/{C.MAX_REINTENTOS}): {e}. Reintento en {espera:.0f}s')
            time.sleep(espera)
    log.error('Agotados los reintentos.')
    raise RuntimeError('max reintentos')

def scrape_banda(amb_label, amb_slug, pmin, pmax):
    """Etapa 1 (listado) de UNA banda de precio, con tope de páginas (evita el bloqueo)."""
    from zonaprop_extractor import filter_out_of_zone, run_scraping
    config = {
        'zona_slug': C.ZONA_SLUG, 'zona_label': C.ZONA_LABEL,
        'ambientes': amb_label, 'antiguedad': C.ANTIGUEDAD_LABEL,
        'antiguedad_slug': C.ANTIGUEDAD_SLUG, 'formato': 'CSV', 'ruta': C.OUT_DIR,
        'url': C.build_url_precio(C.ZONA_SLUG_URL, amb_slug, pmin, pmax),
        'max_paginas': C.MAX_PAGINAS,
    }
    props = _con_reintentos(run_scraping, config)
    props, n_fuera = filter_out_of_zone(props, C.ZONA_SLUG)
    return props, n_fuera

def recolectar_ambiente(amb_label, amb_slug):
    """Recorre bandas de precio con subdivisión adaptativa: si una banda satura
    (trae >= CAP_SATURACION), se parte en dos hasta que entre completa dentro del
    tope de páginas. Devuelve props deduplicados por posting_id."""
    stack = list(C.BANDAS_PRECIO)
    seen, props_all, n_fuera_tot = set(), [], 0
    while stack:
        pmin, pmax = stack.pop()
        props, n_fuera = scrape_banda(amb_label, amb_slug, pmin, pmax)
        n_fuera_tot += n_fuera
        if len(props) >= C.CAP_SATURACION and (pmax - pmin) > C.MIN_ANCHO_BANDA:
            mid = (pmin + pmax) // 2
            log.info(f'  banda {pmin}-{pmax} saturada ({len(props)}) → subdivide en '
                     f'{pmin}-{mid} y {mid}-{pmax}')
            stack.append((pmin, mid)); stack.append((mid, pmax))
            continue
        nuevos = 0
        for p in props:
            pid = str(p.get('posting_id'))
            if pid not in seen:
                seen.add(pid); props_all.append(p); nuevos += 1
        log.info(f'  banda {pmin}-{pmax}: {len(props)} avisos ({nuevos} nuevos) | '
                 f'únicos acumulados={len(props_all)}')
    return props_all, n_fuera_tot

def enrich_detalle(props):
    """Etapa 2 (detalle): direccion, lat/long, descripcion. Reutiliza ZonapropDetailScraper."""
    from zonaprop_scraper import ZonapropDetailScraper
    ds = ZonapropDetailScraper(delay=C.DELAY_DETALLE)
    def prog(cur, tot):
        if cur % 50 == 0 or cur == tot:
            log.info(f'  detalle [{cur}/{tot}] {cur/tot*100:.0f}%')
    return _con_reintentos(ds.enrich, props, on_progress=prog)

def procesar_y_guardar(con, run_id, props, ya_capturados, capture_date):
    n_new, n_exc = 0, 0
    for prop in props:
        pid_aviso = str(prop.get('posting_id'))
        if not pid_aviso or pid_aviso == 'None':
            storage.registrar_exclusion(con, run_id, pid_aviso, 'sin_posting_id'); n_exc += 1; continue
        if pid_aviso in ya_capturados:      # resume
            continue
        if prop.get('precio_valor') in (None, '', 0):
            storage.registrar_exclusion(con, run_id, pid_aviso, 'sin_precio'); n_exc += 1
            # igual lo guardamos como captura (para auditoría), sin pasar a propiedades
        # identidad (dos niveles)
        property_id = storage.property_for_posting(con, pid_aviso)
        if property_id is None:
            property_id, met_pid, conf = identidad.property_id(prop)
        else:
            row_conf = con.execute(
                'SELECT id_confianza FROM propiedades WHERE property_id=?',
                (property_id,),
            ).fetchone()
            met_pid = 'posting_map existente'
            conf = row_conf[0] if row_conf and row_conf[0] else 'posting'
        repub_id, _, _ = identidad.republication_candidate_id(prop)
        bld_id, _ = identidad.building_cluster_id(prop)
        # coordenadas
        lat, lon, geo_src = geo.consolidar_coordenadas(prop)
        in_centro = geo.en_distrito_centro(lat, lon)
        # snapshot crudo
        prop.setdefault('raw_json', {k: prop.get(k) for k in prop})
        ch = _content_hash(prop)
        # persistir
        storage.guardar_captura(
            con, run_id, prop, property_id, repub_id, bld_id, capture_date, ch
        )
        if prop.get('precio_valor') not in (None, '', 0):
            prop['barrio'] = prop.get('barrio')
            prop['direccion_norm'] = identidad.normalizar_direccion(prop.get('direccion_exacta') or '')
            geo_provider = 'zonaprop' if geo_src == 'scraped' else None
            geo_precision = 'portal' if geo_src == 'scraped' else None
            storage.upsert_propiedad(
                con, property_id, prop, lat, lon, geo_src, in_centro, capture_date,
                republication_candidate_id=repub_id,
                geo_provider=geo_provider, geo_precision=geo_precision,
                zona_validation='bbox',
            )
            con.execute('UPDATE propiedades SET building_cluster_id=?, id_confianza=? WHERE property_id=?',
                        (bld_id, conf, property_id))
            storage.map_posting(con, pid_aviso, property_id)
        n_new += 1
    con.commit()
    return n_new, n_exc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ambientes', nargs='?', type=int, help='1-5; vacío = todos')
    ap.add_argument('--resume', help='RUN_ID a reanudar')
    args = ap.parse_args()

    run_id = args.resume or C.nuevo_run_id()
    con = storage.connect(C.DB_PATH)
    capture_date = storage.start_run(con, run_id, C.ZONA_SLUG, notas='scraper_v2')
    # Una corrida nueva debe volver a observar avisos activos para construir snapshots.
    # Solo se omite lo ya guardado dentro de ESTA corrida (reanudar sin duplicar detalle).
    ya = storage.postings_in_run(con, run_id)
    if ya:
        log.info(f'{len(ya)} avisos ya guardados en {run_id} se saltean al reanudar.')

    LOTE = 50
    ambientes = C.AMBIENTES if args.ambientes is None else [a for a in C.AMBIENTES if a[0] == args.ambientes]
    total_new, total_exc, error_count = 0, 0, 0
    for amb_num, amb_label, amb_slug in ambientes:
        log.info(f'=== Ambiente: {amb_label} (recolección por bandas de precio) ===')
        try:
            props, n_fuera = recolectar_ambiente(amb_label, amb_slug)
            props = [p for p in props if str(p.get('posting_id')) not in ya]
            log.info(f'  recolectadas nuevas={len(props)}  fuera_de_zona={n_fuera}')
            # enriquecer + GUARDAR por lotes (no perder progreso ante bloqueos)
            for i in range(0, len(props), LOTE):
                lote = enrich_detalle(props[i:i+LOTE])
                n_new, n_exc = procesar_y_guardar(
                    con, run_id, lote, set(), capture_date
                )
                total_new += n_new; total_exc += n_exc
                ya.update(str(p.get('posting_id')) for p in lote)
                log.info(f'  [guardado parcial {min(i+LOTE,len(props))}/{len(props)}] '
                         f'acum nuevas={total_new} exclusiones={total_exc}')
        except Exception as e:
            error_count += 1
            log.error(f'  Ambiente {amb_label} falló (progreso parcial guardado): {e}')
    status = 'partial' if error_count else 'completed'
    storage.finish_run(con, run_id, status=status, error_count=error_count)
    log.info(f'FIN {run_id}: nuevas={total_new} exclusiones={total_exc}. DB: {C.DB_PATH}')
    con.close()

if __name__ == '__main__':
    main()
