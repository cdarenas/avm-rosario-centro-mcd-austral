#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Genera docs/diccionario_variables.md a partir de la muestra analítica v5.
#
# Convención de capas (clave para leer el dataset):
#   cruda        → valor original del scraper (sin sufijo)         [trazabilidad]
#   _auditado/a  → versión validada en la etapa de auditoría        [trazabilidad]
#   eda_*        → versión final lista para análisis/modelo         [USAR]
#   feat_*       → atributo binario extraído del texto              [USAR]
#   *_geo / geo_*, barrio_oficial_* → localización validada
#   identidad/traza, flags de auditoría → no entran al modelo
#
# Uso:  python3 scripts/data_quality/generar_diccionario_variables.py
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed" / "zonaprop_v2_eda_centro_v5.csv.gz"
OUT = ROOT / "docs" / "diccionario_variables.md"

# Descripciones curadas (las no listadas se completan por patrón).
DESC = {
    # — analítica (eda_) —
    "eda_precio_usd": "**Target.** Precio de publicación en USD, normalizado y auditado. Escala del modelo (log recomendada).",
    "eda_precio_m2": "Valor unitario derivado: `eda_precio_usd` / superficie total.",
    "eda_superficie_total_m2": "Superficie total (m²), auditada y lista para análisis.",
    "eda_superficie_cubierta_m2": "Superficie cubierta (m²), auditada.",
    "eda_banos": "Cantidad de baños, auditada.",
    "eda_cocheras": "Cantidad de cocheras, auditada (NA = sin cochera, ausencia estructural).",
    "eda_expensas": "Expensas mensuales (ARS), parseadas y auditadas.",
    "eda_latitud": "Latitud (WGS84) validada contra cartografía oficial.",
    "eda_longitud": "Longitud (WGS84) validada contra cartografía oficial.",
    "eda_distrito": "Distrito asignado (constante = CENTRO en esta muestra).",
    "eda_version": "Metadato: versión del esquema EDA.",
    # — identidad / trazabilidad —
    "property_id": "Identidad conservadora por `posting_id` (no fusiona publicaciones). Deduplicación.",
    "building_cluster_id": "Agrupamiento por calle-cuadra (proxy de edificio). Uso: *group-aware splitting*.",
    "id_confianza": "Nivel de confianza de la identidad de propiedad.",
    "posting_id_ultimo": "`posting_id` del último aviso capturado de la propiedad.",
    "n_capturas": "N.º de veces que se capturó el aviso (republicaciones/actualizaciones).",
    "cambios_precio": "N.º de cambios de precio observados entre capturas.",
    # — temporal / captura —
    "first_seen": "Primer timestamp en que se capturó el aviso.",
    "last_seen": "Último timestamp en que se capturó el aviso.",
    "fecha_publicacion": "Fecha de publicación original del aviso (datePosted), recuperada de la base del scraper.",
    "antiguedad_aviso_dias": "Antigüedad del aviso = captura − publicación (días). Base del corte ≤ 6 meses.",
    # — estructurales crudas (predictores, sin versión eda_) —
    "ambientes": "**Predictor.** Cantidad de ambientes (1–12). Se usa crudo (sin versión `eda_`).",
    "dormitorios": "**Predictor.** Cantidad de dormitorios (crudo).",
    "banos": "Cantidad de baños (crudo, previo a auditoría).",
    "cocheras": "Cantidad de cocheras (crudo).",
    "toilette": "Cantidad de toilettes (crudo).",
    "superficie_total_m2": "Superficie total (m²) cruda, previa a auditoría.",
    "superficie_cubierta_m2": "Superficie cubierta (m²) cruda.",
    "antiguedad": "**Predictor.** Antigüedad del inmueble (años + categorías 'a estrenar'/'en construcción'). Campo **sucio** (mezcla tipos, valores imposibles): sanear en FE.",
    "disposicion": "**Predictor.** Disposición: Frente / Contrafrente / Lateral / Interno.",
    "orientacion": "**Predictor.** Orientación (N/S/E/O y combinaciones).",
    "expensas_valor": "Expensas crudas (ARS).",
    "tipo_operacion": "PROPERTY (unidad individual) vs DEVELOPMENT (emprendimiento/pozo).",
    "descripcion_completa": "Texto libre del aviso. **Trae HTML/boilerplate del portal** y leyenda legal: sanear antes de features de texto.",
    "titulo": "Título del aviso (crudo).",
    "url": "URL del aviso.",
    "inmobiliaria": "Inmobiliaria/publicadora.",
    "precio_ultimo": "Precio de la última captura (crudo, en la moneda de `precio_moneda`).",
    "precio_moneda": "Moneda del precio crudo (USD/ARS).",
    "precio_min": "Precio mínimo observado entre capturas.",
    "precio_max": "Precio máximo observado entre capturas.",
    "precio_m2_observado": "Precio/m² observado (crudo).",
    # — localización / geo —
    "latitud": "Latitud cruda (previa a auditoría).",
    "longitud": "Longitud cruda.",
    "barrio": "Campo de barrio del portal (vacío en esta muestra; se usa el barrio oficial por cruce espacial).",
    "geo_source": "Fuente de la geolocalización.",
    "in_distrito_centro": "Indicador: la coordenada cae dentro del Distrito Centro.",
    "geo_distrito_oficial": "Distrito oficial asignado por cruce espacial.",
    "geo_nivel_calidad": "**Calidad de geolocalización** (G1 compartida sospechosa / G2 dentro del polígono / G3 georef). Auditoría y segmentación (idea de `geolocation_quality`, Gyger et al. 2026).",
    "geo_coord_n_registros": "N.º de avisos que comparten exactamente la coordenada.",
    "geo_coord_n_direcciones": "N.º de direcciones distintas que comparten la coordenada.",
    "geo_coordenada_compartida_sospechosa": "Flag: coordenada compartida sospechosa (nivel G1).",
    "barrio_oficial_geo": "**Barrio oficial** asignado por *point-in-polygon* contra la cartografía municipal.",
    "barrio_oficial_mslink": "Identificador (MSLINK) del barrio oficial en la cartografía.",
    "apto_eda_espacial_v4": "Flag final: apto para el análisis espacial.",
}

# Orden y rótulo de las capas
def capa(c):
    cl = c.lower()
    if c.startswith("eda_"): return "1. Analítica — lista para el modelo (`eda_*`)"
    if c.startswith("feat_"): return "2. Texto — atributos de la descripción (`feat_*`)"
    if cl.endswith("_auditado") or cl.endswith("_auditada"): return "6. Auditada — trazabilidad (`*_auditado`)"
    if any(k in cl for k in ["property_id","building_cluster","posting_id","id_confianza","n_capturas","cambios_precio","content_hash","run_id","split_group","republication"]): return "3. Identidad y trazabilidad"
    if any(k in cl for k in ["first_seen","last_seen","fecha_publicacion","antiguedad_aviso","capture"]): return "4. Temporal / captura"
    if any(k in cl for k in ["barrio_geo","geo_nivel","geo_","_mslink","apto_eda","direccion","latitud","longitud","distrito","barrio","georef","in_distrito","validacion"]): return "5. Localización / geolocalización"
    if any(k in cl for k in ["auditoria","quality_flag","requiere_revision","motivo","apto_modelado","calidad_espacial","alcance_territorial","incluido_eda"]): return "7. Flags y metadatos de auditoría"
    return "0. Estructurales, target y categóricas (crudas)"

def descripcion(c):
    if c in DESC: return DESC[c]
    if c.startswith("feat_"):
        nombre = c.replace("feat_", "").replace("_", " ")
        if c == "feat_litoral_gas":
            return "Conexión a **gas natural** (regex `gas natural|litoral gas`). Renombrar a `gas_natural` en FE."
        return f"Presencia de '{nombre}' en la descripción (1 = sí, 0 = no), por regex con manejo de negaciones."
    if c.endswith("_auditado") or c.endswith("_auditada"):
        base = c.rsplit("_", 1)[0]
        return f"Versión **auditada** de `{base}` (etapa de auditoría); insumo de la capa `eda_`. Trazabilidad."
    if "legacy" in c.lower(): return "Versión *legacy* (procedencia previa de la geolocalización). Trazabilidad."
    if c.lower().startswith("auditoria"): return "Metadato/estado de la auditoría (fase P0/P1, versión)."
    return "—"

def main():
    df = pd.read_csv(DATA)
    filas, cols = len(df), df.shape[1]
    grupos = {}
    for c in df.columns:
        grupos.setdefault(capa(c), []).append(c)

    L = []
    L.append("# Diccionario de variables — muestra analítica del Distrito Centro (v5)\n")
    L.append(f"*{cols} columnas · {filas:,} filas · dataset `data/processed/zonaprop_v2_eda_centro_v5.csv.gz`*\n")
    L.append("## Convención de nombres\n")
    L.append("El dataset conserva **tres capas** para trazabilidad; para el análisis y el modelo se usa "
             "siempre la capa analítica:\n")
    L.append("| Capa | Sufijo/prefijo | Rol |")
    L.append("|---|---|---|")
    L.append("| Cruda | *(sin sufijo)* | Valor original del scraper. Trazabilidad. |")
    L.append("| Auditada | `*_auditado/a` | Valor validado en la auditoría. Trazabilidad. |")
    L.append("| **Analítica** | **`eda_*`** | **Versión final lista para análisis/modelo. USAR.** |")
    L.append("| **Texto** | **`feat_*`** | **Atributo binario extraído de la descripción. USAR.** |\n")
    L.append("> **Nota:** la convención `eda_*` está aplicada de forma **incompleta**: variables como "
             "`ambientes`, `dormitorios`, `antiguedad`, `disposicion` y `orientacion` se usan **crudas** "
             "(no tienen versión `eda_`). Regularizar esta convención es una tarea de la etapa de "
             "*feature engineering*.\n")

    for g in sorted(grupos):
        cols_g = grupos[g]
        L.append(f"\n## {g[3:] if g[1]=='.' else g}  ({len(cols_g)})\n")
        L.append("| Variable | Tipo | Completitud | Descripción |")
        L.append("|---|---|---:|---|")
        for c in sorted(cols_g):
            comp = f"{df[c].notna().mean()*100:.0f}%"
            L.append(f"| `{c}` | {df[c].dtype} | {comp} | {descripcion(c)} |")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"Diccionario escrito: {OUT.relative_to(ROOT)}  ({cols} variables)")

if __name__ == "__main__":
    main()
