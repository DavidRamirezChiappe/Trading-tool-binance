#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Binance Trading Tools v0.1
# Copyright (c) 2026 David Ramirez Chiappe
#
# Este archivo forma parte del proyecto Binance Trading Tools.
# Distribuido bajo la licencia MIT.
#
# Se permite su uso, copia, modificación, publicación, distribución
# y sublicenciamiento, conforme a los términos de la licencia MIT.
#
# Consulta el archivo LICENSE en la raíz del proyecto para el texto completo.
# Este software se proporciona "tal cual", sin garantías de ningún tipo.
"""
binance_snapshot.py

Descarga datos de Binance Spot para un símbolo y genera:
- summary.json
- klines_15m.csv
- klines_1h.csv
- klines_4h.csv
- analysis_summary.txt

Modo público:
    python binance_snapshot.py --symbol XRPUSDT

Modo con datos privados (solo lectura):
    set BINANCE_API_KEY=tu_api_key
    set BINANCE_API_SECRET=tu_api_secret
    python binance_snapshot.py --symbol XRPUSDT --include-private

Notas:
- Usa data-api.binance.vision para datos públicos.
- Usa api.binance.com para endpoints privados firmados.
- Recomendado: API key de solo lectura, sin permisos de trading ni retiros.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PUBLIC_BASE = "https://data-api.binance.vision"
PRIVATE_BASE = "https://api.binance.com"


def http_get_json(base_url: str, path: str, params: Optional[Dict[str, Any]] = None,
                  headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Any:
    params = params or {}
    headers = headers or {}
    query = urlencode(params)
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{query}"

    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code} al consultar {url}\n{body}") from e
    except URLError as e:
        raise RuntimeError(f"Error de red al consultar {url}: {e}") from e


def get_server_time_ms() -> int:
    data = http_get_json(PRIVATE_BASE, "/api/v3/time")
    return int(data["serverTime"])


def signed_get_json(path: str, api_key: str, api_secret: str,
                    params: Optional[Dict[str, Any]] = None,
                    timeout: int = 20) -> Any:
    params = params or {}
    params["timestamp"] = get_server_time_ms()
    params["recvWindow"] = 10000

    query = urlencode(params)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    signed_query = f"{query}&signature={signature}"
    url = f"{PRIVATE_BASE}{path}?{signed_query}"

    req = Request(
        url,
        headers={"X-MBX-APIKEY": api_key},
        method="GET"
    )

    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code} al consultar {url}\n{body}") from e
    except URLError as e:
        raise RuntimeError(f"Error de red al consultar {url}: {e}") from e


def parse_klines(raw_klines: List[List[Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for k in raw_klines:
        rows.append({
            "open_time_ms": int(k[0]),
            "open_time_utc": datetime.fromtimestamp(int(k[0]) / 1000, tz=timezone.utc).isoformat(),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time_ms": int(k[6]),
            "close_time_utc": datetime.fromtimestamp(int(k[6]) / 1000, tz=timezone.utc).isoformat(),
            "quote_asset_volume": float(k[7]),
            "number_of_trades": int(k[8]),
            "taker_buy_base_volume": float(k[9]),
            "taker_buy_quote_volume": float(k[10]),
        })
    return rows


def moving_average(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def timeframe_summary(candles: List[Dict[str, Any]], recent_window: int = 20) -> Dict[str, Any]:
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    recent = candles[-recent_window:] if len(candles) >= recent_window else candles
    recent_high = max(c["high"] for c in recent) if recent else None
    recent_low = min(c["low"] for c in recent) if recent else None

    return {
        "candles_count": len(candles),
        "last_open_time_utc": candles[-1]["open_time_utc"] if candles else None,
        "last_close": closes[-1] if closes else None,
        "last_high": highs[-1] if highs else None,
        "last_low": lows[-1] if lows else None,
        "last_volume": candles[-1]["volume"] if candles else None,
        "ma7": moving_average(closes, 7),
        "ma25": moving_average(closes, 25),
        "ma99": moving_average(closes, 99),
        "recent_high": recent_high,
        "recent_low": recent_low,
    }


def save_csv(filepath: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    with filepath.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def extract_assets(symbol: str, quote_asset: str = "USDT") -> Dict[str, str]:
    if not symbol.endswith(quote_asset):
        return {"base_asset": symbol, "quote_asset": quote_asset}
    base = symbol[:-len(quote_asset)]
    return {"base_asset": base, "quote_asset": quote_asset}


def build_analysis_text(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"PAR: {summary['symbol']}")
    lines.append(f"PRECIO ACTUAL: {summary['ticker']['lastPrice']}")
    lines.append(f"CAMBIO 24H (%): {summary['ticker']['priceChangePercent']}")
    lines.append(f"MAX 24H: {summary['ticker']['highPrice']}")
    lines.append(f"MIN 24H: {summary['ticker']['lowPrice']}")
    lines.append(f"VOL 24H ({summary['base_asset']}): {summary['ticker']['volume']}")
    lines.append("")

    for tf in ["15m", "1h", "4h"]:
        tf_data = summary["timeframes"][tf]
        lines.append(f"{tf}:")
        lines.append(f"  Last close: {tf_data['last_close']}")
        lines.append(f"  MA7: {tf_data['ma7']}")
        lines.append(f"  MA25: {tf_data['ma25']}")
        lines.append(f"  MA99: {tf_data['ma99']}")
        lines.append(f"  Recent high: {tf_data['recent_high']}")
        lines.append(f"  Recent low: {tf_data['recent_low']}")
        lines.append(f"  Last volume: {tf_data['last_volume']}")
        lines.append("")

    if summary.get("private_data"):
        lines.append("DATOS PRIVADOS:")
        pd = summary["private_data"]

        balances = pd.get("balances", {})
        if balances:
            lines.append(f"  Balance {summary['base_asset']}: {balances.get(summary['base_asset'])}")
            lines.append(f"  Balance {summary['quote_asset']}: {balances.get(summary['quote_asset'])}")

        recent_trades = pd.get("recent_trades", [])
        if recent_trades:
            lines.append("  Trades recientes:")
            for t in recent_trades[:5]:
                lines.append(
                    f"    {t['time_utc']} | side={'BUY' if t['isBuyer'] else 'SELL'} | "
                    f"price={t['price']} | qty={t['qty']} | quoteQty={t['quoteQty']}"
                )

        open_orders = pd.get("open_orders", [])
        if open_orders:
            lines.append("  Órdenes abiertas:")
            for o in open_orders[:10]:
                lines.append(
                    f"    orderId={o['orderId']} | side={o['side']} | type={o['type']} | "
                    f"price={o['price']} | origQty={o['origQty']} | status={o['status']}"
                )
        lines.append("")

    return "\n".join(lines)


def fetch_public_market_data(symbol: str, limit: int) -> Dict[str, Any]:
    ticker = http_get_json(
        PUBLIC_BASE,
        "/api/v3/ticker/24hr",
        params={"symbol": symbol}
    )

    depth = http_get_json(
        PUBLIC_BASE,
        "/api/v3/depth",
        params={"symbol": symbol, "limit": 20}
    )

    timeframes_raw = {
        "15m": http_get_json(PUBLIC_BASE, "/api/v3/klines", params={"symbol": symbol, "interval": "15m", "limit": limit}),
        "1h": http_get_json(PUBLIC_BASE, "/api/v3/klines", params={"symbol": symbol, "interval": "1h", "limit": limit}),
        "4h": http_get_json(PUBLIC_BASE, "/api/v3/klines", params={"symbol": symbol, "interval": "4h", "limit": limit}),
    }

    timeframes = {}
    csv_rows = {}
    for tf, raw in timeframes_raw.items():
        parsed = parse_klines(raw)
        csv_rows[tf] = parsed
        timeframes[tf] = timeframe_summary(parsed)

    return {
        "ticker": ticker,
        "depth_top_10": {
            "bids": depth.get("bids", [])[:10],
            "asks": depth.get("asks", [])[:10],
        },
        "timeframes": timeframes,
        "csv_rows": csv_rows,
    }


def fetch_private_data(symbol: str, base_asset: str, quote_asset: str,
                       api_key: str, api_secret: str) -> Dict[str, Any]:
    account = signed_get_json("/api/v3/account", api_key, api_secret)
    balances_map: Dict[str, Dict[str, str]] = {}
    for b in account.get("balances", []):
        if b["asset"] in {base_asset, quote_asset}:
            balances_map[b["asset"]] = {
                "free": b["free"],
                "locked": b["locked"]
            }

    recent_trades_raw = signed_get_json(
        "/api/v3/myTrades",
        api_key,
        api_secret,
        params={"symbol": symbol, "limit": 20}
    )

    open_orders_raw = signed_get_json(
        "/api/v3/openOrders",
        api_key,
        api_secret,
        params={"symbol": symbol}
    )

    recent_trades = []
    for t in recent_trades_raw:
        recent_trades.append({
            "id": t["id"],
            "orderId": t["orderId"],
            "price": t["price"],
            "qty": t["qty"],
            "quoteQty": t["quoteQty"],
            "commission": t["commission"],
            "commissionAsset": t["commissionAsset"],
            "isBuyer": t["isBuyer"],
            "isMaker": t["isMaker"],
            "time_ms": t["time"],
            "time_utc": datetime.fromtimestamp(t["time"] / 1000, tz=timezone.utc).isoformat(),
        })

    open_orders = []
    for o in open_orders_raw:
        open_orders.append({
            "symbol": o["symbol"],
            "orderId": o["orderId"],
            "price": o["price"],
            "origQty": o["origQty"],
            "executedQty": o["executedQty"],
            "status": o["status"],
            "type": o["type"],
            "side": o["side"],
            "timeInForce": o.get("timeInForce"),
        })

    return {
        "balances": balances_map,
        "recent_trades": recent_trades,
        "open_orders": open_orders,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera snapshot de Binance Spot en JSON y CSV.")
    parser.add_argument("--symbol", required=True, help="Ejemplo: XRPUSDT")
    parser.add_argument("--limit", type=int, default=120, help="Cantidad de velas por timeframe (máx. recomendado: 500)")
    parser.add_argument("--outdir", default="snapshots", help="Carpeta de salida")
    parser.add_argument("--include-private", action="store_true", help="Incluye balances, trades y órdenes abiertas (requiere API key)")
    parser.add_argument("--quote-asset", default="USDT", help="Quote asset para separar el base asset. Por defecto: USDT")
    args = parser.parse_args()

    symbol = args.symbol.upper().strip()
    limit = max(30, min(args.limit, 500))

    assets = extract_assets(symbol, args.quote_asset.upper())
    base_asset = assets["base_asset"]
    quote_asset = assets["quote_asset"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.outdir) / f"{symbol}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        public_data = fetch_public_market_data(symbol, limit)
    except Exception as e:
        print(f"Error obteniendo datos públicos: {e}", file=sys.stderr)
        return 1

    summary: Dict[str, Any] = {
        "generated_at_local": datetime.now().isoformat(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "ticker": public_data["ticker"],
        "depth_top_10": public_data["depth_top_10"],
        "timeframes": public_data["timeframes"],
    }

    if args.include_private:
        api_key = os.getenv("BINANCE_API_KEY", "").strip()
        api_secret = os.getenv("BINANCE_API_SECRET", "").strip()

        if not api_key or not api_secret:
            print("Pediste --include-private pero faltan BINANCE_API_KEY y/o BINANCE_API_SECRET.", file=sys.stderr)
            return 1

        try:
            summary["private_data"] = fetch_private_data(symbol, base_asset, quote_asset, api_key, api_secret)
        except Exception as e:
            print(f"Error obteniendo datos privados: {e}", file=sys.stderr)
            return 1

    summary_path = output_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    for tf, rows in public_data["csv_rows"].items():
        save_csv(output_dir / f"klines_{tf}.csv", rows)

    analysis_text = build_analysis_text(summary)
    with (output_dir / "analysis_summary.txt").open("w", encoding="utf-8") as f:
        f.write(analysis_text)

    print(f"OK. Snapshot generado en: {output_dir.resolve()}")
    print(f"- {summary_path.name}")
    print("- klines_15m.csv")
    print("- klines_1h.csv")
    print("- klines_4h.csv")
    print("- analysis_summary.txt")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())