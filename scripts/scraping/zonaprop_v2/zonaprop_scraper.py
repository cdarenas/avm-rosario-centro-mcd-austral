"""
Scraper de Zonaprop - Departamentos en venta
Extrae datos completos de propiedades desde los listados de Zonaprop.

Estrategia de extracción (doble fuente):
  1. __NEXT_DATA__ JSON: ZonaProp es una app Next.js que embebe todos los datos
     de las propiedades como JSON en el HTML. Es la fuente más rica y confiable.
  2. HTML fallback: Si el JSON no está disponible, parsea las tarjetas HTML.

Campos extraídos (~30):
  IDs, URL, título, precio, moneda, expensas, superficie total/cubierta,
  ambientes, dormitorios, baños, cocheras, antigüedad, piso, orientación,
  disposición, condición, ubicación completa (calle, barrio, ciudad,
  provincia, lat/lng), publicadora (nombre, tipo, teléfono, whatsapp),
  imágenes (cantidad + URLs), descripción, estado, tipo de publicación,
  destacado, fecha de modificación, etiquetas/flags.

Uso:
    python zonaprop_scraper.py --zona rosario --ambientes 1
    python zonaprop_scraper.py --zona palermo --ambientes 2 --paginas 5
    python zonaprop_scraper.py --url https://www.zonaprop.com.ar/...

Instalación de dependencias:
    pip install cloudscraper pandas beautifulsoup4 lxml
"""

import json
import re
import time
import argparse
from datetime import datetime
from pathlib import Path

import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup


# ─── Mapeos de zonas y ambientes ────────────────────────────────────────────

ZONAS = {
    "rosario": "rosario", "rosario-norte": "rosario-norte",
    "rosario-sur": "rosario-sur", "rosario-centro": "rosario-centro",
    "palermo": "palermo", "belgrano": "belgrano", "recoleta": "recoleta",
    "caballito": "caballito", "villa-crespo": "villa-crespo",
    "almagro": "almagro", "flores": "flores", "san-telmo": "san-telmo",
    "microcentro": "microcentro", "puerto-madero": "puerto-madero",
    "nuñez": "nunez", "nunez": "nunez", "colegiales": "colegiales",
    "villa-urquiza": "villa-urquiza", "barracas": "barracas", "boedo": "boedo",
    "capital-federal": "capital-federal", "caba": "capital-federal",
    "gba-norte": "zona-norte", "gba-sur": "zona-sur", "gba-oeste": "zona-oeste",
    "cordoba": "cordoba", "mendoza": "mendoza",
    "mar-del-plata": "mar-del-plata", "salta": "salta", "tucuman": "tucuman",
}

AMBIENTES = {
    1: "1-ambiente", 2: "2-ambientes", 3: "3-ambientes",
    4: "4-ambientes", 5: "5-ambientes-o-mas",
}

# Mapeo de claves de antigüedad a texto legible
ANTIGUEDAD_MAP = {
    "A_ESTRENAR": "A estrenar",
    "LESS_THAN_5": "Menos de 5 años",
    "BETWEEN_5_AND_10": "Entre 5 y 10 años",
    "BETWEEN_10_AND_20": "Entre 10 y 20 años",
    "BETWEEN_20_AND_50": "Entre 20 y 50 años",
    "MORE_THAN_50": "Más de 50 años",
}


def build_url(zona: str, ambientes: int) -> str:
    zona_slug = ZONAS.get(zona.lower().replace(" ", "-"), zona.lower().replace(" ", "-"))
    amb_slug = AMBIENTES.get(ambientes, f"{ambientes}-ambientes")
    return f"https://www.zonaprop.com.ar/departamentos-venta-{zona_slug}-{amb_slug}.html"


# ─── Helpers ────────────────────────────────────────────────────────────────

def safe_get(d, *keys, default=None):
    """Navega un dict anidado sin errores. Ej: safe_get(d, 'a', 'b', 'c')"""
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, default)
        if d is None:
            return default
    return d


def parse_currency_text(text: str):
    """Extrae valor numérico y moneda de un string de precio."""
    if not text:
        return None, None
    try:
        numbers = re.findall(r'[\d.]+', text)
        if numbers:
            value_str = numbers[0].replace('.', '')
            value = int(value_str) if value_str.isdigit() else None
        else:
            value = None
        if 'USD' in text.upper() or 'U$S' in text or 'US$' in text:
            currency = 'USD'
        elif 'ARS' in text.upper() or '$' in text:
            currency = 'ARS'
        else:
            currency = None
        return value, currency
    except Exception:
        return None, None


# Textos que parecen un título pero en realidad no lo son.
# Se usan en parse_property_from_html para descartar falsos títulos del HTML.

# ① Precio directo o variante "desde":
#    "USD 164.000" / "Departamentos desdeUSD 66.000" / "Cocheras y deptos desdeUSD 20.000"
_PRICE_TEXT_RE = re.compile(
    r'(USD|U\$S|US\$|ARS|\$|€)\s*[\d.,]+',
    re.IGNORECASE,
)

# ② Texto de características (lo que ZonaProp pone en el h2 del card HTML):
#    "174 m² tot.3 amb.2 dorm.2 baños1 coch."
#    "3 amb.2 dorm.1 baño"
_FEATURES_TEXT_RE = re.compile(
    r'(\d+\s*m[²2]|\d+\s*amb\.?\s*\d+\s*dorm)',
    re.IGNORECASE,
)

# ③ Placeholder sin precio real:
#    "Consultar precio" / "Consultar"
_CONSULT_TEXT_RE = re.compile(
    r'^\s*consultar',
    re.IGNORECASE,
)


def _is_false_title(text: str) -> bool:
    """Devuelve True si el texto NO es un título real de una publicación."""
    if not text:
        return True
    return bool(
        _PRICE_TEXT_RE.search(text)
        or _FEATURES_TEXT_RE.search(text)
        or _CONSULT_TEXT_RE.match(text)
    )


def parse_features_text(text: str) -> dict:
    """Parsea m², ambientes, baños, cocheras de texto de características."""
    features = {}
    unit_map = {
        'm²': 'superficie_m2', 'm2': 'superficie_m2',
        'amb': 'ambientes', 'dorm': 'dormitorios',
        'baño': 'banos', 'baños': 'banos', 'coch': 'cocheras',
    }
    for unit_key, feature_name in unit_map.items():
        pattern = rf'(\d+(?:\.\d+)?)\s*{re.escape(unit_key)}'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                num = match.group(1)
                features[feature_name] = float(num) if '.' in num else int(num)
            except ValueError:
                pass
    return features


# ─── Parser de __NEXT_DATA__ ────────────────────────────────────────────────

def extract_next_data(soup: BeautifulSoup) -> list:
    """
    Extrae los datos completos de propiedades desde el JSON __NEXT_DATA__
    que Next.js inyecta en el HTML. Retorna lista de propiedades normalizadas.
    """
    script = soup.find('script', id='__NEXT_DATA__')
    if not script:
        return []

    try:
        data = json.loads(script.string)
    except (json.JSONDecodeError, TypeError):
        return []

    # Intentar múltiples rutas posibles hacia el listado de propiedades
    listings = None
    search_paths = [
        ['props', 'pageProps', 'initialState', 'listPostings', 'listPostings'],
        ['props', 'pageProps', 'listPostings'],
        ['props', 'pageProps', 'initialState', 'listPostings'],
        ['props', 'pageProps', 'postings'],
    ]
    for path in search_paths:
        candidate = safe_get(data, *path)
        if isinstance(candidate, list) and len(candidate) > 0:
            listings = candidate
            break

    # Búsqueda recursiva si no encontramos nada con rutas conocidas
    if listings is None:
        listings = _find_listings_recursive(data)

    if not listings:
        return []

    properties = []
    for listing in listings:
        try:
            prop = parse_listing_from_json(listing)
            if prop:
                properties.append(prop)
        except Exception as e:
            print(f"  [JSON] Error parseando propiedad: {e}")
            continue

    return properties


def _find_listings_recursive(obj, depth=0, max_depth=8):
    """Busca recursivamente una lista de dicts con 'postingId' o 'url'."""
    if depth > max_depth:
        return None
    if isinstance(obj, list) and len(obj) > 0:
        first = obj[0]
        if isinstance(first, dict) and (
            'postingId' in first or 'posting_id' in first
            or ('url' in first and 'price' in str(first).lower())
        ):
            return obj
    if isinstance(obj, dict):
        for val in obj.values():
            result = _find_listings_recursive(val, depth + 1, max_depth)
            if result:
                return result
    return None


def parse_listing_from_json(p: dict) -> dict:
    """
    Normaliza un objeto de propiedad del JSON de ZonaProp a un dict plano
    con todos los campos posibles.
    """
    prop = {}

    # ── IDs y URL ──────────────────────────────────────────────────────────
    prop['posting_id']   = p.get('postingId') or p.get('id')
    prop['posting_code'] = p.get('postingCode') or p.get('code')

    url = p.get('url') or p.get('postingUrl') or p.get('link')
    if url:
        prop['url'] = url if url.startswith('http') else f"https://www.zonaprop.com.ar{url}"

    # ── Título y descripción ───────────────────────────────────────────────
    prop['titulo']      = p.get('title') or p.get('headline')
    prop['descripcion'] = (
        p.get('descriptionNormalized')
        or p.get('description')
        or safe_get(p, 'houseInfo', 'description')
    )

    # ── Precio ────────────────────────────────────────────────────────────
    # Estructura: priceOperationTypes[0].prices[0]
    price_ops = p.get('priceOperationTypes') or []
    if price_ops and isinstance(price_ops, list):
        first_op = price_ops[0]
        prop['tipo_operacion'] = safe_get(first_op, 'operationType', 'name') or first_op.get('name')
        prices = first_op.get('prices', [])
        if prices:
            pr = prices[0]
            prop['precio_moneda'] = pr.get('currency')
            prop['precio_valor']  = pr.get('amount')
            prop['precio_texto']  = (
                f"{pr.get('currency', '')} {pr.get('amount', '')}".strip()
                if pr.get('amount') else None
            )
            prop['precio_periodo'] = pr.get('period')  # null para venta, "MONTHLY" para alquiler
    else:
        # Alternativa plana
        prop['precio_valor']  = p.get('price') or p.get('priceAmount')
        prop['precio_moneda'] = p.get('currency') or p.get('priceCurrency')

    # ── Expensas ──────────────────────────────────────────────────────────
    expenses = p.get('expenses') or p.get('maintenanceFee') or {}
    if isinstance(expenses, dict):
        prop['expensas_valor']  = expenses.get('amount')
        prop['expensas_moneda'] = expenses.get('currency')
        if expenses.get('amount'):
            prop['expensas_texto'] = f"{expenses.get('currency', '')} {expenses.get('amount', '')}".strip()
    elif isinstance(expenses, (int, float)):
        prop['expensas_valor'] = expenses

    # ── Características principales ────────────────────────────────────────
    main_feat = p.get('mainFeatures') or {}
    # superficie
    prop['superficie_total_m2']   = (
        safe_get(main_feat, 'totalSurface', 'value')
        or safe_get(main_feat, 'roofedSurface', 'value')
        or main_feat.get('surface')
    )
    prop['superficie_cubierta_m2'] = safe_get(main_feat, 'coveredSurface', 'value')
    # ambientes
    prop['ambientes']    = safe_get(main_feat, 'rooms', 'value')     or main_feat.get('rooms')
    prop['dormitorios']  = safe_get(main_feat, 'bedrooms', 'value')  or main_feat.get('bedrooms')
    prop['banos']        = safe_get(main_feat, 'bathrooms', 'value') or main_feat.get('bathrooms')
    prop['toilettes']    = safe_get(main_feat, 'toilettes', 'value')
    prop['cocheras']     = safe_get(main_feat, 'parkingLots', 'value') or main_feat.get('parkingLots')
    # piso y otros
    prop['piso']         = safe_get(main_feat, 'floor', 'value')     or main_feat.get('floor')
    prop['orientacion']  = safe_get(main_feat, 'orientation', 'label')
    prop['disposicion']  = safe_get(main_feat, 'disposition', 'label')
    prop['condicion']    = safe_get(main_feat, 'condition', 'label')

    # ── Antigüedad ────────────────────────────────────────────────────────
    antiquity = p.get('antiquity') or {}
    if isinstance(antiquity, dict):
        ant_key = antiquity.get('key') or antiquity.get('type')
        prop['antiguedad'] = ANTIGUEDAD_MAP.get(ant_key, ant_key)
        prop['antiguedad_anios'] = antiquity.get('years') or antiquity.get('value')
    elif isinstance(antiquity, str):
        prop['antiguedad'] = ANTIGUEDAD_MAP.get(antiquity, antiquity)

    # ── Características generales (amenities) ─────────────────────────────
    general_feat = p.get('generalFeatures') or []
    if general_feat:
        labels = [
            f.get('label') or f.get('name') or f.get('value')
            for f in general_feat if isinstance(f, dict)
        ]
        prop['amenities'] = ' | '.join(filter(None, labels))

    # ── Características destacadas ────────────────────────────────────────
    highlighted = p.get('highlightedFeatures') or []
    if highlighted:
        labels = [
            f.get('label') or f.get('name')
            for f in highlighted if isinstance(f, dict)
        ]
        prop['caracteristicas_destacadas'] = ' | '.join(filter(None, labels))

    # ── Flags / etiquetas ─────────────────────────────────────────────────
    flags = p.get('flagsFeatures') or p.get('flags') or []
    if flags:
        if isinstance(flags, list):
            flag_labels = [
                f.get('label') or f.get('name') or (f if isinstance(f, str) else None)
                for f in flags
            ]
            prop['flags'] = ' | '.join(filter(None, flag_labels))
        elif isinstance(flags, dict):
            prop['flags'] = ' | '.join(k for k, v in flags.items() if v)

    # ── Ubicación ─────────────────────────────────────────────────────────
    location = p.get('postingLocation') or p.get('location') or {}
    if isinstance(location, dict):
        prop['direccion']  = location.get('address') or location.get('street')
        prop['barrio']     = (
            safe_get(location, 'neighbourhood', 'name')
            or location.get('neighborhood')
            or location.get('neighbourhood')
        )
        prop['ciudad']     = (
            safe_get(location, 'city', 'name')
            or location.get('city')
        )
        prop['provincia']  = (
            safe_get(location, 'state', 'name')
            or location.get('state')
            or location.get('province')
        )
        prop['pais']       = safe_get(location, 'country', 'name') or location.get('country')

        # Coordenadas — ZonaProp usa distintas claves según la versión del JSON
        prop['latitud'] = (
            location.get('latitude')
            or location.get('lat')
            or safe_get(location, 'geoLocation', 'lat')
            or safe_get(location, 'geoPoint',    'lat')
            or safe_get(location, 'point',       'lat')
            or safe_get(location, 'geo',         'lat')
            or safe_get(p, 'geo', 'lat')
            or safe_get(p, 'geoLocation', 'lat')
        )
        prop['longitud'] = (
            location.get('longitude')
            or location.get('lng')
            or location.get('lon')
            or safe_get(location, 'geoLocation', 'lng')
            or safe_get(location, 'geoPoint',    'lng')
            or safe_get(location, 'point',       'lng')
            or safe_get(location, 'geo',         'lng')
            or safe_get(p, 'geo', 'lng')
            or safe_get(p, 'geoLocation', 'lng')
        )
        # Ubicación completa como string
        parts = filter(None, [prop.get('direccion'), prop.get('barrio'),
                               prop.get('ciudad'), prop.get('provincia')])
        prop['ubicacion_completa'] = ', '.join(parts) or None

    # ── Publicadora ───────────────────────────────────────────────────────
    publisher = p.get('publisher') or p.get('agency') or p.get('realEstate') or {}
    if isinstance(publisher, dict):
        prop['publicadora_nombre'] = publisher.get('name')
        prop['publicadora_tipo']   = (
            publisher.get('publisherType')
            or publisher.get('type')
            or publisher.get('realEstateType')
        )
        prop['publicadora_logo']   = publisher.get('logo') or publisher.get('urlLogo')
        prop['whatsapp']           = publisher.get('whatsapp') or publisher.get('whatsappPhone')

        # Teléfonos
        phones = publisher.get('phones') or publisher.get('phoneNumbers') or []
        if isinstance(phones, list) and phones:
            ph = phones[0]
            if isinstance(ph, dict):
                area = ph.get('area') or ph.get('areaCode', '')
                number = ph.get('number') or ph.get('phone', '')
                prop['publicadora_telefono'] = f"{area}{number}".strip() or None
            elif isinstance(ph, str):
                prop['publicadora_telefono'] = ph

    # ── Imágenes ──────────────────────────────────────────────────────────
    pictures = (
        p.get('visiblePictures')
        or p.get('pictures')
        or p.get('images')
        or []
    )
    if isinstance(pictures, list):
        prop['imagenes_cantidad'] = len(pictures)
        urls = []
        for pic in pictures:
            if isinstance(pic, dict):
                img_url = (pic.get('url') or pic.get('src')
                           or safe_get(pic, 'image', 'url')
                           or safe_get(pic, 'thumbnail', 'url'))
                if img_url:
                    urls.append(img_url)
            elif isinstance(pic, str):
                urls.append(pic)
        prop['imagenes_urls'] = ' | '.join(urls) if urls else None

    # ── Estado, tipo, fechas ───────────────────────────────────────────────
    prop['estado']             = p.get('status') or p.get('availability')
    prop['tipo_publicacion']   = p.get('postingType') or p.get('listingType')
    prop['destacado']          = p.get('premier') or p.get('featured') or p.get('isPremier')
    prop['slot']               = p.get('slot')
    prop['slot_color']         = p.get('slotColor')
    prop['unidades']           = p.get('units')
    modified = p.get('modifiedDate') or p.get('updatedAt') or p.get('lastModified')
    prop['fecha_modificacion'] = str(modified) if modified else None

    # ── Limpiar Nones de campos string vacíos ─────────────────────────────
    return {k: v for k, v in prop.items() if v is not None and v != '' and v != []}


# ─── Fallback: parser HTML ───────────────────────────────────────────────────

def parse_property_from_html(element) -> dict:
    """Parser HTML de respaldo cuando __NEXT_DATA__ no está disponible."""
    prop = {}

    # IDs y tipo
    prop['posting_id']     = element.get('data-id') or element.get('data-posting-id')
    prop['tipo_operacion'] = element.get('data-posting-type')

    # URL
    url = element.get('data-to-posting') or element.get('data-id')
    if url:
        prop['url'] = f"https://www.zonaprop.com.ar{url}" if url.startswith('/') else url
    else:
        link = element.find('a', href=True)
        if link:
            href = link['href']
            prop['url'] = href if href.startswith('http') else f"https://www.zonaprop.com.ar{href}"

    # Título — se toma lo que ZonaProp expone en el card (precio, features, etc.)
    for qa in ['POSTING_CARD_TITLE', 'posting-card-title']:
        t = element.find(attrs={'data-qa': qa})
        if t:
            txt = t.get_text(strip=True)
            if txt:
                prop['titulo'] = txt
                break
    if 'titulo' not in prop:
        for h in element.find_all(['h2', 'h3']):
            txt = h.get_text(strip=True)
            if txt:
                prop['titulo'] = txt
                break

    # Precio
    price_elem = element.find(attrs={'data-qa': 'POSTING_CARD_PRICE'})
    if price_elem:
        price_text = price_elem.get_text(strip=True)
        prop['precio_texto'] = price_text
        val, cur = parse_currency_text(price_text)
        prop['precio_valor'], prop['precio_moneda'] = val, cur

    # Expensas
    exp_elem = element.find(attrs={'data-qa': 'expensas'})
    if exp_elem:
        exp_text = exp_elem.get_text(strip=True)
        prop['expensas_texto'] = exp_text
        val, _ = parse_currency_text(exp_text)
        prop['expensas_valor'] = val

    # Ubicación
    loc_elem = element.find(attrs={'data-qa': 'POSTING_CARD_LOCATION'})
    if loc_elem:
        prop['ubicacion_completa'] = loc_elem.get_text(separator=' ', strip=True)

    # Descripción
    desc_elem = element.find(attrs={'data-qa': 'POSTING_CARD_DESCRIPTION'})
    if desc_elem:
        prop['descripcion'] = desc_elem.get_text(separator=' ', strip=True)

    # Características físicas
    feat_elem = element.find(attrs={'data-qa': 'POSTING_CARD_FEATURES'})
    if feat_elem:
        prop.update(parse_features_text(feat_elem.get_text()))

    # Imágenes
    imgs = element.find_all('img', src=True)
    img_urls = [
        i['src'] for i in imgs
        if i['src'].startswith('http') and 'logo' not in i['src'].lower()
    ]
    if img_urls:
        prop['imagenes_cantidad'] = len(img_urls)
        prop['imagenes_urls'] = ' | '.join(img_urls)

    # Publicadora
    for qa in ['POSTING_CARD_PUBLISHER', 'publisher-name']:
        pub = element.find(attrs={'data-qa': qa})
        if pub:
            prop['publicadora_nombre'] = pub.get_text(strip=True)
            break

    # Destacado / premier
    premier = element.find(class_=re.compile(r'premier|premium|featured', re.I))
    if premier:
        prop['destacado'] = True

    # Coordenadas — ZonaProp a veces las embebe como data-attributes en el card
    lat = (
        element.get('data-latitude')
        or element.get('data-lat')
        or element.get('data-posting-latitude')
    )
    lon = (
        element.get('data-longitude')
        or element.get('data-lng')
        or element.get('data-lon')
        or element.get('data-posting-longitude')
    )
    if lat and lon:
        prop['latitud']  = lat
        prop['longitud'] = lon

    # Barrio desde data-attributes o child elements
    barrio_attr = element.get('data-neighborhood') or element.get('data-barrio')
    if barrio_attr:
        prop['barrio'] = barrio_attr

    return {k: v for k, v in prop.items() if v is not None and v != ''}


# ─── Scraper principal ────────────────────────────────────────────────────────

class ZonapropScraper:

    def __init__(self):
        self.scraper = cloudscraper.create_scraper()
        self.scraper.headers.update({
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
            'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8',
        })

    def get_page(self, url: str) -> str:
        response = self.scraper.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    @staticmethod
    def parse_base_url(url: str) -> str:
        return url.replace('.html', '').rstrip('/')

    @staticmethod
    def get_total_listings(soup: BeautifulSoup) -> int:
        try:
            h1 = soup.find('h1')
            if h1:
                text = h1.get_text().replace('.', '').replace(',', '')
                match = re.search(r'\d+', text)
                if match:
                    return int(match.group())
        except Exception:
            pass
        return 0

    def scrape_page(self, base_url: str, page_num: int = 1):
        url = f"{base_url}.html" if page_num == 1 else f"{base_url}-pagina-{page_num}.html"
        print(f"  Obteniendo pág. {page_num}: {url}")

        html = self.get_page(url)
        soup = BeautifulSoup(html, 'lxml')

        # ── Estrategia 1: __NEXT_DATA__ ──────────────────────────────────
        properties = extract_next_data(soup)
        source = 'JSON'

        # ── Estrategia 2: HTML fallback ───────────────────────────────────
        if not properties:
            cards = soup.find_all('div', attrs={'data-posting-type': True})
            if not cards:
                cards = soup.find_all('div', class_=re.compile(r'posting-card|PostingCard', re.I))
            if not cards:
                cards = soup.find_all('article', attrs={'data-qa': True})

            source = 'HTML'
            for card in cards:
                try:
                    prop = parse_property_from_html(card)
                    if prop.get('url') or prop.get('precio_texto'):
                        properties.append(prop)
                except Exception as e:
                    print(f"  [HTML] Error: {e}")

        print(f"  → {len(properties)} propiedades (fuente: {source})")
        return properties, soup

    def scrape(self, url: str, max_pages: int = None) -> list:
        base_url = self.parse_base_url(url)
        print(f"\nScrapeando: {base_url}")
        print("─" * 65)

        all_properties = []
        page = 1

        while True:
            try:
                properties, soup = self.scrape_page(base_url, page)

                if page == 1 and not properties:
                    total = self.get_total_listings(soup)
                    if total == 0:
                        print("No se encontraron propiedades. "
                              "La estructura del sitio pudo haber cambiado.")
                    break

                if not properties:
                    print(f"  Sin propiedades en pág. {page} — fin del listado.")
                    break

                all_properties.extend(properties)
                print(f"  Acumulado: {len(all_properties)} propiedades")

                if max_pages and page >= max_pages:
                    print(f"  Límite de {max_pages} páginas alcanzado.")
                    break

                total = self.get_total_listings(soup)
                if total and len(all_properties) >= total:
                    print(f"  Se alcanzó el total reportado ({total}).")
                    break

                page += 1
                time.sleep(2)

            except Exception as e:
                print(f"  Error en página {page}: {e}")
                break

        return all_properties


# ─── Detail scraper (enriquecimiento por página de propiedad) ─────────────────

from html import unescape as _unescape


class ZonapropDetailScraper:
    """
    Visita la página de detalle de cada propiedad y extrae los campos
    que no están disponibles en el listado:

        titulo_real, fecha_publicacion, descripcion_completa,
        direccion_exacta, latitud, longitud,
        superficie_cubierta_m2, toilette, disposicion, orientacion, luminoso,
        inmobiliaria, inmobiliaria_matricula, telefono_parcial, whatsapp,
        fotos_hd  (URLs de alta resolución 1200×1200, separadas por ' | ')

    Uso desde zonaprop_tui:
        detail_scraper = ZonapropDetailScraper(delay=1.5)
        props = detail_scraper.enrich(props, on_progress=callback)
    """

    # featureId → nombre de columna normalizado
    _FEATURE_ID_MAP: dict = {
        '1000019': 'disposicion',
        '1000027': 'luminoso',
        '1000029': 'orientacion',
        'CFT100':  'superficie_total_m2',
        'CFT101':  'superficie_cubierta_m2',
        'CFT1':    'ambientes',
        'CFT2':    'dormitorios',
        'CFT3':    'banos',
        'CFT7':    'cocheras',
        'CFT4':    'toilette',
        'CFT5':    'antiguedad',
    }

    # label HTML abreviado → columna
    _LABEL_MAP: dict = {
        'tot.': 'superficie_total_m2',  'tot':  'superficie_total_m2',
        'cub.': 'superficie_cubierta_m2', 'cub': 'superficie_cubierta_m2',
        'amb.': 'ambientes',            'amb':  'ambientes',
        'dorm.': 'dormitorios',         'dorm': 'dormitorios',
        'baño': 'banos',  'banos': 'banos',  'baños': 'banos',
        'antiguedad': 'antiguedad',     'antigüedad': 'antiguedad',
        'disposicion': 'disposicion',   'disposición': 'disposicion',
        'orientacion': 'orientacion',   'orientación': 'orientacion',
        'luminoso': 'luminoso',
        'cochera': 'cocheras',          'cocheras': 'cocheras',
        'toilette': 'toilette',
    }

    def __init__(self, delay: float = 1.5):
        self.delay = delay
        self._client = cloudscraper.create_scraper()
        self._client.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'es-AR,es;q=0.9',
        })

    # ── Helpers de extracción ──────────────────────────────────────────────────

    def _get_html(self, url: str) -> str:
        resp = self._client.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text

    def _extract_json_ld(self, html: str) -> dict:
        """Extrae el bloque JSON-LD de tipo Apartment."""
        for m in re.finditer(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE
        ):
            try:
                obj = json.loads(m.group(1))
                if isinstance(obj, dict) and obj.get('@type') == 'Apartment':
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    def _extract_bracket_obj(self, html: str, key: str) -> dict:
        """
        Extrae el objeto JS inmediatamente después de 'key' usando
        conteo de llaves. Convierte comillas simples a dobles y elimina
        trailing commas antes de parsear como JSON.
        """
        for quote in ("'", '"'):
            marker = html.find(f"{quote}{key}{quote}")
            if marker >= 0:
                break
        else:
            return {}
        brace = html.find('{', marker)
        if brace < 0:
            return {}
        depth, i = 1, brace + 1
        while i < len(html) and depth:
            if html[i] == '{':
                depth += 1
            elif html[i] == '}':
                depth -= 1
            i += 1
        raw = html[brace:i]
        raw = raw.replace("'", '"')
        raw = re.sub(r',\s*([}\]])', r'\1', raw)   # trailing commas
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}

    def _extract_bracket_list(self, html: str, key: str) -> list:
        """Igual que _extract_bracket_obj pero para arrays JS."""
        for quote in ("'", '"'):
            marker = html.find(f"{quote}{key}{quote}")
            if marker >= 0:
                break
        else:
            return []
        bracket = html.find('[', marker)
        if bracket < 0:
            return []
        depth, i = 1, bracket + 1
        while i < len(html) and depth:
            if html[i] == '[':
                depth += 1
            elif html[i] == ']':
                depth -= 1
            i += 1
        raw = html[bracket:i].replace("'", '"')
        raw = re.sub(r',\s*([}\]])', r'\1', raw)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []

    def _normalize_label(self, label: str) -> str:
        return (
            label.strip().lower()
            .replace('í', 'i').replace('ó', 'o')
            .replace('ú', 'u').replace('á', 'a').replace('é', 'e')
        )

    def _parse_main_features(self, html: str, result: dict):
        """Extrae mainFeatures y lo normaliza a columnas estándar."""
        mf = self._extract_bracket_obj(html, 'mainFeatures')
        for k, v in mf.items():
            if not isinstance(v, dict) or v.get('value') is None:
                continue
            col = self._LABEL_MAP.get(self._normalize_label(v.get('label', '')))
            if not col:
                for fid in (v.get('featureId'), v.get('feature_id'), k):
                    col = self._FEATURE_ID_MAP.get(str(fid)) if fid is not None else None
                    if col:
                        break
            if col and col not in result:
                result[col] = v['value']

    def _parse_general_features(self, html: str, result: dict):
        """Extrae generalFeatures (amenities categorizados)."""
        gf = self._extract_bracket_obj(html, 'generalFeatures')
        for category, features in gf.items():
            if not isinstance(features, dict):
                continue
            for k, v in features.items():
                if not isinstance(v, dict) or not v.get('value'):
                    continue
                for fid in (v.get('featureId'), k):
                    col = self._FEATURE_ID_MAP.get(str(fid)) if fid is not None else None
                    if col and col not in result:
                        result[col] = v['value']
                        break

    # ── Extracción principal ───────────────────────────────────────────────────

    def _extract_detail_fields(self, html: str) -> dict:
        """Extrae todos los campos de detalle del HTML de una propiedad."""
        result = {}

        # ── Título real ────────────────────────────────────────────────────────
        for pat in [
            r"'postingTitle'\s*:\s*\"((?:[^\"\\]|\\.)*?)\"",
            r'"postingTitle"\s*:\s*"((?:[^"\\]|\\.)*?)"',
        ]:
            m = re.search(pat, html, re.DOTALL)
            if m:
                result['titulo_real'] = _unescape(m.group(1).replace('\\"', '"')).strip()
                break

        # ── Fecha de publicación ───────────────────────────────────────────────
        m = re.search(r"['\"]publicationDateFormatted['\"][\s:]+['\"]([^'\"]+)['\"]", html)
        if m:
            result['fecha_publicacion'] = m.group(1).strip()

        # ── Descripción completa ───────────────────────────────────────────────
        for pat in [
            r"'description'\s*:\s*\"((?:[^\"\\]|\\.)*?)\"",
            r'"description"\s*:\s*"((?:[^"\\]|\\.)*?)"',
        ]:
            m = re.search(pat, html, re.DOTALL)
            if m:
                raw = m.group(1).replace('\\"', '"')
                raw = raw.replace('<br />', '\n').replace('<br/>', '\n').replace('<br>', '\n')
                result['descripcion_completa'] = _unescape(raw).strip()
                break

        # ── Dirección exacta ───────────────────────────────────────────────────
        for pat in [
            r"['\"]address['\"].*?['\"]name['\"][\s:]+['\"]([^'\"]+)['\"]",
            r"['\"]streetAddress['\"][\s:]+['\"]([^'\"]+)['\"]",
        ]:
            m = re.search(pat, html, re.DOTALL)
            if m:
                result['direccion_exacta'] = _unescape(m.group(1).strip())
                break

        # ── Coordenadas ────────────────────────────────────────────────────────
        loc = self._extract_bracket_obj(html, 'location')
        if loc:
            lat = loc.get('lat') or loc.get('latitude')
            lon = loc.get('lon') or loc.get('lng') or loc.get('longitude')
            if lat: result['latitud']  = lat
            if lon: result['longitud'] = lon

        # Fallback coords: geo object en JSON-LD (se integrará en scrape_detail)

        # ── Inmobiliaria y contacto ────────────────────────────────────────────
        m = re.search(r"['\"]publisher['\"].*?['\"]name['\"][\s:]+['\"]([^'\"]+)['\"]", html, re.DOTALL)
        if m:
            result['inmobiliaria'] = m.group(1).strip()

        m = re.search(r"['\"]license['\"][\s:]+['\"]([^'\"]+)['\"]", html)
        if m and m.group(1).strip():
            result['inmobiliaria_matricula'] = m.group(1).strip()

        m = re.search(r"['\"]partialPhone['\"][\s:]+['\"]([^'\"]+)['\"]", html)
        if m and m.group(1).strip():
            result['telefono_parcial'] = m.group(1).strip()

        m = re.search(r"['\"]whatsApp['\"][\s:]+['\"]([^'\"]+)['\"]", html)
        if m and m.group(1).strip():
            result['whatsapp'] = m.group(1).strip()

        # ── mainFeatures y generalFeatures → columnas normalizadas ─────────────
        self._parse_main_features(html, result)
        self._parse_general_features(html, result)

        # ── Fotos en alta resolución ───────────────────────────────────────────
        pics = self._extract_bracket_list(html, 'pictures')
        if pics:
            urls = [
                p.get('url1200x1200') or p.get('resizeUrl1200x1200') or p.get('url730x532', '')
                for p in pics if isinstance(p, dict)
            ]
            urls = [u for u in urls if u]
            if urls:
                result['fotos_hd'] = ' | '.join(urls)

        return result

    def scrape_detail(self, url: str) -> dict:
        """
        Extrae los campos de detalle de una URL de propiedad.
        Combina JSON-LD (más confiable) con avisoInfo JS (más completo).
        """
        try:
            html = self._get_html(url)
        except Exception as e:
            return {'_detalle_error': str(e)}

        result = {}

        # 1. JSON-LD — datos estructurados y confiables
        ld = self._extract_json_ld(html)
        if ld:
            if ld.get('name'):
                result['titulo_real'] = ld['name']
            if isinstance(ld.get('floorSize'), dict):
                result['superficie_total_m2'] = ld['floorSize'].get('value')
            addr = ld.get('address') or {}
            if addr.get('streetAddress'):
                result['direccion_exacta'] = addr['streetAddress']
            if ld.get('telephone'):
                result['telefono_parcial'] = ld['telephone']
            geo = ld.get('geo') or {}
            if geo.get('latitude'):  result['latitud']  = geo['latitude']
            if geo.get('longitude'): result['longitud'] = geo['longitude']

        # 2. Campos del JS (avisoInfo) — más completos; no sobreescribe JSON-LD
        detail = self._extract_detail_fields(html)
        for k, v in detail.items():
            if v is not None and v != '':
                result.setdefault(k, v)

        return result

    # ── Enriquecimiento en lote ────────────────────────────────────────────────

    def enrich(self, props: list, on_progress=None) -> list:
        """
        Enriquece cada propiedad con datos del detalle.

        - Los campos de detalle se agregan solo si el campo está vacío
          en la propiedad base (no sobreescribe datos del listado).
        - on_progress: callable(current: int, total: int) para barra de progreso.
        - Aplica self.delay segundos entre requests para no ser bloqueado.
        """
        total = len(props)
        for i, prop in enumerate(props):
            url = prop.get('url')
            if url:
                try:
                    detail = self.scrape_detail(url)
                    for k, v in detail.items():
                        if prop.get(k) is None or prop.get(k) == '':
                            prop[k] = v
                except Exception as e:
                    prop.setdefault('_detalle_error', str(e))
            if on_progress:
                on_progress(i + 1, total)
            if i < total - 1:       # no esperar después del último
                time.sleep(self.delay)
        return props


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scraper de departamentos en venta de ZonaProp",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python zonaprop_scraper.py --zona rosario --ambientes 1
  python zonaprop_scraper.py --zona palermo --ambientes 2 --paginas 5
  python zonaprop_scraper.py --url https://www.zonaprop.com.ar/departamentos-venta-rosario.html
        """
    )
    parser.add_argument('--zona',     type=str, help='Zona de búsqueda (ej: rosario, palermo)')
    parser.add_argument('--ambientes',type=int, help='Número de ambientes (1–5)')
    parser.add_argument('--url',      type=str, help='URL directa de ZonaProp')
    parser.add_argument('--paginas',  type=int, help='Máx. páginas (default: todas)')
    parser.add_argument('--salida',   type=str, help='Carpeta de salida (default: carpeta del script)')
    args = parser.parse_args()

    # ── Determinar URL ─────────────────────────────────────────────────────
    if args.url:
        url = args.url
        nombre_archivo = "zonaprop_custom"
    elif args.zona and args.ambientes:
        url = build_url(args.zona, args.ambientes)
        nombre_archivo = f"zonaprop_{args.zona.lower().replace(' ','_')}_{args.ambientes}amb"
        print(f"URL: {url}")
    elif args.zona:
        zona_slug = ZONAS.get(args.zona.lower().replace(" ", "-"), args.zona.lower().replace(" ", "-"))
        url = f"https://www.zonaprop.com.ar/departamentos-venta-{zona_slug}.html"
        nombre_archivo = f"zonaprop_{args.zona.lower().replace(' ','_')}"
        print(f"URL: {url}")
    else:
        print("Sin parámetros → usando ejemplo: Rosario, 1 ambiente")
        print("Uso: python zonaprop_scraper.py --zona rosario --ambientes 1\n")
        url = build_url("rosario", 1)
        nombre_archivo = "zonaprop_rosario_1amb"

    # ── Salida ─────────────────────────────────────────────────────────────
    output_dir = Path(args.salida) if args.salida else Path(__file__).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Ejecutar ───────────────────────────────────────────────────────────
    scraper = ZonapropScraper()
    properties = scraper.scrape(url, max_pages=args.paginas)

    if not properties:
        print("\nNo se extrajeron propiedades.")
        return

    df = pd.DataFrame(properties)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
    csv_file  = output_dir / f"{nombre_archivo}_{timestamp}.csv"
    json_file = output_dir / f"{nombre_archivo}_{timestamp}.json"

    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(properties, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 65)
    print(f"✓  {len(properties)} propiedades guardadas en:")
    print(f"   CSV  → {csv_file}")
    print(f"   JSON → {json_file}")
    print(f"\n   Columnas extraídas ({len(df.columns)}): {list(df.columns)}")
    print("\nVista previa (primeras 3 filas):")
    print(df.head(3).to_string())


if __name__ == "__main__":
    main()
