#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Binance Trading Tools v2
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
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PUBLIC_BASE = "https://data-api.binance.vision"
PRIVATE_BASE = "https://api.binance.com"
EPS = 1e-12


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_get_json(
    base_url: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> Any:
    params = params or {}
    headers = headers or {}
    query = urlencode(params, doseq=True)
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


def signed_get_json(
    path: str,
    api_key: str,
    api_secret: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Any:
    params = params.copy() if params else {}
    params["timestamp"] = get_server_time_ms()
    params["recvWindow"] = 10000

    query = urlencode(params, doseq=True)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    url = f"{PRIVATE_BASE}{path}?{query}&signature={signature}"
    req = Request(url, headers={"X-MBX-APIKEY": api_key}, method="GET")
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
        rows.append(
            {
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
            }
        )
    return rows


def moving_average(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def timeframe_summary(candles: List[Dict[str, Any]], recent_window: int = 20) -> Dict[str, Any]:
    closes = [c["close"] for c in candles]
    recent = candles[-recent_window:] if len(candles) >= recent_window else candles
    return {
        "candles_count": len(candles),
        "last_open_time_utc": candles[-1]["open_time_utc"] if candles else None,
        "last_close": closes[-1] if closes else None,
        "last_high": candles[-1]["high"] if candles else None,
        "last_low": candles[-1]["low"] if candles else None,
        "last_volume": candles[-1]["volume"] if candles else None,
        "ma7": moving_average(closes, 7),
        "ma25": moving_average(closes, 25),
        "ma99": moving_average(closes, 99),
        "recent_high": max(c["high"] for c in recent) if recent else None,
        "recent_low": min(c["low"] for c in recent) if recent else None,
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
    return {"base_asset": symbol[: -len(quote_asset)], "quote_asset": quote_asset}


def normalize_number_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        f = float(value)
    except Exception:
        return str(value)
    return format(f, ".16f").rstrip("0").rstrip(".") or "0"


def extract_symbol_filters(exchange_info: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    symbols = exchange_info.get("symbols", [])
    match = next((s for s in symbols if s.get("symbol") == symbol), None)
    if not match:
        return {}

    filters = {f["filterType"]: f for f in match.get("filters", []) if "filterType" in f}

    out = {
        "symbol": match.get("symbol"),
        "status": match.get("status"),
        "baseAsset": match.get("baseAsset"),
        "quoteAsset": match.get("quoteAsset"),
        "baseAssetPrecision": match.get("baseAssetPrecision"),
        "quotePrecision": match.get("quotePrecision"),
        "permissions": match.get("permissions", []),
        "allowTrailingStop": match.get("allowTrailingStop"),
        "cancelReplaceAllowed": match.get("cancelReplaceAllowed"),
        "filters": {},
    }

    wanted = [
        "PRICE_FILTER",
        "LOT_SIZE",
        "MARKET_LOT_SIZE",
        "MIN_NOTIONAL",
        "NOTIONAL",
        "MAX_NUM_ORDERS",
        "MAX_NUM_ALGO_ORDERS",
        "TRAILING_DELTA",
    ]
    for name in wanted:
        if name in filters:
            out["filters"][name] = filters[name]

    price_filter = filters.get("PRICE_FILTER", {})
    lot_size = filters.get("LOT_SIZE", {})
    market_lot_size = filters.get("MARKET_LOT_SIZE", {})
    min_notional = filters.get("MIN_NOTIONAL", {})
    notional = filters.get("NOTIONAL", {})

    out["rules_short"] = {
        "tickSize": price_filter.get("tickSize"),
        "minPrice": price_filter.get("minPrice"),
        "maxPrice": price_filter.get("maxPrice"),
        "stepSize": lot_size.get("stepSize"),
        "minQty": lot_size.get("minQty"),
        "maxQty": lot_size.get("maxQty"),
        "marketStepSize": market_lot_size.get("stepSize"),
        "marketMinQty": market_lot_size.get("minQty"),
        "marketMaxQty": market_lot_size.get("maxQty"),
        "minNotional": min_notional.get("minNotional") or notional.get("minNotional"),
        "maxNotional": notional.get("maxNotional"),
        "maxNumOrders": (filters.get("MAX_NUM_ORDERS") or {}).get("maxNumOrders"),
        "maxNumAlgoOrders": (filters.get("MAX_NUM_ALGO_ORDERS") or {}).get("maxNumAlgoOrders"),
    }

    return out


def depth_summary(depth: Dict[str, Any], levels: int = 10) -> Dict[str, Any]:
    bids = depth.get("bids", [])[:levels]
    asks = depth.get("asks", [])[:levels]

    def sum_notional(rows: List[List[str]]) -> float:
        total = 0.0
        for price, qty in rows:
            total += float(price) * float(qty)
        return total

    best_bid = float(bids[0][0]) if bids else None
    best_ask = float(asks[0][0]) if asks else None
    spread_abs = (best_ask - best_bid) if best_bid is not None and best_ask is not None else None
    spread_pct = (spread_abs / best_bid * 100.0) if spread_abs is not None and best_bid else None

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_abs": spread_abs,
        "spread_pct": spread_pct,
        "bid_notional_top10": sum_notional(bids),
        "ask_notional_top10": sum_notional(asks),
        "bids": bids,
        "asks": asks,
    }


def fetch_public_market_data(symbol: str, limit: int) -> Dict[str, Any]:
    ticker = http_get_json(PUBLIC_BASE, "/api/v3/ticker/24hr", params={"symbol": symbol})
    depth = http_get_json(PUBLIC_BASE, "/api/v3/depth", params={"symbol": symbol, "limit": 20})
    exchange_info = http_get_json(PUBLIC_BASE, "/api/v3/exchangeInfo", params={"symbol": symbol})

    raw_tfs = {
        "15m": http_get_json(PUBLIC_BASE, "/api/v3/klines", params={"symbol": symbol, "interval": "15m", "limit": limit}),
        "1h": http_get_json(PUBLIC_BASE, "/api/v3/klines", params={"symbol": symbol, "interval": "1h", "limit": limit}),
        "4h": http_get_json(PUBLIC_BASE, "/api/v3/klines", params={"symbol": symbol, "interval": "4h", "limit": limit}),
    }

    csv_rows: Dict[str, List[Dict[str, Any]]] = {}
    tf_summary: Dict[str, Any] = {}
    for tf, raw in raw_tfs.items():
        parsed = parse_klines(raw)
        csv_rows[tf] = parsed
        tf_summary[tf] = timeframe_summary(parsed)

    return {
        "ticker": ticker,
        "depth_summary": depth_summary(depth, levels=10),
        "symbol_info": extract_symbol_filters(exchange_info, symbol),
        "csv_rows": csv_rows,
        "timeframes": tf_summary,
    }


def fetch_private_data(symbol: str, base_asset: str, quote_asset: str, api_key: str, api_secret: str, trades_limit: int) -> Dict[str, Any]:
    account = signed_get_json(
        "/api/v3/account",
        api_key,
        api_secret,
        params={"omitZeroBalances": "true"},
    )
    balances_map: Dict[str, Dict[str, str]] = {}
    for b in account.get("balances", []):
        if b["asset"] in {base_asset, quote_asset}:
            balances_map[b["asset"]] = {
                "free": b["free"],
                "locked": b["locked"],
                "total": normalize_number_str(float(b["free"]) + float(b["locked"])),
            }

    recent_trades_raw = signed_get_json(
        "/api/v3/myTrades",
        api_key,
        api_secret,
        params={"symbol": symbol, "limit": trades_limit},
    )

    open_orders_raw = signed_get_json(
        "/api/v3/openOrders",
        api_key,
        api_secret,
        params={"symbol": symbol},
    )

    open_order_lists_raw = signed_get_json(
        "/api/v3/openOrderList",
        api_key,
        api_secret,
    )

    recent_trades: List[Dict[str, Any]] = []
    for t in recent_trades_raw:
        recent_trades.append(
            {
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
            }
        )

    open_orders: List[Dict[str, Any]] = []
    for o in open_orders_raw:
        open_orders.append(
            {
                "symbol": o.get("symbol"),
                "orderId": o.get("orderId"),
                "orderListId": o.get("orderListId"),
                "clientOrderId": o.get("clientOrderId"),
                "price": o.get("price"),
                "origQty": o.get("origQty"),
                "executedQty": o.get("executedQty"),
                "status": o.get("status"),
                "type": o.get("type"),
                "side": o.get("side"),
                "stopPrice": o.get("stopPrice"),
                "timeInForce": o.get("timeInForce"),
                "workingTime": o.get("workingTime"),
            }
        )

    open_order_lists: List[Dict[str, Any]] = []
    for ol in open_order_lists_raw:
        if ol.get("symbol") != symbol:
            continue
        open_order_lists.append(ol)

    return {
        "account_flags": {
            "makerCommission": account.get("makerCommission"),
            "takerCommission": account.get("takerCommission"),
            "buyerCommission": account.get("buyerCommission"),
            "sellerCommission": account.get("sellerCommission"),
            "canTrade": account.get("canTrade"),
            "requireSelfTradePrevention": account.get("requireSelfTradePrevention"),
            "updateTime": account.get("updateTime"),
        },
        "balances": balances_map,
        "recent_trades": recent_trades,
        "open_orders": open_orders,
        "open_order_lists": open_order_lists,
    }


def summarize_trades(recent_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not recent_trades:
        return {}
    ordered = sorted(recent_trades, key=lambda x: x["time_ms"])
    last_trade = ordered[-1]
    last_buy = next((t for t in reversed(ordered) if t["isBuyer"]), None)
    last_sell = next((t for t in reversed(ordered) if not t["isBuyer"]), None)

    buy_quote = sum(float(t["quoteQty"]) for t in ordered if t["isBuyer"])
    sell_quote = sum(float(t["quoteQty"]) for t in ordered if not t["isBuyer"])
    buy_qty = sum(float(t["qty"]) for t in ordered if t["isBuyer"])
    sell_qty = sum(float(t["qty"]) for t in ordered if not t["isBuyer"])

    return {
        "last_trade": last_trade,
        "last_buy": last_buy,
        "last_sell": last_sell,
        "recent_aggregate": {
            "buy_qty": normalize_number_str(buy_qty),
            "sell_qty": normalize_number_str(sell_qty),
            "buy_quote": normalize_number_str(buy_quote),
            "sell_quote": normalize_number_str(sell_quote),
            "net_qty": normalize_number_str(buy_qty - sell_qty),
            "net_quote_flow": normalize_number_str(sell_quote - buy_quote),
        },
    }


def estimate_position_from_recent_trades(current_qty: float, recent_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Estimación práctica, no contable.
    Va hacia atrás sobre trades recientes y reconstruye qué compras probablemente
    alimentan la posición actual. Funciona bien si sueles hacer una sola entrada
    por símbolo y luego salir completo. Si mezclas muchas vueltas en el mismo par,
    tómalo como aproximación.
    """
    if current_qty <= EPS:
        return {
            "current_qty": 0.0,
            "estimated_avg_entry": None,
            "covered_qty": 0.0,
            "missing_qty": 0.0,
            "warning": "Sin posición base actual.",
            "method": "recent-trades-backward-estimate",
            "lots_used": [],
        }

    ordered_desc = sorted(recent_trades, key=lambda x: x["time_ms"], reverse=True)
    target_qty = current_qty
    lots: List[Dict[str, Any]] = []

    for t in ordered_desc:
        qty = float(t["qty"])
        price = float(t["price"])
        if t["isBuyer"]:
            alloc = min(qty, target_qty)
            if alloc > EPS:
                lots.append(
                    {
                        "trade_id": t["id"],
                        "orderId": t["orderId"],
                        "time_utc": t["time_utc"],
                        "qty_used": normalize_number_str(alloc),
                        "price": normalize_number_str(price),
                    }
                )
                target_qty -= alloc
                if target_qty <= EPS:
                    break
        else:
            target_qty += qty

    covered_qty = sum(float(l["qty_used"]) for l in lots)
    avg_entry = None
    if covered_qty > EPS:
        total_cost = sum(float(l["qty_used"]) * float(l["price"]) for l in lots)
        avg_entry = total_cost / covered_qty

    warning = None
    missing = max(0.0, current_qty - covered_qty)
    if missing > EPS:
        warning = (
            "El historial reciente no alcanzó para reconstruir toda la posición actual. "
            "Sube el límite de trades o usa --manual-entry-price / --manual-quote-size si quieres un snapshot más exacto."
        )

    return {
        "current_qty": normalize_number_str(current_qty),
        "estimated_avg_entry": normalize_number_str(avg_entry),
        "covered_qty": normalize_number_str(covered_qty),
        "missing_qty": normalize_number_str(missing),
        "warning": warning,
        "method": "recent-trades-backward-estimate",
        "lots_used": list(reversed(lots)),
    }


def build_position_snapshot(
    symbol: str,
    base_asset: str,
    quote_asset: str,
    ticker: Dict[str, Any],
    private_data: Optional[Dict[str, Any]],
    manual_entry_price: Optional[float],
    manual_quote_size: Optional[float],
) -> Dict[str, Any]:
    last_price = float(ticker["lastPrice"])
    position: Dict[str, Any] = {
        "symbol": symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "last_price": normalize_number_str(last_price),
        "base_qty_total": None,
        "quote_free": None,
        "quote_locked": None,
        "quote_total": None,
        "entry_price": None,
        "position_notional_quote": None,
        "unrealized_pnl_quote": None,
        "unrealized_pnl_pct": None,
        "source": None,
        "notes": [],
    }

    if not private_data:
        if manual_entry_price is not None and manual_quote_size is not None:
            base_qty = manual_quote_size / manual_entry_price
            position.update(
                {
                    "base_qty_total": normalize_number_str(base_qty),
                    "entry_price": normalize_number_str(manual_entry_price),
                    "position_notional_quote": normalize_number_str(base_qty * last_price),
                    "unrealized_pnl_quote": normalize_number_str(base_qty * (last_price - manual_entry_price)),
                    "unrealized_pnl_pct": normalize_number_str(((last_price / manual_entry_price) - 1.0) * 100.0),
                    "source": "manual",
                }
            )
            position["notes"].append("Posición calculada desde parámetros manuales.")
        else:
            position["notes"].append("Sin datos privados ni parámetros manuales; no se pudo construir posición.")
        return position

    balances = private_data.get("balances", {})
    base_balance = balances.get(base_asset, {"free": "0", "locked": "0", "total": "0"})
    quote_balance = balances.get(quote_asset, {"free": "0", "locked": "0", "total": "0"})

    base_qty_total = float(base_balance.get("total", "0") or 0.0)
    position["base_qty_total"] = normalize_number_str(base_qty_total)
    position["quote_free"] = quote_balance.get("free")
    position["quote_locked"] = quote_balance.get("locked")
    position["quote_total"] = quote_balance.get("total")

    trade_summary = summarize_trades(private_data.get("recent_trades", []))
    estimate = estimate_position_from_recent_trades(base_qty_total, private_data.get("recent_trades", []))
    position["trade_summary"] = trade_summary
    position["estimate"] = estimate

    chosen_entry: Optional[float] = None
    source = None
    if manual_entry_price is not None:
        chosen_entry = manual_entry_price
        source = "manual-entry-price"
        position["notes"].append("Se priorizó el entry manual sobre la estimación de trades.")
    elif estimate.get("estimated_avg_entry") is not None:
        chosen_entry = float(estimate["estimated_avg_entry"])
        source = "estimated-from-recent-trades"
        if estimate.get("warning"):
            position["notes"].append(estimate["warning"])
    elif trade_summary.get("last_buy"):
        chosen_entry = float(trade_summary["last_buy"]["price"])
        source = "last-buy-fallback"
        position["notes"].append("No se pudo estimar promedio; se usó el último BUY como fallback.")

    if chosen_entry is not None and base_qty_total > EPS:
        pnl_quote = base_qty_total * (last_price - chosen_entry)
        pnl_pct = ((last_price / chosen_entry) - 1.0) * 100.0 if chosen_entry > EPS else None
        position["entry_price"] = normalize_number_str(chosen_entry)
        position["position_notional_quote"] = normalize_number_str(base_qty_total * last_price)
        position["unrealized_pnl_quote"] = normalize_number_str(pnl_quote)
        position["unrealized_pnl_pct"] = normalize_number_str(pnl_pct)
        position["source"] = source

    if manual_quote_size is not None:
        position["manual_quote_size"] = normalize_number_str(manual_quote_size)

    return position


def summarize_open_oco(open_order_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for ol in open_order_lists:
        orders = ol.get("orders", [])
        reports = ol.get("orderReports", [])
        summary = {
            "orderListId": ol.get("orderListId"),
            "contingencyType": ol.get("contingencyType"),
            "listStatusType": ol.get("listStatusType"),
            "listOrderStatus": ol.get("listOrderStatus"),
            "listClientOrderId": ol.get("listClientOrderId"),
            "transactionTime": ol.get("transactionTime"),
            "symbol": ol.get("symbol"),
            "legs": [],
            "orders": orders,
        }
        for r in reports:
            summary["legs"].append(
                {
                    "orderId": r.get("orderId"),
                    "type": r.get("type"),
                    "side": r.get("side"),
                    "price": r.get("price"),
                    "stopPrice": r.get("stopPrice"),
                    "origQty": r.get("origQty"),
                    "executedQty": r.get("executedQty"),
                    "status": r.get("status"),
                }
            )
        out.append(summary)
    return out


def build_analysis_text(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"PAR: {summary['symbol']}")
    lines.append(f"GENERADO UTC: {summary['generated_at_utc']}")
    lines.append(f"PRECIO ACTUAL: {summary['ticker']['lastPrice']}")
    lines.append(f"CAMBIO 24H (%): {summary['ticker']['priceChangePercent']}")
    lines.append(f"MAX 24H: {summary['ticker']['highPrice']}")
    lines.append(f"MIN 24H: {summary['ticker']['lowPrice']}")
    lines.append(f"VOL 24H ({summary['base_asset']}): {summary['ticker']['volume']}")
    lines.append("")

    rules = summary.get("symbol_info", {}).get("rules_short", {})
    if rules:
        lines.append("REGLAS DEL PAR:")
        for key in [
            "tickSize",
            "stepSize",
            "minQty",
            "maxQty",
            "minNotional",
            "maxNumOrders",
            "maxNumAlgoOrders",
        ]:
            if rules.get(key) is not None:
                lines.append(f"  {key}: {rules[key]}")
        lines.append("")

    depth = summary.get("depth_summary", {})
    if depth:
        lines.append("LIQUIDEZ CORTA:")
        lines.append(f"  best_bid: {depth.get('best_bid')}")
        lines.append(f"  best_ask: {depth.get('best_ask')}")
        lines.append(f"  spread_abs: {depth.get('spread_abs')}")
        lines.append(f"  spread_pct: {depth.get('spread_pct')}")
        lines.append(f"  bid_notional_top10: {depth.get('bid_notional_top10')}")
        lines.append(f"  ask_notional_top10: {depth.get('ask_notional_top10')}")
        lines.append("")

    position = summary.get("position_snapshot", {})
    if position:
        lines.append("POSICIÓN:")
        for key in [
            "base_qty_total",
            "quote_free",
            "quote_locked",
            "quote_total",
            "entry_price",
            "position_notional_quote",
            "unrealized_pnl_quote",
            "unrealized_pnl_pct",
            "source",
        ]:
            if position.get(key) is not None:
                lines.append(f"  {key}: {position[key]}")
        for note in position.get("notes", []):
            lines.append(f"  note: {note}")
        estimate = position.get("estimate")
        if estimate:
            lines.append(f"  estimate_current_qty: {estimate.get('current_qty')}")
            lines.append(f"  estimate_avg_entry: {estimate.get('estimated_avg_entry')}")
            lines.append(f"  estimate_warning: {estimate.get('warning')}")
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

    private_data = summary.get("private_data")
    if private_data:
        lines.append("DATOS PRIVADOS:")
        balances = private_data.get("balances", {})
        if balances:
            for asset, bal in balances.items():
                lines.append(f"  Balance {asset}: free={bal.get('free')} locked={bal.get('locked')} total={bal.get('total')}")

        trade_summary = position.get("trade_summary", {}) if position else {}
        if trade_summary.get("last_buy"):
            lb = trade_summary["last_buy"]
            lines.append(f"  last_buy: {lb['time_utc']} price={lb['price']} qty={lb['qty']} quoteQty={lb['quoteQty']}")
        if trade_summary.get("last_sell"):
            ls = trade_summary["last_sell"]
            lines.append(f"  last_sell: {ls['time_utc']} price={ls['price']} qty={ls['qty']} quoteQty={ls['quoteQty']}")

        open_orders = private_data.get("open_orders", [])
        if open_orders:
            lines.append("  Órdenes abiertas:")
            for o in open_orders[:20]:
                lines.append(
                    f"    orderId={o['orderId']} | listId={o['orderListId']} | side={o['side']} | type={o['type']} | "
                    f"price={o['price']} | stopPrice={o['stopPrice']} | origQty={o['origQty']} | status={o['status']}"
                )

        open_oco = summary.get("open_oco_summary", [])
        if open_oco:
            lines.append("  OCO abiertas:")
            for oco in open_oco:
                lines.append(
                    f"    orderListId={oco['orderListId']} | contingencyType={oco['contingencyType']} | "
                    f"listStatusType={oco['listStatusType']} | listOrderStatus={oco['listOrderStatus']}"
                )
                for leg in oco["legs"]:
                    lines.append(
                        f"      leg orderId={leg['orderId']} | side={leg['side']} | type={leg['type']} | "
                        f"price={leg['price']} | stopPrice={leg['stopPrice']} | status={leg['status']}"
                    )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera snapshot v2 de Binance Spot en JSON y CSV.")
    parser.add_argument("--symbol", required=True, help="Ejemplo: XRPUSDT")
    parser.add_argument("--limit", type=int, default=120, help="Velas por timeframe. Recomendado: 120 a 300.")
    parser.add_argument("--outdir", default="snapshots", help="Carpeta de salida")
    parser.add_argument("--include-private", action="store_true", help="Incluye balances, trades y órdenes abiertas/OCO")
    parser.add_argument("--quote-asset", default="USDT", help="Quote asset; por defecto USDT")
    parser.add_argument("--trades-limit", type=int, default=200, help="Cantidad de trades recientes a descargar")
    parser.add_argument("--manual-entry-price", type=float, default=None, help="Precio de entrada manual para mejorar el snapshot")
    parser.add_argument("--manual-quote-size", type=float, default=None, help="Tamaño en quote asset invertido manualmente")
    args = parser.parse_args()

    symbol = args.symbol.upper().strip()
    limit = max(30, min(args.limit, 500))
    quote_asset = args.quote_asset.upper().strip()
    assets = extract_assets(symbol, quote_asset)
    base_asset = assets["base_asset"]

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
        "generated_at_utc": now_utc_iso(),
        "symbol": symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "ticker": public_data["ticker"],
        "depth_summary": public_data["depth_summary"],
        "symbol_info": public_data["symbol_info"],
        "timeframes": public_data["timeframes"],
    }

    private_data: Optional[Dict[str, Any]] = None
    if args.include_private:
        api_key = os.getenv("BINANCE_API_KEY", "").strip()
        api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
        if not api_key or not api_secret:
            print("Pediste --include-private pero faltan BINANCE_API_KEY y/o BINANCE_API_SECRET.", file=sys.stderr)
            return 1
        try:
            private_data = fetch_private_data(symbol, base_asset, quote_asset, api_key, api_secret, args.trades_limit)
            summary["private_data"] = private_data
            summary["open_oco_summary"] = summarize_open_oco(private_data.get("open_order_lists", []))
        except Exception as e:
            print(f"Error obteniendo datos privados: {e}", file=sys.stderr)
            return 1

    summary["position_snapshot"] = build_position_snapshot(
        symbol=symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        ticker=public_data["ticker"],
        private_data=private_data,
        manual_entry_price=args.manual_entry_price,
        manual_quote_size=args.manual_quote_size,
    )

    summary_path = output_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    for tf, rows in public_data["csv_rows"].items():
        save_csv(output_dir / f"klines_{tf}.csv", rows)

    analysis_text = build_analysis_text(summary)
    with (output_dir / "analysis_summary.txt").open("w", encoding="utf-8") as f:
        f.write(analysis_text)

    print(f"OK. Snapshot v2 generado en: {output_dir.resolve()}")
    print("- summary.json")
    print("- klines_15m.csv")
    print("- klines_1h.csv")
    print("- klines_4h.csv")
    print("- analysis_summary.txt")
    if args.include_private:
        print("- private_data incluido: balances, trades, openOrders y openOrderList")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
