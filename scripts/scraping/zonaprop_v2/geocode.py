#!/usr/bin/env python3
"""
geocode.py — Fase 4: geocodificación de respaldo para completar coordenadas al 100%.

Estrategia:
  1) Prioridad a las coordenadas scrapeadas (geo_source='scraped'), ya persistidas.
  2) Para las propiedades con geo_source='pendiente_geocode' (o lat NULL), geocodificar la
     dirección con un proveedor (Nominatim/OSM vía geopy), respetando rate-limit y user_agent.
  3) Cache persistente (query -> lat/lon) para no repetir pedidos; se siembra con el
     geocodificacion.csv existente (1.782 direcciones ya resueltas).
  4) Validar que el resultado caiga dentro del Distrito Centro; marcar dudosos.

El geocodificador es inyectable (para testear sin red). En producción usar NominatimGeocoder.
"""
import os, csv, time, re, html as _html
import identidad, geo

# ── normalización de la query de geocodificación ──────────────────────────────
def preparar_query(direccion: str) -> str:
    """Limpia una dirección scrapeada para geocodificar. Maneja entidades HTML,
    basura pegada (piso/edificio/aclaraciones), cruces de calles y 'al 400'.
    'Francia al 1100 - 6° Piso' -> 'Francia 1100, Rosario, Santa Fe, Argentina'
    'Cochabamba y San Martin'   -> 'Cochabamba & San Martin, Rosario, ...'
    """
    if not direccion:
        return ''
    s = _html.unescape(str(direccion))              # &#x27; &quot; -> ' "
    for sep in [' - ', ' – ', ' — ', ' | ']:         # cortar aclaración/edificio/piso
        if sep in s:
            s = s.split(sep)[0]
    s = s.split('. ')[0]
    s = re.sub(r'[\"\'`´]', ' ', s)                  # comillas
    s = re.sub(r'\b\d+\s*°.*$', '', s)               # "6° Piso ..."
    s = re.sub(r'\b(piso|depto|dpto|monoambiente|mono|ph|duplex|loft|oficina|of)\b.*$', '', s, flags=re.I)
    s = re.sub(r'\b[Aa][Ll]\b\s*', '', s)            # "al 400" -> "400"
    s = re.sub(r'\s+[yY]\s+', ' & ', s)              # cruce "Calle Y Calle" -> "Calle & Calle"
    s = re.sub(r'[^0-9A-Za-zÀ-ÿ&\s]', ' ', s)        # dejar solo letras/números/&
    s = re.sub(r'\s+', ' ', s).strip().strip('&').strip()
    if not s:
        return ''
    if 'rosario' not in s.lower():
        s = f'{s}, Rosario, Santa Fe, Argentina'
    return s

def preparar_query_calle(direccion: str) -> str:
    """Fallback a nivel calle: solo el nombre de la calle (sin altura), para
    geocodificar a nivel cuadra cuando la dirección exacta no resuelve."""
    if not direccion:
        return ''
    s = _html.unescape(str(direccion))
    for sep in [' - ', ' – ', ' — ', ' | ', ',', '.']:
        if sep in s:
            s = s.split(sep)[0]
    s = re.sub(r'[\"\'`´]', ' ', s)
    s = re.split(r'\s+[yY&]\s+', s)[0]                # primera calle del cruce
    s = re.sub(r'\d+', '', s)                          # sacar alturas
    s = re.sub(r'\b(al|piso|depto|dpto|monoambiente|mono|esquina|of|oficina)\b.*$', '', s, flags=re.I)
    s = re.sub(r'[^0-9A-Za-zÀ-ÿ\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    if not s or len(s) < 3:
        return ''
    return f'{s}, Rosario, Santa Fe, Argentina'

def reevaluar_zona(con, log=print):
    """Recalcula in_distrito_centro para todas las propiedades con coordenadas
    (correr tras ajustar el bounding box)."""
    filas = con.execute("SELECT property_id, latitud, longitud FROM propiedades WHERE latitud IS NOT NULL").fetchall()
    dentro = limpiadas = 0
    for pid, lat, lon in filas:
        if geo.en_distrito_centro(lat, lon) == 1:
            con.execute("UPDATE propiedades SET in_distrito_centro=1 WHERE property_id=?", (pid,))
            dentro += 1
        else:
            # geocode grosero guardado antes -> limpiar y devolver a pendiente
            con.execute("UPDATE propiedades SET latitud=NULL, longitud=NULL, "
                        "geo_source='pendiente_geocode', geo_provider=NULL, "
                        "geo_precision=NULL, geo_query=NULL, "
                        "in_distrito_centro=NULL WHERE property_id=?", (pid,))
            limpiadas += 1
    con.commit()
    log(f'Reevaluación de zona: {dentro} dentro del Distrito Centro | '
        f'{limpiadas} geocodes errados limpiados (vuelven a pendiente)')
    return dentro

def _key(q: str) -> str:
    return re.sub(r'\s+', ' ', str(q).lower()).strip()

# ── cache ─────────────────────────────────────────────────────────────────────
class Cache:
    def __init__(self, path):
        self.path = path
        self.d = {}
        if path and os.path.exists(path):
            with open(path, newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    q = row.get('query') or row.get('direccion')
                    try:
                        self.d[_key(q)] = (float(row['lat']), float(row.get('lon') or row.get('lng')))
                    except (TypeError, ValueError, KeyError):
                        pass
    def get(self, q):
        return self.d.get(_key(q))
    def put(self, q, lat, lon):
        self.d[_key(q)] = (lat, lon)
    def guardar(self, path=None):
        path = path or self.path
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f); w.writerow(['query', 'lat', 'lon'])
            for q, (lat, lon) in self.d.items():
                w.writerow([q, lat, lon])

# ── geocodificadores ──────────────────────────────────────────────────────────
class GeorefGeocoder:
    """Geocodificador oficial argentino (apis.datos.gob.ar/georef). Mejor para
    direcciones de Argentina que Nominatim. Gratuito, sin API key."""
    URL = 'https://apis.datos.gob.ar/georef/api/direcciones'
    provider = 'georef'
    precision = 'address'
    def __init__(self, delay=0.3, provincia='santa fe', localidad='rosario'):
        import requests
        self._get = requests.get
        self.delay = delay
        self.prov = provincia
        self.loc = localidad
    def __call__(self, query):
        calle = query.split(',')[0].strip()   # Georef quiere solo "Calle Altura"
        params = {'direccion': calle, 'provincia': self.prov,
                  'localidad': self.loc, 'max': 1}
        try:
            r = self._get(self.URL, params=params, timeout=10)
            time.sleep(self.delay)
            ds = (r.json() or {}).get('direcciones') or []
            if ds:
                u = ds[0].get('ubicacion') or {}
                if u.get('lat') and u.get('lon'):
                    return (float(u['lat']), float(u['lon']))
        except Exception:
            return None
        return None

class NominatimGeocoder:
    """Wrapper de geopy/Nominatim con rate-limit (1 req/s) y user_agent (requisito de OSM)."""
    def __init__(self, user_agent='tesis-avm-rosario', delay=1.1):
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
        self._geo = Nominatim(user_agent=user_agent)
        self._call = RateLimiter(self._geo.geocode, min_delay_seconds=delay,
                                 max_retries=2, error_wait_seconds=5.0)
        self.provider = 'nominatim'
        self.precision = 'address_unverified'
    def __call__(self, query):
        loc = self._call(query, country_codes='ar', addressdetails=False, timeout=10)
        return (loc.latitude, loc.longitude) if loc else None

# ── proceso principal ─────────────────────────────────────────────────────────
def geocodificar_pendientes(con, geocoder, cache, log=print, checkpoint=100,
                            query_fn=None, precision=None):
    """Completa lat/lon de propiedades sin coordenadas. Devuelve (ok, fuera_centro, fallidas).
    Muestra progreso y persiste (commit DB + guarda cache) cada `checkpoint` filas.
    query_fn: función que construye la query desde la dirección (por defecto preparar_query;
    usar preparar_query_calle para el fallback a nivel calle)."""
    query_fn = query_fn or preparar_query
    provider = getattr(geocoder, 'provider', 'unknown') if geocoder else 'cache'
    geo_precision = precision or getattr(geocoder, 'precision', 'unknown')
    filas = con.execute("""
        SELECT property_id, direccion_exacta FROM propiedades
        WHERE (latitud IS NULL OR geo_source='pendiente_geocode') AND direccion_exacta IS NOT NULL
    """).fetchall()
    total = len(filas)
    log(f'A geocodificar: {total} propiedades pendientes')
    ok = fuera = fail = 0
    for i, (property_id, direccion) in enumerate(filas, 1):
        q = query_fn(direccion)
        if not q:
            fail += 1
        else:
            res = cache.get(q)
            if res is None and geocoder is not None:
                try:
                    res = geocoder(q)
                    if res: cache.put(q, res[0], res[1])
                except Exception as e:
                    log(f'  geocode fallo [{q}]: {e}'); res = None
            if not res:
                fail += 1
            else:
                lat, lon = res
                if geo.en_distrito_centro(lat, lon) == 1:
                    con.execute("""
                        UPDATE propiedades
                        SET latitud=?, longitud=?, geo_source='geocoded',
                            geo_provider=?, geo_precision=?, geo_query=?,
                            zona_validation='bbox', in_distrito_centro=1
                        WHERE property_id=?
                    """, (lat, lon, provider, geo_precision, q, property_id))
                    ok += 1
                else:
                    fuera += 1    # geocode fuera de Rosario central -> se descarta (queda pendiente)
        if i % 50 == 0 or i == total:
            log(f'  [{i}/{total}] ok={ok} fuera_centro={fuera} fallidas={fail}')
        if i % checkpoint == 0:          # persistencia incremental
            con.commit()
            if cache.path: cache.guardar()
    con.commit()
    if cache.path: cache.guardar()
    log(f'Geocodificación: ok={ok} (fuera_centro={fuera}) fallidas={fail}')
    return ok, fuera, fail
