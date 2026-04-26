#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Binance Trading Tools v4.1.1
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
Binance Trading Tools v4.1.1
Novedades:
- Mejora significativa en el ranking: ahora penaliza activamente estados "degradado" e "invalido"
- Incorpora pullback_quality en el cálculo del score
- Incorpora rr_estructural_preliminar en el score (premia buen riesgo/recompensa)
- Nuevo filtro --only-vigent para mostrar solo activos con setup "vigente"
- Nuevo score_final que combina score base con multiplicador por calidad del setup
- Ranking más preciso y alineado con la verdadera operabilidad de cada activo
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
SCRIPT_TITLE = "BINANCE TRADING TOOL - David Ramírez Chiappe"
SCRIPT_VERSION = "4.1.2"


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


def true_range(curr: Dict[str, Any], prev_close: Optional[float]) -> float:
    high = float(curr["high"])
    low = float(curr["low"])
    if prev_close is None:
        return high - low
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def average_true_range(candles: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    trs: List[float] = []
    prev_close = None
    for candle in candles:
        trs.append(true_range(candle, prev_close))
        prev_close = float(candle["close"])
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def slope_pct(values: List[float], period: int) -> Optional[float]:
    if len(values) < period + 1:
        return None
    base = values[-period - 1]
    curr = values[-1]
    if abs(base) <= EPS:
        return None
    return ((curr / base) - 1.0) * 100.0


def find_last_swing_low(candles: List[Dict[str, Any]], left: int = 2, right: int = 2) -> Optional[float]:
    if len(candles) < left + right + 1:
        return None
    lows = [float(c["low"]) for c in candles]
    last_idx = None
    for i in range(left, len(lows) - right):
        center = lows[i]
        if all(center < lows[j] for j in range(i - left, i)) and all(center <= lows[j] for j in range(i + 1, i + right + 1)):
            last_idx = i
    return lows[last_idx] if last_idx is not None else None


def find_last_swing_high(candles: List[Dict[str, Any]], left: int = 2, right: int = 2) -> Optional[float]:
    if len(candles) < left + right + 1:
        return None
    highs = [float(c["high"]) for c in candles]
    last_idx = None
    for i in range(left, len(highs) - right):
        center = highs[i]
        if all(center > highs[j] for j in range(i - left, i)) and all(center >= highs[j] for j in range(i + 1, i + right + 1)):
            last_idx = i
    return highs[last_idx] if last_idx is not None else None


def candidate_price_key(value: float, tick_size: Optional[str]) -> str:
    formatted = format_price(value, tick_size)
    return formatted if formatted is not None else normalize_number_str(value, 8) or str(value)


def dedupe_candidates(
    candidates: List[Dict[str, Any]],
    tick_size: Optional[str],
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for c in candidates:
        key = candidate_price_key(float(c["value"]), tick_size)
        existing = grouped.get(key)
        if existing is None:
            clone = dict(c)
            clone["aliases"] = [c["name"]]
            grouped[key] = clone
            continue

        existing["aliases"] = sorted(set(existing.get("aliases", []) + [c["name"]]))
        if c["score"] > existing["score"] or (
            c["score"] == existing["score"] and c["distance_pct"] > existing["distance_pct"]
        ):
            keep_aliases = existing["aliases"]
            grouped[key] = dict(c)
            grouped[key]["aliases"] = keep_aliases

    return list(grouped.values())


def pick_best_by_names(
    candidates: List[Dict[str, Any]],
    preferred_names: List[str],
    used_names: Optional[set] = None,
) -> Optional[Dict[str, Any]]:
    used_names = used_names or set()
    valid = [c for c in candidates if c["name"] not in used_names]
    for name in preferred_names:
        matches = [c for c in valid if c["name"] == name]
        if matches:
            return sorted(matches, key=lambda x: (-x["score"], x["distance_pct"], x["value"]))[0]
    return None


def pick_distinct_candidate(
    candidates: List[Dict[str, Any]],
    used_names: set,
    min_distance_pct: Optional[float] = None,
    prefer_farthest: bool = False,
) -> Optional[Dict[str, Any]]:
    valid = [c for c in candidates if c["name"] not in used_names]
    if min_distance_pct is not None:
        valid = [c for c in valid if c["distance_pct"] >= min_distance_pct]
    if not valid:
        return None
    if prefer_farthest:
        valid = sorted(valid, key=lambda x: (x["distance_pct"], x["score"], -x["value"]), reverse=True)
    else:
        valid = sorted(valid, key=lambda x: (-x["score"], x["distance_pct"], x["value"]))
    return valid[0]


def level_separation_pct(last_price: Optional[float], atr1: Optional[float], tick_size: Optional[str]) -> float:
    atr_component = 0.0
    if last_price is not None and atr1 is not None and atr1 > EPS and last_price > EPS:
        atr_component = (atr1 / last_price) * 100.0 * 0.25

    tick_component = 0.0
    if last_price is not None and last_price > EPS and tick_size not in (None, '', '0', '0.0'):
        try:
            tick_component = (float(tick_size) / last_price) * 100.0 * 6.0
        except Exception:
            tick_component = 0.0

    return max(0.12, atr_component, tick_component)


def candidate_pref_index(name: str, preferred_names: List[str]) -> int:
    try:
        return preferred_names.index(name)
    except ValueError:
        return len(preferred_names) + 10


def pick_entry_with_constraints(
    candidates: List[Dict[str, Any]],
    preferred_names: List[str],
    tick_size: Optional[str],
    min_distance_pct: Optional[float] = None,
    max_distance_pct: Optional[float] = None,
    min_gap_from: Optional[List[Tuple[float, str]]] = None,
    used_price_keys: Optional[set] = None,
    mode: str = 'balanced',
) -> Optional[Dict[str, Any]]:
    used_price_keys = used_price_keys or set()
    min_gap_from = min_gap_from or []

    valid: List[Dict[str, Any]] = []
    for c in candidates:
        if min_distance_pct is not None and c['distance_pct'] < min_distance_pct:
            continue
        if max_distance_pct is not None and c['distance_pct'] > max_distance_pct:
            continue
        price_key = candidate_price_key(float(c['value']), tick_size)
        if price_key in used_price_keys:
            continue
        ok = True
        for ref_dist, gap in min_gap_from:
            if c['distance_pct'] < ref_dist + gap:
                ok = False
                break
        if ok:
            valid.append(c)

    if not valid:
        return None

    def sort_key(c: Dict[str, Any]):
        pref = candidate_pref_index(c['name'], preferred_names)
        if mode == 'nearest':
            return (pref, c['distance_pct'], -c['score'], c['value'])
        if mode == 'deep':
            return (pref, -c['distance_pct'], -c['score'], c['value'])
        return (pref, abs(c['distance_pct'] - 2.0), -c['score'], c['value'])

    valid = sorted(valid, key=sort_key)
    return valid[0]


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
# Progreso visual en consola
# =========================

def render_progress_bar(current: int, total: int, width: int = 20) -> str:
    if total <= 0:
        total = 1
    ratio = max(0.0, min(1.0, current / total))
    filled = int(round(ratio * width))
    return f"[{'#' * filled}{'.' * (width - filled)}] {int(ratio * 100):>3}%"


def print_console_banner(mode_label: str) -> None:
    print(SCRIPT_TITLE, flush=True)
    print(f"Modo: {mode_label} | Versión: {SCRIPT_VERSION}", flush=True)
    print("", flush=True)


def print_progress_header(total: int) -> None:
    print(f"Iniciando análisis de {total} par(es)...", flush=True)


def print_symbol_progress(index: int, total: int, symbol: str, stage: str) -> None:
    bar = render_progress_bar(index, total)
    print(f"{bar} | Analizando {symbol} ({index}/{total}) | {stage}", flush=True)


def print_symbol_done(index: int, total: int, symbol: str, status: str = 'OK') -> None:
    bar = render_progress_bar(index, total)
    print(f"{bar} | {symbol} -> {status}", flush=True)


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


def is_support_reliable(price_level: float, candles: List[Dict[str, Any]], volume_threshold: float = 10000) -> bool:
    """Verifica si el nivel de soporte ha sido validado por volumen significativo en las últimas velas."""
    if not candles or price_level <= EPS:
        return True
    
    check_candles = candles[-20:] if len(candles) >= 20 else candles
    
    touches = 0
    for candle in check_candles:
        low = candle.get("low")
        volume = candle.get("volume", 0)
        if low is None:
            continue
        
        if abs(low - price_level) / price_level < 0.01:
            if volume > volume_threshold:
                touches += 1
    
    return touches >= 2


def timeframe_summary(
    candles: List[Dict[str, Any]],
    recent_window: int = 20,
    absolute_window: Optional[int] = None,
    atr_period: int = 14,
    volume_threshold: float = 10000,
) -> Dict[str, Any]:
    closes = [float(c["close"]) for c in candles]
    recent = candles[-recent_window:] if len(candles) >= recent_window else candles
    absolute = candles[-absolute_window:] if absolute_window and len(candles) >= absolute_window else candles

    last_close = closes[-1] if closes else None
    ma7 = moving_average(closes, 7)
    ma25 = moving_average(closes, 25)
    ma99 = moving_average(closes, 99)
    atr14 = average_true_range(candles, atr_period)
    last_swing_low = find_last_swing_low(candles[-max(recent_window * 2, 12):]) if candles else None
    last_swing_high = find_last_swing_high(candles[-max(recent_window * 2, 12):]) if candles else None
    ma7_slope_pct_5 = slope_pct([v for v in closes if v is not None], 5) if closes else None

    zone_candidates = [
        ("ma25", ma25),
        ("ma99", ma99),
        ("recent_low", min(float(c["low"]) for c in recent) if recent else None),
        ("swing_low", last_swing_low),
    ]
    zone_values = []
    for name, value in zone_candidates:
        if value is not None and last_close is not None and value <= last_close:
            if is_support_reliable(value, candles, volume_threshold):
                zone_values.append(value)
    
    support_zone = None
    if zone_values:
        support_zone = {
            "low": min(zone_values),
            "high": max(zone_values),
        }

    return {
        "candles_count": len(candles),
        "recent_window": recent_window,
        "absolute_window": absolute_window or len(candles),
        "atr_period": atr_period,
        "last_open_time_utc": candles[-1]["open_time_utc"] if candles else None,
        "last_close": last_close,
        "last_high": candles[-1]["high"] if candles else None,
        "last_low": candles[-1]["low"] if candles else None,
        "last_volume": candles[-1]["volume"] if candles else None,
        "ma7": ma7,
        "ma25": ma25,
        "ma99": ma99,
        "ma7_slope_pct_5": ma7_slope_pct_5,
        "atr14": atr14,
        "recent_high": max(float(c["high"]) for c in recent) if recent else None,
        "recent_low": min(float(c["low"]) for c in recent) if recent else None,
        "absolute_high": max(float(c["high"]) for c in absolute) if absolute else None,
        "absolute_low": min(float(c["low"]) for c in absolute) if absolute else None,
        "last_swing_low": last_swing_low,
        "last_swing_high": last_swing_high,
        "swing_low_definition": {"left": 2, "right": 2, "method": "pivot_low"},
        "swing_high_definition": {"left": 2, "right": 2, "method": "pivot_high"},
        "support_zone": support_zone,
        "dist_pct_vs_ma7": pct_change(last_close, ma7),
        "dist_pct_vs_ma25": pct_change(last_close, ma25),
        "dist_pct_vs_ma99": pct_change(last_close, ma99),
        "atr_pct_of_price": pct_change((last_close + atr14) if last_close is not None and atr14 is not None else None, last_close),
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
        "minNotional": notional.get("minNotional"),
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
        tf_summary[tf] = timeframe_summary(parsed, recent_window=20, absolute_window=min(len(parsed), limit), atr_period=14)

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

    last_price = safe_float(position_snapshot.get("last_price"))
    if last_price is not None and active_oco is not None:
        sl_trigger = safe_float(active_oco.get("sl_trigger"))
        if sl_trigger is not None and sl_trigger > EPS:
            dist_to_sl_pct = ((last_price / sl_trigger) - 1.0) * 100.0 if last_price > sl_trigger else None
            if dist_to_sl_pct is not None and dist_to_sl_pct < 1.5:
                alerts.append(f"⚠️ Precio a menos de 1.5% del stop loss ({active_oco.get('sl_trigger')})")

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
# Setup / soportes / invalidación
# =========================

def classify_setup_status(public_data: Dict[str, Any], suggestion: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ticker = public_data["ticker"]
    t1 = public_data["timeframes"]["1h"]
    t4 = public_data["timeframes"]["4h"]

    last_price = safe_float(ticker.get("lastPrice"))
    ma25_1 = safe_float(t1.get("ma25"))
    ma99_1 = safe_float(t1.get("ma99"))
    ma25_4 = safe_float(t4.get("ma25"))
    ma99_4 = safe_float(t4.get("ma99"))
    limit_price = safe_float((suggestion or {}).get("suggested_limit_buy"))
    limit_dist_pct = safe_float((suggestion or {}).get("distance_pct_from_last"))

    state = "vigente"
    reasons: List[str] = []

    if last_price is not None and ma25_4 is not None and ma99_4 is not None and last_price < min(ma25_4, ma99_4):
        state = "invalido"
        reasons.append("Precio por debajo de MA25 y MA99 en 4h.")
    elif last_price is not None and ma99_1 is not None and last_price < ma99_1:
        state = "degradado"
        reasons.append("Precio por debajo de MA99 en 1h.")
    elif limit_dist_pct is not None and limit_dist_pct > 5.5:
        state = "extendido"
        reasons.append("La compra límite base queda bastante lejos del precio actual.")
    elif last_price is not None and ma25_1 is not None and last_price < ma25_1:
        state = "pullback_activo"
        reasons.append("Retroceso activo sobre MA25 de 1h sin romper estructura mayor.")
    else:
        reasons.append("Estructura general todavía favorable para retroceso controlado.")

    quality = "media"
    context_bias = "mixto"

    if last_price is not None and ma25_4 is not None and ma99_4 is not None and ma99_1 is not None:
        if last_price > ma25_4 and last_price > ma99_4 and last_price > ma99_1:
            if ma25_1 is not None and last_price > ma25_1:
                quality = "alta"
                context_bias = "alcista_4h"
            else:
                quality = "media"
                context_bias = "alcista_4h_con_pullback"
        elif last_price > ma25_4 and (ma99_4 is None or last_price > ma99_1):
            quality = "media"
            context_bias = "alcista_moderado"
        else:
            quality = "baja"
            context_bias = "debil_4h"
    elif state in ("degradado", "invalido"):
        quality = "baja"
        context_bias = "debil_4h"

    if state == "extendido" and quality == "alta":
        quality = "media"

    if limit_price is not None:
        reasons.append(f"Entrada base sugerida: {normalize_number_str(limit_price, 8)}")

    return {
        "state": state,
        "trend_quality": quality,
        "context_bias": context_bias,
        "reasons": reasons,
    }


def build_invalidation_levels(public_data: Dict[str, Any], entry_price: Optional[float] = None) -> Dict[str, Any]:
    rules = public_data.get("symbol_info", {}).get("rules_short", {})
    tick_size = rules.get("tickSize")

    t1 = public_data["timeframes"]["1h"]
    t4 = public_data["timeframes"]["4h"]

    operational_candidates = [
        ("1h_recent_low", safe_float(t1.get("recent_low"))),
        ("1h_last_swing_low", safe_float(t1.get("last_swing_low"))),
        ("1h_ma99", safe_float(t1.get("ma99"))),
        ("4h_ma25", safe_float(t4.get("ma25"))),
    ]
    structural_candidates = [
        ("1h_recent_low", safe_float(t1.get("recent_low"))),
        ("1h_last_swing_low", safe_float(t1.get("last_swing_low"))),
        ("4h_ma25", safe_float(t4.get("ma25"))),
        ("4h_recent_low", safe_float(t4.get("recent_low"))),
        ("4h_absolute_low", safe_float(t4.get("absolute_low"))),
    ]

    op_valid = [(name, value) for name, value in operational_candidates if value is not None]
    st_valid = [(name, value) for name, value in structural_candidates if value is not None]
    if not st_valid and not op_valid:
        return {
            "stop_candidate_operativo": None,
            "stop_candidate_estructural": None,
            "trigger_candidate_operativo": None,
            "trigger_candidate_estructural": None,
            "reason": "Sin suficientes soportes para calcular invalidación.",
            "risk_pct_from_entry_operativo": None,
            "risk_pct_from_entry_estructural": None,
            "stop_candidate": None,
            "trigger_candidate": None,
            "risk_pct_from_entry": None,
        }

    op_name, op_value = (max(op_valid, key=lambda x: x[1]) if op_valid else (None, None))
    st_name, st_value = (min(st_valid, key=lambda x: x[1]) if st_valid else (None, None))

    op_trigger = max((v for _, v in op_valid if op_value is not None and v <= op_value * 1.01), default=op_value)
    st_trigger = max((v for _, v in st_valid if st_value is not None and v <= st_value * 1.01), default=st_value)

    risk_pct_operativo = None
    risk_pct_estructural = None
    if entry_price is not None and entry_price > EPS:
        if op_value is not None and entry_price > op_value:
            risk_pct_operativo = ((entry_price / op_value) - 1.0) * 100.0
        if st_value is not None and entry_price > st_value:
            risk_pct_estructural = ((entry_price / st_value) - 1.0) * 100.0

    return {
        "stop_candidate_operativo": format_price(op_value, tick_size),
        "stop_candidate_estructural": format_price(st_value, tick_size),
        "trigger_candidate_operativo": format_price(op_trigger, tick_size),
        "trigger_candidate_estructural": format_price(st_trigger, tick_size),
        "reason": (
            f"Invalidación operativa basada en soporte táctico cercano ({op_name}) e "
            f"invalidación estructural basada en el soporte profundo relevante ({st_name})."
        ),
        "risk_pct_from_entry_operativo": format_pct(risk_pct_operativo),
        "risk_pct_from_entry_estructural": format_pct(risk_pct_estructural),
        "reference_levels": [
            {"name": name, "value": normalize_number_str(value, 8)}
            for name, value in dict(op_valid + st_valid).items()
        ],
        "stop_candidate": format_price(st_value, tick_size),
        "trigger_candidate": format_price(st_trigger, tick_size),
        "risk_pct_from_entry": format_pct(risk_pct_estructural),
    }


# =========================
# Lógica de compra límite
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
    atr1 = safe_float(t1.get("atr14"))
    if last_price is None:
        return {
            "suggested_limit_buy": None,
            "reference": None,
            "second_support": None,
            "distance_pct_from_last": None,
            "note": "No se pudo leer el precio actual.",
            "entries": {},
            "support_zone": None,
            "setup_status": None,
            "candidates_debug": [],
        }

    raw_candidates = [
        ("1h_ma25", safe_float(t1.get("ma25")), 8, "near"),
        ("1h_last_swing_low", safe_float(t1.get("last_swing_low")), 7, "near"),
        ("15m_recent_low", safe_float(t15.get("recent_low")), 5, "near"),
        ("4h_ma25", safe_float(t4.get("ma25")), 7, "base"),
        ("1h_ma99", safe_float(t1.get("ma99")), 7, "base"),
        ("1h_recent_low", safe_float(t1.get("recent_low")), 6, "base"),
        ("4h_ma99", safe_float(t4.get("ma99")), 4, "deep"),
        ("4h_recent_low", safe_float(t4.get("recent_low")), 3, "deep"),
    ]

    candidates: List[Dict[str, Any]] = []

    for name, value, base_score, tier in raw_candidates:
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

        if tier == "near" and dist_pct < 0.55:
            score -= 2
        elif tier == "deep" and dist_pct > max_distance_pct + 1.5:
            score -= 1

        if name == "4h_ma99" and dist_pct < 0.7:
            score -= 1

        atr_distance = None
        if atr1 is not None and atr1 > EPS:
            atr_distance = (last_price - value) / atr1
            if 0.7 <= atr_distance <= 2.2:
                score += 1
            elif atr_distance > 3.5:
                score -= 1

        candidates.append(
            {
                "name": name,
                "value": value,
                "distance_pct": dist_pct,
                "atr_distance_1h": atr_distance,
                "score": score,
                "tier": tier,
            }
        )

    if not candidates:
        setup_status = classify_setup_status(public_data, None)
        return {
            "suggested_limit_buy": None,
            "reference": None,
            "second_support": None,
            "distance_pct_from_last": None,
            "note": "No se encontraron soportes válidos por debajo del precio actual.",
            "entries": {},
            "support_zone": None,
            "setup_status": setup_status,
            "candidates_debug": [],
        }

    deduped = dedupe_candidates(candidates, tick_size)
    candidates_sorted = sorted(
        deduped,
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

    support_zone_pool = candidates_sorted[: min(4, len(candidates_sorted))]
    support_zone_low = min(c["value"] for c in support_zone_pool)
    support_zone_high = max(c["value"] for c in support_zone_pool)

    aggressive_pref = ["1h_ma25", "1h_last_swing_low", "15m_recent_low", "4h_ma25", "1h_ma99", "1h_recent_low"]
    base_pref = ["4h_ma25", "1h_ma99", "1h_recent_low", "1h_last_swing_low", "4h_ma99", "4h_recent_low"]
    conservative_pref = ["4h_recent_low", "4h_ma99", "1h_recent_low", "1h_ma99", "4h_ma25"]

    sep_pct = level_separation_pct(last_price, atr1, tick_size)
    min_aggressive_dist = max(0.25, min_distance_pct * 0.45)

    aggressive = pick_entry_with_constraints(
        candidates_sorted,
        aggressive_pref,
        tick_size,
        min_distance_pct=min_aggressive_dist,
        max_distance_pct=max_distance_pct + 0.75,
        used_price_keys=set(),
        mode='nearest',
    ) or candidates_sorted[0]

    used_price_keys = {candidate_price_key(float(aggressive['value']), tick_size)}

    base_entry = pick_entry_with_constraints(
        candidates_sorted,
        base_pref,
        tick_size,
        min_distance_pct=min_distance_pct,
        max_distance_pct=max_distance_pct + 1.25,
        min_gap_from=[(aggressive['distance_pct'], sep_pct)],
        used_price_keys=used_price_keys,
        mode='balanced',
    )

    if base_entry is None:
        base_entry = pick_entry_with_constraints(
            candidates_sorted,
            base_pref,
            tick_size,
            min_distance_pct=aggressive['distance_pct'] + sep_pct,
            min_gap_from=[(aggressive['distance_pct'], sep_pct)],
            used_price_keys=used_price_keys,
            mode='balanced',
        )

    if base_entry is not None:
        used_price_keys.add(candidate_price_key(float(base_entry['value']), tick_size))

    conservative = None
    if base_entry is not None:
        conservative = pick_entry_with_constraints(
            candidates_sorted,
            conservative_pref,
            tick_size,
            min_distance_pct=base_entry['distance_pct'] + sep_pct,
            min_gap_from=[(aggressive['distance_pct'], sep_pct), (base_entry['distance_pct'], sep_pct)],
            used_price_keys=used_price_keys,
            mode='deep',
        )

    if conservative is None and base_entry is None:
        conservative = pick_entry_with_constraints(
            candidates_sorted,
            conservative_pref,
            tick_size,
            min_distance_pct=aggressive['distance_pct'] + sep_pct,
            min_gap_from=[(aggressive['distance_pct'], sep_pct)],
            used_price_keys=used_price_keys,
            mode='deep',
        )

    second = None
    if base_entry is not None:
        second = next((c for c in candidates_sorted if c['name'] != base_entry['name']), None)
    else:
        second = next((c for c in candidates_sorted if c['name'] != aggressive['name']), None)

    note_parts = [
        "Sugerencia mecánica basada en soportes por debajo del precio actual.",
        "La selección de entradas 4.0 prioriza zonas operativas, fuerza escalones distintos (aggressive/base/conservative), exige separación mínima entre escalones y devuelve null cuando no existen niveles realmente distintos."
    ]
    base_for_note = base_entry or aggressive
    if base_for_note["distance_pct"] < min_distance_pct:
        note_parts.append("La entrada base está bastante pegada al precio actual.")
    elif base_for_note["distance_pct"] > max_distance_pct:
        note_parts.append("La entrada base queda bastante lejos; el rebote podría darse antes.")
    else:
        note_parts.append("La distancia de la entrada base al precio actual luce razonable para buscar retroceso.")
    if base_entry is None:
        note_parts.append("No se encontró un escalón base realmente distinto; se devuelve null para evitar falsa precisión.")
    if conservative is None:
        note_parts.append("No se encontró un escalón conservador suficientemente separado; se devuelve null.")
    if atr1 is not None:
        note_parts.append(f"ATR 1h aprox.: {normalize_number_str(atr1, 8)}.")

    result = {
        "suggested_limit_buy": floor_to_step((base_entry or aggressive)["value"], tick_size),
        "reference": (base_entry or aggressive)["name"],
        "second_support": {
            "name": second["name"],
            "value": normalize_number_str(second["value"], 8),
            "distance_pct": normalize_number_str(second["distance_pct"], 4),
        } if second else None,
        "distance_pct_from_last": normalize_number_str((base_entry or aggressive)["distance_pct"], 4),
        "entries": {
            "aggressive": {
                "reference": aggressive["name"],
                "price": floor_to_step(aggressive["value"], tick_size),
                "distance_pct": normalize_number_str(aggressive["distance_pct"], 4),
            },
            "base": {
                "reference": (base_entry or aggressive)["name"],
                "price": floor_to_step(base_entry["value"], tick_size),
                "distance_pct": normalize_number_str(base_entry["distance_pct"], 4),
            } if base_entry is not None else None,
            "conservative": {
                "reference": conservative["name"],
                "price": floor_to_step(conservative["value"], tick_size),
                "distance_pct": normalize_number_str(conservative["distance_pct"], 4),
            } if conservative is not None else None,
        },
        "entries_quality": "full" if base_entry is not None and conservative is not None else ("two_levels" if base_entry is not None else "single_level_only"),
        "support_zone": {
            "low": format_price(support_zone_low, tick_size),
            "high": format_price(support_zone_high, tick_size),
        },
        "note": " ".join(note_parts),
        "setup_status": None,
        "candidates_debug": [
            {
                "name": c["name"],
                "aliases": c.get("aliases", [c["name"]]),
                "value": normalize_number_str(c["value"], 8),
                "distance_pct": normalize_number_str(c["distance_pct"], 4),
                "atr_distance_1h": normalize_number_str(c["atr_distance_1h"], 4),
                "score": c["score"],
                "tier": c["tier"],
            }
            for c in candidates_sorted
        ],
    }
    result["setup_status"] = classify_setup_status(public_data, result)
    return result


# =========================
# Enriquecimiento de watchlist v3.9
# =========================

def score_bucket(score: int) -> str:
    if score >= 20:
        return "A"
    if score >= 12:
        return "B"
    if score >= 4:
        return "C"
    return "D"


def classify_extension_risk(dist_1h_ma25: Optional[float], dist_4h_ma25: Optional[float], dist_4h_ma99: Optional[float]) -> Dict[str, Any]:
    vals = [v for v in [dist_1h_ma25, dist_4h_ma25, dist_4h_ma99] if v is not None]
    max_abs = max(vals) if vals else None
    state = "unknown"
    if max_abs is not None:
        if max_abs <= 1.5:
            state = "compressed"
        elif max_abs <= 4.0:
            state = "normal"
        elif max_abs <= 7.0:
            state = "extended"
        else:
            state = "overextended"
    return {
        "state": state,
        "dist_1h_vs_ma25": format_pct(dist_1h_ma25),
        "dist_4h_vs_ma25": format_pct(dist_4h_ma25),
        "dist_4h_vs_ma99": format_pct(dist_4h_ma99),
    }


def get_pullback_score(pullback_quality: str) -> int:
    """Convierte la calidad del pullback en puntos para el score."""
    score_map = {
        "ordenado": 3,
        "profundo_pero_sano": 2,
        "profundo": 0,
        "debil_sin_confirmacion": -2,
        "brusco": -3,
        "shallow_not_ready": -1,
    }
    return score_map.get(pullback_quality, 0)


def get_rr_score(rr: Optional[float]) -> int:
    """Convierte el ratio riesgo/recompensa en puntos para el score."""
    if rr is None:
        return 0
    if rr >= 2.0:
        return 3
    if rr >= 1.5:
        return 2
    if rr >= 1.0:
        return 1
    if rr < 0.3:
        return -3
    if rr < 0.5:
        return -2
    if rr < 0.8:
        return -1
    return 0


def get_setup_multiplier(setup_state: str) -> float:
    """Devuelve multiplicador para ajustar el score según calidad del setup."""
    multipliers = {
        "vigente": 1.0,
        "pullback_activo": 0.9,
        "degradado": 0.7,
        "extendido": 0.8,
        "invalido": 0.5,
    }
    return multipliers.get(setup_state, 0.6)


def classify_pullback_quality(
    last_price: Optional[float],
    recent_high_1h: Optional[float],
    c1: Optional[float],
    ma25_1: Optional[float],
    ma99_1: Optional[float],
    c15: Optional[float],
    ma25_15: Optional[float],
    ma7_15: Optional[float],
    candles_15: Optional[List[Dict[str, Any]]] = None,
) -> str:
    if last_price is None or recent_high_1h is None or recent_high_1h <= EPS:
        return "unknown"
    pullback_pct = ((recent_high_1h - last_price) / recent_high_1h) * 100.0
    above_ma99_1 = c1 is not None and ma99_1 is not None and c1 > ma99_1
    above_ma25_1 = c1 is not None and ma25_1 is not None and c1 > ma25_1
    
    weak_15m = False
    if candles_15 and len(candles_15) >= 3:
        weak_count = 0
        for i in range(-3, 0):
            close = safe_float(candles_15[i].get("close"))
            ma25_val = ma25_15
            ma7_val = ma7_15
            if close is not None:
                if (ma25_val is not None and close < ma25_val) or (ma7_val is not None and close < ma7_val):
                    weak_count += 1
        weak_15m = weak_count >= 2
    else:
        weak_15m = c15 is not None and ((ma25_15 is not None and c15 < ma25_15) or (ma7_15 is not None and c15 < ma7_15))

    if pullback_pct < 0.6:
        return "shallow_not_ready"
    if 0.6 <= pullback_pct <= 4.5 and above_ma99_1 and weak_15m:
        return "ordenado"
    if 4.5 < pullback_pct <= 7.0 and above_ma99_1:
        return "profundo_pero_sano"
    if pullback_pct > 7.0 and above_ma99_1:
        return "profundo"
    if not above_ma99_1 and above_ma25_1:
        return "debil_sin_confirmacion"
    return "brusco"


def classify_support_quality(suggestion: Dict[str, Any], public_data: Dict[str, Any]) -> Dict[str, Any]:
    t1 = public_data["timeframes"]["1h"]
    t4 = public_data["timeframes"]["4h"]
    refs = [
        safe_float(t1.get("ma99")),
        safe_float(t4.get("ma25")),
        safe_float(t1.get("recent_low")),
        safe_float(t4.get("recent_low")),
        safe_float(t1.get("last_swing_low")),
    ]
    refs = [r for r in refs if r is not None]
    support_zone = suggestion.get("support_zone") or {}
    low = safe_float(support_zone.get("low"))
    high = safe_float(support_zone.get("high"))
    width_pct = None
    if low is not None and high is not None and low > EPS:
        width_pct = ((high / low) - 1.0) * 100.0

    confluence = 0
    if low is not None and high is not None:
        for r in refs:
            if low - EPS <= r <= high + EPS:
                confluence += 1

    entries_quality = suggestion.get("entries_quality")
    if entries_quality == "single_level_only":
        state = "baja"
    elif confluence >= 3 and (width_pct is None or width_pct <= 2.2):
        state = "alta"
    elif confluence >= 2 and (width_pct is None or width_pct <= 3.8):
        state = "media"
    else:
        state = "baja"
    return {
        "state": state,
        "confluence_count": confluence,
        "zone_width_pct": format_pct(width_pct),
        "entries_quality": entries_quality,
    }


def classify_zone_integrity(suggestion: Dict[str, Any], public_data: Dict[str, Any], support_quality: Dict[str, Any]) -> Dict[str, Any]:
    entries = suggestion.get("entries") or {}
    entries_quality = suggestion.get("entries_quality") or "single_level_only"
    if entries_quality == "single_level_only":
        return {"state": "single_level_only", "gap_aggressive_base_pct": None, "gap_base_conservative_pct": None}

    aggr = safe_float(((entries.get("aggressive") or {}).get("price")))
    base = safe_float(((entries.get("base") or {}).get("price")))
    cons = safe_float(((entries.get("conservative") or {}).get("price")))
    second_support = safe_float((suggestion.get("second_support") or {}).get("value"))
    atr_pct_1h = safe_float(((public_data.get("timeframes") or {}).get("1h") or {}).get("atr_pct_of_price")) or 0.0
    compact_threshold = max(0.12, atr_pct_1h * 0.30)
    wide_threshold = max(0.35, atr_pct_1h * 0.85)

    gap_ab = None
    gap_bc = None
    if aggr and base and aggr > EPS and base > EPS:
        gap_ab = abs(((aggr / base) - 1.0) * 100.0)
    if base and cons and base > EPS and cons > EPS:
        gap_bc = abs(((base / cons) - 1.0) * 100.0)

    state = "escalonada"
    if gap_ab is not None and gap_ab <= compact_threshold:
        state = "compacta"
    if second_support is not None and aggr is not None and base is not None and second_support > EPS:
        gap_second = abs(((aggr / second_support) - 1.0) * 100.0)
        gap_base = abs(((aggr / base) - 1.0) * 100.0)
        if gap_second <= compact_threshold and gap_base >= wide_threshold:
            state = "forzada"

    if support_quality.get("state") == "baja" and entries_quality == "two_levels" and gap_ab is not None and gap_ab >= wide_threshold:
        state = "forzada"

    return {
        "state": state,
        "gap_aggressive_base_pct": format_pct(gap_ab),
        "gap_base_conservative_pct": format_pct(gap_bc),
        "compact_threshold_pct": format_pct(compact_threshold),
    }


def compute_resistance_snapshot(public_data: Dict[str, Any], entry_price: Optional[float], stop_price_operativo: Optional[float], stop_price_estructural: Optional[float]) -> Dict[str, Any]:
    ticker = public_data["ticker"]
    t15 = public_data["timeframes"]["15m"]
    t1 = public_data["timeframes"]["1h"]
    t4 = public_data["timeframes"]["4h"]
    tick_size = public_data.get("symbol_info", {}).get("rules_short", {}).get("tickSize")
    last_price = safe_float(ticker.get("lastPrice"))
    atr1 = safe_float(t1.get("atr14"))

    micro_gap = 0.0
    oper_gap = 0.0
    if atr1 is not None:
        micro_gap = max(micro_gap, atr1 * 0.20)
        oper_gap = max(oper_gap, atr1 * 0.90)
    if entry_price is not None:
        micro_gap = max(micro_gap, entry_price * 0.003)
        oper_gap = max(oper_gap, entry_price * 0.015)

    micro_candidates = [
        ("15m_last_swing_high", safe_float(t15.get("last_swing_high"))),
        ("1h_last_swing_high", safe_float(t1.get("last_swing_high"))),
        ("1h_recent_high", safe_float(t1.get("recent_high"))),
        ("4h_last_swing_high", safe_float(t4.get("last_swing_high"))),
        ("4h_recent_high", safe_float(t4.get("recent_high"))),
        ("24h_high", safe_float(ticker.get("highPrice"))),
    ]
    oper_candidates = [
        ("1h_recent_high", safe_float(t1.get("recent_high"))),
        ("4h_last_swing_high", safe_float(t4.get("last_swing_high"))),
        ("4h_recent_high", safe_float(t4.get("recent_high"))),
        ("24h_high", safe_float(ticker.get("highPrice"))),
    ]

    valid_micro = []
    valid_oper = []
    if entry_price is not None:
        for n, v in micro_candidates:
            if v is None or v <= entry_price + micro_gap:
                continue
            valid_micro.append((n, v))
        for n, v in oper_candidates:
            if v is None or v <= entry_price + oper_gap:
                continue
            valid_oper.append((n, v))

    nearest_micro = min(valid_micro, key=lambda x: x[1]) if valid_micro else None
    nearest_oper = min(valid_oper, key=lambda x: x[1]) if valid_oper else None
    if nearest_oper is None:
        nearest_oper = nearest_micro

    dist_pct = None
    reward_pct = None
    rr_operativo = None
    rr_estructural = None
    risk_pct_operativo = None
    risk_pct_estructural = None

    if nearest_oper is not None and entry_price and entry_price > EPS:
        reward_pct = ((nearest_oper[1] / entry_price) - 1.0) * 100.0
        if last_price is not None and last_price > EPS:
            dist_pct = ((nearest_oper[1] / last_price) - 1.0) * 100.0
    if stop_price_operativo is not None and entry_price and stop_price_operativo > EPS and entry_price > stop_price_operativo:
        risk_pct_operativo = ((entry_price / stop_price_operativo) - 1.0) * 100.0
        if reward_pct is not None and risk_pct_operativo > EPS:
            rr_operativo = reward_pct / risk_pct_operativo
    if stop_price_estructural is not None and entry_price and stop_price_estructural > EPS and entry_price > stop_price_estructural:
        risk_pct_estructural = ((entry_price / stop_price_estructural) - 1.0) * 100.0
        if reward_pct is not None and risk_pct_estructural > EPS:
            rr_estructural = reward_pct / risk_pct_estructural

    return {
        "nearest_resistance_micro": {
            "name": nearest_micro[0],
            "value": format_price(nearest_micro[1], tick_size),
        } if nearest_micro else None,
        "nearest_resistance_operativa": {
            "name": nearest_oper[0],
            "value": format_price(nearest_oper[1], tick_size),
        } if nearest_oper else None,
        "distance_to_resistance_pct": format_pct(dist_pct),
        "reward_pct_to_resistance": format_pct(reward_pct),
        "rr_operativa_preliminar": format_pct(rr_operativo),
        "rr_estructural_preliminar": format_pct(rr_estructural),
        "initial_rr": format_pct(rr_operativo),
        "risk_pct_from_entry_operativo": format_pct(risk_pct_operativo),
        "risk_pct_from_entry_estructural": format_pct(risk_pct_estructural),
        "resistance_method": "micro_and_operational_resistance_with_min_gap",
        "micro_min_gap_abs": format_price(micro_gap, tick_size),
        "operational_min_gap_abs": format_price(oper_gap, tick_size),
    }


def build_rank_reason(setup_status: Dict[str, Any], trend_score: int, tradeability_score: int, extension_state: str, pullback_quality: str, support_quality: str) -> str:
    state = (setup_status or {}).get("state") or "sin_estado"
    parts = []
    if trend_score >= 6:
        parts.append("estructura 4h/1h sólida")
    elif trend_score >= 2:
        parts.append("estructura aceptable")
    else:
        parts.append("estructura débil")

    if tradeability_score >= 5:
        parts.append("operable ahora")
    elif tradeability_score >= 1:
        parts.append("operable con matices")
    else:
        parts.append("poca operabilidad inmediata")

    if extension_state in ("extended", "overextended"):
        parts.append(f"activo {extension_state}")
    else:
        parts.append(f"pullback {pullback_quality}")

    parts.append(f"soporte {support_quality}")
    parts.append(f"estado {state}")
    return "; ".join(parts) + "."


# =========================
# Ranking de watchlist v3.9 (MEJORADO)
# =========================

def score_rebound_candidate(symbol: str, public_data: Dict[str, Any], capital_quote: float = 35.0) -> Dict[str, Any]:
    ticker = public_data["ticker"]
    depth = public_data["depth_summary"]
    t15 = public_data["timeframes"]["15m"]
    t1 = public_data["timeframes"]["1h"]
    t4 = public_data["timeframes"]["4h"]
    candles_15 = public_data["csv_rows"].get("15m", [])

    last_price = safe_float(ticker.get("lastPrice"))
    reasons: List[str] = []
    breakdown = {
        "structure_4h": 0,
        "pullback_1h": 0,
        "timing_15m": 0,
        "liquidity": 0,
        "execution": 0,
    }

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
            breakdown["structure_4h"] += 2
            reasons.append("4h por encima de MA25")
        else:
            breakdown["structure_4h"] -= 2
            reasons.append("4h por debajo de MA25")

    dist_4h_vs_ma99 = pct_change(c4, ma99_4)
    dist_4h_vs_ma25 = pct_change(c4, ma25_4)
    dist_1h_vs_ma25 = pct_change(c1, ma25_1)
    if c4 is not None and ma99_4 is not None:
        if c4 > ma99_4:
            breakdown["structure_4h"] += 3
            reasons.append("4h por encima de MA99")
        else:
            if dist_4h_vs_ma99 is not None:
                if dist_4h_vs_ma99 >= -1.5:
                    breakdown["structure_4h"] -= 2
                    reasons.append("4h ligeramente por debajo de MA99")
                elif dist_4h_vs_ma99 >= -4.0:
                    breakdown["structure_4h"] -= 4
                    reasons.append("4h claramente por debajo de MA99")
                else:
                    breakdown["structure_4h"] -= 6
                    reasons.append("4h muy débil frente a MA99")
            else:
                breakdown["structure_4h"] -= 3
                reasons.append("4h por debajo de MA99")

    if ma25_4 is not None and ma99_4 is not None:
        if ma25_4 > ma99_4:
            breakdown["structure_4h"] += 2
            reasons.append("sesgo alcista en 4h (MA25 > MA99)")
        else:
            breakdown["structure_4h"] -= 2
            reasons.append("sesgo flojo en 4h (MA25 <= MA99)")

    if c1 is not None and ma99_1 is not None:
        if c1 > ma99_1:
            breakdown["pullback_1h"] += 2
            reasons.append("1h aún por encima de MA99")
        else:
            breakdown["pullback_1h"] -= 2
            reasons.append("1h perdió MA99")

    if c1 is not None and ma7_1 is not None and c1 < ma7_1:
        breakdown["pullback_1h"] += 1
        reasons.append("hay retroceso corto en 1h")

    if c1 is not None and ma25_1 is not None:
        if dist_1h_vs_ma25 is not None and -2.5 <= dist_1h_vs_ma25 <= 1.0:
            breakdown["pullback_1h"] += 2
            reasons.append("retroceso razonable cerca de MA25 de 1h")
        elif dist_1h_vs_ma25 is not None and dist_1h_vs_ma25 < -5.0:
            breakdown["pullback_1h"] -= 2
            reasons.append("retroceso demasiado profundo vs MA25 de 1h")

    if last_price is not None and recent_high_1 is not None and recent_high_1 > EPS:
        pullback_pct = ((recent_high_1 - last_price) / recent_high_1) * 100.0
        if 0.8 <= pullback_pct <= 4.5:
            breakdown["pullback_1h"] += 3
            reasons.append("pullback sano desde máximo reciente")
        elif 4.5 < pullback_pct <= 7.0:
            breakdown["pullback_1h"] += 1
            reasons.append("pullback amplio, aún recuperable")
        elif pullback_pct > 7.0:
            breakdown["pullback_1h"] -= 2
            reasons.append("pullback ya muy profundo")
        else:
            breakdown["pullback_1h"] -= 1
            reasons.append("precio todavía muy pegado al máximo reciente")

    if c15 is not None and ma7_15 is not None and c15 < ma7_15:
        breakdown["timing_15m"] += 1
        reasons.append("15m descargando")
    if c15 is not None and ma25_15 is not None and c15 < ma25_15:
        breakdown["timing_15m"] += 1
        reasons.append("15m ya cedió algo hacia MA25")

    if spread_pct is not None:
        if spread_pct <= 0.01:
            breakdown["liquidity"] += 2
            reasons.append("spread muy corto")
        elif spread_pct <= 0.05:
            breakdown["liquidity"] += 1
            reasons.append("spread controlado")
        elif spread_pct <= 0.10:
            reasons.append("spread aceptable")
        elif spread_pct <= 0.25:
            breakdown["liquidity"] -= 1
            reasons.append("spread algo amplio")
        else:
            breakdown["liquidity"] -= 3
            reasons.append("spread claramente amplio")

    if min_side_notional is not None and capital_quote > 0:
        depth_ratio = min_side_notional / capital_quote
        if depth_ratio < 50:
            breakdown["liquidity"] -= 3
            reasons.append("profundidad corta insuficiente para el capital de referencia")
        elif depth_ratio < 150:
            breakdown["liquidity"] -= 1
            reasons.append("profundidad corta algo justa")
        elif depth_ratio > 400:
            reasons.append("profundidad corta holgada para el capital de referencia")

    suggestion = suggest_limit_buy(public_data)
    suggested_limit = suggestion.get("suggested_limit_buy")
    suggested_dist = safe_float(suggestion.get("distance_pct_from_last"))
    if suggested_limit is None:
        breakdown["execution"] -= 2
        reasons.append("sin compra límite razonable por debajo del precio actual")
    else:
        if suggested_dist is not None:
            if 0.8 <= suggested_dist <= 4.0:
                breakdown["execution"] += 2
                reasons.append("compra límite propuesta con distancia razonable")
            elif suggested_dist < 0.5:
                breakdown["execution"] -= 2
                reasons.append("compra límite demasiado pegada al precio actual")
            elif suggested_dist > 6.0:
                breakdown["execution"] -= 1
                reasons.append("compra límite bastante alejada")

    setup_status = suggestion.get("setup_status", {}) if suggestion else {}
    pullback_quality = classify_pullback_quality(last_price, recent_high_1, c1, ma25_1, ma99_1, c15, ma25_15, ma7_15, candles_15)
    
    # ===== MEJORAS v3.9 =====
    
    # 1. Penalizar más fuerte estados degradado e invalido
    if setup_status.get("state") == "degradado":
        breakdown["execution"] -= 3      # Antes -1
        breakdown["structure_4h"] -= 2   # Penalización adicional
        reasons.append("estado degradado: penalización por pérdida de MA99 en 1h")
    elif setup_status.get("state") == "invalido":
        breakdown["execution"] -= 5      # Antes -3
        breakdown["structure_4h"] -= 3   # Penalización adicional
        reasons.append("estado invalido: penalización por estructura debilitada")
    elif setup_status.get("state") == "pullback_activo":
        breakdown["execution"] += 1
    
    # 2. Incorporar pullback_quality al score
    pullback_score = get_pullback_score(pullback_quality)
    breakdown["pullback_1h"] += pullback_score
    if pullback_score > 0:
        reasons.append(f"pullback de calidad '{pullback_quality}' suma puntos")
    elif pullback_score < 0:
        reasons.append(f"pullback de calidad '{pullback_quality}' resta puntos")
    
    # 3. Incorporar rr_estructural_preliminar al score
    rr_estructural = safe_float(suggestion.get("rr_estructural_preliminar")) if suggestion else None
    rr_score = get_rr_score(rr_estructural)
    breakdown["execution"] += rr_score
    if rr_score > 0:
        reasons.append(f"ratio riesgo/recompensa favorable ({rr_estructural:.2f}) suma puntos")
    elif rr_score < 0:
        reasons.append(f"ratio riesgo/recompensa desfavorable ({rr_estructural:.2f}) resta puntos")
    
    # 4. Calcular score base
    score = sum(breakdown.values())
    
    # 5. Aplicar multiplicador por calidad del setup
    setup_multiplier = get_setup_multiplier(setup_status.get("state", "invalido"))
    score_final = int(score * setup_multiplier)
    
    # 6. Mantener compatibilidad con versiones anteriores
    trend_score = breakdown["structure_4h"] + max(0, breakdown["pullback_1h"])
    tradeability_score = breakdown["timing_15m"] + breakdown["liquidity"] + breakdown["execution"] + min(2, max(-2, breakdown["pullback_1h"]))
    bucket = score_bucket(score_final)
    
    # ===== Fin mejoras =====

    extension = classify_extension_risk(dist_1h_vs_ma25, dist_4h_vs_ma25, dist_4h_vs_ma99)
    support_quality = classify_support_quality(suggestion, public_data)
    zone_integrity = classify_zone_integrity(suggestion, public_data, support_quality)

    base_entry = None
    entries = suggestion.get("entries") or {}
    if entries.get("base") and entries["base"].get("price") is not None:
        base_entry = safe_float(entries["base"].get("price"))
    elif entries.get("aggressive") and entries["aggressive"].get("price") is not None:
        base_entry = safe_float(entries["aggressive"].get("price"))

    invalidation = build_invalidation_levels(public_data, entry_price=base_entry)
    stop_candidate_operativo = safe_float(invalidation.get("stop_candidate_operativo"))
    stop_candidate_estructural = safe_float(invalidation.get("stop_candidate_estructural"))
    resistance = compute_resistance_snapshot(public_data, base_entry, stop_candidate_operativo, stop_candidate_estructural)
    tactical_plan = build_tactical_plan(public_data, base_entry, resistance, invalidation)
    why_ranked_here = build_rank_reason(setup_status, trend_score, tradeability_score, extension["state"], pullback_quality, support_quality["state"])

    candidate_payload = {
        "symbol": symbol,
        "last_price": normalize_number_str(last_price, 8),
        "score": score_final,
        "score_raw": score,
        "score_bucket": bucket,
        "trend_score": trend_score,
        "tradeability_score": tradeability_score,
        "score_breakdown": breakdown,
        "setup_status": setup_status,
        "extension_risk": extension,
        "pullback_quality": pullback_quality,
        "support_quality": support_quality,
        "zone_integrity": zone_integrity,
        "why_ranked_here": why_ranked_here,
        "reasons": reasons,
        "suggested_limit_buy": suggested_limit,
        "entries": entries,
        "limit_reference": suggestion.get("reference"),
        "support_zone": suggestion.get("support_zone"),
        "distance_pct_from_last": suggestion.get("distance_pct_from_last"),
        "second_support": suggestion.get("second_support"),
        "dist_4h_vs_ma99": normalize_number_str(dist_4h_vs_ma99, 4),
        "spread_pct": normalize_number_str(spread_pct, 4),
        "min_side_notional_top10": normalize_number_str(min_side_notional, 4),
        "distance_to_resistance_pct": resistance.get("distance_to_resistance_pct"),
        "nearest_resistance_micro": resistance.get("nearest_resistance_micro"),
        "nearest_resistance_operativa": resistance.get("nearest_resistance_operativa"),
        "reward_pct_to_resistance": resistance.get("reward_pct_to_resistance"),
        "rr_operativa_preliminar": resistance.get("rr_operativa_preliminar"),
        "rr_estructural_preliminar": resistance.get("rr_estructural_preliminar"),
        "initial_rr": resistance.get("initial_rr"),
        "resistance_method": resistance.get("resistance_method"),
        "resistance_micro_min_gap_abs": resistance.get("micro_min_gap_abs"),
        "resistance_operational_min_gap_abs": resistance.get("operational_min_gap_abs"),
        "invalidation_snapshot": {
            "stop_candidate_operativo": invalidation.get("stop_candidate_operativo"),
            "stop_candidate_estructural": invalidation.get("stop_candidate_estructural"),
            "risk_pct_from_entry_operativo": invalidation.get("risk_pct_from_entry_operativo"),
            "risk_pct_from_entry_estructural": invalidation.get("risk_pct_from_entry_estructural"),
        },
        "note": suggestion.get("note"),
        "tp_tactico": tactical_plan.get("tp_tactico"),
        "stop_tactico": tactical_plan.get("stop_tactico"),
        "rr_tactico_estimado": tactical_plan.get("rr_tactico_estimado"),
        "tp_reference": tactical_plan.get("tp_reference"),
        "stop_reference": tactical_plan.get("stop_reference"),
    }

    passes_visible_filters, hard_filter_reasons = passes_hard_filters(candidate_payload)
    candidate_payload["passes_hard_filters"] = passes_visible_filters
    candidate_payload["hard_filter_reasons"] = hard_filter_reasons
    candidate_payload["quality_score_v4"] = compute_quality_v4(candidate_payload) if passes_visible_filters else None
    candidate_payload["visible_state"] = visible_state_from_quality(candidate_payload["quality_score_v4"], candidate_payload) if passes_visible_filters else None
    candidate_payload["quality_grade"] = visible_grade_from_quality(candidate_payload["score"], candidate_payload["quality_score_v4"]) if passes_visible_filters else None
    return candidate_payload


# =========================
# Texto de salida
# =========================

def build_ui_header(title: str, version: str, mode_label: str) -> List[str]:
    mode_map = {
        "mercado": "Mercado",
        "posicion": "Posición",
        "posición": "Posición",
    }
    mode_pretty = mode_map.get(str(mode_label).strip().lower(), str(mode_label).strip().title())
    return [
        f"{title}",
        f"Modo: {mode_pretty} | Versión: {version}",
        "",
    ]


def build_position_analysis_text(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.extend(build_ui_header(summary.get("title", SCRIPT_TITLE), summary.get("version", SCRIPT_VERSION), summary.get("mode", "posicion")))
    lines.append(f"PAR: {summary['symbol']}")
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
        lines.append(f"  Recent high ({tf_data.get('recent_window')}): {normalize_number_str(tf_data['recent_high'], 8)}")
        lines.append(f"  Recent low ({tf_data.get('recent_window')}): {normalize_number_str(tf_data['recent_low'], 8)}")
        lines.append(f"  Absolute low ({tf_data.get('absolute_window')}): {normalize_number_str(tf_data.get('absolute_low'), 8)}")
        lines.append(f"  Last swing low: {normalize_number_str(tf_data.get('last_swing_low'), 8)}")
        if tf_data.get('swing_low_definition'):
            lines.append(f"  Swing low definition: {tf_data.get('swing_low_definition')}")
        lines.append(f"  ATR14: {normalize_number_str(tf_data.get('atr14'), 8)}")
        lines.append(f"  Last volume: {normalize_number_str(tf_data['last_volume'], 4)}")
        lines.append(f"  Dist vs MA7 (%): {normalize_number_str(tf_data['dist_pct_vs_ma7'], 4)}")
        lines.append(f"  Dist vs MA25 (%): {normalize_number_str(tf_data['dist_pct_vs_ma25'], 4)}")
        lines.append(f"  Dist vs MA99 (%): {normalize_number_str(tf_data['dist_pct_vs_ma99'], 4)}")
        lines.append(f"  MA7 slope 5 velas (%): {normalize_number_str(tf_data.get('ma7_slope_pct_5'), 4)}")
        if tf_data.get('support_zone'):
            lines.append(f"  Support zone: {tf_data.get('support_zone')}")
        lines.append("")

    suggestion = summary.get("suggested_limit_buy_info", {})
    if suggestion:
        lines.append("SOPORTES / COMPRA MECÁNICA:")
        lines.append(f"  suggested_limit_buy: {suggestion.get('suggested_limit_buy')}")
        lines.append(f"  reference: {suggestion.get('reference')}")
        lines.append(f"  second_support: {suggestion.get('second_support')}")
        lines.append(f"  support_zone: {suggestion.get('support_zone')}")
        lines.append(f"  entries: {suggestion.get('entries')}")
        lines.append(f"  distance_pct_from_last: {suggestion.get('distance_pct_from_last')}")
        if suggestion.get('setup_status'):
            lines.append(f"  setup_status: {suggestion.get('setup_status')}")
        lines.append(f"  note: {suggestion.get('note')}")
        lines.append("")

    invalidation = summary.get("invalidation_info", {})
    if invalidation:
        lines.append("INVALIDACIÓN MECÁNICA:")
        lines.append(f"  trigger_candidate_operativo: {invalidation.get('trigger_candidate_operativo')}")
        lines.append(f"  stop_candidate_operativo: {invalidation.get('stop_candidate_operativo')}")
        lines.append(f"  risk_pct_from_entry_operativo: {invalidation.get('risk_pct_from_entry_operativo')}")
        lines.append(f"  trigger_candidate_estructural: {invalidation.get('trigger_candidate_estructural')}")
        lines.append(f"  stop_candidate_estructural: {invalidation.get('stop_candidate_estructural')}")
        lines.append(f"  risk_pct_from_entry_estructural: {invalidation.get('risk_pct_from_entry_estructural')}")
        lines.append(f"  reason: {invalidation.get('reason')}")
        refs = invalidation.get("reference_levels") or []
        if refs:
            lines.append(f"  reference_levels: {refs}")
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
    lines.extend(build_ui_header(payload.get("title", SCRIPT_TITLE), payload.get("version", SCRIPT_VERSION), payload.get("mode", "mercado")))
    lines.append(f"GENERADO UTC: {payload['generated_at_utc']}")
    lines.append(f"PARES: {', '.join(payload['symbols'])}")
    lines.append(f"CAPITAL_REFERENCIA_USDT: {payload.get('capital_quote_reference')}")
    lines.append("")

    visible_ranking = payload.get("ranking") or []
    expanded_ranking = payload.get("watchlist_expanded") or []
    lines.append("COMPRA REAL (lista única ordenada por calidad):")
    if not visible_ranking:
        lines.append(f"  No hay oportunidades visibles que pasen los filtros duros v{payload.get('version')} en este corte.")
        lines.append("  Esto no es un error por sí mismo: significa que el mercado actual no ofrece setups suficientemente limpios según las reglas vigentes.")
        lines.append("")
    for idx, item in enumerate(visible_ranking, start=1):
        lines.append(
            f"{idx}. {item['symbol']} | estado_visible={item.get('visible_state')} | calidad={item.get('quality_grade')} | score={item['score']} ({item.get('score_bucket')}) | raw={item.get('score_raw')} | trend={item.get('trend_score')} | tradeability={item.get('tradeability_score')} | estado_setup={((item.get('setup_status') or {}).get('state'))} | precio={item['last_price']} | compra_limite={item['suggested_limit_buy']} | ref={item['limit_reference']}"
        )
        lines.append(
            f"   - distancia_vs_precio_actual: {item['distance_pct_from_last']}% | dist_4h_vs_ma99: {item['dist_4h_vs_ma99']}% | spread: {item['spread_pct']}%"
        )
        if item.get("extension_risk"):
            lines.append(f"   - extension_risk: {item['extension_risk']}")
        if item.get("pullback_quality"):
            lines.append(f"   - pullback_quality: {item['pullback_quality']}")
        if item.get("support_quality"):
            lines.append(f"   - support_quality: {item['support_quality']}")
        if item.get("zone_integrity"):
            lines.append(f"   - zone_integrity: {item['zone_integrity']}")
        if item.get("support_zone"):
            lines.append(f"   - zona_soporte: {item['support_zone']}")
        if item.get("entries"):
            lines.append(f"   - entradas: {item['entries']}")
        if item.get("second_support"):
            lines.append(f"   - segundo_soporte: {item['second_support']}")
        if item.get("nearest_resistance_micro") or item.get("nearest_resistance_operativa") or item.get("rr_operativa_preliminar"):
            lines.append(f"   - resistencia_micro: {item.get('nearest_resistance_micro')} | resistencia_operativa: {item.get('nearest_resistance_operativa')} | distancia_resistencia_pct: {item.get('distance_to_resistance_pct')} | reward_pct: {item.get('reward_pct_to_resistance')} | rr_operativa_preliminar: {item.get('rr_operativa_preliminar')} | rr_estructural_preliminar: {item.get('rr_estructural_preliminar')} | metodo: {item.get('resistance_method')}")
        if item.get("invalidation_snapshot"):
            lines.append(f"   - invalidacion: {item['invalidation_snapshot']}")
        if item.get("tp_tactico") or item.get("stop_tactico"):
            lines.append(f"   - plan_tactico: tp={item.get('tp_tactico')} ({item.get('tp_reference')}) | stop={item.get('stop_tactico')} ({item.get('stop_reference')}) | rr_tactico={item.get('rr_tactico_estimado')} | quality_v4={item.get('quality_score_v4')}")
        if item.get('score_breakdown'):
            lines.append(f"   - breakdown: {item['score_breakdown']}")
        if item.get('why_ranked_here'):
            lines.append(f"   - resumen: {item['why_ranked_here']}")
        for reason in item["reasons"]:
            lines.append(f"   - {reason}")
        lines.append("")

    lines.append("")
    lines.append("VIGILANCIA AMPLIADA (informativa, no ejecutable):")
    if not expanded_ranking:
        lines.append("  No hay activos en vigilancia ampliada para este corte.")
    else:
        for idx, item in enumerate(expanded_ranking, start=1):
            lines.append(
                f"{idx}. {item['symbol']} | estado_visible=Vigilancia | calidad={item.get('quality_grade')} | score={item['score']} ({item.get('score_bucket')}) | setup={((item.get('setup_status') or {}).get('state'))} | precio={item['last_price']} | compra_limite={item['suggested_limit_buy']} | ref={item['limit_reference']}"
            )
            lines.append(
                f"   - motivos_no_ejecutable: {', '.join(item.get('hard_filter_reasons') or [])}"
            )
            lines.append(
                f"   - tp_tactico={item.get('tp_tactico')} | stop_tactico={item.get('stop_tactico')} | rr_tactico={item.get('rr_tactico_estimado')}"
            )
    lines.append("")
    lines.append("NOTA:")
    lines.append("  La lista de compra real ya excluye activos que fallan filtros duros de la versión actual. La vigilancia ampliada es informativa y no implica compra automática. rr_operativa_preliminar y rr_estructural_preliminar siguen siendo referencias iniciales, no un R:R definitivo.")
    return "\n".join(lines)




# =========================
# v4.0 - filtros duros / calidad / estados visibles
# =========================

def safe_decimal_str_to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(str(value))
    except Exception:
        return None


def build_tactical_plan(
    public_data: Dict[str, Any],
    entry_price: Optional[float],
    resistance_snapshot: Dict[str, Any],
    invalidation: Dict[str, Any],
) -> Dict[str, Any]:
    tick_size = (((public_data.get("symbol_info") or {}).get("rules_short") or {}).get("tickSize"))
    if entry_price is None or entry_price <= EPS:
        return {
            "tp_tactico": None,
            "stop_tactico": None,
            "rr_tactico_estimado": None,
            "tp_reference": None,
            "stop_reference": None,
        }

    t15 = public_data["timeframes"]["15m"]
    t1 = public_data["timeframes"]["1h"]
    t4 = public_data["timeframes"]["4h"]
    support_zone = ((public_data.get("suggested_limit_buy_info") or {}).get("support_zone") or {})

    tp_candidates = [
        ("resistencia_operativa", safe_float(((resistance_snapshot.get("nearest_resistance_operativa") or {}).get("value")))),
        ("resistencia_micro", safe_float(((resistance_snapshot.get("nearest_resistance_micro") or {}).get("value")))),
        ("15m_last_swing_high", safe_float(t15.get("last_swing_high"))),
        ("1h_recent_high", safe_float(t1.get("recent_high"))),
    ]
    primary_stop_candidates = [
        ("1h_recent_low", safe_float(t1.get("recent_low"))),
        ("1h_last_swing_low", safe_float(t1.get("last_swing_low"))),
        ("4h_recent_low", safe_float(t4.get("recent_low"))),
        ("4h_ma99", safe_float(t4.get("ma99"))),
        ("support_zone_low", safe_float(support_zone.get("low"))),
    ]
    fallback_stop_candidates = [
        ("support_zone_low", safe_float(support_zone.get("low"))),
        ("4h_recent_low", safe_float(t4.get("recent_low"))),
        ("4h_ma99", safe_float(t4.get("ma99"))),
        ("1h_recent_low", safe_float(t1.get("recent_low"))),
        ("1h_last_swing_low", safe_float(t1.get("last_swing_low"))),
    ]

    tp = None
    tp_name = None
    for name, val in tp_candidates:
        if val is not None and val > entry_price:
            tp = val
            tp_name = name
            break

    atr_1h = safe_float(t1.get("atr14")) or 0.0
    min_stop_pct = max(0.35, ((0.6 * atr_1h) / entry_price) * 100.0 if atr_1h > EPS else 0.35)
    primary_max_stop_pct = 3.2
    fallback_max_stop_pct = 4.2
    primary_buffer_abs = max(entry_price * 0.001, 0.20 * atr_1h) if atr_1h > EPS else (entry_price * 0.001)
    fallback_buffer_abs = max(entry_price * 0.0008, 0.10 * atr_1h) if atr_1h > EPS else (entry_price * 0.0008)

    def try_candidates(candidates, max_stop_pct: float, buffer_abs: float, label_prefix: str = ""):
        for name, level in candidates:
            if level is None or level >= entry_price:
                continue
            candidate_stop = level - buffer_abs
            if candidate_stop <= 0 or candidate_stop >= entry_price:
                continue
            stop_distance_pct = ((entry_price - candidate_stop) / entry_price) * 100.0
            if stop_distance_pct < min_stop_pct:
                continue
            if stop_distance_pct > max_stop_pct:
                continue
            rr_local = None
            if tp is not None and entry_price > candidate_stop and tp > entry_price:
                risk = entry_price - candidate_stop
                reward = tp - entry_price
                if risk > EPS:
                    rr_local = reward / risk
            return candidate_stop, f"{label_prefix}{name}", rr_local
        return None, None, None

    stop, stop_name, rr = try_candidates(primary_stop_candidates, primary_max_stop_pct, primary_buffer_abs)
    if stop is None:
        stop, stop_name, rr = try_candidates(fallback_stop_candidates, fallback_max_stop_pct, fallback_buffer_abs, "fallback:")

    return {
        "tp_tactico": format_price(tp, tick_size),
        "stop_tactico": format_price(stop, tick_size),
        "rr_tactico_estimado": format_pct(rr, 4) if rr is not None else None,
        "tp_reference": tp_name,
        "stop_reference": stop_name,
    }


def passes_hard_filters(candidate: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    setup_state = (((candidate.get("setup_status") or {}).get("state")) or "").lower()
    pullback_quality = (candidate.get("pullback_quality") or "").lower()
    distance_to_resistance = safe_decimal_str_to_float(candidate.get("distance_to_resistance_pct"))
    reward_pct = safe_decimal_str_to_float(candidate.get("reward_pct_to_resistance"))
    tp_tactico = candidate.get("tp_tactico")
    stop_tactico = candidate.get("stop_tactico")
    stop_reference = (candidate.get("stop_reference") or "")
    rr_tactico = safe_decimal_str_to_float(candidate.get("rr_tactico_estimado"))
    is_fallback = str(stop_reference).startswith("fallback:")

    if setup_state == "invalido":
        reasons.append("setup_status=invalido")
    if pullback_quality == "debil_sin_confirmacion":
        reasons.append("pullback_quality=debil_sin_confirmacion")
    if distance_to_resistance is None or distance_to_resistance < 0.25:
        reasons.append("resistencia_demasiado_cerca")
    if reward_pct is None or reward_pct < 1.80:
        reasons.append("reward_insuficiente")
    if not tp_tactico or not stop_tactico:
        reasons.append("sin_plan_tactico")
    elif rr_tactico is None:
        reasons.append("rr_tactico_insuficiente")
    else:
        rr_min = 0.90 if (setup_state == "degradado" and is_fallback) else 1.20
        if rr_tactico < rr_min:
            reasons.append("rr_tactico_insuficiente")
    return (len(reasons) == 0, reasons)


def compute_quality_v4(candidate: Dict[str, Any]) -> int:
    q = 0
    reward = safe_decimal_str_to_float(candidate.get("reward_pct_to_resistance"))
    pullback_quality = (candidate.get("pullback_quality") or "").lower()
    ext_state = (((candidate.get("extension_risk") or {}).get("state")) or "").lower()
    support_state = (((candidate.get("support_quality") or {}).get("state")) or "").lower()
    zone_state = (((candidate.get("zone_integrity") or {}).get("state")) or "").lower()
    setup_state = (((candidate.get("setup_status") or {}).get("state")) or "").lower()
    distance_to_res = safe_decimal_str_to_float(candidate.get("distance_to_resistance_pct"))
    rr_tactico = safe_decimal_str_to_float(candidate.get("rr_tactico_estimado"))

    if setup_state == "degradado":
        q -= 4

    if reward is not None:
        if reward >= 4.0:
            q += 2
        elif reward >= 2.5:
            q += 1

    if pullback_quality == "ordenado":
        q += 2
    elif pullback_quality == "brusco":
        q += 0
    elif pullback_quality == "shallow_not_ready":
        q -= 2

    if ext_state == "normal":
        q += 1
    elif ext_state == "compressed":
        q += 0
    elif ext_state == "extended":
        q -= 1
    elif ext_state == "overextended":
        q -= 2

    if support_state == "alta":
        q += 1
    elif support_state == "media":
        q += 0
    elif support_state == "baja":
        q -= 2

    if zone_state == "escalonada":
        q += 1
    elif zone_state == "forzada":
        q -= 1
    elif zone_state == "single_level_only":
        q -= 2

    if distance_to_res is not None:
        if distance_to_res < 0.60:
            q -= 2
        elif distance_to_res < 1.00:
            q -= 1

    if rr_tactico is not None:
        if rr_tactico >= 1.2:
            q += 1
        elif rr_tactico < 0.8:
            q -= 1

    return q


def visible_state_from_quality(quality_score_v4: int, candidate: Optional[Dict[str, Any]] = None) -> str:
    stop_reference = ((candidate or {}).get("stop_reference") or "")
    if str(stop_reference).startswith("fallback:"):
        return "Vigilancia"
    return "Ejecutable" if quality_score_v4 >= 3 else "Vigilancia"


def visible_grade_from_quality(base_score: int, quality_score_v4: int) -> str:
    total = base_score + quality_score_v4
    if total >= 22:
        return "A+"
    if total >= 18:
        return "A"
    if total >= 14:
        return "B+"
    if total >= 10:
        return "B"
    return "C"


def passes_expanded_watchlist(candidate: Dict[str, Any]) -> bool:
    setup_state = (((candidate.get("setup_status") or {}).get("state")) or "").lower()
    pullback_quality = (candidate.get("pullback_quality") or "").lower()
    reward_pct = safe_decimal_str_to_float(candidate.get("reward_pct_to_resistance"))
    quality = compute_quality_v4(candidate)
    if setup_state == "invalido":
        return False
    if pullback_quality == "debil_sin_confirmacion":
        return False
    if reward_pct is None or reward_pct < 1.0:
        return False
    return quality >= -2


def build_expanded_watchlist(ranking_sorted: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    expanded: List[Dict[str, Any]] = []
    for item in ranking_sorted:
        if item.get("passes_hard_filters"):
            continue
        if not passes_expanded_watchlist(item):
            continue
        clone = dict(item)
        quality = compute_quality_v4(clone)
        clone["quality_score_v4"] = quality
        clone["quality_grade"] = visible_grade_from_quality(clone.get("score") or 0, quality)
        clone["visible_state"] = "Vigilancia"
        expanded.append(clone)
    expanded = sorted(expanded, key=lambda x: (-(x.get("quality_score_v4") or -999), -(x.get("score") or -999)))
    return expanded[:limit]


# =========================
# Historial de rankings
# =========================

def save_ranking_history(ranking: List[Dict[str, Any]], symbols: List[str], capital: float, output_dir: Path) -> None:
    """Guarda un registro histórico del ranking en la carpeta Snapshots/Historial"""
    history_dir = output_dir.parent / "Historial"
    history_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_entry = {
        "timestamp": timestamp,
        "datetime_utc": now_utc_iso(),
        "symbols_analizados": symbols,
        "capital_referencia": capital,
        "top5": [
            {
                "symbol": r["symbol"],
                "score": r["score"],
                "score_raw": r.get("score_raw"),
                "score_bucket": r["score_bucket"],
                "setup_state": r.get("setup_status", {}).get("state"),
                "visible_state": r.get("visible_state"),
                "quality_grade": r.get("quality_grade"),
                "last_price": r["last_price"],
                "suggested_limit_buy": r["suggested_limit_buy"],
            }
            for r in ranking[:5]
        ],
        "full_ranking": [
            {
                "symbol": r["symbol"],
                "score": r["score"],
                "score_raw": r.get("score_raw"),
                "score_bucket": r["score_bucket"],
                "trend_score": r.get("trend_score"),
                "tradeability_score": r.get("tradeability_score"),
            }
            for r in ranking
        ]
    }
    
    history_file = history_dir / f"ranking_{timestamp}.json"
    write_json(history_file, history_entry)
    
    consolidated_file = history_dir / "rankings_history.json"
    all_rankings = []
    if consolidated_file.exists():
        try:
            with consolidated_file.open("r", encoding="utf-8") as f:
                all_rankings = json.load(f)
                if not isinstance(all_rankings, list):
                    all_rankings = []
        except Exception:
            all_rankings = []
    
    all_rankings.insert(0, history_entry)
    all_rankings = all_rankings[:30]
    write_json(consolidated_file, all_rankings)


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

    print_console_banner("Posición")
    print_progress_header(1)

    try:
        print_symbol_progress(1, 1, symbol, "descargando 15m / 1h / 4h y market data")
        public_data = fetch_public_market_data(symbol, args.limit)

        print_symbol_progress(1, 1, symbol, "calculando soportes y zonas de entrada")
        suggestion = suggest_limit_buy(public_data)

        print_symbol_progress(1, 1, symbol, "armando resumen y guardando archivos")
        
        summary: Dict[str, Any] = {
            "title": SCRIPT_TITLE,
            "mode": "posicion",
            "version": SCRIPT_VERSION,
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
        summary["invalidation_info"] = build_invalidation_levels(public_data, entry_price=args.manual_entry_price)

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

        estimated_entry_for_invalidation = safe_float(summary.get("position_snapshot", {}).get("entry_price")) or args.manual_entry_price
        summary["invalidation_info"] = build_invalidation_levels(public_data, entry_price=estimated_entry_for_invalidation)

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

        print_symbol_done(1, 1, symbol, "OK")

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

    except Exception as e:
        print_symbol_done(1, 1, symbol, "ERROR")
        print(f"Error procesando {symbol}: {e}", file=sys.stderr)
        return 1


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
    total_symbols = len(symbols)

    print_console_banner("Mercado")
    print_progress_header(total_symbols)

    for index, symbol in enumerate(symbols, start=1):
        quote_asset = args.quote_asset.upper().strip()
        assets = extract_assets(symbol, quote_asset)
        base_asset = assets["base_asset"]

        try:
            print_symbol_progress(index, total_symbols, symbol, "descargando 15m / 1h / 4h y market data")
            public_data = fetch_public_market_data(symbol, args.limit)

            print_symbol_progress(index, total_symbols, symbol, "calculando soportes y zonas de entrada")
            suggestion = suggest_limit_buy(public_data)

            print_symbol_progress(index, total_symbols, symbol, "armando resumen y guardando archivos")
            single_summary = {
                "title": SCRIPT_TITLE,
                "mode": "mercado",
                "version": SCRIPT_VERSION,
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

            print_symbol_progress(index, total_symbols, symbol, "evaluando ranking operativo")
            ranking.append(score_rebound_candidate(symbol, public_data, capital_quote=args.capital))
            print_symbol_done(index, total_symbols, symbol, "OK")

        except Exception as e:
            print_symbol_done(index, total_symbols, symbol, "ERROR")
            print(f"Error obteniendo datos públicos para {symbol}: {e}", file=sys.stderr)
            continue

    print("Generando archivos finales de oportunidades v4.1...", flush=True)
    
    ranking_sorted = sorted(ranking, key=lambda x: x["score"], reverse=True)
    
    # Filtrar solo vigentes si se solicitó antes de aplicar la visibilidad final
    if args.only_vigent:
        ranking_sorted = [r for r in ranking_sorted if r.get("setup_status", {}).get("state") == "vigente"]
        print(f"Filtro --only-vigent aplicado: {len(ranking_sorted)} activos con estado vigente", flush=True)

    visible_ranking = [r for r in ranking_sorted if r.get("passes_hard_filters")]
    visible_ranking = sorted(
        visible_ranking,
        key=lambda x: (
            x.get("visible_state") != "Ejecutable",
            -(x.get("quality_score_v4") or -999),
            -(x.get("score") or -999),
        ),
    )

    expanded_watchlist = build_expanded_watchlist(ranking_sorted, limit=5)

    payload = {
        "title": SCRIPT_TITLE,
        "mode": "mercado",
        "version": SCRIPT_VERSION,
        "generated_at_local": datetime.now().isoformat(),
        "generated_at_utc": now_utc_iso(),
        "capital_quote_reference": args.capital,
        "symbols": symbols,
        "ranking": visible_ranking,
        "watchlist_expanded": expanded_watchlist,
        "ranking_all": ranking_sorted,
        "visible_count": len(visible_ranking),
        "expanded_count": len(expanded_watchlist),
        "hidden_count": max(0, len(ranking_sorted) - len(visible_ranking)),
        "per_symbol_summary": symbol_summaries,
    }

    write_json(output_dir / "watchlist_summary.json", payload)
    write_text(output_dir / "watchlist_summary.txt", build_watchlist_text(payload))
    
    save_ranking_history(visible_ranking, symbols, args.capital, output_dir)

    print(render_progress_bar(total_symbols, total_symbols) + " | Análisis v4.1 finalizado", flush=True)
    print(f"OK. Análisis v4.1 generado en: {output_dir.resolve()}")
    print("- watchlist_summary.json")
    print("- watchlist_summary.txt")
    print("- archivos por símbolo: *_summary.json y *_klines_15m/1h/4h.csv")
    print("- Historial guardado en: Snapshots/Historial/")
    return 0


# =========================
# CLI
# =========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Binance Trading v4.1.2: modo posición (OCO) y modo mercado (watchlist ejecutable + vigilancia ampliada)."
    )

    subparsers = parser.add_subparsers(dest="mode", required=True)

    # ---- MODO POSICION ----
    p_pos = subparsers.add_parser(
        "posicion",
        help="Analiza una moneda ya comprada para contexto de OCO / gestión."
    )
    p_pos.add_argument("--par", "--symbol", dest="symbol", required=True, help="Ejemplo: XRPUSDT")
    p_pos.add_argument("--velas", "--limit", dest="limit", type=int, default=120, help="Velas por timeframe. Recomendado: 120 a 300")
    p_pos.add_argument("--salida", "--outdir", dest="outdir", default="Snapshots", help="Carpeta de salida")
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
        help="Analiza varios pares y devuelve una lista única de oportunidades v4.0."
    )
    p_mkt.add_argument("--pares", "--symbols", dest="symbols", nargs="+", required=True, help="Ejemplo: ETHUSDT SOLUSDT ADAUSDT XRPUSDT POLUSDT")
    p_mkt.add_argument("--velas", "--limit", dest="limit", type=int, default=120, help="Velas por timeframe. Recomendado: 120 a 300")
    p_mkt.add_argument("--salida", "--outdir", dest="outdir", default="Snapshots", help="Carpeta de salida")
    p_mkt.add_argument("--cotizacion", "--quote-asset", dest="quote_asset", default="USDT", help="Quote asset; por defecto USDT")
    p_mkt.add_argument("--capital", type=float, default=35.0, help="Capital de referencia en quote asset para evaluar liquidez relativa. Default: 35")
    p_mkt.add_argument("--only-vigent", dest="only_vigent", action="store_true", help="Filtra el ranking para mostrar solo activos con setup 'vigente'")
    p_mkt.set_defaults(func=run_market_mode)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
