#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Binance Trading Tools v3.2
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
En el archivo README.md puedes encontrar toda la documentación de este script.
Tambien encontrarás:
 - Ejemplos de cómo utilizar este script
 - Cómo colocar la API de Binance en un archivo aparte
 - Mayor información del script y sus argumentos
 - Info de esta versión y versiones anteriores
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PUBLIC_BASE = "https://data-api.binance.vision"
PRIVATE_BASE = "https://api.binance.com"
EPS = 1e-12


# =========================
# Utilidades generales
# =========================

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


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def to_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def normalize_number_str(value: Any, decimals: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        if decimals is not None:
            q = Decimal("1").scaleb(-decimals)
            d = d.quantize(q, rounding=ROUND_HALF_UP)
        s = format(d, "f")
        return s.rstrip("0").rstrip(".") or "0"
    except Exception:
        return str(value)


def pct_change(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or abs(b) <= EPS:
        return None
    return ((a / b) - 1.0) * 100.0


def save_csv(filepath: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    with filepath.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(filepath: Path, payload: Dict[str, Any]) -> None:
    with filepath.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_text(filepath: Path, content: str) -> None:
    with filepath.open("w", encoding="utf-8") as f:
        f.write(content)


def extract_assets(symbol: str, quote_asset: str = "USDT") -> Dict[str, str]:
    if not symbol.endswith(quote_asset):
        return {"base_asset": symbol, "quote_asset": quote_asset}
    return {"base_asset": symbol[: -len(quote_asset)], "quote_asset": quote_asset}


def moving_average(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def decimal_places_from_step(step: Optional[str]) -> Optional[int]:
    if not step or step in ("0", "0.0"):
        return None
    try:
        d = Decimal(str(step)).normalize()
        exp = d.as_tuple().exponent
        return max(0, -exp)
    except Exception:
        return None


def format_with_step(value: Any, step: Optional[str], rounding=ROUND_HALF_UP) -> Optional[str]:
    if value is None:
        return None
    if not step or step in ("0", "0.0"):
        return normalize_number_str(value, 8)
    try:
        d = Decimal(str(value))
        q = Decimal(str(step))
        d = d.quantize(q, rounding=rounding)
        s = format(d, "f")
        return s.rstrip("0").rstrip(".") or "0"
    except (InvalidOperation, ValueError):
        return normalize_number_str(value, 8)


def format_price(value: Any, tick_size: Optional[str]) -> Optional[str]:
    return format_with_step(value, tick_size, rounding=ROUND_HALF_UP)


def format_qty(value: Any, step_size: Optional[str]) -> Optional[str]:
    return format_with_step(value, step_size, rounding=ROUND_DOWN)


def format_quote(value: Any, decimals: int = 6) -> Optional[str]:
    return normalize_number_str(value, decimals)


def format_pct(value: Any, decimals: int = 4) -> Optional[str]:
    return normalize_number_str(value, decimals)


def floor_to_step(value: float, step: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if step in (None, "", "0", "0.0"):
        return normalize_number_str(value, 8)
    v = to_decimal(value)
    s = to_decimal(step)
    floored = (v / s).to_integral_value(rounding=ROUND_DOWN) * s
    return format(floored, "f").rstrip("0").rstrip(".") or "0"


# =========================
# Lectura de .env
# =========================

def load_dotenv_file(env_path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and (
            (value.startswith('"') and value.endswith('"')) or
            (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]

        values[key] = value

    return values


def resolve_binance_credentials(env_file_arg: Optional[str]) -> Tuple[str, str, str]:
    env_key = os.getenv("BINANCE_API_KEY", "").strip()
    env_secret = os.getenv("BINANCE_API_SECRET", "").strip()

    if env_key and env_secret:
        return env_key, env_secret, "variables_de_entorno"

    candidate_paths: List[Path] = []

    if env_file_arg:
        candidate_paths.append(Path(env_file_arg).expanduser().resolve())

    script_dir = Path(__file__).resolve().parent
    candidate_paths.append(script_dir / ".env")
    candidate_paths.append(Path.cwd() / ".env")

    seen = set()
    unique_paths: List[Path] = []
    for p in candidate_paths:
        p_str = str(p)
        if p_str not in seen:
            seen.add(p_str)
            unique_paths.append(p)

    for path in unique_paths:
        data = load_dotenv_file(path)
        key = data.get("BINANCE_API_KEY", "").strip()
        secret = data.get("BINANCE_API_SECRET", "").strip()
        if key and secret:
            return key, secret, f"archivo_env:{path}"

    return "", "", "no_encontrado"


# =========================
# Klines y resúmenes
# =========================

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


def timeframe_summary(candles: List[Dict[str, Any]], recent_window: int = 20) -> Dict[str, Any]:
    closes = [c["close"] for c in candles]
    recent = candles[-recent_window:] if len(candles) >= recent_window else candles

    last_close = closes[-1] if closes else None
    ma7 = moving_average(closes, 7)
    ma25 = moving_average(closes, 25)
    ma99 = moving_average(closes, 99)

    return {
        "candles_count": len(candles),
        "last_open_time_utc": candles[-1]["open_time_utc"] if candles else None,
        "last_close": last_close,
        "last_high": candles[-1]["high"] if candles else None,
        "last_low": candles[-1]["low"] if candles else None,
        "last_volume": candles[-1]["volume"] if candles else None,
        "ma7": ma7,
        "ma25": ma25,
        "ma99": ma99,
        "recent_high": max(c["high"] for c in recent) if recent else None,
        "recent_low": min(c["low"] for c in recent) if recent else None,
        "dist_pct_vs_ma7": pct_change(last_close, ma7),
        "dist_pct_vs_ma25": pct_change(last_close, ma25),
        "dist_pct_vs_ma99": pct_change(last_close, ma99),
    }


# =========================
# Exchange info y profundidad
# =========================

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

    bid_notional = sum_notional(bids)
    ask_notional = sum_notional(asks)

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_abs": spread_abs,
        "spread_pct": spread_pct,
        "bid_notional_top10": bid_notional,
        "ask_notional_top10": ask_notional,
        "min_side_notional_top10": min(bid_notional, ask_notional) if bids and asks else None,
        "bids": bids,
        "asks": asks,
    }


# =========================
# Datos públicos por símbolo
# =========================

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


# =========================
# Datos privados
# =========================

def fetch_private_data(
    symbol: str,
    base_asset: str,
    quote_asset: str,
    api_key: str,
    api_secret: str,
    trades_limit: int,
) -> Dict[str, Any]:
    account = signed_get_json(
        "/api/v3/account",
        api_key,
        api_secret,
        params={"omitZeroBalances": "true"},
    )

    balances_map: Dict[str, Dict[str, str]] = {}
    for b in account.get("balances", []):
        if b["asset"] in {base_asset, quote_asset}:
            free_val = float(b["free"])
            locked_val = float(b["locked"])
            balances_map[b["asset"]] = {
                "free": b["free"],
                "locked": b["locked"],
                "total": normalize_number_str(free_val + locked_val, 8),
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
            "buy_qty": normalize_number_str(buy_qty, 8),
            "sell_qty": normalize_number_str(sell_qty, 8),
            "buy_quote": normalize_number_str(buy_quote, 8),
            "sell_quote": normalize_number_str(sell_quote, 8),
            "net_qty": normalize_number_str(buy_qty - sell_qty, 8),
            "net_quote_flow": normalize_number_str(sell_quote - buy_quote, 8),
        },
    }


def estimate_position_from_recent_trades(current_qty: float, recent_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                        "qty_used": normalize_number_str(alloc, 8),
                        "price": normalize_number_str(price, 8),
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
            "Usa --precio / --inversion si quieres un snapshot más exacto."
        )

    return {
        "current_qty": normalize_number_str(current_qty, 8),
        "estimated_avg_entry": normalize_number_str(avg_entry, 8),
        "covered_qty": normalize_number_str(covered_qty, 8),
        "missing_qty": normalize_number_str(missing, 8),
        "warning": warning,
        "method": "recent-trades-backward-estimate",
        "lots_used": list(reversed(lots)),
    }


def summarize_open_oco(open_order_lists: List[Dict[str, Any]], open_orders: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    out = []
    open_orders = open_orders or []

    by_list_id: Dict[Any, List[Dict[str, Any]]] = {}
    for o in open_orders:
        by_list_id.setdefault(o.get("orderListId"), []).append(o)

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

        if reports:
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
        else:
            list_id = ol.get("orderListId")
            for o in by_list_id.get(list_id, []):
                summary["legs"].append(
                    {
                        "orderId": o.get("orderId"),
                        "type": o.get("type"),
                        "side": o.get("side"),
                        "price": o.get("price"),
                        "stopPrice": o.get("stopPrice"),
                        "origQty": o.get("origQty"),
                        "executedQty": o.get("executedQty"),
                        "status": o.get("status"),
                    }
                )

        out.append(summary)
    return out


# =========================
# Snapshot de posición
# =========================

def build_position_snapshot(
    symbol: str,
    base_asset: str,
    quote_asset: str,
    ticker: Dict[str, Any],
    symbol_info: Dict[str, Any],
    private_data: Optional[Dict[str, Any]],
    manual_entry_price: Optional[float],
    manual_quote_size: Optional[float],
) -> Dict[str, Any]:
    rules = symbol_info.get("rules_short", {})
    tick_size = rules.get("tickSize")
    step_size = rules.get("stepSize")

    last_price = float(ticker["lastPrice"])
    position: Dict[str, Any] = {
        "symbol": symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "last_price": format_price(last_price, tick_size),
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
                    "base_qty_total": format_qty(base_qty, step_size),
                    "entry_price": format_price(manual_entry_price, tick_size),
                    "position_notional_quote": format_quote(base_qty * last_price),
                    "unrealized_pnl_quote": format_quote(base_qty * (last_price - manual_entry_price)),
                    "unrealized_pnl_pct": format_pct(((last_price / manual_entry_price) - 1.0) * 100.0),
                    "source": "manual",
                }
            )
            position["notes"].append("Posición calculada desde --precio y --inversion.")
        else:
            position["notes"].append("Sin datos privados ni parámetros manuales; no se pudo construir la posición.")
        return position

    balances = private_data.get("balances", {})
    base_balance = balances.get(base_asset, {"free": "0", "locked": "0", "total": "0"})
    quote_balance = balances.get(quote_asset, {"free": "0", "locked": "0", "total": "0"})

    base_qty_total = float(base_balance.get("total", "0") or 0.0)
    position["base_qty_total"] = format_qty(base_qty_total, step_size)
    position["quote_free"] = normalize_number_str(quote_balance.get("free"), 8)
    position["quote_locked"] = normalize_number_str(quote_balance.get("locked"), 8)
    position["quote_total"] = normalize_number_str(quote_balance.get("total"), 8)

    trade_summary = summarize_trades(private_data.get("recent_trades", []))
    estimate = estimate_position_from_recent_trades(base_qty_total, private_data.get("recent_trades", []))
    position["trade_summary"] = trade_summary
    position["estimate"] = estimate

    chosen_entry: Optional[float] = None
    source = None

    if manual_entry_price is not None:
        chosen_entry = manual_entry_price
        source = "manual"
        position["notes"].append("Se priorizó --precio sobre la estimación automática.")
    elif estimate.get("estimated_avg_entry") is not None:
        chosen_entry = float(estimate["estimated_avg_entry"])
        source = "estimado_desde_trades"
        if estimate.get("warning"):
            position["notes"].append(estimate["warning"])
    elif trade_summary.get("last_buy"):
        chosen_entry = float(trade_summary["last_buy"]["price"])
        source = "ultimo_buy_fallback"
        position["notes"].append("No se pudo estimar promedio; se usó el último BUY como fallback.")

    if chosen_entry is not None and base_qty_total > EPS:
        pnl_quote = base_qty_total * (last_price - chosen_entry)
        pnl_pct = ((last_price / chosen_entry) - 1.0) * 100.0 if chosen_entry > EPS else None
        position["entry_price"] = format_price(chosen_entry, tick_size)
        position["position_notional_quote"] = format_quote(base_qty_total * last_price)
        position["unrealized_pnl_quote"] = format_quote(pnl_quote)
        position["unrealized_pnl_pct"] = format_pct(pnl_pct)
        position["source"] = source

    if manual_quote_size is not None:
        position["manual_quote_size"] = format_quote(manual_quote_size)

    return position


def build_position_operational_summary(
    symbol_info: Dict[str, Any],
    position_snapshot: Dict[str, Any],
    open_oco_summary: Optional[List[Dict[str, Any]]],
    private_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    rules = symbol_info.get("rules_short", {})
    tick_size = rules.get("tickSize")
    step_size = rules.get("stepSize")

    total_qty = safe_float(position_snapshot.get("base_qty_total")) or 0.0
    entry_price = safe_float(position_snapshot.get("entry_price"))
    estimate_avg = safe_float((position_snapshot.get("estimate") or {}).get("estimated_avg_entry"))

    oco_lists = open_oco_summary or []
    open_orders = (private_data or {}).get("open_orders", [])

    oco_details: List[Dict[str, Any]] = []
    total_covered_qty = 0.0

    for oco in oco_lists:
        legs = oco.get("legs", []) or []
        tp_leg = next((l for l in legs if str(l.get("type")) == "LIMIT_MAKER"), None)
        stop_leg = next((l for l in legs if "STOP" in str(l.get("type", ""))), None)

        covered_qty = 0.0
        sell_legs = [l for l in legs if str(l.get("side")) == "SELL"]
        if sell_legs:
            covered_qty = max(safe_float(l.get("origQty")) or 0.0 for l in sell_legs)

        total_covered_qty += covered_qty

        tp_price = safe_float(tp_leg.get("price")) if tp_leg else None
        sl_trigger = safe_float(stop_leg.get("stopPrice")) if stop_leg else None
        sl_limit = safe_float(stop_leg.get("price")) if stop_leg else None

        tp_dist_pct = pct_change(tp_price, entry_price) if tp_price and entry_price else None
        sl_trigger_dist_pct = pct_change(sl_trigger, entry_price) if sl_trigger and entry_price else None
        sl_limit_dist_pct = pct_change(sl_limit, entry_price) if sl_limit and entry_price else None

        rr_bruto = None
        if tp_price and sl_trigger and entry_price and sl_trigger < entry_price < tp_price:
            reward = tp_price - entry_price
            risk = entry_price - sl_trigger
            if risk > EPS:
                rr_bruto = reward / risk

        oco_details.append(
            {
                "orderListId": oco.get("orderListId"),
                "listStatusType": oco.get("listStatusType"),
                "listOrderStatus": oco.get("listOrderStatus"),
                "qty_cubierta": format_qty(covered_qty, step_size),
                "tp_price": format_price(tp_price, tick_size),
                "sl_trigger": format_price(sl_trigger, tick_size),
                "sl_limit": format_price(sl_limit, tick_size),
                "tp_dist_pct": format_pct(tp_dist_pct),
                "sl_trigger_dist_pct": format_pct(sl_trigger_dist_pct),
                "sl_limit_dist_pct": format_pct(sl_limit_dist_pct),
                "rr_bruto": format_pct(rr_bruto, 4) if rr_bruto is not None else None,
            }
        )

    total_covered_qty_effective = min(total_qty, total_covered_qty)
    free_outside_oco = max(0.0, total_qty - total_covered_qty_effective)
    pct_covered = (total_covered_qty_effective / total_qty * 100.0) if total_qty > EPS else None

    active_oco = None
    if oco_details:
        active_oco = max(
            oco_details,
            key=lambda x: safe_float(x.get("qty_cubierta")) or 0.0
        )

    extra_open_orders = []
    for o in open_orders:
        if o.get("orderListId") in [d.get("orderListId") for d in oco_details]:
            continue
        extra_open_orders.append(o)

    alerts: List[str] = []

    if total_qty > EPS and not oco_details:
        alerts.append("Hay posición abierta pero no se detectó una OCO activa.")

    if total_qty > EPS and pct_covered is not None and pct_covered < 90.0:
        alerts.append(f"La OCO cubre menos del 90% de la posición ({format_pct(pct_covered)}%).")

    if len(oco_details) > 1:
        alerts.append("Hay múltiples OCO activas para el mismo par; revisar si es intencional.")

    if free_outside_oco > EPS:
        alerts.append(
            f"Queda cantidad fuera de la OCO: {format_qty(free_outside_oco, step_size)} {symbol_info.get('baseAsset', '')}".strip()
        )

    if extra_open_orders:
        alerts.append("Existen órdenes abiertas adicionales fuera de la OCO para este par.")

    manual_entry = safe_float(position_snapshot.get("entry_price")) if position_snapshot.get("source") == "manual" else None
    if manual_entry is not None and estimate_avg is not None:
        diff_pct = abs(((manual_entry / estimate_avg) - 1.0) * 100.0) if estimate_avg > EPS else None
        if diff_pct is not None and diff_pct > 0.5:
            alerts.append(
                f"El precio manual difiere del estimado por trades en {format_pct(diff_pct)}%."
            )

    return {
        "qty_total": format_qty(total_qty, step_size),
        "qty_cubierta_por_oco": format_qty(total_covered_qty_effective, step_size),
        "qty_libre_fuera_oco": format_qty(free_outside_oco, step_size),
        "pct_cubierto_por_oco": format_pct(pct_covered),
        "oco_count": len(oco_details),
        "oco_details": oco_details,
        "active_oco": active_oco,
        "alerts": alerts,
    }


# =========================
# Lógica de compra límite (igual a 3.1)
# =========================

def suggest_limit_buy(
    public_data: Dict[str, Any],
    min_distance_pct: float = 0.8,
    ideal_distance_pct: float = 3.5,
    max_distance_pct: float = 6.0,
) -> Dict[str, Any]:
    ticker = public_data["ticker"]
    t15 = public_data["timeframes"]["15m"]
    t1 = public_data["timeframes"]["1h"]
    t4 = public_data["timeframes"]["4h"]
    rules = public_data.get("symbol_info", {}).get("rules_short", {})
    tick_size = rules.get("tickSize")

    last_price = safe_float(ticker.get("lastPrice"))
    if last_price is None:
        return {
            "suggested_limit_buy": None,
            "reference": None,
            "second_support": None,
            "distance_pct_from_last": None,
            "note": "No se pudo leer el precio actual.",
            "candidates_debug": [],
        }

    raw_candidates = [
        ("1h_ma25", safe_float(t1.get("ma25")), 8),
        ("1h_recent_low", safe_float(t1.get("recent_low")), 7),
        ("4h_ma25", safe_float(t4.get("ma25")), 6),
        ("1h_ma99", safe_float(t1.get("ma99")), 5),
        ("4h_ma99", safe_float(t4.get("ma99")), 4),
        ("15m_recent_low", safe_float(t15.get("recent_low")), 3),
        ("4h_recent_low", safe_float(t4.get("recent_low")), 2),
    ]

    candidates: List[Dict[str, Any]] = []

    for name, value, base_score in raw_candidates:
        if value is None or value >= last_price:
            continue

        dist_pct = ((last_price / value) - 1.0) * 100.0
        score = base_score

        if dist_pct < min_distance_pct:
            score -= 4
        elif dist_pct <= ideal_distance_pct:
            score += 3
        elif dist_pct <= max_distance_pct:
            score += 1
        else:
            score -= 2

        if name.startswith("15m") and dist_pct < 1.2:
            score -= 1

        if name.startswith("4h_ma99") and dist_pct < 0.7:
            score -= 1

        candidates.append(
            {
                "name": name,
                "value": value,
                "distance_pct": dist_pct,
                "score": score,
            }
        )

    if not candidates:
        return {
            "suggested_limit_buy": None,
            "reference": None,
            "second_support": None,
            "distance_pct_from_last": None,
            "note": "No se encontraron soportes válidos por debajo del precio actual.",
            "candidates_debug": [],
        }

    candidates_sorted = sorted(
        candidates,
        key=lambda x: (x["score"], -abs(x["distance_pct"] - 1.8), x["value"]),
        reverse=True,
    )

    chosen = candidates_sorted[0]
    if chosen["distance_pct"] < min_distance_pct:
        alt = next(
            (c for c in candidates_sorted[1:] if min_distance_pct <= c["distance_pct"] <= max_distance_pct),
            None
        )
        if alt:
            chosen = alt

    second = next((c for c in candidates_sorted if c["name"] != chosen["name"]), None)

    note_parts = ["Sugerencia mecánica basada en soportes por debajo del precio actual."]
    if chosen["distance_pct"] < min_distance_pct:
        note_parts.append("La entrada está bastante pegada al precio actual.")
    elif chosen["distance_pct"] > max_distance_pct:
        note_parts.append("La entrada queda bastante lejos; el rebote podría darse antes.")
    else:
        note_parts.append("La distancia al precio actual luce razonable para buscar retroceso.")

    return {
        "suggested_limit_buy": floor_to_step(chosen["value"], tick_size),
        "reference": chosen["name"],
        "second_support": {
            "name": second["name"],
            "value": normalize_number_str(second["value"], 8),
            "distance_pct": normalize_number_str(second["distance_pct"], 4),
        } if second else None,
        "distance_pct_from_last": normalize_number_str(chosen["distance_pct"], 4),
        "note": " ".join(note_parts),
        "candidates_debug": [
            {
                "name": c["name"],
                "value": normalize_number_str(c["value"], 8),
                "distance_pct": normalize_number_str(c["distance_pct"], 4),
                "score": c["score"],
            }
            for c in candidates_sorted
        ],
    }


# =========================
# Ranking de watchlist (igual a 3.1)
# =========================

def score_rebound_candidate(symbol: str, public_data: Dict[str, Any], capital_quote: float = 35.0) -> Dict[str, Any]:
    ticker = public_data["ticker"]
    depth = public_data["depth_summary"]
    t15 = public_data["timeframes"]["15m"]
    t1 = public_data["timeframes"]["1h"]
    t4 = public_data["timeframes"]["4h"]

    last_price = safe_float(ticker.get("lastPrice"))
    score = 0
    reasons: List[str] = []

    c4 = safe_float(t4.get("last_close"))
    ma25_4 = safe_float(t4.get("ma25"))
    ma99_4 = safe_float(t4.get("ma99"))

    c1 = safe_float(t1.get("last_close"))
    ma7_1 = safe_float(t1.get("ma7"))
    ma25_1 = safe_float(t1.get("ma25"))
    ma99_1 = safe_float(t1.get("ma99"))

    c15 = safe_float(t15.get("last_close"))
    ma7_15 = safe_float(t15.get("ma7"))
    ma25_15 = safe_float(t15.get("ma25"))

    recent_high_1 = safe_float(t1.get("recent_high"))
    spread_pct = safe_float(depth.get("spread_pct"))
    min_side_notional = safe_float(depth.get("min_side_notional_top10"))

    if c4 is not None and ma25_4 is not None:
        if c4 > ma25_4:
            score += 2
            reasons.append("4h por encima de MA25")
        else:
            score -= 2
            reasons.append("4h por debajo de MA25")

    dist_4h_vs_ma99 = pct_change(c4, ma99_4)
    if c4 is not None and ma99_4 is not None:
        if c4 > ma99_4:
            score += 3
            reasons.append("4h por encima de MA99")
        else:
            if dist_4h_vs_ma99 is not None:
                if dist_4h_vs_ma99 >= -1.5:
                    score -= 2
                    reasons.append("4h ligeramente por debajo de MA99")
                elif dist_4h_vs_ma99 >= -4.0:
                    score -= 4
                    reasons.append("4h claramente por debajo de MA99")
                else:
                    score -= 6
                    reasons.append("4h muy débil frente a MA99")
            else:
                score -= 3
                reasons.append("4h por debajo de MA99")

    if ma25_4 is not None and ma99_4 is not None:
        if ma25_4 > ma99_4:
            score += 2
            reasons.append("sesgo alcista en 4h (MA25 > MA99)")
        else:
            score -= 2
            reasons.append("sesgo flojo en 4h (MA25 <= MA99)")

    if c1 is not None and ma99_1 is not None:
        if c1 > ma99_1:
            score += 2
            reasons.append("1h aún por encima de MA99")
        else:
            score -= 2
            reasons.append("1h perdió MA99")

    if c1 is not None and ma7_1 is not None and c1 < ma7_1:
        score += 1
        reasons.append("hay retroceso corto en 1h")

    if c1 is not None and ma25_1 is not None:
        dist_1h_ma25 = pct_change(c1, ma25_1)
        if dist_1h_ma25 is not None and -2.5 <= dist_1h_ma25 <= 1.0:
            score += 2
            reasons.append("retroceso razonable cerca de MA25 de 1h")
        elif dist_1h_ma25 is not None and dist_1h_ma25 < -5.0:
            score -= 2
            reasons.append("retroceso demasiado profundo vs MA25 de 1h")

    if last_price is not None and recent_high_1 is not None and recent_high_1 > EPS:
        pullback_pct = ((recent_high_1 - last_price) / recent_high_1) * 100.0
        if 0.8 <= pullback_pct <= 4.5:
            score += 3
            reasons.append("pullback sano desde máximo reciente")
        elif 4.5 < pullback_pct <= 7.0:
            score += 1
            reasons.append("pullback amplio, aún recuperable")
        elif pullback_pct > 7.0:
            score -= 2
            reasons.append("pullback ya muy profundo")
        else:
            score -= 1
            reasons.append("precio todavía muy pegado al máximo reciente")

    if c15 is not None and ma7_15 is not None and c15 < ma7_15:
        score += 1
        reasons.append("15m descargando")
    if c15 is not None and ma25_15 is not None and c15 < ma25_15:
        score += 1
        reasons.append("15m ya cedió algo hacia MA25")

    if spread_pct is not None:
        if spread_pct <= 0.01:
            score += 2
            reasons.append("spread muy corto")
        elif spread_pct <= 0.05:
            score += 1
            reasons.append("spread controlado")
        elif spread_pct <= 0.10:
            reasons.append("spread aceptable")
        elif spread_pct <= 0.25:
            score -= 1
            reasons.append("spread algo amplio")
        else:
            score -= 3
            reasons.append("spread claramente amplio")

    if min_side_notional is not None and capital_quote > 0:
        depth_ratio = min_side_notional / capital_quote
        if depth_ratio < 50:
            score -= 3
            reasons.append("profundidad corta insuficiente para el capital de referencia")
        elif depth_ratio < 150:
            score -= 1
            reasons.append("profundidad corta algo justa")
        elif depth_ratio > 400:
            reasons.append("profundidad corta holgada para el capital de referencia")

    suggestion = suggest_limit_buy(public_data)

    suggested_limit = suggestion.get("suggested_limit_buy")
    suggested_dist = safe_float(suggestion.get("distance_pct_from_last"))
    if suggested_limit is None:
        score -= 2
        reasons.append("sin compra límite razonable por debajo del precio actual")
    else:
        if suggested_dist is not None:
            if 0.8 <= suggested_dist <= 4.0:
                score += 2
                reasons.append("compra límite propuesta con distancia razonable")
            elif suggested_dist < 0.5:
                score -= 2
                reasons.append("compra límite demasiado pegada al precio actual")
            elif suggested_dist > 6.0:
                score -= 1
                reasons.append("compra límite bastante alejada")

    return {
        "symbol": symbol,
        "last_price": normalize_number_str(last_price, 8),
        "score": score,
        "reasons": reasons,
        "suggested_limit_buy": suggested_limit,
        "limit_reference": suggestion.get("reference"),
        "distance_pct_from_last": suggestion.get("distance_pct_from_last"),
        "second_support": suggestion.get("second_support"),
        "dist_4h_vs_ma99": normalize_number_str(dist_4h_vs_ma99, 4),
        "spread_pct": normalize_number_str(spread_pct, 4),
        "min_side_notional_top10": normalize_number_str(min_side_notional, 4),
        "note": suggestion.get("note"),
    }


# =========================
# Texto de salida
# =========================

def build_position_analysis_text(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"PAR: {summary['symbol']}")
    lines.append(f"VERSIÓN: {summary.get('version')}")
    lines.append(f"GENERADO UTC: {summary['generated_at_utc']}")
    lines.append(f"PRECIO ACTUAL: {summary['ticker']['lastPrice']}")
    lines.append(f"CAMBIO 24H (%): {summary['ticker']['priceChangePercent']}")
    lines.append(f"MAX 24H: {summary['ticker']['highPrice']}")
    lines.append(f"MIN 24H: {summary['ticker']['lowPrice']}")
    lines.append(f"VOL 24H ({summary['base_asset']}): {summary['ticker']['volume']}")
    lines.append("")

    cred_source = summary.get("credenciales_origen")
    if cred_source:
        lines.append(f"CREDENCIALES: {cred_source}")
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
        lines.append(f"  best_bid: {normalize_number_str(depth.get('best_bid'), 8)}")
        lines.append(f"  best_ask: {normalize_number_str(depth.get('best_ask'), 8)}")
        lines.append(f"  spread_abs: {normalize_number_str(depth.get('spread_abs'), 8)}")
        lines.append(f"  spread_pct: {normalize_number_str(depth.get('spread_pct'), 4)}")
        lines.append(f"  bid_notional_top10: {normalize_number_str(depth.get('bid_notional_top10'), 4)}")
        lines.append(f"  ask_notional_top10: {normalize_number_str(depth.get('ask_notional_top10'), 4)}")
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
        lines.append(f"  fuente_entrada: {position.get('source')}")
        for note in position.get("notes", []):
            lines.append(f"  note: {note}")
        estimate = position.get("estimate")
        if estimate:
            lines.append(f"  estimate_current_qty: {estimate.get('current_qty')}")
            lines.append(f"  estimate_avg_entry: {estimate.get('estimated_avg_entry')}")
            lines.append(f"  estimate_warning: {estimate.get('warning')}")
        lines.append("")

    op = summary.get("position_operational_summary", {})
    if op:
        lines.append("RESUMEN OPERATIVO:")
        lines.append(f"  qty_total: {op.get('qty_total')}")
        lines.append(f"  qty_cubierta_por_oco: {op.get('qty_cubierta_por_oco')}")
        lines.append(f"  qty_libre_fuera_oco: {op.get('qty_libre_fuera_oco')}")
        lines.append(f"  pct_cubierto_por_oco: {op.get('pct_cubierto_por_oco')}")
        lines.append(f"  oco_count: {op.get('oco_count')}")
        active = op.get("active_oco")
        if active:
            lines.append("  OCO activa principal:")
            lines.append(f"    orderListId: {active.get('orderListId')}")
            lines.append(f"    qty_cubierta: {active.get('qty_cubierta')}")
            lines.append(f"    tp_price: {active.get('tp_price')}")
            lines.append(f"    sl_trigger: {active.get('sl_trigger')}")
            lines.append(f"    sl_limit: {active.get('sl_limit')}")
            lines.append(f"    tp_dist_pct: {active.get('tp_dist_pct')}")
            lines.append(f"    sl_trigger_dist_pct: {active.get('sl_trigger_dist_pct')}")
            lines.append(f"    sl_limit_dist_pct: {active.get('sl_limit_dist_pct')}")
            lines.append(f"    rr_bruto: {active.get('rr_bruto')}")
        alerts = op.get("alerts", [])
        if alerts:
            lines.append("  ALERTAS:")
            for alert in alerts:
                lines.append(f"    - {alert}")
        lines.append("")

    for tf in ["15m", "1h", "4h"]:
        tf_data = summary["timeframes"][tf]
        lines.append(f"{tf}:")
        lines.append(f"  Last close: {normalize_number_str(tf_data['last_close'], 8)}")
        lines.append(f"  MA7: {normalize_number_str(tf_data['ma7'], 8)}")
        lines.append(f"  MA25: {normalize_number_str(tf_data['ma25'], 8)}")
        lines.append(f"  MA99: {normalize_number_str(tf_data['ma99'], 8)}")
        lines.append(f"  Recent high: {normalize_number_str(tf_data['recent_high'], 8)}")
        lines.append(f"  Recent low: {normalize_number_str(tf_data['recent_low'], 8)}")
        lines.append(f"  Last volume: {normalize_number_str(tf_data['last_volume'], 4)}")
        lines.append(f"  Dist vs MA7 (%): {normalize_number_str(tf_data['dist_pct_vs_ma7'], 4)}")
        lines.append(f"  Dist vs MA25 (%): {normalize_number_str(tf_data['dist_pct_vs_ma25'], 4)}")
        lines.append(f"  Dist vs MA99 (%): {normalize_number_str(tf_data['dist_pct_vs_ma99'], 4)}")
        lines.append("")

    suggestion = summary.get("suggested_limit_buy_info", {})
    if suggestion:
        lines.append("SOPORTES / COMPRA MECÁNICA:")
        lines.append(f"  suggested_limit_buy: {suggestion.get('suggested_limit_buy')}")
        lines.append(f"  reference: {suggestion.get('reference')}")
        lines.append(f"  second_support: {suggestion.get('second_support')}")
        lines.append(f"  distance_pct_from_last: {suggestion.get('distance_pct_from_last')}")
        lines.append(f"  note: {suggestion.get('note')}")
        lines.append("")

    private_data = summary.get("private_data")
    if private_data:
        lines.append("DATOS PRIVADOS:")
        balances = private_data.get("balances", {})
        if balances:
            for asset, bal in balances.items():
                lines.append(
                    f"  Balance {asset}: free={bal.get('free')} locked={bal.get('locked')} total={bal.get('total')}"
                )

        trade_summary = position.get("trade_summary", {}) if position else {}
        if trade_summary.get("last_buy"):
            lb = trade_summary["last_buy"]
            lines.append(
                f"  last_buy: {lb['time_utc']} price={lb['price']} qty={lb['qty']} quoteQty={lb['quoteQty']}"
            )
        if trade_summary.get("last_sell"):
            ls = trade_summary["last_sell"]
            lines.append(
                f"  last_sell: {ls['time_utc']} price={ls['price']} qty={ls['qty']} quoteQty={ls['quoteQty']}"
            )

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
                        f"price={leg['price']} | stopPrice={leg['stopPrice']} | status={leg['status']} | origQty={leg['origQty']}"
                    )
        lines.append("")

    return "\n".join(lines)


def build_watchlist_text(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("WATCHLIST / MODO MERCADO")
    lines.append(f"VERSIÓN: {payload.get('version')}")
    lines.append(f"GENERADO UTC: {payload['generated_at_utc']}")
    lines.append(f"PARES: {', '.join(payload['symbols'])}")
    lines.append(f"CAPITAL_REFERENCIA_USDT: {payload.get('capital_quote_reference')}")
    lines.append("")

    lines.append("RANKING (más alto = mejor candidato mecánico de rebote):")
    for idx, item in enumerate(payload["ranking"], start=1):
        lines.append(
            f"{idx}. {item['symbol']} | score={item['score']} | precio={item['last_price']} | "
            f"compra_limite={item['suggested_limit_buy']} | ref={item['limit_reference']}"
        )
        lines.append(
            f"   - distancia_vs_precio_actual: {item['distance_pct_from_last']}% | "
            f"dist_4h_vs_ma99: {item['dist_4h_vs_ma99']}% | spread: {item['spread_pct']}%"
        )
        if item.get("second_support"):
            lines.append(f"   - segundo_soporte: {item['second_support']}")
        for reason in item["reasons"]:
            lines.append(f"   - {reason}")
        lines.append("")

    lines.append("NOTA:")
    lines.append("  El ranking es una heurística para priorizar revisión humana. No sustituye criterio ni gestión de riesgo.")
    return "\n".join(lines)


# =========================
# Modo posición
# =========================

def run_position_mode(args: argparse.Namespace) -> int:
    symbol = args.symbol.upper().strip()
    quote_asset = args.quote_asset.upper().strip()
    assets = extract_assets(symbol, quote_asset)
    base_asset = assets["base_asset"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.outdir) / f"posicion_{symbol}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        public_data = fetch_public_market_data(symbol, args.limit)
    except Exception as e:
        print(f"Error obteniendo datos públicos: {e}", file=sys.stderr)
        return 1

    summary: Dict[str, Any] = {
        "mode": "posicion",
        "version": "3.2",
        "generated_at_local": datetime.now().isoformat(),
        "generated_at_utc": now_utc_iso(),
        "symbol": symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "ticker": public_data["ticker"],
        "depth_summary": public_data["depth_summary"],
        "symbol_info": public_data["symbol_info"],
        "timeframes": public_data["timeframes"],
        "suggested_limit_buy_info": suggest_limit_buy(public_data),
    }

    private_data: Optional[Dict[str, Any]] = None
    cred_source = None

    if args.include_private:
        api_key, api_secret, cred_source = resolve_binance_credentials(args.env_file)
        if not api_key or not api_secret:
            print(
                "Pediste --privados pero no encontré BINANCE_API_KEY y BINANCE_API_SECRET.\n"
                "Opciones:\n"
                "1. Crear un archivo .env junto al script con:\n"
                "   BINANCE_API_KEY=tu_api_key\n"
                "   BINANCE_API_SECRET=tu_api_secret\n"
                "2. O indicar otro archivo con --archivo-env ruta/al/archivo.env\n"
                "3. O usar variables de entorno del sistema.",
                file=sys.stderr,
            )
            return 1

        summary["credenciales_origen"] = cred_source

        try:
            private_data = fetch_private_data(
                symbol=symbol,
                base_asset=base_asset,
                quote_asset=quote_asset,
                api_key=api_key,
                api_secret=api_secret,
                trades_limit=args.trades_limit,
            )
            summary["private_data"] = private_data
            summary["open_oco_summary"] = summarize_open_oco(
                private_data.get("open_order_lists", []),
                private_data.get("open_orders", []),
            )
        except Exception as e:
            print(f"Error obteniendo datos privados: {e}", file=sys.stderr)
            return 1

    summary["position_snapshot"] = build_position_snapshot(
        symbol=symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        ticker=public_data["ticker"],
        symbol_info=public_data["symbol_info"],
        private_data=private_data,
        manual_entry_price=args.manual_entry_price,
        manual_quote_size=args.manual_quote_size,
    )

    summary["position_operational_summary"] = build_position_operational_summary(
        symbol_info=public_data["symbol_info"],
        position_snapshot=summary["position_snapshot"],
        open_oco_summary=summary.get("open_oco_summary", []),
        private_data=private_data,
    )

    write_json(output_dir / "summary.json", summary)
    for tf, rows in public_data["csv_rows"].items():
        save_csv(output_dir / f"klines_{tf}.csv", rows)

    txt = build_position_analysis_text(summary)
    write_text(output_dir / "analysis_summary.txt", txt)

    print(f"OK. Snapshot de posición generado en: {output_dir.resolve()}")
    print("- summary.json")
    print("- analysis_summary.txt")
    print("- klines_15m.csv")
    print("- klines_1h.csv")
    print("- klines_4h.csv")
    if args.include_private:
        print("- private_data incluido: balances, trades, openOrders y openOrderList")
        print(f"- credenciales cargadas desde: {cred_source}")
    return 0


# =========================
# Modo mercado
# =========================

def parse_symbols_input(raw_values: List[str]) -> List[str]:
    symbols: List[str] = []
    for item in raw_values:
        parts = [p.strip().upper() for p in item.replace(";", ",").split(",")]
        for p in parts:
            if p:
                symbols.append(p)
    return symbols


def run_market_mode(args: argparse.Namespace) -> int:
    symbols = parse_symbols_input(args.symbols)
    if not symbols:
        print("No se recibieron pares válidos para modo mercado.", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.outdir) / f"mercado_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    ranking: List[Dict[str, Any]] = []
    symbol_summaries: Dict[str, Any] = {}

    for symbol in symbols:
        quote_asset = args.quote_asset.upper().strip()
        assets = extract_assets(symbol, quote_asset)
        base_asset = assets["base_asset"]

        try:
            public_data = fetch_public_market_data(symbol, args.limit)
        except Exception as e:
            print(f"Error obteniendo datos públicos para {symbol}: {e}", file=sys.stderr)
            continue

        suggestion = suggest_limit_buy(public_data)

        single_summary = {
            "mode": "mercado",
            "version": "3.2",
            "generated_at_local": datetime.now().isoformat(),
            "generated_at_utc": now_utc_iso(),
            "symbol": symbol,
            "base_asset": base_asset,
            "quote_asset": quote_asset,
            "ticker": public_data["ticker"],
            "depth_summary": public_data["depth_summary"],
            "symbol_info": public_data["symbol_info"],
            "timeframes": public_data["timeframes"],
            "suggested_limit_buy_info": suggestion,
        }
        symbol_summaries[symbol] = single_summary

        write_json(output_dir / f"{symbol}_summary.json", single_summary)
        for tf, rows in public_data["csv_rows"].items():
            save_csv(output_dir / f"{symbol}_klines_{tf}.csv", rows)

        ranking.append(score_rebound_candidate(symbol, public_data, capital_quote=args.capital))

    ranking_sorted = sorted(ranking, key=lambda x: x["score"], reverse=True)

    payload = {
        "mode": "mercado",
        "version": "3.2",
        "generated_at_local": datetime.now().isoformat(),
        "generated_at_utc": now_utc_iso(),
        "capital_quote_reference": args.capital,
        "symbols": symbols,
        "ranking": ranking_sorted,
        "per_symbol_summary": symbol_summaries,
    }

    write_json(output_dir / "watchlist_summary.json", payload)
    write_text(output_dir / "watchlist_summary.txt", build_watchlist_text(payload))

    print(f"OK. Watchlist generada en: {output_dir.resolve()}")
    print("- watchlist_summary.json")
    print("- watchlist_summary.txt")
    print("- archivos por símbolo: *_summary.json y *_klines_15m/1h/4h.csv")
    return 0


# =========================
# CLI
# =========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Binance Trading v3.2: modo posición (OCO) y modo mercado (watchlist)."
    )

    subparsers = parser.add_subparsers(dest="mode", required=True)

    # ---- MODO POSICION ----
    p_pos = subparsers.add_parser(
        "posicion",
        help="Analiza una moneda ya comprada para contexto de OCO / gestión."
    )
    p_pos.add_argument("--par", "--symbol", dest="symbol", required=True, help="Ejemplo: XRPUSDT")
    p_pos.add_argument("--velas", "--limit", dest="limit", type=int, default=120, help="Velas por timeframe. Recomendado: 120 a 300")
    p_pos.add_argument("--salida", "--outdir", dest="outdir", default="snapshots", help="Carpeta de salida")
    p_pos.add_argument("--privados", "--include-private", dest="include_private", action="store_true", help="Incluye balances, trades y órdenes abiertas/OCO")
    p_pos.add_argument("--cotizacion", "--quote-asset", dest="quote_asset", default="USDT", help="Quote asset; por defecto USDT")
    p_pos.add_argument("--trades-limit", type=int, default=500, help="Cantidad de trades recientes a descargar. Default: 500")
    p_pos.add_argument("--precio", "--manual-entry-price", dest="manual_entry_price", type=float, default=None, help="Precio de compra manual")
    p_pos.add_argument("--inversion", "--manual-quote-size", dest="manual_quote_size", type=float, default=None, help="Monto invertido manual en quote asset")
    p_pos.add_argument("--archivo-env", dest="env_file", default=None, help="Ruta a archivo .env con BINANCE_API_KEY y BINANCE_API_SECRET")
    p_pos.set_defaults(func=run_position_mode)

    # ---- MODO MERCADO ----
    p_mkt = subparsers.add_parser(
        "mercado",
        help="Analiza varios pares para priorizar una posible compra límite."
    )
    p_mkt.add_argument("--pares", "--symbols", dest="symbols", nargs="+", required=True, help="Ejemplo: ETHUSDT SOLUSDT ADAUSDT XRPUSDT POLUSDT")
    p_mkt.add_argument("--velas", "--limit", dest="limit", type=int, default=120, help="Velas por timeframe. Recomendado: 120 a 300")
    p_mkt.add_argument("--salida", "--outdir", dest="outdir", default="snapshots", help="Carpeta de salida")
    p_mkt.add_argument("--cotizacion", "--quote-asset", dest="quote_asset", default="USDT", help="Quote asset; por defecto USDT")
    p_mkt.add_argument("--capital", type=float, default=35.0, help="Capital de referencia en quote asset para evaluar liquidez relativa. Default: 35")
    p_mkt.set_defaults(func=run_market_mode)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())