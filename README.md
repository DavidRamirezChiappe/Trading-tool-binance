# Binance Trading Tools

Herramientas en Python para análisis de mercado y posiciones en Binance Spot, 
orientadas a una operativa simple de compra límite, 
gestión con OCO y comparación de múltiples pares.

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
Su uso es responsabilidad exclusiva del usuario. No constituye asesoría financiera, legal ni profesional.

# Trading Tools

Este documento resume los scripts creados para analizar mercado y posiciones en Binance Spot, con foco en una operativa simple de:

* elegir moneda
* definir compra límite
* gestionar posiciones con OCO
* comparar varias monedas cuando estoy en USDT

## Objetivo general

La idea de estos scripts es reemplazar parte del análisis visual por un análisis más riguroso, usando datos exactos de Binance:

* velas `15m`, `1h`, `4h`
* precio actual
* medias simples
* profundidad corta del libro
* balances, trades y órdenes abiertas
* OCO activas

Así, el análisis posterior en ChatGPT se hace sobre datos estructurados y no solo sobre capturas.

---

# 1. `binance_snapshot.py`

## Utilidad

Primera versión básica para descargar información pública de un par y guardarla en archivos.

## Qué hace

* descarga datos públicos de Binance
* obtiene velas de:

  * `15m`
  * `1h`
  * `4h`
* genera:

  * `summary.json`
  * `analysis_summary.txt`
  * `klines_15m.csv`
  * `klines_1h.csv`
  * `klines_4h.csv`

## Para qué sirve

* tener una primera fotografía del mercado
* reemplazar capturas por datos numéricos
* revisar estructura general de una moneda

## Limitaciones

* no estaba orientado todavía a posiciones reales
* no estaba pensado aún para OCO o watchlist de varias monedas
* no manejaba bien datos privados ni contexto completo de la posición

---

# 2. `binance_snapshot_v2.py`

## Utilidad

Segunda versión orientada a enriquecer el snapshot con datos privados y contexto de posición.

## Qué mejora respecto a la v1

* añade posibilidad de usar datos privados con API key
* obtiene:

  * balances
  * trades recientes
  * órdenes abiertas
  * OCO abiertas
* añade reglas del par:

  * `tickSize`
  * `stepSize`
  * `minNotional`
  * etc.

## Para qué sirve

* revisar una posición abierta con más contexto
* contrastar entrada manual con trades recientes
* ver si la OCO existe y está bien detectada

## Limitaciones

* interfaz menos amigable
* argumentos más “técnicos”
* todavía no separaba bien el caso de:

  * analizar una posición
  * analizar varias monedas para decidir una entrada nueva

---

# 3. `binance_trading_v3.py`

## Utilidad

Primera versión unificada y ya orientada a dos modos de trabajo reales:

* `posicion`
* `mercado`

## Idea central

En vez de tener dos scripts totalmente separados, se creó un solo script con dos modos:

### Modo `posicion`

Para cuando ya compré una moneda y quiero analizarla para:

* gestionar el trade
* revisar la OCO
* evaluar la estructura actual

### Modo `mercado`

Para cuando estoy en USDT y quiero comparar varias monedas para decidir:

* cuál tiene mejor estructura
* cuál tiene mejor retroceso
* dónde podría poner una compra límite

## Características

* nombres de argumentos más amigables
* opción de usar:

  * `--privados`
  * `--precio`
  * `--inversion`
* `--trades-limit` con default más amplio
* dos subcomandos:

  * `posicion`
  * `mercado`

## Limitaciones

* el ranking de `mercado` aún tenía sesgos
* sobrevaloraba algunos activos flojos, como POL en ciertos escenarios
* el modo `posicion` todavía necesitaba mejorar el resumen operativo y la lectura de OCO

---

# 4. `binance_trading_v3_1.py`

## Utilidad

Versión centrada en mejorar el modo `mercado`.

## Qué mejora

* corrige la heurística del ranking
* penaliza más la debilidad real en `4h`, sobre todo frente a `MA99`
* mejora la lógica de spread y liquidez relativa
* mejora la elección de compra límite para que no quede demasiado pegada al precio actual

## Resultado esperado

El ranking de monedas queda más razonable cuando comparo varias opciones, por ejemplo:

* ETH
* SOL
* ADA
* XRP
* POL

## Para qué sirve

* priorizar qué moneda analizar o comprar
* definir una compra límite mecánica razonable
* evitar entrar por intuición o por sesgo de recencia

## Limitaciones

* el modo `posicion` todavía no mostraba todo lo deseable sobre cobertura real de OCO y riesgo operativo

---

# 5. `binance_trading_v3_2.py`

## Utilidad

Versión enfocada en dejar el modo `posicion` realmente útil y legible.

Esta es la versión más completa y la que se decidió usar como base.

## Qué mejora respecto a la v3.1

### En modo `posicion`

* mejora el formateo numérico
* reconstruye mejor la OCO
* muestra cobertura real de la posición:

  * `qty_total`
  * `qty_cubierta_por_oco`
  * `qty_libre_fuera_oco`
  * `pct_cubierto_por_oco`
* añade resumen operativo:

  * `tp_price`
  * `sl_trigger`
  * `sl_limit`
  * distancia porcentual al TP
  * distancia porcentual al SL
  * `rr_bruto`
* añade alertas:

  * posición sin OCO
  * OCO cubriendo menos del 90%
  * múltiples OCO
  * residuos fuera de OCO
  * órdenes adicionales fuera de OCO
  * diferencias entre precio manual y estimado

### En modo `mercado`

Mantiene la lógica mejorada de la v3.1:

* ranking más robusto
* soporte principal y segundo soporte
* mejor priorización entre varias monedas

## Estado actual

Es la versión más madura del proyecto.

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

# Ejemplos de uso de `binance_trading_v3_2.py`

## A. Analizar una sola moneda ya comprada (`posicion`)

### Con datos privados y entrada manual

```bash
python binance_trading_v3_2.py posicion --par XRPUSDT --privados --precio 1.4120 --inversion 32.3
```

### Con archivo `.env` en otra ruta

```bash
python binance_trading_v3_2.py posicion --par XRPUSDT --privados --precio 1.4120 --inversion 32.3 --archivo-env C:\mis_claves\binance.env
```

### Sin datos privados, solo con entrada manual

```bash
python binance_trading_v3_2.py posicion --par ETHUSDT --precio 2028 --inversion 31.75
```

### Con más velas

```bash
python binance_trading_v3_2.py posicion --par ETHUSDT --privados --precio 2028 --inversion 31.75 --velas 200
```

---

## B. Analizar varias monedas (`mercado`)

### Watchlist básica

```bash
python binance_trading_v3_2.py mercado --pares ETHUSDT SOLUSDT ADAUSDT XRPUSDT POLUSDT
```

### Watchlist con capital de referencia personalizado

```bash
python binance_trading_v3_2.py mercado --pares ETHUSDT SOLUSDT ADAUSDT XRPUSDT POLUSDT --capital 31.2
```

### Watchlist con más velas

```bash
python binance_trading_v3_2.py mercado --pares ETHUSDT SOLUSDT ADAUSDT XRPUSDT POLUSDT --capital 31.2 --velas 200
```

---

# Flujo de trabajo recomendado

## Caso 1: estoy en USDT

1. Ejecutar modo `mercado`
2. Revisar:

   * ranking
   * compra límite sugerida
   * segundo soporte
3. elegir la moneda candidata
4. colocar la orden límite
5. esperar cierre de `4h` antes de reanalizar, salvo cambio estructural

## Caso 2: ya compré una moneda

1. Ejecutar modo `posicion`
2. revisar:

   * posición real
   * OCO
   * cobertura
   * riesgo operativo
   * alertas
3. decidir si:

   * mantener OCO
   * ajustar OCO
   * o salir del trade

---

# Regla operativa general adoptada

Cuando la decisión se tomó con base en `1h + 4h`:

* **no revisar cada hora por ansiedad**
* **revisar normalmente al cierre de una nueva vela de 4h**
* revisar antes solo si:

  * el precio está muy cerca de la orden
  * la estructura se rompe
  * el precio se aleja tanto que la orden queda desfasada

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

---

# Recomendación final

La versión recomendada para seguir usando es:

**`binance_trading_v3_2.py`**

porque:

* ya resuelve bien el modo `mercado`
* ya resuelve bien el modo `posicion`
* usa `.env`
* genera salidas legibles
* permite análisis más rigurosos y consistentes

---

# Resumen corto

## Script recomendado actual

**`binance_trading_v3_2.py`**

## Modos principales

* `posicion`: una moneda ya comprada
* `mercado`: varias monedas para elegir compra

## Archivo auxiliar recomendado

* `.env` con:

  * `BINANCE_API_KEY`
  * `BINANCE_API_SECRET`

---

