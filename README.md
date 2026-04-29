# Binance Trading Tools

Herramienta de análisis técnico para pares de Binance orientada a dos flujos de trabajo:

* **Modo mercado**: revisar varios pares y generar un watchlist priorizado.
* **Modo posición**: analizar un solo activo ya comprado para revisar contexto, soportes, resistencias e invalidaciones de referencia.

El objetivo del script es servir como **herramienta de screening y apoyo de decisión**, no como sistema automático de ejecución.

---

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

---

### Nuevas capacidades en v4.2.0

La versión 4.2 introduce una capa táctica adicional orientada a mejorar la operabilidad real de las órdenes límite y las futuras OCO.

#### `entry_mode`

El sistema ahora puede seleccionar entradas mediante distintos modos:

* `conservative`
* `balanced`
* `aggressive`

Esto permite equilibrar:

* calidad técnica
* probabilidad de ejecución
* reward/risk posterior

---

#### `fill_probability`

Nueva métrica que estima la probabilidad de que la orden límite llegue a ejecutarse.

Considera:

* distancia al precio actual
* distancia en ATR
* aceleración del timeframe `15m`
* cercanía a máximos recientes
* calidad del pullback

---

#### `oco_viability`

Evalúa si una futura OCO tiene sentido económico antes de recomendar la compra.

Incluye:

* TP táctico
* stop táctico
* reward %
* risk %
* RR táctico
* aire técnico del stop (`stop_air_atr`)
* alcanzabilidad del TP (`tp_reachability`)

---

#### `expected_value_score`

Nueva métrica compuesta que intenta priorizar oportunidades más operables en trading real.

Combina:

* probabilidad de fill
* calidad de la OCO
* relación reward/risk

---

### Nueva estructura de outputs (v4.2)

Cada ejecución ahora genera su propia subcarpeta:

```bash
Snapshots/
├── Historial/
├── Mercado/
│   └── mercado_TIMESTAMP/
└── Posicion/
    └── posicion_SYMBOL_TIMESTAMP/
```

Esto mejora:

* trazabilidad
* auditoría
* comparación entre ejecuciones
* organización histórica

---

### Filosofía operativa actual

La lógica del sistema ya no intenta únicamente encontrar “compras baratas”.

Ahora intenta responder:

> “Si compro aquí, ¿la futura OCO tendrá sentido económico real?”

Por eso el ranking actual considera:

* probabilidad de ejecución
* calidad del soporte
* espacio hasta resistencia
* aire técnico del stop
* alcanzabilidad del TP
* reward/risk táctico


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

* Descarga velas OHLCV desde Binance.
* Calcula métricas por timeframe (`15m`, `1h`, `4h`).
* Evalúa estructura con medias móviles (`MA7`, `MA25`, `MA99`).
* Calcula volatilidad con `ATR14`.
* Detecta soportes y resistencias de referencia.
* Genera entradas sugeridas por escalones:

  * `aggressive`
  * `base`
  * `conservative`
* Estima contexto operativo:

  * `setup_status`
  * `trend_quality`
  * `context_bias`
  * `extension_risk`
  * `pullback_quality`
  * `support_quality`
  * `zone_integrity`

### Modo mercado

Se generan:

* `1_Watchlist_YYYYMMDD_HHMMSS.json`
* `1_Watchlist_YYYYMMDD_HHMMSS.txt`
* archivos individuales por símbolo

### Modo posición

Se generan:

* `1_<SIMBOLO>_summary.json`
* `1_<SIMBOLO>_summary.txt`

---

## Qué no hace

* No ejecuta órdenes en Binance.
* No reemplaza validación humana.
* No garantiza take profit, stop loss u OCO correctos por sí solos.
* No debe interpretarse como asesoría financiera.

---

## Requisitos

* Python 3.10 o superior
* Dependencias instaladas del proyecto
* Archivo de claves API de Binance con permisos de lectura de mercado

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

* `1_Watchlist_*.json`
* `1_Watchlist_*.txt`

---

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

## Campos más útiles en versiones recientes

* `setup_status`
* `trend_quality`
* `context_bias`
* `support_zone`
* `entries`
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

# Ejemplos de uso (v4.2)

## A. Analizar una sola moneda (`posicion`)

```bash
python binance_trading_v4_2.py posicion --par XRPUSDT --privados --precio 1.4120 --inversion 32.3
```

## B. Analizar varias monedas (`mercado`)

```bash
python binance_trading_v4_2.py mercado --pares ETHUSDT SOLUSDT ADAUSDT XRPUSDT POLUSDT
python binance_trading_v4_2.py mercado --pares SUIUSDT LINKUSDT ROBOUSDT --capital 44.1
```

---

# Observaciones importantes

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

* Analiza siempre con datos recientes.
* Usa el watchlist como filtro, no como piloto automático.
* Contrasta el activo elegido con su resumen individual.
* No tomes métricas como órdenes listas para ejecutar sin revisión humana.
* En compras límite, revisa el contexto antes de definir OCO.

---

## Estructura recomendada del proyecto

```bash
project/
├── binance_trading_v4_2.py
├── .env
├── README.md
├── CHANGELOG.md
└── Snapshots/
```
