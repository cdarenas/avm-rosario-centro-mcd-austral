#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Genera el reporte HTML del EDA a partir del notebook (fuente reproducible).
#
#   Fuente:  notebooks/01_eda/04_eda_final_centro_v4.ipynb
#   Salida:  reports/eda_final_centro_v4.html   (reporte limpio, sin código)
#            reports/mapas/mapa_barrios_distrito_centro.html  (mapa standalone)
#
# Uso:   bash scripts/eda/exportar_reporte_html.sh
#
# Requisitos:  pip install jupyter nbconvert nbclient ipykernel \
#                          pandas numpy matplotlib seaborn folium branca
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/../.."          # raíz del repo

NB="notebooks/01_eda/04_eda_final_centro_v4.ipynb"

echo "1/2 · Ejecutando el notebook de punta a punta…"
jupyter nbconvert --to notebook --execute --inplace "$NB"

echo "2/2 · Exportando a HTML (sin celdas de código)…"
jupyter nbconvert --to html --no-input "$NB" \
    --output-dir reports --output eda_final_centro_v4

# Ajuste de presentación: ancho de lectura cómodo + imágenes centradas a tamaño completo
python3 - <<'PY'
from pathlib import Path
p = Path("reports/eda_final_centro_v4.html")
html = p.read_text(encoding="utf-8")
css = """<style>
.jp-Notebook, #notebook, .jp-Cell { max-width: 1120px; margin-left: auto; margin-right: auto; }
.jp-RenderedHTMLCommon { font-size: 15px; line-height: 1.6; }
.jp-OutputArea-output img, img { max-width: 100%; height: auto; display: block; margin: 0.6em auto; }
table.dataframe { margin: 0.6em auto; font-size: 13.5px; }
</style>"""
if "</head>" in html and "max-width: 1120px" not in html:
    p.write_text(html.replace("</head>", css + "\n</head>", 1), encoding="utf-8")
    print("· presentación HTML ajustada (ancho de lectura + imágenes centradas)")
PY

echo "Listo:"
echo "  · reports/eda_final_centro_v4.html"
echo "  · reports/mapas/mapa_barrios_distrito_centro.html"
