# Binance Trading Tools

Herramienta de análisis técnico para pares de Binance orientada a dos flujos de trabajo principales:

* **Modo mercado**: analiza varios pares y genera un watchlist priorizado.
* **Modo posición**: analiza un activo ya comprado para revisar contexto, riesgo, cobertura, soportes, resistencias y OCO activas.

El objetivo del proyecto es servir como **herramienta de screening y apoyo de decisión**, no como sistema automático de ejecución.

---

## Autor

**David Ramirez Chiappe**

---

## Licencia

Este proyecto es de uso libre y gratuito, y se distribuye bajo la **MIT License**.

Puedes usarlo, copiarlo, modificarlo, publicarlo, distribuirlo y utilizarlo comercialmente, siempre que conserves el aviso de copyright y la licencia original.

Consulta el archivo `LICENSE` para el texto completo.

---

## Descargo de responsabilidad

Este software se proporciona “tal cual”, sin garantías de ningún tipo.

Su uso es responsabilidad exclusiva del usuario. No constituye asesoría financiera, legal ni profesional. El script no garantiza resultados, beneficios, ejecución de órdenes, take profit ni stop loss correctos.

---

## Objetivo general

La idea del script es reemplazar parte del análisis visual manual por un análisis más estructurado usando datos de Binance:

* velas OHLCV
* precio actual
* medias móviles
* ATR / volatilidad
* profundidad corta del libro
* balances
* trades recientes
* órdenes abiertas
* OCO activas

El análisis posterior puede hacerse sobre datos estructurados en vez de depender solo de capturas o interpretación visual.

---

## Qué hace

El script puede:

* descargar datos públicos de mercado desde Binance
* analizar pares en timeframes `15m`, `1h` y `4h`
* calcular métricas técnicas básicas
* evaluar estructura de mercado
* estimar soportes y resistencias
* sugerir zonas de compra límite
* calcular contexto táctico de TP y stop
* estimar probabilidad de ejecución de una orden límite
* evaluar viabilidad de una futura OCO
* priorizar pares en un ranking
* revisar posiciones abiertas
* detectar OCO activas
* estimar PnL no realizado
* generar archivos JSON, TXT y CSV para auditoría

---

## Qué no hace

El script no:

* ejecuta órdenes automáticamente
* reemplaza la revisión humana
* garantiza beneficios
* garantiza que una OCO sea correcta
* predice el futuro del mercado
* debe usarse como asesoría financiera

---

## Requisitos

* Python 3.10 o superior
* Acceso a internet
* Cuenta de Binance
* API Key y API Secret de Binance si se usará el modo privado
* Permisos de lectura para consultar balances, trades y órdenes

---

## Archivo `.env`

Para usar funciones privadas, crea un archivo `.env` en la misma carpeta del script.

Contenido esperado:

```env
BINANCE_API_KEY=TU_API_KEY
BINANCE_API_SECRET=TU_API_SECRET
```

Ventajas:

* evita pegar claves en cada ejecución
* mantiene las claves fuera del código
* permite que el script las lea automáticamente

No compartas tu archivo `.env`.

---

## Modos de uso

El script tiene dos modos principales:

```bash
mercado
posicion
```

---

## Modo mercado

Usa `mercado` cuando estás en USDT y quieres decidir entre varias monedas.

Ejemplo:

```bash
python binance_trading_v4_2_2.py mercado --pares SUIUSDT LINKUSDT TRXUSDT BNBUSDT AVAXUSDT ETHUSDT SOLUSDT XRPUSDT POLUSDT TAOUSDT LTCUSDT DOGEUSDT SHIBUSDT ROBOUSDT CFGUSDT --capital 42
```

También puedes analizar menos pares:

```bash
python binance_trading_v4_2_2.py mercado --pares ETHUSDT SOLUSDT XRPUSDT POLUSDT --capital 42
```

### Velas por defecto

El estándar operativo es usar 200 velas.

No necesitas indicar `--velas` si quieres usar el valor estándar.

Ejemplo con valor por defecto:

```bash
python binance_trading_v4_2_2.py mercado --pares ETHUSDT SOLUSDT XRPUSDT --capital 42
```

Ejemplo modificando la cantidad de velas:

```bash
python binance_trading_v4_2_2.py mercado --pares ETHUSDT SOLUSDT XRPUSDT --capital 42 --velas 300
```

---

## Modo posición

Usa `posicion` cuando ya compraste una moneda y quieres revisar la operación.

Ejemplo con datos privados:

```bash
python binance_trading_v4_2_2.py posicion --par POLUSDT --privados --precio 0.0918 --inversion 42
```

Ejemplo sin datos privados:

```bash
python binance_trading_v4_2_2.py posicion --par POLUSDT --precio 0.0918 --inversion 42
```

Parámetros habituales:

* `--par`: símbolo a analizar
* `--privados`: usa datos privados de Binance
* `--precio`: precio de entrada
* `--inversion`: inversión aproximada en USDT

---

## Estructura de salidas

El script genera archivos dentro de `Snapshots/`.

Estructura general:

```bash
Snapshots/
├── Historial/
├── Mercado/
│   └── mercado_TIMESTAMP/
└── Posicion/
    └── posicion_SYMBOL_TIMESTAMP/
```

---

## Archivos principales

En modo mercado:

```bash
1_Watchlist_YYYYMMDD_HHMMSS.json
1_Watchlist_YYYYMMDD_HHMMSS.txt
```

En modo posición:

```bash
1_SYMBOL_summary.json
1_SYMBOL_summary.txt
```

Además, pueden generarse archivos auxiliares:

```bash
klines_15m.csv
klines_1h.csv
klines_4h.csv
summary.json
analysis_summary.txt
ranking_features_*.jsonl
rankings_history.json
trade_journal.json
```

---

## Historial

El script mantiene un historial en:

```bash
Snapshots/Historial/
```

Archivos relevantes:

```bash
rankings_history.json
trade_journal.json
```

`rankings_history.json` guarda información de rankings y señales por corrida.

`trade_journal.json` permite registrar resultados reales de operaciones, como:

* orden no ejecutada
* take profit
* stop loss
* cancelación
* símbolo
* entrada
* TP
* stop
* resultado
* duración

El objetivo del journal es mejorar la evaluación futura del sistema usando resultados reales, no solo señales teóricas.

---

## Campos útiles del análisis

Algunos campos relevantes que pueden aparecer en los outputs:

```text
setup_status
trend_quality
context_bias
entry_mode
fill_probability
fill_score
fill_atr_distance_1h
oco_viability
oco_rr
reward_pct
risk_pct
stop_air_atr
stop_air_quality
expected_value_score
trade_mode
market_regime
diagnostic_flags
```

Estos campos ayudan a interpretar si una oportunidad es técnica, operable, de vigilancia o descartable.

---

## Interpretación general

El ranking no debe leerse como una orden automática.

Antes de operar, conviene revisar:

* estructura en `4h`
* calidad del pullback en `1h`
* timing en `15m`
* distancia de la entrada al precio actual
* distancia en ATR
* R:R táctico
* aire real del stop
* alcanzabilidad del TP
* spread
* liquidez
* contexto general del mercado

---

## Modos operativos internos

El script puede clasificar oportunidades en modos como:

```text
SWING_OCO
SCALP_FAST_DIAGNOSTIC
WATCHLIST
NO_TRADE
```

Significado general:

* `SWING_OCO`: oportunidad apta para análisis de compra límite con posible OCO.
* `SCALP_FAST_DIAGNOSTIC`: posible oportunidad rápida, solo informativa.
* `WATCHLIST`: activo interesante, pero no listo para operar.
* `NO_TRADE`: activo descartado por filtros o contexto.

`SCALP_FAST_DIAGNOSTIC` no debe interpretarse como recomendación automática de compra.

---

## Buenas prácticas

* Ejecuta el análisis con datos recientes.
* Usa el modo mercado como filtro inicial.
* Revisa el resumen individual antes de operar.
* No uses el ranking como piloto automático.
* Revisa siempre el R:R realista después de ajustar el stop.
* Evita operar si el mercado general está débil y no hay setups claros.
* Registra los resultados reales en el trade journal.
* Revisa el CHANGELOG para entender los cambios de cada versión.

---

## Estructura recomendada del proyecto

```bash
project/
├── binance_trading_v4_2_2.py
├── .env
├── README.md
├── CHANGELOG.md
├── LICENSE
└── Snapshots/
```

---

## Historial de versiones

Los detalles de cada versión se documentan en `CHANGELOG.md`.

El README se mantiene como guía de uso general del script.
