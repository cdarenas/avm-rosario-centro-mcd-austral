#!/usr/bin/env python3
"""
storage.py — Capa de almacenamiento del scraper v2 (esquema objetivo de la tesis).

Diseño (Fase 1):
  - capturas: un registro por aviso POR corrida (snapshot). Permite historial de precios
    y detección de republicaciones. Guarda el JSON crudo para re-parsear sin re-scrapear.
  - propiedades: identidad conservadora por publicación (property_id), con coordenadas
    persistidas. Las posibles republicaciones se registran como candidatos auditables.
  - posting_property_map: relación estable posting_id -> property_id.
  - exclusiones: motivo de descarte por aviso (no perder datos en silencio).

Todo con capture_date y run_id para trazabilidad y ventana temporal.
"""
import sqlite3
import json
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS capturas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL,
    posting_id     TEXT NOT NULL,
    property_id    TEXT,
    republication_candidate_id TEXT,
    building_cluster_id TEXT,               -- nivel edificio/cuadra (group-aware split)
    capture_date   TEXT NOT NULL,           -- ISO8601 UTC de la captura
    fecha_publicacion TEXT,
    precio_valor   REAL,
    precio_moneda  TEXT,
    estado         TEXT,                     -- activo / pausado / vendido / desconocido
    content_hash   TEXT,                     -- hash del contenido relevante (detectar cambios)
    raw_json       TEXT,                     -- snapshot del __NEXT_DATA__ / dict crudo
    UNIQUE(run_id, posting_id)
);
CREATE INDEX IF NOT EXISTS ix_capturas_posting ON capturas(posting_id);
CREATE INDEX IF NOT EXISTS ix_capturas_property ON capturas(property_id);
CREATE INDEX IF NOT EXISTS ix_capturas_fecha ON capturas(capture_date);

CREATE TABLE IF NOT EXISTS propiedades (
    property_id            TEXT PRIMARY KEY,
    republication_candidate_id TEXT,
    building_cluster_id    TEXT,             -- para group-aware splitting (nivel edificio)
    id_confianza           TEXT,             -- 'posting' (actual) | valores legacy
    posting_id_ultimo      TEXT,
    tipo_operacion         TEXT,
    url                    TEXT,
    titulo                 TEXT,
    -- localización
    direccion_exacta       TEXT,
    direccion_norm         TEXT,
    barrio                 TEXT,
    latitud                REAL,
    longitud               REAL,
    geo_source             TEXT,             -- 'scraped' | 'geocoded' | 'none'
    geo_provider           TEXT,             -- zonaprop | georef | nominatim
    geo_precision          TEXT,             -- portal | address | street | unknown
    geo_query              TEXT,             -- query utilizada para geocodificar
    zona_validation        TEXT,             -- bbox | polygon | portal_filter
    in_distrito_centro     INTEGER,          -- 1/0/NULL (validación point-in-polygon)
    -- estructurales
    superficie_total_m2    REAL,
    superficie_cubierta_m2 REAL,
    ambientes              INTEGER,
    dormitorios            INTEGER,
    banos                  INTEGER,
    cocheras               INTEGER,
    toilette               INTEGER,
    antiguedad             TEXT,
    disposicion            TEXT,
    orientacion            TEXT,
    expensas_valor         REAL,
    descripcion_completa   TEXT,
    inmobiliaria           TEXT,
    -- trazabilidad / historial
    first_seen             TEXT,
    last_seen              TEXT,
    n_capturas             INTEGER DEFAULT 0,
    precio_ultimo          REAL,
    precio_moneda          TEXT,
    precio_min             REAL,
    precio_max             REAL,
    cambios_precio         INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_prop_barrio ON propiedades(barrio);

CREATE TABLE IF NOT EXISTS posting_property_map (
    posting_id   TEXT PRIMARY KEY,
    property_id  TEXT NOT NULL,
    first_seen   TEXT
);

CREATE TABLE IF NOT EXISTS exclusiones (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT,
    posting_id   TEXT,
    capture_date TEXT,
    motivo       TEXT,                       -- fuera_de_zona / sin_precio / parsing_error / duplicado / ...
    detalle      TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    started_at   TEXT,
    finished_at  TEXT,
    zona         TEXT,
    n_capturas   INTEGER,
    n_propiedades INTEGER,
    n_exclusiones INTEGER,
    status        TEXT DEFAULT 'running',     -- running | completed | partial | failed
    error_count   INTEGER DEFAULT 0,
    notas        TEXT
);
"""

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def connect(db_path):
    con = sqlite3.connect(db_path, timeout=60)   # espera hasta 60s si está bloqueada
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=60000")
    con.executescript(SCHEMA)
    _ensure_column(con, 'propiedades', 'geo_provider', 'TEXT')
    _ensure_column(con, 'propiedades', 'geo_precision', 'TEXT')
    _ensure_column(con, 'propiedades', 'geo_query', 'TEXT')
    _ensure_column(con, 'propiedades', 'zona_validation', 'TEXT')
    _ensure_column(con, 'runs', 'status', "TEXT DEFAULT 'running'")
    _ensure_column(con, 'runs', 'error_count', 'INTEGER DEFAULT 0')
    _ensure_column(con, 'capturas', 'republication_candidate_id', 'TEXT')
    _ensure_column(con, 'propiedades', 'republication_candidate_id', 'TEXT')
    return con

def start_run(con, run_id, zona, notas=""):
    started_at = now_iso()
    con.execute("""
        INSERT OR IGNORE INTO runs(run_id, started_at, zona, status, error_count, notas)
        VALUES (?,?,?,'running',0,?)
    """, (run_id, started_at, zona, notas))
    con.commit()
    return con.execute("SELECT started_at FROM runs WHERE run_id=?", (run_id,)).fetchone()[0]

def registrar_exclusion(con, run_id, posting_id, motivo, detalle="", capture_date=None):
    con.execute("INSERT INTO exclusiones(run_id, posting_id, capture_date, motivo, detalle) VALUES (?,?,?,?,?)",
                (run_id, posting_id, capture_date or now_iso(), motivo, detalle))

def guardar_captura(con, run_id, prop, property_id, republication_candidate_id,
                    building_cluster_id, capture_date, content_hash):
    """Inserta un snapshot en 'capturas'. prop es el dict del aviso."""
    con.execute("""
        INSERT OR IGNORE INTO capturas
        (run_id, posting_id, property_id, republication_candidate_id,
         building_cluster_id, capture_date, fecha_publicacion,
         precio_valor, precio_moneda, estado, content_hash, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        run_id, str(prop.get('posting_id')), property_id, republication_candidate_id,
        building_cluster_id, capture_date,
        prop.get('fecha_publicacion'),
        _num(prop.get('precio_valor')), prop.get('precio_moneda'),
        prop.get('estado', 'desconocido'), content_hash,
        json.dumps(prop.get('raw_json') or {}, ensure_ascii=False),
    ))

def upsert_propiedad(con, property_id, prop, lat, lon, geo_source, in_centro, capture_date,
                     republication_candidate_id=None,
                     geo_provider=None, geo_precision=None, geo_query=None,
                     zona_validation='bbox'):
    """Crea o actualiza la identidad física y su historial de precios."""
    precio = _num(prop.get('precio_valor'))
    row = con.execute("""
        SELECT n_capturas, precio_min, precio_max, precio_ultimo
        FROM propiedades WHERE property_id=?
    """,
                      (property_id,)).fetchone()
    if row is None:
        con.execute("""
            INSERT INTO propiedades
            (property_id, republication_candidate_id, posting_id_ultimo, tipo_operacion, url, titulo,
             direccion_exacta, direccion_norm, barrio, latitud, longitud, geo_source,
             geo_provider, geo_precision, geo_query, zona_validation, in_distrito_centro,
             superficie_total_m2, superficie_cubierta_m2, ambientes, dormitorios, banos, cocheras, toilette,
             antiguedad, disposicion, orientacion, expensas_valor, descripcion_completa, inmobiliaria,
             first_seen, last_seen, n_capturas, precio_ultimo, precio_moneda, precio_min, precio_max, cambios_precio)
            VALUES (?,?,?,?,?,? ,?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?)
        """, (
            property_id, republication_candidate_id, str(prop.get('posting_id')),
            prop.get('tipo_operacion'), prop.get('url'), prop.get('titulo'),
            prop.get('direccion_exacta'), prop.get('direccion_norm'), prop.get('barrio'), lat, lon, geo_source,
            geo_provider, geo_precision, geo_query, zona_validation, in_centro,
            _num(prop.get('superficie_total_m2')), _num(prop.get('superficie_cubierta_m2')),
            _int(prop.get('ambientes')), _int(prop.get('dormitorios')), _int(prop.get('banos')),
            _int(prop.get('cocheras')), _int(prop.get('toilette')),
            prop.get('antiguedad'), prop.get('disposicion'), prop.get('orientacion'),
            _num(prop.get('expensas_valor')), prop.get('descripcion_completa'), prop.get('inmobiliaria'),
            capture_date, capture_date, 1, precio, prop.get('precio_moneda'), precio, precio, 0,
        ))
    else:
        n, pmin, pmax, pult = row
        cambio = 1 if (precio is not None and pult is not None and precio != pult) else 0
        con.execute("""
            UPDATE propiedades SET
              posting_id_ultimo=?, last_seen=?, n_capturas=n_capturas+1,
              precio_ultimo=?, precio_min=MIN(COALESCE(precio_min,?),COALESCE(?,precio_min)),
              precio_max=MAX(COALESCE(precio_max,?),COALESCE(?,precio_max)),
              cambios_precio=cambios_precio+?,
              latitud=CASE WHEN ?='scraped' THEN ? ELSE COALESCE(latitud,?) END,
              longitud=CASE WHEN ?='scraped' THEN ? ELSE COALESCE(longitud,?) END,
              geo_source=CASE
                WHEN ?='scraped' THEN 'scraped'
                WHEN geo_source IS NULL OR geo_source='pendiente_geocode' THEN ?
                ELSE geo_source END,
              geo_provider=CASE WHEN ?='scraped' THEN ? ELSE COALESCE(geo_provider,?) END,
              geo_precision=CASE WHEN ?='scraped' THEN ? ELSE COALESCE(geo_precision,?) END,
              zona_validation=COALESCE(zona_validation,?),
              in_distrito_centro=COALESCE(in_distrito_centro,?)
            WHERE property_id=?
        """, (str(prop.get('posting_id')), capture_date, precio,
              precio, precio, precio, precio, cambio,
              geo_source, lat, lat, geo_source, lon, lon,
              geo_source, geo_source,
              geo_source, geo_provider, geo_provider,
              geo_source, geo_precision, geo_precision,
              zona_validation, in_centro, property_id))

def map_posting(con, posting_id, property_id):
    con.execute("INSERT OR IGNORE INTO posting_property_map(posting_id, property_id, first_seen) VALUES (?,?,?)",
                (str(posting_id), property_id, now_iso()))

def property_for_posting(con, posting_id):
    row = con.execute(
        "SELECT property_id FROM posting_property_map WHERE posting_id=?",
        (str(posting_id),),
    ).fetchone()
    return row[0] if row else None

def postings_in_run(con, run_id):
    return {
        row[0] for row in con.execute(
            "SELECT DISTINCT posting_id FROM capturas WHERE run_id=?", (run_id,)
        )
    }

def finish_run(con, run_id, status='completed', error_count=0):
    n_cap = con.execute("SELECT COUNT(*) FROM capturas WHERE run_id=?", (run_id,)).fetchone()[0]
    n_prop = con.execute(
        "SELECT COUNT(DISTINCT property_id) FROM capturas WHERE run_id=? AND property_id IS NOT NULL",
        (run_id,),
    ).fetchone()[0]
    n_exc = con.execute("SELECT COUNT(*) FROM exclusiones WHERE run_id=?", (run_id,)).fetchone()[0]
    con.execute("""
        UPDATE runs
        SET finished_at=?, n_capturas=?, n_propiedades=?, n_exclusiones=?,
            status=?, error_count=?
        WHERE run_id=?
    """, (now_iso(), n_cap, n_prop, n_exc, status, error_count, run_id))
    con.commit()

def _ensure_column(con, table, column, definition):
    existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def _num(x):
    try: return float(x)
    except (TypeError, ValueError): return None
def _int(x):
    v=_num(x)
    return int(v) if v is not None else None
