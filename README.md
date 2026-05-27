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
