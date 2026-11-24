# Flujo de captura por ambiente — scraper_v2

Guía operativa para armar el dataset del Distrito Centro **de a un ambiente por vez**. Base de salida: `salida/zonaprop_v2.db` (todo se acumula ahí, deduplicando).

## Pasos por ambiente

```bash
cd scripts/scraping/zonaprop_v2

# 1) Scraping (listado por bandas de precio + detalle). Guarda incremental cada 50.
python3 run_scraping_v2.py 2        # luego 3, 4, 5 en sesiones separadas

# 2) Geocodificación — Georef es el PRINCIPAL (rápido, confiable para AR).
python3 geocodificar_georef.py      # 1º: Georef, dirección exacta (el grueso)
python3 geocodificar_fallback.py    # 2º: Georef a nivel calle (cruces/difíciles)
python3 geocodificar.py             # 3º OPCIONAL: Nominatim para el resto
                                    #    (servidor público inestable: da 503 seguido; se puede saltar)

# 3) Verificación de calidad
python3 verificar_corrida.py
```

## Reglas de ritmo (para no quemar la IP)

- **Un ambiente por sesión**, espaciados (no los 4 de corrido). El **detalle** es lo lento e intensivo (~1,5 s/aviso) y es lo que gatilla el bloqueo de Cloudflare.
- Si ZonaProp empieza a bloquear (requests que tardan minutos, muchos 403), **frená y retomá más tarde o desde otra red** (hotspot del celular / VPN). El bloqueo es temporal (horas).
- Para ser más conservador: subir `DELAY_DETALLE` en `config.py` a 2,5–3 s.

## Robustez (ya incorporada)

- **Guardado incremental cada 50** avisos → un corte o bloqueo pierde a lo sumo 50.
- **Reanudación:** `--resume RUN_ID` saltea lo ya guardado en esa corrida. Una
  corrida nueva vuelve a observar avisos activos y genera un snapshot temporal.
- **Particionado por bandas de precio** con subdivisión adaptativa → supera el tope de ~9 páginas de ZonaProp y captura ~100% de los avisos por ambiente.
- **Exclusiones** registradas con motivo (sin precio, fuera de zona…). No se pierden datos en silencio.

## Qué esperar

- La cobertura de coordenadas debe medirse en cada corrida y desagregarse por
  proveedor y precisión. Los faltantes se conservan; su tratamiento corresponde
  al pipeline de cada modelo.
- Precio: se captura **precio de publicación** en USD; los avisos en ARS o sin precio quedan marcados/excluidos.
- Tiempos: el detalle domina. 1.400 avisos ≈ 35 min sin bloqueo; con bloqueo, mucho más (ahí conviene parar).

## Al terminar todos los ambientes

- Correr `verificar_corrida.py` sobre la base completa.
- Revisar: volumen total, cobertura de coordenadas, tasa de republicación, faltantes, plausibilidad.
- Recién ahí: EDA y feature engineering (geoespacial + texto) sobre `zonaprop_v2.db`.

## Referencia de scripts

| Script | Qué hace |
|---|---|
| `run_scraping_v2.py [amb]` | Scraping + detalle + guardado (incremental). |
| `geocodificar_georef.py` | 1ª pasada con Georef (dirección). |
| `geocodificar_fallback.py` | 2ª pasada a nivel calle (Georef). |
| `geocodificar.py` | 3ª pasada opcional con Nominatim. |
| `reevaluar.py` | Recalcula zona / limpia geocodes errados (sin red). |
| `verificar_corrida.py` | Informe de calidad de la base. |
| `construir_dataset_candidato.py` | Tabla interim con flags, sin exclusiones. |
| `exportar_auditoria_identidad.py` | CSV para validar candidatos de republicación y clusters. |
