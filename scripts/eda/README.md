# EDA reproducible

`perfil_eda_inicial.py` genera tablas descriptivas y un manifiesto a partir del
dataset preliminar compartido. No modifica la entrada, no imputa faltantes, no
recorta outliers y no convierte las alertas en exclusiones automáticas.

```bash
python scripts/eda/perfil_eda_inicial.py \
  data/processed/zonaprop_v2_eda_centro_v1.csv.gz \
  reports/tables/eda_centro_v1
```

El perfil distingue el universo completo, los casos aptos para análisis espacial
preliminar y los casos pendientes. Las tablas producidas son insumos de auditoría
y no constituyen todavía evidencia de desempeño predictivo.
