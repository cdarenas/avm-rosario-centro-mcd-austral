#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Preprocesamiento (v5 → v6): limpieza a nivel dataset + regularización de nombres.
#
# NO imputa faltantes ni recorta outliers: esas transformaciones se aprenden dentro
# de cada fold (Kuhn & Johnson, 2013) y van en el pipeline de modelado. Acá solo:
#   1) saneo de descripciones (HTML + boilerplate/leyenda legal del corredor)
#   2) limpieza de 'antiguedad' (años numéricos + categoría, marca valores imposibles)
#   3) regularización de nombres (eda_* para predictores; feat_litoral_gas→feat_gas_natural)
#   4) documenta políticas de faltantes y outliers en el reporte
#
# Entrada : data/processed/zonaprop_v2_eda_centro_v5.csv.gz
# Salida  : data/processed/zonaprop_v2_eda_centro_v6.csv.gz
#           reports/preprocesamiento_centro_v6.md
#
# Uso:  python3 scripts/preprocessing/preprocesar_dataset.py
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path
import re
import hashlib, json, datetime, gzip
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
V5 = ROOT / "data" / "processed" / "zonaprop_v2_eda_centro_v5.csv.gz"
V6 = ROOT / "data" / "processed" / "zonaprop_v2_eda_centro_v6.csv.gz"
REP = ROOT / "reports" / "preprocesamiento_centro_v6.md"

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _content_sha256(path):
    """Hash del CONTENIDO (CSV descomprimido): reproducible sin importar el wrapper gzip ni el escritor."""
    raw = open(path, "rb").read()
    data = gzip.decompress(raw) if str(path).endswith(".gz") else raw
    return hashlib.sha256(data).hexdigest()

def escribir_manifiesto(salida, entrada, stage, in_shape, out_shape, extra=None):
    """Manifiesto de linaje: hash de contenido in/out, filas/cols, decisiones."""
    man = {
        "artifact": salida.name, "artifact_sha256": _sha256(salida),
        "content_sha256": _content_sha256(salida),
        "stage": stage,
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "input_artifact": entrada.name, "input_sha256": _sha256(entrada),
        "input_content_sha256": _content_sha256(entrada),
        "input_rows": int(in_shape[0]), "output_rows": int(out_shape[0]),
        "input_columns": int(in_shape[1]), "output_columns": int(out_shape[1]),
    }
    if extra:
        man.update(extra)
    (salida.parent / (salida.name + ".manifest.json")).write_text(
        json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    return man["artifact_sha256"]

# ── 1. Saneo de descripciones ────────────────────────────────────────────────
_LEGAL = re.compile(r"(corredor|corretaje|matr[ií]cula|cucicba|colegio de corredores|"
                    r"lealtad comercial|c[oó]digo civil|defensa del consumidor|"
                    r"intermediaci[oó]n|operaciones inmobiliarias)", re.I)
_JUNK = re.compile(r"\b(ver datos|descripciondatosanunciante|span|btn|href|button)\b", re.I)

def limpiar_descripcion(t: str) -> str:
    t = re.sub(r"<[^>]+>", " ", str(t))            # etiquetas HTML
    t = re.sub(r"&[a-z#0-9]+;", " ", t)             # entidades HTML
    segmentos = re.split(r"[\n\r]+|(?<=[.;])\s+", t)  # por líneas y oraciones
    segmentos = [s for s in segmentos if not _LEGAL.search(s)]  # quita leyenda legal
    t = " ".join(segmentos)
    t = _JUNK.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()

# ── 2. Limpieza de antigüedad ────────────────────────────────────────────────
def parse_antiguedad(v):
    """Devuelve (años:float|nan, estado:str|None)."""
    s = str(v).strip().lower()
    if s in ("", "nan", "none"):
        return np.nan, None
    if "estrenar" in s:
        return 0.0, "A estrenar"
    if "construc" in s:
        return np.nan, "En construcción"
    try:
        y = float(s.replace(",", "."))
    except ValueError:
        return np.nan, None
    if 0 <= y <= 150:
        return y, ("A estrenar" if y == 0 else "Usado")
    return np.nan, "valor_invalido"          # imposibles (p. ej. 792)

def main():
    df = pd.read_csv(V5)
    n0, c0 = df.shape
    log = {}

    # 1) descripciones
    d = df["descripcion_completa"].astype(str)
    log["desc_con_html"] = float(d.str.contains(r"<[^>]+>").mean() * 100)
    log["desc_con_legal"] = float(d.str.lower().str.contains("corredor|lealtad comercial|código civil|codigo civil").mean() * 100)
    df["descripcion_limpia"] = d.map(limpiar_descripcion)
    log["desc_reduccion_media_pct"] = float((1 - df["descripcion_limpia"].str.len() / d.str.len().replace(0, np.nan)).mean() * 100)

    # 2) antigüedad (usa la auditada como fuente; cae a la cruda si falta)
    fuente = df["antiguedad_auditada"].where(df["antiguedad_auditada"].notna(), df["antiguedad"])
    parsed = fuente.map(parse_antiguedad)
    df["eda_antiguedad_anos"] = parsed.map(lambda t: t[0])
    df["eda_antiguedad_estado"] = parsed.map(lambda t: t[1])
    log["antig_invalidos"] = int((df["eda_antiguedad_estado"] == "valor_invalido").sum())
    log["antig_cobertura_anos"] = float(df["eda_antiguedad_anos"].notna().mean() * 100)
    log["antig_estados"] = df["eda_antiguedad_estado"].value_counts(dropna=False).to_dict()

    # 3) regularización de nombres: eda_* para predictores que se usaban crudos
    copias = {"eda_ambientes": "ambientes", "eda_dormitorios": "dormitorios",
              "eda_disposicion": "disposicion", "eda_orientacion": "orientacion",
              "eda_tipo_operacion": "tipo_operacion", "eda_toilette": "toilette"}
    for nuevo, base in copias.items():
        df[nuevo] = df[base]
    # feat_litoral_gas → feat_gas_natural (nombre claro; no es la empresa distribuidora)
    renombre = {}
    if "feat_litoral_gas" in df.columns:
        df = df.rename(columns={"feat_litoral_gas": "feat_gas_natural"})
        renombre["feat_litoral_gas"] = "feat_gas_natural"
    log["eda_creadas"] = list(copias.keys()) + ["eda_antiguedad_anos", "eda_antiguedad_estado"]
    log["renombradas"] = renombre

    df["preproc_version"] = 6
    n1, c1 = df.shape
    # gzip determinístico (mtime=0): bytes reproducibles → hash estable entre corridas
    df.to_csv(V6, index=False, compression={"method": "gzip", "mtime": 0})
    escribir_manifiesto(
        V6, V5, "processed_preproc_centro_v6", (n0, c0), (n1, c1),
        extra={"transformaciones": ["descripcion_limpia (saneo HTML/legal)",
                                    "eda_antiguedad_anos/estado (limpieza)",
                                    "regularizacion_nombres (eda_*)",
                                    "rename feat_litoral_gas->feat_gas_natural"],
               "columnas_agregadas": int(c1 - c0),
               "imputation_applied": False, "winsorization_applied": False,
               "filas_filtradas": 0,
               "warning": "Limpieza row-wise + nombres. Imputacion/encoding/outliers van por fold en el modelado."})

    # ── Reporte ──────────────────────────────────────────────────────────────
    claves = ["eda_precio_usd", "eda_superficie_total_m2", "eda_superficie_cubierta_m2",
              "eda_banos", "eda_cocheras", "eda_expensas", "eda_antiguedad_anos",
              "eda_dormitorios", "eda_disposicion", "eda_orientacion"]
    faltantes = [(c, f"{df[c].notna().mean()*100:.0f}%") for c in claves if c in df.columns]

    L = []
    L.append("# Preprocesamiento — limpieza y regularización (v5 → v6)\n")
    L.append(f"*Entrada: `{V5.name}` ({n0:,} filas, {c0} cols) → Salida: `{V6.name}` "
             f"({n1:,} filas, {c1} cols)*\n")
    L.append("> **Alcance:** limpieza a nivel dataset y regularización de nombres. **No** se imputan "
             "faltantes ni se recortan outliers: esas transformaciones se aprenden dentro de cada "
             "*fold* (Kuhn & Johnson, 2013) y van en el pipeline de modelado.\n")

    L.append("## Controles de validez de la muestra de entrada\n")
    L.append("El filtrado por alcance (moneda, distrito, fecha) y el descarte de valores basura se "
             "resolvieron **aguas arriba** (auditoría y validación previas, documentadas en "
             "`docs/PIPELINE.md`, y corte temporal de v5), no en esta "
             "etapa. Se verifica que esos controles **se cumplen** en la muestra de entrada:\n")
    _p = pd.to_numeric(df["eda_precio_usd"], errors="coerce")
    _usd = (df["precio_moneda"] == "USD").mean() * 100
    _ctr = (df["eda_distrito"] == "CENTRO").mean() * 100
    _ant = pd.to_numeric(df["antiguedad_aviso_dias"], errors="coerce").max()
    _ok = lambda c: "✓" if c else "✗ REVISAR"
    L.append("| control | resultado | estado |")
    L.append("|---|---|:---:|")
    L.append(f"| Target sin valores basura | mín USD {_p.min():,.0f} | {_ok(_p.min() > 1000)} |")
    L.append(f"| Moneda = USD | {_usd:.0f}% | {_ok(_usd == 100)} |")
    L.append(f"| Ubicación = Distrito Centro | {_ctr:.0f}% | {_ok(_ctr == 100)} |")
    L.append(f"| Antigüedad del aviso ≤ 6 meses | máx {_ant:.0f} días | {_ok(_ant <= 183)} |")
    L.append("")

    L.append("## 1. Saneo de descripciones\n")
    L.append(f"Las descripciones traían **HTML residual** ({log['desc_con_html']:.0f}% de los avisos) "
             f"y la **leyenda legal del corredor** ({log['desc_con_legal']:.0f}%), que contaminaban "
             "tokens y n-gramas (ver EDA). Se creó **`descripcion_limpia`** quitando etiquetas HTML, "
             "entidades y los segmentos con la leyenda legal (corredor público, código civil, ley de "
             "lealtad comercial, defensa del consumidor, intermediación). El campo original se conserva. "
             f"Reducción media de longitud: {log['desc_reduccion_media_pct']:.0f}%. "
             "Esta columna es el insumo para (re)generar los `feat_*` de texto en FE.\n")

    L.append("## 2. Limpieza de `antiguedad`\n")
    L.append("El campo mezclaba años numéricos con categorías ('A estrenar', 'En construcción') y "
             f"arrastraba valores imposibles. Se derivaron dos columnas: **`eda_antiguedad_anos`** "
             f"(numérica, cobertura {log['antig_cobertura_anos']:.0f}%) y **`eda_antiguedad_estado`** "
             f"(A estrenar / En construcción / Usado / valor_invalido). Valores imposibles marcados "
             f"(anos=NA): **{log['antig_invalidos']}**.\n")
    L.append("| estado | avisos |")
    L.append("|---|---:|")
    for k, v in sorted(log["antig_estados"].items(), key=lambda x: -x[1]):
        etq = "(sin dato)" if (k is None or (isinstance(k, float) and pd.isna(k))) else k
        L.append(f"| {etq} | {v:,} |")
    L.append("")

    L.append("## 3. Regularización de nombres\n")
    L.append("Para que la regla \"el modelo consume `eda_*` y `feat_*`\" sea completa, se crearon "
             "versiones `eda_` de los predictores que se usaban crudos (el original se conserva para "
             "trazabilidad):\n")
    L.append("| nueva | origen |")
    L.append("|---|---|")
    for nuevo, base in copias.items():
        L.append(f"| `{nuevo}` | `{base}` |")
    L.append("| `eda_antiguedad_anos`, `eda_antiguedad_estado` | `antiguedad` (limpiada) |")
    L.append("")
    if renombre:
        L.append("Renombre por claridad: **`feat_litoral_gas` → `feat_gas_natural`** "
                 "(captura conexión a gas natural; *Litoral Gas* es la distribuidora, confundía).\n")

    L.append("## 4. Política de faltantes (documentada, sin imputar)\n")
    L.append("Se distingue **ausencia estructural** de **faltante genuino** (Rubin, 1976; Kuhn & "
             "Johnson, 2019): p. ej. `eda_cocheras`/`eda_expensas` en NA suelen indicar *ausencia* "
             "(sin cochera / no informa expensas), no un dato perdido. La imputación se aprende dentro "
             "del fold y, cuando corresponda, se acompaña de indicadores de 'informado'. Faltantes "
             "actuales en variables clave:\n")
    L.append("| variable | completitud |")
    L.append("|---|---:|")
    for c, comp in faltantes:
        L.append(f"| `{c}` | {comp} |")
    L.append("")

    L.append("## 5. Política de outliers (documentada, sin recortar)\n")
    L.append("Los atípicos se marcaron con la regla robusta **3·IQR** (Tukey, 1977) en el EDA. El "
             "recorte, winsorización o exclusión se decide en el modelado, con criterio de dominio y "
             "evaluando su efecto OOS: muchos extremos son propiedades legítimamente premium, no "
             "errores. No se elimina nada a nivel dataset.\n")

    L.append("## 6. Prevención de fuga de información (*data leakage*)\n")
    L.append("La razón por la que la imputación, el *encoding* y el escalado **no** se aplican en esta "
             "etapa sino dentro del pipeline de modelado es **metodológica, no de conveniencia**: evitar "
             "la **fuga de información**. Toda transformación que **estima parámetros a partir de los "
             "datos** (la media/mediana de una imputación, la tabla de un *target/mean encoding*, la "
             "media y el desvío de un escalado, un λ de Box-Cox, una selección de variables o un PCA) "
             "debe ajustarse **usando solo la porción de entrenamiento de cada *fold*** y aplicarse a la "
             "porción retenida. Estimar esos parámetros sobre todo el dataset antes de particionar filtra "
             "información del conjunto de validación/test y **sobreestima la performance**.\n")
    L.append("Por eso se distinguen dos tipos de operación:\n")
    L.append("- **Determinísticas y por fila** (no miran a las otras observaciones): limpieza de HTML, "
             "parseo de `antiguedad`, `log(precio)`, `precio/m² = precio/superficie`, renombres. **No "
             "inducen fuga** y se hacen a nivel dataset — es lo que resuelve esta etapa (v6).\n"
             "- **Que estiman parámetros de la distribución**: imputación, *encoding*, estandarización, "
             "selección de variables, reducción de dimensionalidad. **Van dentro del *fold***, vía "
             "`Pipeline` / `ColumnTransformer` ajustados solo con el *train*.\n")
    L.append("Se complementa con el **split *group-aware*** por `property_id` / `building_cluster_id`, "
             "que evita la otra fuente de fuga —la misma unidad (republicada) cayendo en *train* y "
             "*test*—.\n")
    L.append("**Fundamento.** La referencia canónica es **Hastie, Tibshirani & Friedman — *ESL*, "
             "§7.10.2** (\"The Wrong and Right Way to Do Cross-Validation\"), que muestra cómo "
             "preprocesar sobre todos los datos antes de la CV puede dar error casi nulo incluso con "
             "datos aleatorios. **Kuhn & Johnson (2013)** exige ajustar el preprocesamiento dentro del "
             "resampling; **James et al. — *ISL*, cap. 5** y **Géron (2019), cap. 2** (`fit` solo con "
             "*train*, encapsulado en `Pipeline`) lo operacionalizan; **Kuhn & Johnson (2019)** extiende "
             "el criterio a la selección de variables; y el recaudo de republicaciones sigue a "
             "**Gutiérrez et al. (2026)**.\n")

    L.append("## Próximos pasos (feature engineering)\n")
    L.append("- Regenerar los `feat_*` desde `descripcion_limpia` y evaluar nuevos atributos de texto.\n"
             "- Ratios derivados (p. ej. cubierta/total, precio por ambiente) y variables de "
             "microlocalización.\n- Encoding e imputación dentro del pipeline de modelado (por fold).\n")

    L.append("## Referencias\n")
    L.append("- Hastie, T., Tibshirani, R., & Friedman, J. (2009). *The Elements of Statistical "
             "Learning* (2ª ed.), §7.10.2. Springer.\n"
             "- James, G., Witten, D., Hastie, T., & Tibshirani, R. (2021). *An Introduction to "
             "Statistical Learning* (cap. 5). Springer.\n"
             "- Kuhn, M., & Johnson, K. (2013). *Applied Predictive Modeling* (cap. 3 y resampling). Springer.\n"
             "- Kuhn, M., & Johnson, K. (2019). *Feature Engineering and Selection*. CRC Press.\n"
             "- Géron, A. (2019). *Hands-On Machine Learning* (2ª ed., cap. 2). O'Reilly.\n"
             "- Rubin, D. B. (1976). Inference and missing data. *Biometrika, 63*(3), 581–592.\n"
             "- Tukey, J. W. (1977). *Exploratory Data Analysis*. Addison-Wesley.\n"
             "- Gutiérrez et al. (2026). Antecedente argentino (Buenos Aires): identificación de republicaciones.\n"
             "- *Complementarias (a incorporar a la biblioteca):* Kaufman, Rosset & Perlich (2012), "
             "\"Leakage in Data Mining\" (ACM TKDD); Kapoor & Narayanan (2023), \"Leakage and the "
             "reproducibility crisis in ML-based science\" (Patterns); scikit-learn — *Common pitfalls: "
             "data leakage* (Pedregosa et al., 2011).\n")

    REP.parent.mkdir(parents=True, exist_ok=True)
    REP.write_text("\n".join(L), encoding="utf-8")

    print(f"v6 escrito: {V6.relative_to(ROOT)}  ({n1:,} filas · {c1} cols, +{c1-c0} columnas)")
    print(f"reporte:    {REP.relative_to(ROOT)}")
    print(f"antigüedad inválidos marcados: {log['antig_invalidos']} · "
          f"descripciones saneadas (reducción media {log['desc_reduccion_media_pct']:.0f}%)")

if __name__ == "__main__":
    main()
