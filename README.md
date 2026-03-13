# Binance Trading Tools

Herramienta de análisis técnico para pares de Binance orientada a dos flujos de trabajo:

- **Modo mercado**: revisar varios pares y generar un watchlist priorizado.
- **Modo posición**: analizar un solo activo ya comprado para revisar contexto, soportes, resistencias e invalidaciones de referencia.

El objetivo del script es servir como **herramienta de screening y apoyo de decisión**, no como sistema automático de ejecución.

## Autor
**David Ramirez Chiappe** 

## Licencia
Este proyecto es de **uso libre y gratuito**, y se distribuye bajo la **MIT License**.

Esto significa que cualquier persona puede usarlo, copiarlo, modificarlo, publicarlo,
distribuirlo e incluso utilizarlo comercialmente, siempre que conserve el aviso de
copyright y la licencia original.

Consulta el archivo [`LICENSE`](./LICENSE) para el texto completo.

## Descargo de responsabilidad
Este software se proporciona **“tal cual”**, sin garantías de ningún tipo.
Su uso es responsabilidad exclusiva del usuario. No constituye asesoría financiera,
legal ni profesional.

## Objetivo general

La idea de estos scripts es reemplazar parte del análisis visual por un análisis más
riguroso, usando datos exactos de Binance:

* velas `15m`, `1h`, `4h`
* precio actual
* medias simples
* ATR / volatilidad
* profundidad corta del libro
* balances, trades y órdenes abiertas
* OCO activas

Así, el análisis posterior en ChatGPT se hace sobre datos estructurados y no solo
sobre capturas.

---

## Qué hace

- Descarga velas OHLCV desde Binance.
- Calcula métricas por timeframe (`15m`, `1h`, `4h`).
- Evalúa estructura con medias móviles (`MA7`, `MA25`, `MA99`).
- Calcula volatilidad con `ATR14`.
- Detecta soportes y resistencias de referencia.
- Genera entradas sugeridas por escalones:
  - `aggressive`
  - `base`
  - `conservative`
- Estima contexto operativo:
  - `setup_status`
  - `trend_quality`
  - `context_bias`
  - `extension_risk`
  - `pullback_quality`
  - `support_quality`
  - `zone_integrity`
- Genera salidas en:
  - `watchlist_summary.json`
  - `watchlist_summary.txt`
  - `<SIMBOLO>_summary.json`

---

## Qué no hace

- No ejecuta órdenes en Binance.
- No reemplaza validación humana.
- No garantiza take profit, stop loss u OCO correctos por sí solos.
- No debe interpretarse como asesoría financiera.

---

## Requisitos

- Python 3.10 o superior
- Dependencias instaladas del proyecto
- Archivo de claves API de Binance con permisos de lectura de mercado

---
# Archivo `.env`

## Para qué sirve

Permite guardar las credenciales de Binance fuera del código.

## Contenido esperado

Crear un archivo llamado `.env` en la misma carpeta del script:

```env
BINANCE_API_KEY=TU_API_KEY
BINANCE_API_SECRET=TU_API_SECRET
```

## Ventajas

* no hay que pegar claves en cada ejecución
* no se meten claves dentro del script
* el script puede leerlas automáticamente

---

# Archivos generados por los scripts

Según el modo y la versión, normalmente se generan:

* `summary.json`
* `analysis_summary.txt`
* `klines_15m.csv`
* `klines_1h.csv`
* `klines_4h.csv`

En modo `mercado` además:

* `watchlist_summary.json`
* `watchlist_summary.txt`
* archivos individuales por símbolo:

  * `ETHUSDT_summary.json`
  * `ETHUSDT_klines_15m.csv`
  * etc.

## Qué significa cada uno

### `summary.json`

Resumen estructurado y más completo, pensado para análisis técnico y revisión detallada.

### `analysis_summary.txt`

Versión legible y resumida para lectura rápida.

### `klines_*.csv`

Datos crudos de velas. Sirven para:

* recalcular indicadores
* auditoría
* análisis posterior
* detectar patrones más finos

### `watchlist_summary.*`

Resumen comparativo de varias monedas.

## Campos más útiles en versiones recientes

En `v3_5` y `v3_6` aparecen, según el modo:

* `setup_status`
* `trend_quality`
* `context_bias`
* `support_zone`
* `entries`:

  * `aggressive`
  * `base`
  * `conservative`
* `entries_quality`
* `zone_integrity`
* `trend_score`
* `tradeability_score`
* `score_bucket`
* `extension_risk`
* `pullback_quality`
* `support_quality`
* `why_ranked_here`
* `nearest_resistance_micro`
* `nearest_resistance_operativa`
* `rr_operativa_preliminar`
* `rr_estructural_preliminar`
* `stop_candidate_operativo`
* `stop_candidate_estructural`
* `atr14`
* `candidates_debug`

---

# Cuándo usar cada modo

## Usar `posicion`

Cuando:

* ya compré una moneda
* ya tengo o quiero tener OCO
* quiero revisar riesgo, cobertura, PnL y estructura

## Usar `mercado`

Cuando:

* estoy en USDT
* quiero decidir entre varias monedas
* quiero identificar una compra límite razonable
* quiero un ranking de candidatos

---

# Ejemplos de uso de `binance_trading_v3_6.py`

## A. Analizar una sola moneda ya comprada (`posicion`)

### Con datos privados y entrada manual

```bash
python binance_trading_v3_6.py posicion --par XRPUSDT --privados --precio 1.4120 --inversion 32.3
```

### Con archivo `.env` en otra ruta

```bash
python binance_trading_v3_6.py posicion --par XRPUSDT --privados --precio 1.4120 --inversion 32.3 --archivo-env C:\mis_claves\binance.env
```

### Sin datos privados, solo con entrada manual

```bash
python binance_trading_v3_6.py posicion --par ETHUSDT --precio 2028 --inversion 31.75
```

### Con más velas

```bash
python binance_trading_v3_6.py posicion --par ETHUSDT --privados --precio 2028 --inversion 31.75 --velas 200
```

---

## B. Analizar varias monedas (`mercado`)

### Watchlist básica

```bash
python binance_trading_v3_6.py mercado --pares ETHUSDT SOLUSDT ADAUSDT XRPUSDT POLUSDT
```

### Watchlist con capital de referencia personalizado

```bash
python binance_trading_v3_6.py mercado --pares ETHUSDT SOLUSDT ADAUSDT XRPUSDT POLUSDT --capital 31.2
```

### Watchlist con más velas

```bash
python binance_trading_v3_6.py mercado --pares ETHUSDT SOLUSDT ADAUSDT XRPUSDT POLUSDT --capital 31.2 --velas 200
```

### Watchlist con todos los pares que quieras analizar

```bash
python binance_trading_v3_6.py mercado --pares ETHUSDT SOLUSDT ADAUSDT XRPUSDT POLUSDT ROBOUSDT
```

---

# Observaciones importantes

## Sobre `--precio` y `--inversion`

Sirven para anclar el análisis a la operación que realmente interesa.

Aunque el script puede inferir información desde `--privados`, no siempre puede reconstruir perfectamente:

* qué entrada exacta quieres analizar
* cuánto USDT invertiste en esa operación concreta

Por eso estos argumentos siguen siendo útiles.

## Sobre los CSV

Aunque muchas veces basta con `summary.json` y `analysis_summary.txt`, los CSV siguen siendo valiosos porque:

* guardan los datos crudos
* permiten recalcular indicadores
* sirven para auditoría
* ayudan si luego se quiere hacer backtesting o mejoras del sistema

## Sobre el ranking

El ranking es una ayuda de priorización, no una garantía de compra.

Sirve para comparar candidatos, pero la decisión final debe revisar también:

* estructura `4h`
* calidad del pullback `1h`
* contexto del `15m`
* cercanía real al soporte
* invalidación técnica
* calidad de la zona
* operabilidad real del setup

---

## Buenas prácticas de uso

- Analiza siempre con datos recientes.
- Usa el watchlist como filtro, no como piloto automático.
- Contrasta el activo elegido con su resumen individual.
- No tomes `score`, `rr_operativa_preliminar` o invalidaciones como órdenes listas para ejecutar sin revisión humana.
- En compras límite, revisa luego el contexto actualizado antes de definir OCO.

---

## Estructura recomendada del proyecto

```bash
project/
├── binance_trading_v3_6.py
├── README.md
├── CHANGELOG.md
└── snapshots/
```

Puedes guardar los outputs en una carpeta separada si quieres mantener el proyecto más ordenado.

---
