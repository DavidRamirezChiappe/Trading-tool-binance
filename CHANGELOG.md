# CHANGELOG

Todos los cambios relevantes de este proyecto se documentan aquí.

Este archivo sigue un formato simple, cronológico y orientado a uso práctico.
Las versiones listadas resumen los cambios funcionales más importantes del proyecto.

---

## [3.7] - Mejora visual de ejecución y Estado actual recomendado

### Añadido
* indicador visual de progreso en consola durante el análisis
* barra de avance global por cantidad de monedas procesadas
* línea informativa por símbolo en progreso, por ejemplo `Analizando TRXUSDT (3/10)`
* estados visibles por etapa para reforzar confianza del usuario durante la ejecución

### Cambiado
* experiencia de uso en consola más clara mientras el script trabaja en modo `mercado`
* mejora estética sin modificar la lógica de datos, ranking, zonas de entrada ni valoración técnica

### Objetivo
* mostrar al usuario que el script sigue trabajando y en qué parte del proceso se encuentra
* mejorar la confianza operativa cuando se analizan muchas monedas y el proceso tarda varios minutos

---

## [3.6] 

### Añadido
* separación entre resistencia **micro** y resistencia **operativa**
* separación entre invalidación **operativa** y **estructural**
* `zone_integrity` para clasificar la calidad de la escalera de entradas
* métricas más explícitas:
  * `rr_operativa_preliminar`
  * `rr_estructural_preliminar`

### Cambiado
* metadatos y cabeceras corregidos para reflejar correctamente la versión `3.6`
* homogeneización de textos `note`
* consolidación del watchlist como herramienta de screening más auditable
* mejora de la honestidad del output al distinguir mejor entre:
  * estructura del setup
  * operabilidad táctica
  * invalidación estructural

### Observaciones
* la parte más madura de la versión 3.6 es el screening, el ranking relativo,
  la lectura multi-timeframe y la selección de entradas
* la invalidación operativa sigue siendo una métrica preliminar y debe leerse con criterio

---

## [3.5]

### Añadido
* `trend_score`
* `tradeability_score`
* `score_bucket`
* `extension_risk`
* `pullback_quality`
* `support_quality`
* `why_ranked_here`
* primer bloque de reward/risk preliminar

### Cambiado
* el watchlist deja de ser solo un ranking simple y pasa a incluir una lectura más cercana
  a un screening profesional
* se mejora la distinción entre fuerza estructural y operabilidad táctica

### Limitaciones detectadas
* la resistencia usada para reward/risk podía quedar demasiado corta
* `initial_rr` era útil como referencia, pero no suficientemente robusto como métrica principal

---

## [3.4.1]

### Añadido
* separación mínima entre escalones usando ATR 1h y `tickSize`
* `entries_quality`:
  * `full`
  * `two_levels`
  * `single_level_only`

### Cambiado
* corrección de metadatos de versión
* posibilidad de devolver `null` cuando no existen tres entradas realmente útiles

### Resultado
* mejora clara en activos como POL, evitando falsa precisión y escalones ficticios

---

## [3.4]

### Añadido
* `candidates_debug` con `aliases`
* `trend_quality`
* `context_bias`
* `swing_low_definition`

### Cambiado
* reescritura de la lógica de entradas para intentar separar mejor:
  * `aggressive`
  * `base`
  * `conservative`
* deduplicación de niveles equivalentes tras redondeo por `tickSize`

### Objetivo
* dejar de producir entradas casi duplicadas en el modo `mercado`

---

## [3.3]

### Añadido
* ATR14 por timeframe
* `absolute_low`
* `recent_low`
* `last_swing_low`
* `support_zone`
* clasificación del setup:
  * `vigente`
  * `pullback_activo`
  * `extendido`
  * `degradado`
  * `invalido`
* invalidación mecánica inicial
* `score_breakdown`
* tres entradas:
  * `aggressive`
  * `base`
  * `conservative`

### Cambiado
* el análisis deja de depender de una única compra “exacta”
* mejora el contexto técnico tanto en `mercado` como en `posicion`

---

## [3.2]

### Añadido
* mejor reconstrucción de OCO
* cobertura real de posición:
  * `qty_total`
  * `qty_cubierta_por_oco`
  * `qty_libre_fuera_oco`
  * `pct_cubierto_por_oco`
* resumen operativo de TP / SL
* alertas de calidad de cobertura y residuos fuera de OCO

### Cambiado
* el modo `posicion` pasa a ser realmente útil para revisar un trade vivo

---

## [3.1]

### Cambiado
* mejora de la heurística del ranking en modo `mercado`
* mayor penalización a debilidad real en `4h`
* mejora de spread, liquidez relativa y selección de compra límite

### Objetivo
* priorizar mejor entre varias monedas y reducir entradas impulsivas

---

## [3.0]

### Añadido
* script unificado con dos subcomandos:
  * `posicion`
  * `mercado`
* argumentos más amigables
* posibilidad de usar:
  * `--privados`
  * `--precio`
  * `--inversion`

### Resultado
* primera versión realmente orientada al flujo de trabajo real del usuario

---

## [snapshot_v2]

### Añadido
* datos privados vía API
* balances
* trades recientes
* órdenes abiertas
* OCO abiertas
* reglas del par (`tickSize`, `stepSize`, `minNotional`, etc.)

### Resultado
* mejor contexto para posiciones reales que en la primera versión pública

---

## [snapshot]

### Añadido
* descarga de velas públicas `15m`, `1h`, `4h`
* generación de:
  * `summary.json`
  * `analysis_summary.txt`
  * `klines_15m.csv`
  * `klines_1h.csv`
  * `klines_4h.csv`

### Resultado
* primera base de trabajo para sustituir capturas de pantalla por datos estructurados.
* La idea principal es evitar la necesidad de hacer una captura de pantalla de las velas (3 por cada moneda: 15m, 1h y 4h).
