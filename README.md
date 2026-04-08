# Binance Trading Tools

Herramienta de análisis técnico para pares de Binance orientada a dos flujos de trabajo:

- **Modo mercado**: revisar varios pares y generar un watchlist priorizado.
- **Modo posición**: analizar un solo activo ya comprado para revisar contexto, soportes, resistencias e invalidaciones de referencia.

El objetivo del script es servir como **herramienta de screening y apoyo de decisión**, no como sistema automático de ejecución.

La versión `v3_9` mejora significativamente el ranking, resolviendo el sesgo que priorizaba activos con buen score pero estado `degradado` (como TAO) por encima de activos más operables con estado `vigente`. Ahora incorpora `pullback_quality`, `rr_estructural_preliminar` y un multiplicador por calidad del setup.

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
- Filtra soportes por volumen para evitar falsos positivos.
- Genera entradas sugeridas por escalones:
  - `aggressive`
  - `base`
  - `conservative`
- Estima contexto operativo:
  - `setup_status` (vigente / degradado / invalido / pullback_activo / extendido)
  - `trend_quality`
  - `context_bias`
  - `extension_risk`
  - `pullback_quality`
  - `support_quality`
  - `zone_integrity`
- **Nuevo en v3.9:** Calcula `score_final` combinando score base con multiplicador por calidad del setup, incorporando `pullback_quality` y `rr_estructural_preliminar`
- **Nuevo en v3.9:** Flag `--only-vigent` para filtrar ranking a solo activos con setup "vigente"
- Genera salidas en:
  - `watchlist_summary.json`
  - `watchlist_summary.txt`
  - `<SIMBOLO>_summary.json`
- Guarda historial de rankings en `Snapshots/Historial/`

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

## Progreso visual

Cuando se analiza una lista amplia de monedas, el script muestra en consola:

* barra global de avance
* moneda actual en análisis
* mensajes breves por etapa del proceso
* confirmación de avance para evitar la sensación de que el script está detenido

En modo `posicion` también muestra la misma barra de progreso (consistencia visual).

---

# Ejemplos de uso con filtro vigente

```bash
py binance_trading_v3_9.py mercado --pares ETHUSDT SOLUSDT SUIUSDT --only-vigent
```
```bash
py binance_trading_v3_9.py mercado --pares BNBUSDT AVAXUSDT ETHUSDT SOLUSDT ADAUSDT --capital 433.4
```
```bash
py binance_trading_v3_9.py posicion --par ETHUSDT --privados --precio 2123.60 --inversion 423.1
```

# Archivo `.env`

## Para qué sirve

Permite guardar las credenciales de Binance fuera del código.

## Contenido esperado

Crear un archivo llamado `.env` en la misma carpeta del script:

```env
BINANCE_API_KEY=TU_API_KEY
BINANCE_API_SECRET=TU_API_SECRET
