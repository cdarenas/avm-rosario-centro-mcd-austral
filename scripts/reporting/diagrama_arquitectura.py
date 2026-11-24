#!/usr/bin/env python3
"""Diagrama de la arquitectura propuesta (trabajo futuro): disponibilizar el
modelo de valuación como una solución de software. Genera un PNG profesional
con Graphviz. Salida: reports/figures/arquitectura/arquitectura_propuesta.png
"""
from graphviz import Digraph
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "reports" / "figures" / "arquitectura"
OUT.mkdir(parents=True, exist_ok=True)

# paleta coherente con los reportes de la tesis
AZUL, NARANJA, VERDE, VIOL, GRIS = "#2c6e91", "#c0562b", "#3f8f5c", "#7C3AED", "#5b6b7a"

g = Digraph("arquitectura", format="png")
g.attr(rankdir="LR", splines="spline", nodesep="0.35", ranksep="0.75",
       fontname="Helvetica", bgcolor="white")
g.attr("node", shape="box", style="rounded,filled", fontname="Helvetica",
       fontsize="11", color=AZUL, fillcolor="#eaf2f7", penwidth="1.6", margin="0.18,0.11")
g.attr("edge", fontname="Helvetica", fontsize="9", color=GRIS, penwidth="1.3")

# --- Cliente ---
with g.subgraph(name="cluster_cli") as c:
    c.attr(label="Cliente", style="rounded,dashed", color=AZUL, fontcolor=AZUL, fontsize="12")
    c.node("user", "Usuario\n(tasador · inmobiliaria · particular)", fillcolor="#e0f2fe", color=AZUL)
    c.node("app", "Aplicación web\ninterfaz de tasación", fillcolor="#ede9fe", color=VIOL)

# --- Servicio de tasación (contenedor) ---
with g.subgraph(name="cluster_svc") as c:
    c.attr(label="Servicio de tasación  (contenedor)", style="rounded,filled",
           color=VERDE, fontcolor=VERDE, fillcolor="#f3fbf6", fontsize="12")
    c.node("api", "API REST\n(FastAPI)", fillcolor="#dbeafe", color=AZUL)
    c.node("orq", "Orquestador\nde la tasación", fillcolor="#fff2e8", color=NARANJA)
    c.node("modelo", "Modelo LightGBM\nprecio + intervalo", fillcolor="#ecfdf5", color=VERDE)
    c.node("shap", "Explicador SHAP\nexplicación de la tasación", fillcolor="#ecfdf5", color=VERDE)
    c.node("comp", "Comparables\npropiedades similares", fillcolor="#ecfdf5", color=VERDE)

# --- Artefactos del modelo ---
with g.subgraph(name="cluster_art") as c:
    c.attr(label="Artefactos del modelo", style="rounded,dashed", color=NARANJA, fontcolor=NARANJA, fontsize="12")
    c.node("artm", "Modelo entrenado (.pkl)\n+ configuración", shape="cylinder", fillcolor="#fffbeb", color=NARANJA)
    c.node("artd", "Datos de referencia\nmedianas por barrio · vecinos", shape="cylinder", fillcolor="#fffbeb", color=NARANJA)

# --- Servicios externos ---
with g.subgraph(name="cluster_ext") as c:
    c.attr(label="Servicios externos", style="rounded,dashed", color=VIOL, fontcolor=VIOL, fontsize="12")
    c.node("geo", "Geocodificación\ndirección → coordenadas", fillcolor="#fdf4ff", color=VIOL)

# --- MLOps ---
with g.subgraph(name="cluster_ops") as c:
    c.attr(label="Reproducibilidad y actualización (MLOps)", style="rounded,dashed",
           color=GRIS, fontcolor=GRIS, fontsize="12")
    c.node("pipe", "Pipeline reproducible\nreentrenamiento periódico", fillcolor="#f1f5f9", color=GRIS)
    c.node("reg", "Registro de versiones\ndatos y modelo por hash", fillcolor="#f1f5f9", color=GRIS)

# --- Flujo principal ---
g.edge("user", "app", label="HTTP", color=AZUL, fontcolor=AZUL)
g.edge("app", "api", label="solicitud de tasación")
g.edge("api", "orq", label="atributos")
g.edge("orq", "modelo", label="precio")
g.edge("orq", "shap", label="explicación")
g.edge("orq", "comp", label="similares")
g.edge("orq", "api", label="precio + intervalo + explicación", color=VERDE, fontcolor=VERDE, constraint="false")
g.edge("api", "app", label="respuesta (JSON)", color=AZUL, fontcolor=AZUL, constraint="false")

# --- Dependencias (punteadas) ---
g.attr("edge", style="dashed")
g.edge("api", "geo", label="dirección (opcional)", color=VIOL, fontcolor=VIOL)
g.edge("modelo", "artm", label="carga")
g.edge("modelo", "artd", label="lee")
g.edge("pipe", "artm", label="actualiza", color=GRIS)
g.edge("reg", "pipe", color=GRIS)

g.render(OUT / "arquitectura_propuesta", cleanup=True)
print("OK ->", OUT / "arquitectura_propuesta.png")
