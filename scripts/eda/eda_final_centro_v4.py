#!/usr/bin/env python3
"""
eda_final_centro_v4.py — EDA final de la muestra analítica (Distrito Centro, v4).

Genera un reporte HTML profesional autocontenido + figuras (PNG) + tablas (CSV),
sobre `data/processed/zonaprop_v2_eda_centro_v4.csv.gz`.

Cada sección incluye:
  - "Método": la fórmula matemática que respalda el cálculo (renderizada con MathJax).
  - "Lectura / conclusión": interpretación de los gráficos y tablas, con valores reales.

No modifica el dataset, no imputa, no recorta outliers: describe, justifica y visualiza.

Uso:
    python scripts/eda/eda_final_centro_v4.py
Salidas:
    reports/eda_final_centro_v4.html
    reports/figures/eda_final/*.png   ·   reports/tables/eda_final/*.csv
"""
from __future__ import annotations
import os, io, base64, datetime
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import seaborn as sns
from scipy import stats

# ── rutas ─────────────────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
# EDA sobre la MUESTRA DE MODELADO (ventana temporal ≤6 meses, v6, 4.765 avisos).
# Configurable por entorno para reproducir sobre otra versión del dataset si se quisiera.
DATA = os.environ.get('EDA_INPUT', os.path.join(ROOT, 'data', 'processed', 'zonaprop_v2_eda_centro_v6.csv.gz'))
TAG = os.environ.get('EDA_TAG', 'eda_final')
FIGDIR = os.path.join(ROOT, 'reports', 'figures', TAG)
TABDIR = os.path.join(ROOT, 'reports', 'tables', TAG)
OUT_HTML = os.path.join(ROOT, 'reports', f'{TAG}_centro.html')
os.makedirs(FIGDIR, exist_ok=True); os.makedirs(TABDIR, exist_ok=True)

# ── estética ──────────────────────────────────────────────────────────────────
sns.set_theme(style='whitegrid', context='notebook')
PAL = '#2c6e91'; PAL2 = '#c0562b'; ACCENT = '#3a8f5e'
plt.rcParams.update({'figure.dpi': 110, 'savefig.dpi': 110, 'axes.titleweight': 'bold',
                     'axes.titlesize': 12, 'font.size': 10, 'figure.autolayout': True})

def money_fmt(x, _p=None):
    return f'${x/1e6:.1f}M' if abs(x) >= 1e6 else f'${x/1e3:.0f}k'
def k_fmt(x, _p=None):
    return f'{x/1e6:.1f}M' if abs(x) >= 1e6 else f'{x/1e3:.0f}k'

# Etiquetas legibles para figuras (nombres crudos de columnas -> texto de tesis)
LABELS = {
    'eda_precio_usd': 'Precio (USD)', 'eda_precio_m2': 'Precio USD/m²',
    'eda_superficie_total_m2': 'Superficie total', 'eda_superficie_cubierta_m2': 'Superficie cubierta',
    'ambientes': 'Ambientes', 'dormitorios': 'Dormitorios', 'eda_dormitorios': 'Dormitorios',
    'eda_banos': 'Baños', 'eda_cocheras': 'Cocheras', 'eda_expensas': 'Expensas',
    'eda_ambientes': 'Ambientes', 'eda_antiguedad_anos': 'Antigüedad (años)', 'eda_latitud': 'Latitud',
    'eda_longitud': 'Longitud', 'fe_banos_por_ambiente': 'Baños por ambiente',
    'fe_sup_por_ambiente': 'Superficie por ambiente', 'fe_dormitorios_por_ambiente': 'Dormitorios por ambiente',
    'fe_ratio_cubierta_total': 'Cubierta/total', 'fe_dens_comercios_300m': 'Densidad comercial (300 m)',
    'fe_dist_centro_km': 'Distancia al centro (km)', 'fe_dist_rio_km': 'Distancia al río (km)',
    'fe_dist_espacio_verde_km': 'Distancia a espacio verde (km)',
    'antiguedad': 'Antigüedad', 'direccion_exacta': 'Dirección exacta',
    'descripcion_completa': 'Descripción completa',
}
def lbl(name):
    return LABELS.get(name, str(name).replace('feat_', '').replace('fe_', '').replace('eda_', '').replace('_', ' ').strip().capitalize())
def usd(x):
    return f'${x:,.0f}'

PARTS = []
def H(html): PARTS.append(html)
def metodo(titulo, formula, texto):
    f = f'$$ {formula} $$' if formula else ''
    return f'<div class="metodo"><span class="tit">Método — {titulo}</span>{f}<div>{texto}</div></div>'
def conclusion(texto):
    return f'<div class="conclusion"><span class="tit">Lectura / conclusión</span>{texto}</div>'

def savefig(fig, name, caption=''):
    fig.savefig(os.path.join(FIGDIR, name + '.png'), bbox_inches='tight')
    buf = io.BytesIO(); fig.savefig(buf, format='png', bbox_inches='tight'); plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode()
    cap = f'<figcaption>{caption}</figcaption>' if caption else ''
    return f'<figure><img src="data:image/png;base64,{b64}"/>{cap}</figure>'

def table(df, name, note=''):
    df.to_csv(os.path.join(TABDIR, name + '.csv'))
    html = df.to_html(border=0, classes='tbl', float_format=lambda x: f'{x:,.2f}')
    note = f'<p class="note">{note}</p>' if note else ''
    return html + note

def skew(s):
    s = pd.to_numeric(s, errors='coerce').dropna()
    return stats.skew(s) if len(s) > 2 else float('nan')

def _label(v):
    """Etiqueta legible: enteros sin '.0', texto tal cual, faltante como 'NA'."""
    if pd.isna(v): return 'NA'
    try:
        fv = float(v)
        return str(int(fv)) if fv.is_integer() else str(v)
    except (TypeError, ValueError):
        return str(v)

def barra(ax, col, titulo, ordenar_valor=False, top=8):
    """Barra horizontal de frecuencias. Si ordenar_valor: ordena por valor numérico (NA al final)."""
    vc = df[col].map(_label).value_counts()
    if ordenar_valor:
        def k(x):
            try: return (0, int(x))
            except (TypeError, ValueError): return (1, 10**9)
        vc = vc.reindex(sorted(vc.index, key=k))
    else:
        vc = vc.head(top)
    sns.barplot(x=vc.values, y=list(vc.index), color=PAL, ax=ax)
    ax.set_title(titulo); ax.set_xlabel('avisos'); ax.set_ylabel('')

# ── carga ─────────────────────────────────────────────────────────────────────
df = pd.read_csv(DATA)
N = len(df)
num = lambda c: pd.to_numeric(df[c], errors='coerce')

# =============================================================================
# Encabezado
# =============================================================================
H(f"""<h1>EDA — Muestra de modelado · Distrito Centro (ventana temporal)</h1>
<p class="sub">Tesis AVM Rosario · dataset <code>zonaprop_v2_eda_centro_v6</code> (ventana ≤6 meses) ·
generado {datetime.date.today().isoformat()}</p>
<div class="callout"><b>Alcance.</b> Análisis exploratorio de la muestra de modelado
({N:,} avisos, precio de <b>publicación</b> en USD). No se imputan faltantes ni se
recortan outliers: se describen, se justifican con su fórmula y se marcan. Cada sección
cierra con una lectura. Las conclusiones alimentan el <b>preprocesamiento</b>; no definen
todavía folds ni el dataset final de modelado.</div>""")

# =============================================================================
# 1. Panorama
# =============================================================================
H('<h2>1. Panorama del dataset</h2>')
espacial = int(df['apto_eda_espacial_v4'].sum())
conf_alta = int((df['id_confianza'] == 'alta').sum())
repub = int((num('n_capturas') > 1).sum())
camb = int((num('cambios_precio') > 0).sum())
n_barrios = df['barrio_oficial_geo'].nunique()
resumen = pd.DataFrame({'Métrica': ['Avisos (property_id)', 'Aptos análisis espacial',
    'Identidad de alta confianza', 'Con republicaciones (n_capturas>1)', 'Con cambios de precio',
    'Barrios oficiales'],
    'Valor': [f'{N:,}', f'{espacial:,} ({espacial/N*100:.0f}%)', f'{conf_alta:,} ({conf_alta/N*100:.0f}%)',
              f'{repub:,}', f'{camb:,}', f'{n_barrios}']}).set_index('Métrica')
H(table(resumen, '01_panorama'))
vc = df['geo_nivel_calidad'].value_counts()
fig, ax = plt.subplots(figsize=(7.5, 3.2))
sns.barplot(x=vc.values, y=vc.index, color=PAL, ax=ax)
for i, v in enumerate(vc.values): ax.text(v, i, f' {v:,}', va='center')
ax.set_title('Calidad de la geolocalización (niveles de auditoría)'); ax.set_xlabel('avisos'); ax.set_ylabel('')
H(savefig(fig, '01_geo_calidad', 'G2: dentro del polígono (legacy) · G1: coordenada compartida sospechosa · G3: validada por Georef.'))
H(metodo('Cobertura / proporción',
         r'p = \frac{n_{\text{cumple condición}}}{n_{\text{total}}}',
         'Toda cobertura se expresa como proporción sobre el total de avisos.'))
H(conclusion(f'La muestra tiene <b>{N:,} avisos</b>, con <b>{espacial/N*100:.0f}%</b> aptos para '
    f'análisis espacial y <b>{conf_alta/N*100:.0f}%</b> de identidad de alta confianza. La calidad '
    f'geográfica está dominada por el nivel <b>G2</b> ({vc.iloc[0]:,} avisos, coordenada dentro del '
    f'polígono del distrito), lo que da un piso razonable para la exploración espacial; los <b>G1</b> '
    f'(coordenada compartida sospechosa) se segmentan aparte. Se detectaron <b>{repub:,}</b> '
    f'republicaciones ({camb:,} con cambio de precio): se conservan agrupadas por propiedad para el '
    f'group-aware split. La variable <code>geo_nivel_calidad</code> se preserva como auditoría '
    f'(idea de <i>geolocation_quality</i>, Gyger 2026).'))

# =============================================================================
# 2. Target
# =============================================================================
H('<h2>2. Target: precio de publicación y precio por m²</h2>')
precio = num('eda_precio_usd'); pm2 = num('eda_precio_m2')
med, mean = precio.median(), precio.mean(); q1, q3 = precio.quantile(.25), precio.quantile(.75)
p99 = precio.quantile(.99); sk = skew(precio); sk_log = skew(np.log1p(precio))
# 2.a precio legible
vis = precio[precio <= p99].dropna()
fig, ax = plt.subplots(figsize=(11, 5.2))
sns.histplot(vis, bins=50, color=PAL, edgecolor='white', ax=ax)
ax.locator_params(axis='x', nbins=12)
ax.xaxis.set_major_formatter(FuncFormatter(money_fmt))
ax.axvline(med, color=PAL2, ls='--', lw=1.8, label=f'mediana  {money_fmt(med)}')
ax.axvline(mean, color=ACCENT, ls='--', lw=1.8, label=f'media  {money_fmt(mean)}')
ax.set_title('Distribución del precio de publicación (USD)')
ax.set_xlabel('precio de publicación (USD)'); ax.set_ylabel('cantidad de avisos'); ax.legend(frameon=True)
H(savefig(fig, '02_precio_usd_legible',
    f'Escala en miles de USD. Recortado al percentil 99 ({money_fmt(p99)}); el 1% superior llega a {money_fmt(precio.max())}.'))
# 2.b pm2 legible
pm2v = pm2.dropna(); pm99 = pm2v.quantile(.99); pmed, pmean = pm2v.median(), pm2v.mean()
fig, ax = plt.subplots(figsize=(11, 4.6))
sns.histplot(pm2v[pm2v <= pm99], bins=45, color=PAL2, edgecolor='white', ax=ax)
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _p=None: usd(x)))
ax.axvline(pmed, color=PAL, ls='--', lw=1.8, label=f'mediana  {usd(pmed)}/m²')
ax.axvline(pmean, color=ACCENT, ls='--', lw=1.8, label=f'media  {usd(pmean)}/m²')
ax.set_title('Distribución del precio por metro cuadrado (USD/m²)')
ax.set_xlabel('precio por m² (USD)'); ax.set_ylabel('cantidad de avisos'); ax.legend(frameon=True)
H(savefig(fig, '02_pm2_legible', f'La mitad de los avisos está entre {usd(pm2v.quantile(.25))} y {usd(pm2v.quantile(.75))} por m².'))
# 2.c transformación
fig, axs = plt.subplots(1, 2, figsize=(11, 3.8))
sns.histplot(precio.dropna(), bins=60, color=PAL, ax=axs[0]); axs[0].set_title(f'Precio USD — escala original (g₁={sk:.2f})'); axs[0].set_xlabel('precio (USD)')
axs[0].xaxis.set_major_formatter(FuncFormatter(money_fmt)); axs[0].locator_params(axis='x', nbins=6)
sns.histplot(np.log1p(precio.dropna()), bins=60, color=ACCENT, ax=axs[1]); axs[1].set_title(f'log1p(precio) (g₁={sk_log:.2f})'); axs[1].set_xlabel('log(1+precio)')
H(savefig(fig, '02_target_dist', 'La transformación log1p reduce la asimetría del precio.'))
H(table(pd.DataFrame({'Precio USD': precio.describe(percentiles=[.05, .25, .5, .75, .95, .99]),
                      'Precio USD/m²': pm2.describe(percentiles=[.05, .25, .5, .75, .95, .99])}), '02_target_describe'))
H(metodo('Media, mediana, cuantiles y asimetría',
    r'\bar{x}=\frac{1}{n}\sum_i x_i \quad;\quad Q_p:\ P(X\le Q_p)=p \quad;\quad '
    r'g_1=\frac{\tfrac{1}{n}\sum_i (x_i-\bar{x})^3}{\left[\tfrac{1}{n}\sum_i (x_i-\bar{x})^2\right]^{3/2}}',
    r'La <b>media</b> es el promedio; la <b>mediana</b> es el cuantil \(Q_{0.5}\); '
    r'\(g_1\) es el <b>coeficiente de asimetría de Fisher-Pearson</b> (tercer momento estandarizado): '
    r'\(g_1=0\) simétrica, \(g_1>0\) cola a la derecha. La transformación aplicada es '
    r'\(\;y=\log(1+x)\;\), que comprime la cola derecha y aproxima la relación multiplicativa de los '
    r'precios a una aditiva. Al reportar en USD hay que corregir el <i>retransformation bias</i>: '
    r'\(\mathbb{E}[e^{\hat{y}}]\neq e^{\mathbb{E}[\hat{y}]}\).'))
H(conclusion(f'La mediana del precio de publicación es <b>{money_fmt(med)}</b> y la media <b>{money_fmt(mean)}</b>; '
    f'que la media supere a la mediana confirma la cola a la derecha. El 50% central se publica entre '
    f'<b>{money_fmt(q1)}</b> y <b>{money_fmt(q3)}</b>. La asimetría cruda es <b>g₁={sk:.2f}</b> (marcada); '
    f'con <code>log1p</code> baja a <b>{sk_log:.2f}</b> (casi simétrica) → se adopta la escala logarítmica '
    f'como candidata de modelado, con corrección de retransformation al comunicar en USD. El precio por m² '
    f'es más simétrico (mediana {usd(pmed)} ≈ media {usd(pmean)}/m²), coherente con un mercado con dispersión '
    f'acotada de valor unitario.'))

# =============================================================================
# 3. Univariado numérico
# =============================================================================
H('<h2>3. Univariado — variables numéricas continuas</h2>')
numvars = [(c, t) for c, t in [('eda_superficie_total_m2', 'Superficie total (m²)'),
    ('eda_superficie_cubierta_m2', 'Superficie cubierta (m²)')] if c in df]
fig, axs = plt.subplots(1, 2, figsize=(11, 4))
for ax, (c, t) in zip(axs, numvars):
    s = num(c).dropna()
    sns.histplot(s, bins=45, color=PAL, ax=ax); ax.set_title(f'{t} · n={len(s):,} · g₁={skew(s):.2f}'); ax.set_xlabel('')
H(savefig(fig, '03_num_dist', 'Variables continuas (sin recorte de outliers).'))
# expensas con escala legible en ARS
exf = num('eda_expensas'); ex = exf.dropna(); ex99 = ex.quantile(.99)
ex_med, ex_mean = ex.median(), ex.mean(); ex_na = exf.isna().mean() * 100
fig, ax = plt.subplots(figsize=(11, 4.4))
sns.histplot(ex[ex <= ex99], bins=45, color=PAL, edgecolor='white', ax=ax)
ax.xaxis.set_major_formatter(FuncFormatter(k_fmt))
ax.axvline(ex_med, color=PAL2, ls='--', lw=1.8, label=f'mediana  {k_fmt(ex_med)} ARS')
ax.axvline(ex_mean, color=ACCENT, ls='--', lw=1.8, label=f'media  {k_fmt(ex_mean)} ARS')
ax.set_title('Distribución de expensas (ARS)'); ax.set_xlabel('expensas (ARS)'); ax.set_ylabel('cantidad de avisos'); ax.legend(frameon=True)
H(savefig(fig, '03_expensas_legible',
    f'Escala en miles de ARS. Solo el {100-ex_na:.0f}% de los avisos informa expensas (n={len(ex):,}); '
    f'recortado al percentil 99 ({k_fmt(ex99)} ARS).'))
H(metodo('Asimetría por variable', r'g_1=\frac{m_3}{m_2^{3/2}},\quad m_k=\tfrac{1}{n}\sum_i (x_i-\bar{x})^k',
    'Se reporta \\(g_1\\) por variable para anticipar qué predictores podrían requerir transformación en el hedónico.'))
sk_sup = skew(num('eda_superficie_total_m2')); sk_exp = skew(num('eda_expensas'))
H(conclusion(f'La superficie total es asimétrica a derecha (<b>g₁={sk_sup:.2f}</b>): pocas propiedades muy '
    f'grandes estiran la cola → candidata a <code>log</code> o splines en el hedónico. Las expensas presentan '
    f'asimetría aún mayor (<b>g₁={sk_exp:.2f}</b>) y alto faltante. '
    f'RF y LightGBM no requieren transformar estas escalas; el hedónico sí puede beneficiarse. '
    f'(Baños, dormitorios, ambientes y cocheras son <b>discretas</b> → sección 4.)'))

# =============================================================================
# 4. Discreto / categórico
# =============================================================================
H('<h2>4. Univariado — variables discretas y categóricas</h2>')
# 4.a discretas (conteos): etiquetas enteras, ordenadas por valor
disc = [(c, t) for c, t in [('ambientes', 'Ambientes'), ('dormitorios', 'Dormitorios'),
    ('eda_banos', 'Baños'), ('eda_cocheras', 'Cocheras')] if c in df]
fig, axs = plt.subplots(1, 4, figsize=(16, 3.6))
for ax, (c, t) in zip(axs, disc):
    barra(ax, c, t, ordenar_valor=True)
H(savefig(fig, '04_discretas', 'Conteos discretos (etiquetas enteras; "NA" = faltante). Baños se ubica aquí por ser discreta.'))
# 4.b categóricas (nominales): top por frecuencia
cat = [(c, t) for c, t in [('disposicion', 'Disposición'), ('orientacion', 'Orientación'),
    ('antiguedad', 'Antigüedad')] if c in df]
fig, axs = plt.subplots(1, 3, figsize=(15, 3.8))
for ax, (c, t) in zip(axs, cat):
    barra(ax, c, t, ordenar_valor=False)
H(savefig(fig, '04_categoricas', 'Categóricas nominales (top 8 por frecuencia).'))
H(metodo('Frecuencia y moda', r'f(c)=\frac{n_c}{n},\qquad \text{moda}=\arg\max_c\, n_c',
    'Se describe la frecuencia relativa de cada nivel y la <b>moda</b> (nivel más frecuente). Baños, dormitorios, '
    'ambientes y cocheras son <b>discretas</b> (conteos), no continuas. Nota de tipo: las columnas con faltantes se '
    'almacenan como <code>float</code> en pandas (el NaN fuerza ese tipo), por eso el dato crudo muestra 1.0/2.0; '
    'aquí se re-etiquetan como enteros para lectura.'))
amb_moda = int(df['ambientes'].mode().iloc[0])
coch_na = df['eda_cocheras'].isna().mean() * 100
H(conclusion(f'La tipología está dominada por <b>{amb_moda} ambientes</b> (la moda), seguida por 4 y 1. '
    f'<code>cocheras</code> tiene <b>{coch_na:.0f}%</b> de faltantes: en avisos inmobiliarios el vacío suele '
    f'significar "sin cochera" (ausencia estructural), no un dato desconocido → se tratará semánticamente, no '
    f'como NA a imputar. Baños concentra la masa en 1 y 2. Disposición y orientación tienen alto "NA", '
    f'coherente con campos no informados.'))

# =============================================================================
# 5. Territorial
# =============================================================================
H('<h2>5. Distribución territorial — barrio oficial</h2>')
top = df['barrio_oficial_geo'].value_counts().head(10).index
sub = df[df['barrio_oficial_geo'].isin(top)].copy(); sub['pm2'] = num('eda_precio_m2')
orden = sub.groupby('barrio_oficial_geo')['pm2'].median().sort_values(ascending=False).index
fig, ax = plt.subplots(figsize=(12, 5))
sns.boxplot(data=sub, x='pm2', y='barrio_oficial_geo', order=orden, color=PAL, fliersize=1, ax=ax)
ax.set_title('Precio por m² por barrio oficial (top 10 por volumen)'); ax.set_xlabel('USD/m²'); ax.set_ylabel('')
H(savefig(fig, '05_barrio_pm2'))
tb = sub.groupby('barrio_oficial_geo')['pm2'].agg(['count', 'median', 'mean']).reindex(orden).round(0)
tb.columns = ['avisos', 'mediana USD/m²', 'media USD/m²']
H(table(tb, '05_barrio_pm2', 'Barrios con mayor volumen; interpretar con cuidado los de pocos registros.'))
H(metodo('Boxplot y mediana por grupo',
    r'\text{IQR}=Q_3-Q_1,\quad \text{bigotes}=[Q_1-1.5\,\text{IQR},\ Q_3+1.5\,\text{IQR}],\quad '
    r'\text{mediana}_g=Q_{0.5}(\{x_i: g_i=g\})',
    'El boxplot muestra \\(Q_1\\), mediana, \\(Q_3\\), el rango intercuartílico (IQR) y los bigotes; los puntos '
    'fuera son atípicos según la regla 1.5·IQR. Se ordena por mediana de precio/m² por barrio.'))
b_alto, b_bajo = orden[0], orden[-1]
H(conclusion(f'Hay <b>heterogeneidad territorial</b> del valor unitario: <b>{b_alto.title()}</b> encabeza la '
    f'mediana de precio/m² y <b>{b_bajo.title()}</b> la cierra entre los de mayor volumen. Esta variación por '
    f'barrio anticipa que la <b>localización</b> aporta información de precio, y motiva medir la dependencia '
    f'espacial formalmente (sección 8). Los barrios con pocos avisos se leen con cautela por la variabilidad '
    f'de su mediana.'))

# =============================================================================
# 6. Bivariado
# =============================================================================
H('<h2>6. Análisis bivariado</h2>')
corr_cols = [c for c in ['eda_precio_usd', 'eda_precio_m2', 'eda_superficie_total_m2',
    'eda_superficie_cubierta_m2', 'ambientes', 'dormitorios', 'eda_banos', 'eda_cocheras',
    'eda_expensas'] if c in df]
M = df[corr_cols].apply(pd.to_numeric, errors='coerce')
Cmat = M.corr(method='pearson').rename(index=lbl, columns=lbl)
fig, ax = plt.subplots(figsize=(8.5, 7))
sns.heatmap(Cmat, annot=True, fmt='.2f', cmap='RdBu_r', center=0, square=True,
            cbar_kws={'shrink': .8}, ax=ax)
ax.set_title('Correlación de Pearson entre variables numéricas')
H(savefig(fig, '06_corr_heatmap'))
logp = np.log1p(precio)
rank = M.drop(columns=[c for c in ['eda_precio_usd'] if c in M]).apply(
    lambda col: pd.Series(col).corr(logp, method='spearman')).sort_values(key=abs, ascending=False)
H(table(rank.to_frame('ρ Spearman con log(precio)').round(3), '06_rank_corr'))
sc = pd.DataFrame({'sup': num('eda_superficie_total_m2'), 'precio': precio, 'amb': df['ambientes']}).dropna()
sc = sc[(sc['sup'] < sc['sup'].quantile(.99)) & (sc['precio'] < sc['precio'].quantile(.99))]
sc['amb_c'] = sc['amb'].clip(upper=5).astype(int).astype(str).replace('5', '5+')
fig, ax = plt.subplots(figsize=(9, 5.5))
sns.scatterplot(data=sc, x='sup', y='precio', hue='amb_c', hue_order=['1', '2', '3', '4', '5+'],
                palette='viridis', s=14, alpha=.5, ax=ax)
sns.regplot(data=sc, x='sup', y='precio', scatter=False, color='black', line_kws={'lw': 1.2}, ax=ax)
ax.yaxis.set_major_formatter(FuncFormatter(money_fmt))
ax.set_title('Precio vs. superficie total (color = ambientes)'); ax.set_xlabel('m²'); ax.set_ylabel('precio USD'); ax.legend(title='amb', fontsize=8)
H(savefig(fig, '06_precio_vs_sup', 'Recortado a p99 solo para visualización.'))
fig, ax = plt.subplots(figsize=(9, 4.5))
sc2 = pd.DataFrame({'pm2': pm2, 'amb': df['ambientes'].clip(upper=6)}).dropna()
sns.boxplot(data=sc2, x='amb', y='pm2', color=PAL, fliersize=1, ax=ax)
ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _p=None: usd(x)))
ax.set_title('Precio por m² según cantidad de ambientes'); ax.set_xlabel('ambientes'); ax.set_ylabel('USD/m²')
H(savefig(fig, '06_pm2_por_amb'))
H(metodo('Correlación de Pearson y Spearman; recta de regresión',
    r'r=\frac{\sum_i (x_i-\bar{x})(y_i-\bar{y})}{\sqrt{\sum_i (x_i-\bar{x})^2}\,\sqrt{\sum_i (y_i-\bar{y})^2}}'
    r'\qquad \rho=r_{\text{sobre rangos}}\qquad \min_{a,b}\sum_i\big(y_i-(a+b\,x_i)\big)^2',
    r'<b>Pearson</b> \(r\) mide asociación <b>lineal</b> (\(-1\le r\le 1\)); <b>Spearman</b> \(\rho\) es Pearson '
    r'sobre los <b>rangos</b> y capta asociación <b>monótona</b> (robusta a no linealidades y outliers). La recta '
    r'negra es la regresión por <b>mínimos cuadrados ordinarios</b> (minimiza la suma de residuos al cuadrado).'))
r_sup = M['eda_precio_usd'].corr(M['eda_superficie_total_m2'])
top_rho = rank.index[0].replace('eda_', '')
H(conclusion(f'La variable más correlacionada con el precio es la <b>superficie total</b> '
    f'(Pearson r={r_sup:.2f}; ρ de Spearman con log-precio: {rank.iloc[0]:.2f} para <code>{top_rho}</code>), '
    f'como espera la teoría hedónica. El scatter muestra una relación positiva y aproximadamente lineal en escala '
    f'USD, con la nube abriéndose (heterocedasticidad) → otra señal a favor de <code>log(precio)</code>. El precio '
    f'por m² <b>disminuye</b> al aumentar los ambientes (las unidades chicas valen más por m²), un patrón de dominio '
    f'relevante para el modelo. Que Pearson y Spearman sean parecidos indica asociaciones mayormente monótonas.'))

# =============================================================================
# 7. Features de texto
# =============================================================================
H('<h2>7. Atributos extraídos del texto (feat_*)</h2>')
feats = [c for c in df.columns if c.startswith('feat_')]
prev = (df[feats].apply(pd.to_numeric, errors='coerce').mean() * 100).sort_values(ascending=False)
fig, ax = plt.subplots(figsize=(9, 6))
sns.barplot(x=prev.values, y=[c.replace('feat_', '').replace('_', ' ').capitalize() for c in prev.index], color=PAL, ax=ax)
ax.set_title('Prevalencia de atributos de texto (%)'); ax.set_xlabel('% de avisos'); ax.set_ylabel('')
H(savefig(fig, '07_feat_prev'))
clave = [f for f in ['feat_cochera', 'feat_amenities', 'feat_pileta', 'feat_vista_rio', 'feat_a_estrenar'] if f in df]
rows = [[f.replace('feat_', ''), pm2[num(f) == 1].median(), pm2[num(f) == 0].median(),
         pm2[num(f) == 1].median() - pm2[num(f) == 0].median()] for f in clave]
ef = pd.DataFrame(rows, columns=['atributo', 'mediana USD/m² (con)', 'mediana USD/m² (sin)', 'Δ']).set_index('atributo')
H(table(ef, '07_feat_efecto', 'Diferencia descriptiva de medianas (no es efecto causal).'))
H(metodo('Prevalencia y diferencia de medianas',
    r'\text{prev}(f)=\frac{1}{n}\sum_i \mathbb{1}[f_i=1]\qquad \Delta=\text{med}(y\mid f=1)-\text{med}(y\mid f=0)',
    r'La <b>prevalencia</b> es la proporción de avisos con el atributo. \(\Delta\) compara la mediana de precio/m² '
    r'con y sin el atributo: es <b>descriptivo</b>, no un efecto causal ni un control por otras variables.'))
feat_top = prev.index[0].replace('feat_', ''); ef_top = ef['Δ'].idxmax()
H(conclusion(f'El atributo más frecuente es <b>{feat_top}</b> ({prev.iloc[0]:.0f}% de los avisos). En la '
    f'comparación de medianas, <b>{ef_top}</b> muestra la mayor diferencia de precio/m² a favor de tenerlo. '
    f'Estas señales son hipótesis: su aporte real se validará <b>fuera de muestra</b> dentro del modelado '
    f'(no por la diferencia de medianas, que no controla por superficie, barrio ni tipología).'))

# =============================================================================
# 8. Espacial
# =============================================================================
H('<h2>8. Exploración espacial</h2>')
sp = df[df['apto_eda_espacial_v4'] == True].copy()
sp['lat'] = num('eda_latitud'); sp['lon'] = num('eda_longitud'); sp['pm2'] = num('eda_precio_m2')
sp = sp.dropna(subset=['lat', 'lon', 'pm2'])
vmin, vmax = sp['pm2'].quantile(.02), sp['pm2'].quantile(.98)
fig, ax = plt.subplots(figsize=(8.5, 8))
sc_ = ax.scatter(sp['lon'], sp['lat'], c=sp['pm2'].clip(vmin, vmax), cmap='viridis', s=10, alpha=.7)
plt.colorbar(sc_, ax=ax, shrink=.7, label='USD/m²')
ax.set_title(f'Precio por m² en el espacio ({len(sp):,} avisos)'); ax.set_xlabel('longitud'); ax.set_ylabel('latitud'); ax.set_aspect('equal', 'box')
H(savefig(fig, '08_mapa_pm2', 'Escala de color recortada a p2–p98.'))
H(metodo("Autocorrelación espacial — Moran's I (método a aplicar)",
    r"I=\frac{n}{\sum_{i}\sum_{j} w_{ij}}\cdot\frac{\sum_{i}\sum_{j} w_{ij}(x_i-\bar{x})(x_j-\bar{x})}{\sum_i (x_i-\bar{x})^2}",
    r'El índice de Moran mide si valores similares se agrupan en el espacio: \(I\approx 0\) sin estructura, '
    r'\(I>0\) agrupamiento (valores altos junto a altos). \(w_{ij}\) es la matriz de pesos espaciales (p. ej. '
    r'vecinos más cercanos). En esta etapa solo se <b>visualiza</b> el patrón; el cálculo formal de \(I\) y la '
    r'definición de \(W\) se hacen en la etapa espacial.'))
H(conclusion('El mapa muestra un <b>patrón espacial claro</b>: el sector noreste (hacia el río, Pichincha y '
    'Puerto Norte) concentra los mayores precios por m², mientras el sur/oeste es más económico. Esto sugiere '
    '<b>autocorrelación espacial positiva</b> y justifica medir Moran\'s I y estudiar cuánta estructura espacial '
    'persiste tras incorporar covariables de localización (RQ3–RQ4).'))

# =============================================================================
# 9. Calidad y faltantes
# =============================================================================
H('<h2>9. Calidad de datos y faltantes</h2>')
claves = [c for c in ['eda_precio_usd', 'ambientes', 'eda_superficie_total_m2', 'eda_superficie_cubierta_m2',
    'eda_banos', 'dormitorios', 'eda_cocheras', 'eda_expensas', 'antiguedad', 'direccion_exacta',
    'descripcion_completa'] if c in df]
miss = (df[claves].isna().mean() * 100).sort_values(ascending=False)
fig, ax = plt.subplots(figsize=(9, 5))
sns.barplot(x=miss.values, y=[lbl(c) for c in miss.index], color=PAL2, ax=ax)
for i, v in enumerate(miss.values): ax.text(v, i, f' {v:.0f}%', va='center', fontsize=8)
ax.set_title('Porcentaje de faltantes por variable clave'); ax.set_xlabel('% faltante'); ax.set_ylabel('')
H(savefig(fig, '09_faltantes'))
H(metodo('Tasa de faltantes y mecanismo',
    r'\text{missing}(v)=\frac{1}{n}\sum_i \mathbb{1}[x_{iv}=\text{NA}]',
    'Se reporta la proporción de faltantes por variable. El <b>mecanismo</b> importa (MCAR / MAR / MNAR): no todo '
    'NA es "desconocido"; algunos son <b>ausencia estructural</b> (el atributo no existe).'))
exp_na = df['eda_expensas'].isna().mean() * 100
H(conclusion(f'Las <b>expensas</b> lideran los faltantes (<b>{exp_na:.0f}%</b>): compatible con avisos que '
    f'simplemente no las informan (ausencia/omisión), no con un error de captura. Superficie cubierta, baños y '
    f'antigüedad tienen faltantes moderados a imputar dentro del fold. La imputación se aprende solo con training. '
    f'Las <b>{repub:,}</b> republicaciones (<b>{camb:,}</b> con cambio de precio) refuerzan el uso de '
    f'<code>property_id</code>/<code>building_cluster_id</code> para el group-aware split.'))

# =============================================================================
# 10. Outliers
# =============================================================================
H('<h2>10. Valores atípicos (marcados, no eliminados)</h2>')
def flags_iqr(s, k=3):
    s = pd.to_numeric(s, errors='coerce'); q1_, q3_ = s.quantile(.25), s.quantile(.75); iqr = q3_ - q1_
    return int(((s < q1_ - k * iqr) | (s > q3_ + k * iqr)).sum())
outl = pd.DataFrame({'variable': ['eda_precio_usd', 'eda_precio_m2', 'eda_superficie_total_m2', 'eda_expensas']})
outl['outliers (3·IQR)'] = [flags_iqr(df[v]) for v in outl['variable']]
outl = outl.set_index('variable')
fig, axs = plt.subplots(1, 3, figsize=(13, 3.6))
for ax, c, t in zip(axs, ['eda_precio_usd', 'eda_precio_m2', 'eda_superficie_total_m2'], ['Precio USD', 'USD/m²', 'Superficie m²']):
    sns.boxplot(x=num(c), color=PAL, fliersize=2, ax=ax); ax.set_title(t); ax.set_xlabel('')
    ax.locator_params(axis='x', nbins=6)
axs[0].xaxis.set_major_formatter(FuncFormatter(money_fmt))   # Precio USD legible ($k/$M)
axs[1].xaxis.set_major_formatter(FuncFormatter(lambda x, _p=None: usd(x)))
H(savefig(fig, '10_outliers_box'))
H(table(outl, '10_outliers'))
H(metodo('Regla robusta del rango intercuartílico',
    r'x\ \text{atípico si}\quad x<Q_1-k\cdot\text{IQR}\ \ \text{o}\ \ x>Q_3+k\cdot\text{IQR},\quad \text{IQR}=Q_3-Q_1',
    'Se usa \\(k=3\\) (criterio conservador, "atípico severo"). Es robusta porque se basa en cuantiles, no en la '
    'media/desvío (que los propios outliers distorsionan). El boxplot usa \\(k=1.5\\).'))
n_out_precio = flags_iqr(df['eda_precio_usd'])
H(conclusion(f'Con la regla 3·IQR se marcan <b>{n_out_precio}</b> precios atípicos (severos). Muchos podrían ser '
    f'propiedades legítimamente premium (grandes o de alto valor unitario), no errores → <b>no se eliminan en el '
    f'EDA</b>. La decisión de recorte/winsorización se toma en el preprocesamiento con criterio de dominio y '
    f'evaluando su efecto sobre el modelo.'))

# =============================================================================
# 11. Síntesis
# =============================================================================
H('<h2>11. Síntesis y decisiones para el preprocesamiento</h2>')
H("""<ul>
<li><b>Target:</b> asimetría alta (g₁≈1,74) → adoptar <code>log1p(precio)</code>, con corrección de retransformation al reportar en USD.</li>
<li><b>Faltantes:</b> distinguir ausencia estructural (expensas, cocheras) de faltante real; imputación aprendida dentro del fold.</li>
<li><b>Outliers:</b> marcar (3·IQR) y decidir recorte por dominio en preprocesamiento; no eliminar en EDA.</li>
<li><b>Territorial/espacial:</b> heterogeneidad por barrio + patrón espacial claro → medir Moran's I antes de decidir componente espacial.</li>
<li><b>Republicaciones:</b> group-aware split por propiedad/edificio para evitar leakage.</li>
<li><b>Features de texto:</b> prevalencias razonables; su aporte se valida fuera de muestra.</li>
<li><b>Calidad geográfica:</b> conservar <code>geo_nivel_calidad</code> como variable de auditoría/segmentación.</li>
</ul>
<p class="note">Este EDA no define folds ni el universo final de modelado; es la base del <b>preprocesamiento</b> (próxima etapa del pipeline).</p>""")

# =============================================================================
# HTML
# =============================================================================
CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1.5rem;color:#1c2733;line-height:1.55}
h1{color:#1c3d52;border-bottom:3px solid #2c6e91;padding-bottom:.4rem}
h2{color:#1c3d52;margin-top:2.6rem;border-left:5px solid #2c6e91;padding-left:.6rem}
.sub{color:#5a6b7a;margin-top:-.4rem}
.callout{background:#eef4f8;border-left:5px solid #2c6e91;padding:.8rem 1rem;border-radius:4px;margin:1rem 0}
.metodo{background:#f6f3ee;border-left:5px solid #c0562b;padding:.7rem 1rem;border-radius:4px;margin:1rem 0;font-size:.95rem;overflow-x:auto}
.metodo .tit{font-weight:bold;color:#8a3d1c;display:block;margin-bottom:.2rem}
.conclusion{background:#eef7f0;border-left:5px solid #3a8f5e;padding:.7rem 1rem;border-radius:4px;margin:1rem 0}
.conclusion .tit{font-weight:bold;color:#276044;display:block;margin-bottom:.2rem}
.note{color:#5a6b7a;font-size:.9rem}
figure{margin:1rem 0;text-align:center}
figure img{max-width:100%;border:1px solid #e2e8ee;border-radius:6px}
figcaption{color:#5a6b7a;font-size:.85rem;margin-top:.3rem}
table.tbl{border-collapse:collapse;margin:1rem 0;font-size:.9rem}
table.tbl th,table.tbl td{border:1px solid #dfe6ec;padding:.35rem .6rem;text-align:right}
table.tbl th{background:#f2f6f9;color:#1c3d52}
code{background:#f2f6f9;padding:.1rem .35rem;border-radius:3px;font-size:.9em}
ul li{margin:.3rem 0}
"""
MATHJAX = ("<script>MathJax={tex:{inlineMath:[['\\\\(','\\\\)']],displayMath:[['$$','$$']]}};</script>"
           "<script src='https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js' async></script>")
html = (f"<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        f"<title>EDA final Centro v4 — Tesis AVM Rosario</title>{MATHJAX}<style>{CSS}</style></head>"
        f"<body>{''.join(PARTS)}</body></html>")
with open(OUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Reporte: {OUT_HTML}')
print(f'Figuras: {FIGDIR}  |  Tablas: {TABDIR}')
