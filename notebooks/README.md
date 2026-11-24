# Notebooks

Los notebooks se organizan según su función:

- `01_eda/`: exploración inicial.
- `02_data_quality/`: controles y diagnóstico de calidad.
- `03_spatial/`: análisis y transformaciones espaciales.
- `04_experiments/`: ejecución y presentación de experimentos.

Dentro de cada carpeta, usar nombres ordenados y descriptivos. El código que se
reutilice debe trasladarse a `src/avm_rosario/`.

## Ejecución en VS Code

Crear y seleccionar el entorno `.venv`, instalar
`scripts/eda/requirements.txt` y abrir
`01_eda/01_eda_inicial_centro_v2.ipynb`. El kernel debe apuntar a
`.venv/bin/python`. Luego ejecutar `Run All` desde la raíz del repositorio.

El notebook v2 conserva outliers y faltantes. Los límites p01–p99 utilizados en
algunos histogramas son exclusivamente visuales y no alteran los datos.

`01_eda/03_eda_muestra_analitica_centro_v4.ipynb` trabaja sobre la muestra v4 y
usa las variables consolidadas `eda_*`. Resume el flujo de observaciones,
faltantes, distribuciones, tipologías y cobertura espacial. Sus gráficos no
realizan recortes ni transformaciones permanentes.
