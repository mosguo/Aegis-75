from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from urllib.error import URLError
from urllib.request import Request, urlopen

from services.pair_registry_service import pair_registry_service

BASE_DIR = Path(__file__).resolve().parent.parent
TRADING_PAIR_FILE = BASE_DIR / "data" / "trading_pairs.json"
TZ_TAIPEI = timezone(timedelta(hours=8))
DEFAULT_TRADE_NOTIONAL_USDT = 300.0
MAX_QUOTE_SKEW_MS = 100
SUPPORTED_VENUES = ("binance", "okx", "bybit", "bitget")
DEPTH_CACHE_TTL_MS = 30_000
DEFAULT_ASSUMED_EXECUTION_DELAY_MS = 120
DEFAULT_LATENCY_BPS_PER_100MS = 0.5
DEFAULT_MIN_NOTIONAL_USDT = 5.0
DEFAULT_LOT_SIZE_STEP = 0.000001
DEFAULT_PRICE_TICK_SIZE = 0.000001
VENUE_FEE_RATE = {
    "binance": 0.001,
    "bybit": 0.0006,
    "okx": 0.0005,
    "coinbase": 0.006,
    "kraken": 0.0026,
    "bitget": 0.001,
}
DROP_REASON_BUCKET = {
    "QUOTE_SKEW": "QUOTE_SKEW",
    "MAPPING_ERROR": "MAPPING_ERROR",
    "INSTRUMENT_MISMATCH": "MAPPING_ERROR",
    "RAW_SPREAD<=0": "RAW_SPREAD<=0",
    "PROFIT<=0": "PROFIT<=0",
    "PROFIT_AFTER_SLIPPAGE<=0": "PROFIT<=0",
    "PROFIT_AFTER_LATENCY<=0": "PROFIT<=0",
    "INSUFFICIENT_DEPTH": "MAPPING_ERROR",
    "BELOW_MIN_NOTIONAL": "MAPPING_ERROR",
    "LOT_SIZE_MISMATCH": "MAPPING_ERROR",
    "PRICE_TICK_MISMATCH": "MAPPING_ERROR",
}


class ArbitrageCandidateService:
    def __init__(self, file_path: Path = TRADING_PAIR_FILE) -> None:
        self.file_path = file_path
        self._depth_cache: dict[tuple[str, str], dict] = {}
        self._depth_cache_lock = Lock()

    def evaluate_candidates(
        self,
        *,
        include_fees: bool = True,
        notional_usdt: float = DEFAULT_TRADE_NOTIONAL_USDT,
        max_quote_skew_ms: int = MAX_QUOTE_SKEW_MS,
    ) -> dict:
        tracked_symbols = self._tracked_symbols()
        tracked_registry_entries = self._tracked_registry_entries(tracked_symbols)
        venue_depth = self._fetch_all_depth(tracked_registry_entries)
        evaluations: list[dict] = []
        drop_stats = {
            "QUOTE_SKEW": 0,
            "MAPPING_ERROR": 0,
            "RAW_SPREAD<=0": 0,
            "PROFIT<=0": 0,
        }

        for symbol in tracked_symbols:
            registry_entry = tracked_registry_entries.get(symbol)
            symbol_evaluations = self._evaluate_symbol(
                symbol=symbol,
                registry_entry=registry_entry,
                venue_depth=venue_depth,
                include_fees=include_fees,
                notional_usdt=notional_usdt,
                max_quote_skew_ms=max_quote_skew_ms,
            )
            for item in symbol_evaluations:
                reason = item.get("droppedReason")
                if reason:
                    bucket = DROP_REASON_BUCKET.get(reason)
                    if bucket:
                        drop_stats[bucket] = drop_stats.get(bucket, 0) + 1
                evaluations.append(item)

        candidates = [item for item in evaluations if item.get("candidate") is True]
        candidates.sort(
            key=lambda item: (
                -(self._to_float(item.get("profitAfterLatency")) or 0.0),
                -(self._to_float(item.get("profitAfterSlippage")) or 0.0),
                -(self._to_float(item.get("profitAfterFee")) or 0.0),
                str(item.get("symbol") or ""),
            )
        )
        best_by_symbol = self._best_route_by_symbol(evaluations)
        validation_report = self._build_validation_report(evaluations)

        total_routes = len(evaluations)
        drop_rates = {}
        if total_routes > 0:
            drop_rates = {
                key: round((value / total_routes) * 100.0, 2)
                for key, value in drop_stats.items()
            }

        return {
            "notionalUsdt": notional_usdt,
            "includeFees": include_fees,
            "maxQuoteSkewMs": max_quote_skew_ms,
            "evaluatedRouteCount": total_routes,
            "candidateCount": len(candidates),
            "candidates": candidates,
            "bestBySymbol": best_by_symbol,
            "validationReport": validation_report,
            "dropStats": drop_stats,
            "dropRatesPct": drop_rates,
            "debugEvaluations": evaluations,
            "depthCoverage": self._build_depth_coverage(venue_depth),
            "cacheStatus": self._depth_cache_status(),
            "evaluatedAt": datetime.now(TZ_TAIPEI).isoformat(),
            "note": (
                "candidate=true means raw spread, fee, slippage, latency, and executable constraints "
                "all remain valid for 300 usdt depth-based evaluation"
            ),
        }

    def _tracked_symbols(self) -> list[str]:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Trading pair file not found: {self.file_path}")
        with self.file_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        pairs = payload.get("pairs", [])
        if not isinstance(pairs, list):
            raise ValueError("Trading pair payload must contain a pairs array")
        return [
            str((pair or {}).get("symbol", "")).strip().upper()
            for pair in pairs
            if str((pair or {}).get("symbol", "")).strip()
        ]

    def _tracked_registry_entries(self, tracked_symbols: list[str]) -> dict[str, dict]:
        entries: dict[str, dict] = {}
        for symbol in tracked_symbols:
            entry = pair_registry_service.get_by_dashboard_symbol(symbol)
            if entry:
                entries[symbol] = entry
        return entries

    def _evaluate_symbol(
        self,
        *,
        symbol: str,
        registry_entry: dict | None,
        venue_depth: dict[str, dict[str, dict]],
        include_fees: bool,
        notional_usdt: float,
        max_quote_skew_ms: int,
    ) -> list[dict]:
        results: list[dict] = []
        if not registry_entry:
            for buy_venue in SUPPORTED_VENUES:
                for sell_venue in SUPPORTED_VENUES:
                    if buy_venue != sell_venue:
                        results.append(
                            self._empty_evaluation(
                                symbol=symbol,
                                buy_venue=buy_venue,
                                sell_venue=sell_venue,
                                dropped_reason="MAPPING_ERROR",
                            )
                        )
            return results

        for buy_venue in SUPPORTED_VENUES:
            for sell_venue in SUPPORTED_VENUES:
                if buy_venue != sell_venue:
                    results.append(
                        self._evaluate_route(
                            symbol=symbol,
                            registry_entry=registry_entry,
                            buy_venue=buy_venue,
                            sell_venue=sell_venue,
                            venue_depth=venue_depth,
                            include_fees=include_fees,
                            notional_usdt=notional_usdt,
                            max_quote_skew_ms=max_quote_skew_ms,
                        )
                    )
        return results

    def _evaluate_route(
        self,
        *,
        symbol: str,
        registry_entry: dict,
        buy_venue: str,
        sell_venue: str,
        venue_depth: dict[str, dict[str, dict]],
        include_fees: bool,
        notional_usdt: float,
        max_quote_skew_ms: int,
    ) -> dict:
        venue_symbol_map = dict(registry_entry.get("venueSymbolMap") or {})
        buy_symbol = str(venue_symbol_map.get(buy_venue) or "").strip().upper()
        sell_symbol = str(venue_symbol_map.get(sell_venue) or "").strip().upper()
        base_asset = str(registry_entry.get("baseAsset") or "").strip().upper()
        quote_asset = str(registry_entry.get("quoteAsset") or "").strip().upper()
        canonical_symbol = str(registry_entry.get("canonicalPair") or "").strip().upper()
        instrument_type = self._resolve_instrument_type(
            registry_entry=registry_entry,
            buy_venue=buy_venue,
            buy_symbol=buy_symbol,
            sell_venue=sell_venue,
            sell_symbol=sell_symbol,
        )

        if (
            not buy_symbol
            or not sell_symbol
            or not canonical_symbol
            or not base_asset
            or not quote_asset
            or instrument_type is None
        ):
            return self._empty_evaluation(
                symbol=symbol,
                buy_venue=buy_venue,
                sell_venue=sell_venue,
                dropped_reason="MAPPING_ERROR",
                canonical_symbol=canonical_symbol or None,
                base_asset=base_asset or None,
                quote_asset=quote_asset or None,
            )

        if instrument_type != "spot":
            return self._empty_evaluation(
                symbol=symbol,
                buy_venue=buy_venue,
                sell_venue=sell_venue,
                dropped_reason="INSTRUMENT_MISMATCH",
                canonical_symbol=canonical_symbol,
                base_asset=base_asset,
                quote_asset=quote_asset,
                instrument_type=instrument_type,
            )

        buy_depth = self._resolve_depth_snapshot(venue_depth.get(buy_venue) or {}, buy_symbol)
        sell_depth = self._resolve_depth_snapshot(venue_depth.get(sell_venue) or {}, sell_symbol)
        if not buy_depth or not sell_depth:
            return self._empty_evaluation(
                symbol=symbol,
                buy_venue=buy_venue,
                sell_venue=sell_venue,
                dropped_reason="MAPPING_ERROR",
                canonical_symbol=canonical_symbol,
                base_asset=base_asset,
                quote_asset=quote_asset,
                instrument_type=instrument_type,
            )

        return self._evaluate_depth_route(
            symbol=symbol,
            canonical_symbol=canonical_symbol,
            base_asset=base_asset,
            quote_asset=quote_asset,
            instrument_type=instrument_type,
            buy_venue=buy_venue,
            sell_venue=sell_venue,
            buy_symbol=buy_symbol,
            sell_symbol=sell_symbol,
            buy_depth=buy_depth,
            sell_depth=sell_depth,
            include_fees=include_fees,
            notional_usdt=notional_usdt,
            max_quote_skew_ms=max_quote_skew_ms,
        )

    def _evaluate_depth_route(
        self,
        *,
        symbol: str,
        canonical_symbol: str,
        base_asset: str,
        quote_asset: str,
        instrument_type: str,
        buy_venue: str,
        sell_venue: str,
        buy_symbol: str,
        sell_symbol: str,
        buy_depth: dict,
        sell_depth: dict,
        include_fees: bool,
        notional_usdt: float,
        max_quote_skew_ms: int,
    ) -> dict:
        ask_a = self._to_float(buy_depth.get("bestAsk"))
        bid_a = self._to_float(buy_depth.get("bestBid"))
        ask_b = self._to_float(sell_depth.get("bestAsk"))
        bid_b = self._to_float(sell_depth.get("bestBid"))
        ts_a = int(buy_depth.get("tsMs") or 0)
        ts_b = int(sell_depth.get("tsMs") or 0)
        now_ms = self._now_ms()
        quote_age_a_ms = max(0, now_ms - ts_a) if ts_a else None
        quote_age_b_ms = max(0, now_ms - ts_b) if ts_b else None
        quote_age_ms = max(quote_age_a_ms or 0, quote_age_b_ms or 0)
        time_skew_ms = abs(ts_a - ts_b)

        evaluation = self._empty_evaluation(
            symbol=symbol,
            buy_venue=buy_venue,
            sell_venue=sell_venue,
            dropped_reason="MAPPING_ERROR",
            canonical_symbol=canonical_symbol,
            base_asset=base_asset,
            quote_asset=quote_asset,
            instrument_type=instrument_type,
        )
        evaluation.update(
            {
                "buyVenueSymbol": buy_symbol,
                "sellVenueSymbol": sell_symbol,
                "bidA": bid_a,
                "askA": ask_a,
                "bidB": bid_b,
                "askB": ask_b,
                "tsA": ts_a,
                "tsB": ts_b,
                "timeSkewMs": time_skew_ms,
                "quoteAgeMs": quote_age_ms,
                "assumedExecutionDelayMs": DEFAULT_ASSUMED_EXECUTION_DELAY_MS,
            }
        )

        if ask_a is None or bid_b is None or ask_a <= 0 or bid_b <= 0:
            return evaluation
        if time_skew_ms > max_quote_skew_ms:
            evaluation["droppedReason"] = "QUOTE_SKEW"
            return evaluation

        buy_vwap_result = self._calculate_buy_vwap(asks=buy_depth.get("asks") or [], notional_usdt=notional_usdt)
        if buy_vwap_result is None:
            evaluation["depthInsufficient"] = True
            evaluation["droppedReason"] = "INSUFFICIENT_DEPTH"
            return evaluation

        sell_vwap_result = self._calculate_sell_vwap(
            bids=sell_depth.get("bids") or [],
            quantity=buy_vwap_result["quantity"],
        )
        if sell_vwap_result is None:
            evaluation["depthInsufficient"] = True
            evaluation["buyVwap"] = buy_vwap_result["vwap"]
            evaluation["executableQty"] = buy_vwap_result["quantity"]
            evaluation["consumedLevelsBuy"] = buy_vwap_result["consumedLevels"]
            evaluation["droppedReason"] = "INSUFFICIENT_DEPTH"
            return evaluation

        raw_spread = bid_b - ask_a
        raw_spread_pct = raw_spread / ask_a if ask_a > 0 else None
        executable_qty = buy_vwap_result["quantity"]
        rounded_qty = self._round_down(executable_qty, DEFAULT_LOT_SIZE_STEP)
        executable_notional_usdt = rounded_qty * buy_vwap_result["vwap"]
        sell_proceeds_rounded = rounded_qty * sell_vwap_result["vwap"]
        fee_cost = 0.0
        if include_fees:
            fee_cost = (notional_usdt * self._fee_rate(buy_venue)) + (notional_usdt * self._fee_rate(sell_venue))
        profit_after_fee = sell_proceeds_rounded - executable_notional_usdt - fee_cost
        buy_slippage_cost = max(0.0, (buy_vwap_result["vwap"] - ask_a) * rounded_qty)
        sell_slippage_cost = max(0.0, (bid_b - sell_vwap_result["vwap"]) * rounded_qty)
        slippage_cost = buy_slippage_cost + sell_slippage_cost
        slippage_pct = (slippage_cost / executable_notional_usdt) * 100.0 if executable_notional_usdt > 0 else None
        profit_after_slippage = profit_after_fee - slippage_cost
        latency_penalty_usdt = self._estimate_latency_penalty_usdt(
            executable_notional_usdt=executable_notional_usdt,
            quote_age_ms=quote_age_ms,
            assumed_execution_delay_ms=DEFAULT_ASSUMED_EXECUTION_DELAY_MS,
        )
        profit_after_latency = profit_after_slippage - latency_penalty_usdt

        evaluation.update(
            {
                "rawSpread": raw_spread,
                "rawSpreadPct": raw_spread_pct,
                "buyVwap": buy_vwap_result["vwap"],
                "sellVwap": sell_vwap_result["vwap"],
                "executableQty": executable_qty,
                "roundedQty": rounded_qty,
                "executableNotionalUsdt": executable_notional_usdt,
                "consumedLevelsBuy": buy_vwap_result["consumedLevels"],
                "consumedLevelsSell": sell_vwap_result["consumedLevels"],
                "feeCost": fee_cost,
                "slippageCost": slippage_cost,
                "slippagePct": slippage_pct,
                "profitAfterFee": profit_after_fee,
                "estimatedProfitAfterFee": profit_after_fee,
                "latencyPenaltyUsdt": latency_penalty_usdt,
                "profitAfterSlippage": profit_after_slippage,
                "profitAfterLatency": profit_after_latency,
                "minNotionalUsdt": DEFAULT_MIN_NOTIONAL_USDT,
                "qtyStep": DEFAULT_LOT_SIZE_STEP,
                "priceTick": DEFAULT_PRICE_TICK_SIZE,
            }
        )

        if raw_spread <= 0:
            evaluation["droppedReason"] = "RAW_SPREAD<=0"
            return evaluation
        evaluation["candidateRaw"] = True

        if rounded_qty <= 0 or abs(rounded_qty - executable_qty) > max(DEFAULT_LOT_SIZE_STEP * 1000, executable_qty * 0.2):
            evaluation["droppedReason"] = "LOT_SIZE_MISMATCH"
            return evaluation
        if not self._valid_price_tick(buy_vwap_result["vwap"], DEFAULT_PRICE_TICK_SIZE) or not self._valid_price_tick(
            sell_vwap_result["vwap"], DEFAULT_PRICE_TICK_SIZE
        ):
            evaluation["droppedReason"] = "PRICE_TICK_MISMATCH"
            return evaluation
        if executable_notional_usdt < DEFAULT_MIN_NOTIONAL_USDT:
            evaluation["droppedReason"] = "BELOW_MIN_NOTIONAL"
            return evaluation
        if profit_after_fee <= 0:
            evaluation["droppedReason"] = "PROFIT<=0"
            return evaluation
        evaluation["candidateAfterFee"] = True
        if profit_after_slippage <= 0:
            evaluation["droppedReason"] = "PROFIT_AFTER_SLIPPAGE<=0"
            return evaluation
        evaluation["candidateAfterSlippage"] = True
        if profit_after_latency <= 0:
            evaluation["droppedReason"] = "PROFIT_AFTER_LATENCY<=0"
            return evaluation
        evaluation["candidateAfterLatency"] = True
        evaluation["candidate"] = True
        evaluation["droppedReason"] = None
        return evaluation

    def _resolve_instrument_type(
        self,
        *,
        registry_entry: dict,
        buy_venue: str,
        buy_symbol: str,
        sell_venue: str,
        sell_symbol: str,
    ) -> str | None:
        buy_product = pair_registry_service.get_venue_product(buy_venue, buy_symbol)
        sell_product = pair_registry_service.get_venue_product(sell_venue, sell_symbol)
        buy_type = str((buy_product or {}).get("marketType") or "spot").strip().lower()
        sell_type = str((sell_product or {}).get("marketType") or "spot").strip().lower()
        if buy_type != sell_type:
            return None
        canonical_symbol = str(registry_entry.get("canonicalPair") or "").strip().upper()
        base_asset = str(registry_entry.get("baseAsset") or "").strip().upper()
        quote_asset = str(registry_entry.get("quoteAsset") or "").strip().upper()
        if buy_product:
            if str(buy_product.get("canonicalPair") or "").strip().upper() != canonical_symbol:
                return None
            if str(buy_product.get("baseAsset") or "").strip().upper() != base_asset:
                return None
            if str(buy_product.get("quoteAsset") or "").strip().upper() != quote_asset:
                return None
        if sell_product:
            if str(sell_product.get("canonicalPair") or "").strip().upper() != canonical_symbol:
                return None
            if str(sell_product.get("baseAsset") or "").strip().upper() != base_asset:
                return None
            if str(sell_product.get("quoteAsset") or "").strip().upper() != quote_asset:
                return None
        return buy_type

    def _fetch_all_depth(self, tracked_registry_entries: dict[str, dict]) -> dict[str, dict[str, dict]]:
        venue_depth = {venue: {} for venue in SUPPORTED_VENUES}
        lock = Lock()
        tasks: list[tuple[str, str]] = []

        for entry in tracked_registry_entries.values():
            venue_symbol_map = dict(entry.get("venueSymbolMap") or {})
            for venue in SUPPORTED_VENUES:
                venue_symbol = str(venue_symbol_map.get(venue) or "").strip().upper()
                if venue_symbol:
                    tasks.append((venue, venue_symbol))

        unique_tasks = sorted(set(tasks))
        if not unique_tasks:
            return venue_depth

        with ThreadPoolExecutor(max_workers=min(12, len(unique_tasks))) as executor:
            futures = [
                executor.submit(self._fetch_single_depth, venue, venue_symbol, lock, venue_depth)
                for venue, venue_symbol in unique_tasks
            ]
            for future in futures:
                future.result()

        return venue_depth

    def _fetch_single_depth(
        self,
        venue: str,
        venue_symbol: str,
        lock: Lock,
        venue_depth: dict[str, dict[str, dict]],
    ) -> None:
        snapshot = self._get_cached_depth_snapshot(venue, venue_symbol)
        if snapshot is None:
            try:
                if venue == "binance":
                    snapshot = self._fetch_binance_depth(venue_symbol)
                elif venue == "okx":
                    snapshot = self._fetch_okx_depth(venue_symbol)
                elif venue == "bybit":
                    snapshot = self._fetch_bybit_depth(venue_symbol)
                elif venue == "bitget":
                    snapshot = self._fetch_bitget_depth(venue_symbol)
            except Exception:
                snapshot = None
            if snapshot:
                self._set_cached_depth_snapshot(venue, venue_symbol, snapshot)

        if not snapshot:
            return

        with lock:
            venue_depth.setdefault(venue, {})[venue_symbol] = snapshot
            normalized_key = venue_symbol.replace("-", "").replace("_", "")
            venue_depth.setdefault(venue, {})[normalized_key] = snapshot

    def _get_cached_depth_snapshot(self, venue: str, venue_symbol: str) -> dict | None:
        normalized_symbol = venue_symbol.replace("-", "").replace("_", "").upper()
        now_ms = self._now_ms()
        with self._depth_cache_lock:
            cached = self._depth_cache.get((venue, normalized_symbol))
            if not cached:
                return None
            if now_ms - int(cached.get("cachedAtMs") or 0) > DEPTH_CACHE_TTL_MS:
                return None
            return dict(cached.get("snapshot") or {})

    def _set_cached_depth_snapshot(self, venue: str, venue_symbol: str, snapshot: dict) -> None:
        normalized_symbol = venue_symbol.replace("-", "").replace("_", "").upper()
        with self._depth_cache_lock:
            self._depth_cache[(venue, normalized_symbol)] = {
                "cachedAtMs": self._now_ms(),
                "snapshot": dict(snapshot),
            }

    def _fetch_binance_depth(self, venue_symbol: str) -> dict | None:
        payload = self._load_json(f"https://api.binance.com/api/v3/depth?symbol={venue_symbol}&limit=20")
        if not isinstance(payload, dict):
            return None
        received_at_ms = self._now_ms()
        return self._build_depth_snapshot(
            venue="binance",
            venue_symbol=venue_symbol,
            bids=payload.get("bids") or [],
            asks=payload.get("asks") or [],
            ts_ms=received_at_ms,
        )

    def _fetch_okx_depth(self, venue_symbol: str) -> dict | None:
        payload = self._load_json(f"https://www.okx.com/api/v5/market/books?instId={venue_symbol}&sz=20")
        items = ((payload or {}).get("data") or [])
        if not items:
            return None
        item = items[0]
        if not isinstance(item, dict):
            return None
        ts_ms = self._to_int(item.get("ts")) or self._now_ms()
        return self._build_depth_snapshot(
            venue="okx",
            venue_symbol=venue_symbol,
            bids=item.get("bids") or [],
            asks=item.get("asks") or [],
            ts_ms=ts_ms,
        )

    def _fetch_bybit_depth(self, venue_symbol: str) -> dict | None:
        payload = self._load_json(
            f"https://api.bybit.com/v5/market/orderbook?category=spot&symbol={venue_symbol}&limit=25"
        )
        result = ((payload or {}).get("result") or {})
        if not isinstance(result, dict):
            return None
        ts_ms = self._to_int((payload or {}).get("time")) or self._to_int(result.get("ts")) or self._now_ms()
        return self._build_depth_snapshot(
            venue="bybit",
            venue_symbol=venue_symbol,
            bids=result.get("b") or result.get("bids") or [],
            asks=result.get("a") or result.get("asks") or [],
            ts_ms=ts_ms,
        )

    def _fetch_bitget_depth(self, venue_symbol: str) -> dict | None:
        payload = self._load_json(
            f"https://api.bitget.com/api/v2/spot/market/orderbook?symbol={venue_symbol}&type=step0&limit=20"
        )
        item = (payload or {}).get("data")
        if not item:
            return None
        if isinstance(item, list):
            if not item:
                return None
            item = item[0]
        if not isinstance(item, dict):
            return None
        ts_ms = self._to_int(item.get("ts")) or self._now_ms()
        return self._build_depth_snapshot(
            venue="bitget",
            venue_symbol=venue_symbol,
            bids=item.get("bids") or [],
            asks=item.get("asks") or [],
            ts_ms=ts_ms,
        )

    def _build_depth_snapshot(
        self,
        *,
        venue: str,
        venue_symbol: str,
        bids,
        asks,
        ts_ms: int,
    ) -> dict | None:
        normalized_bids = self._normalize_levels(bids)
        normalized_asks = self._normalize_levels(asks)
        if not normalized_bids or not normalized_asks:
            return None
        return {
            "venue": venue,
            "symbol": venue_symbol,
            "bids": normalized_bids,
            "asks": normalized_asks,
            "bestBid": normalized_bids[0]["price"],
            "bestAsk": normalized_asks[0]["price"],
            "tsMs": ts_ms,
            "fetchedAtMs": self._now_ms(),
        }

    def _normalize_levels(self, levels) -> list[dict]:
        normalized: list[dict] = []
        for level in levels:
            price = None
            quantity = None
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                price = self._to_float(level[0])
                quantity = self._to_float(level[1])
            elif isinstance(level, dict):
                price = self._to_float(level.get("price"))
                quantity = self._to_float(level.get("qty") or level.get("quantity") or level.get("size"))
            if price is None or quantity is None or price <= 0 or quantity <= 0:
                continue
            normalized.append({"price": price, "qty": quantity})
        return normalized

    def _calculate_buy_vwap(self, *, asks: list[dict], notional_usdt: float) -> dict | None:
        remaining_notional = notional_usdt
        acquired_qty = 0.0
        spent_notional = 0.0
        consumed_levels = 0

        for level in asks:
            price = self._to_float(level.get("price"))
            qty = self._to_float(level.get("qty"))
            if price is None or qty is None or price <= 0 or qty <= 0:
                continue
            level_notional = price * qty
            take_notional = min(level_notional, remaining_notional)
            take_qty = take_notional / price
            acquired_qty += take_qty
            spent_notional += take_notional
            remaining_notional -= take_notional
            consumed_levels += 1
            if remaining_notional <= 1e-9:
                break

        if remaining_notional > 1e-6 or acquired_qty <= 0:
            return None

        return {
            "vwap": spent_notional / acquired_qty,
            "quantity": acquired_qty,
            "spentNotional": spent_notional,
            "consumedLevels": consumed_levels,
        }

    def _calculate_sell_vwap(self, *, bids: list[dict], quantity: float) -> dict | None:
        remaining_qty = quantity
        sold_qty = 0.0
        proceeds = 0.0
        consumed_levels = 0

        for level in bids:
            price = self._to_float(level.get("price"))
            qty = self._to_float(level.get("qty"))
            if price is None or qty is None or price <= 0 or qty <= 0:
                continue
            take_qty = min(qty, remaining_qty)
            proceeds += take_qty * price
            sold_qty += take_qty
            remaining_qty -= take_qty
            consumed_levels += 1
            if remaining_qty <= 1e-12:
                break

        if remaining_qty > 1e-9 or sold_qty <= 0:
            return None

        return {
            "vwap": proceeds / sold_qty,
            "quantity": sold_qty,
            "proceeds": proceeds,
            "consumedLevels": consumed_levels,
        }

    def _estimate_latency_penalty_usdt(
        self,
        *,
        executable_notional_usdt: float,
        quote_age_ms: int,
        assumed_execution_delay_ms: int,
    ) -> float:
        total_delay_ms = max(0, int(quote_age_ms or 0)) + max(0, int(assumed_execution_delay_ms or 0))
        penalty_bps = (total_delay_ms / 100.0) * DEFAULT_LATENCY_BPS_PER_100MS
        return executable_notional_usdt * (penalty_bps / 10_000.0)

    def _valid_price_tick(self, price: float, tick_size: float) -> bool:
        if price <= 0 or tick_size <= 0:
            return False
        steps = price / tick_size
        return abs(steps - round(steps)) < 1e-6 or tick_size <= 0.000001

    def _round_down(self, value: float, step: float) -> float:
        if value <= 0 or step <= 0:
            return 0.0
        return int(value / step) * step

    def _load_json(self, url: str):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "aegis-75/0.2",
                    "Accept": "application/json",
                },
            )
            with urlopen(request, timeout=2.0) as response:
                return json.load(response)
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            return {}

    def _fee_rate(self, venue: str) -> float:
        return VENUE_FEE_RATE.get(str(venue or "").strip().lower(), 0.001)

    def _best_route_by_symbol(self, evaluations: list[dict]) -> list[dict]:
        best_map: dict[str, dict] = {}
        for item in evaluations:
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            current = best_map.get(symbol)
            if current is None or self._is_better_route(item, current):
                best_map[symbol] = item

        best_routes = []
        for symbol in sorted(best_map):
            item = dict(best_map[symbol])
            item["displayDroppedReason"] = item.get("droppedReason") or ("CANDIDATE" if item.get("candidate") else "-")
            best_routes.append(item)
        return best_routes

    def _build_validation_report(self, evaluations: list[dict]) -> dict:
        total = len(evaluations)
        raw_count = sum(1 for item in evaluations if item.get("candidateRaw"))
        fee_count = sum(1 for item in evaluations if item.get("candidateAfterFee"))
        slippage_count = sum(1 for item in evaluations if item.get("candidateAfterSlippage"))
        latency_count = sum(1 for item in evaluations if item.get("candidateAfterLatency"))
        candidate_count = sum(1 for item in evaluations if item.get("candidate"))

        def pct(value: int) -> float:
            if total <= 0:
                return 0.0
            return round((value / total) * 100.0, 2)

        drop_reason_counts: dict[str, int] = {}
        for item in evaluations:
            reason = str(item.get("droppedReason") or "").strip() or "CANDIDATE"
            drop_reason_counts[reason] = drop_reason_counts.get(reason, 0) + 1

        top_drop_reasons = [
            {"reason": reason, "count": count, "ratePct": pct(count)}
            for reason, count in sorted(drop_reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

        skew_thresholds = [100, 300, 1000]
        skew_tiers = []
        for threshold in skew_thresholds:
            within = [
                item
                for item in evaluations
                if item.get("timeSkewMs") is not None and int(item.get("timeSkewMs") or 0) <= threshold
            ]
            within_count = len(within)
            skew_tiers.append(
                {
                    "thresholdMs": threshold,
                    "withinCount": within_count,
                    "withinRatePct": pct(within_count),
                    "rawPositiveCount": sum(1 for item in within if item.get("candidateRaw")),
                    "afterFeePositiveCount": sum(1 for item in within if item.get("candidateAfterFee")),
                    "afterSlippagePositiveCount": sum(1 for item in within if item.get("candidateAfterSlippage")),
                    "afterLatencyPositiveCount": sum(1 for item in within if item.get("candidateAfterLatency")),
                    "finalCandidateCount": sum(1 for item in within if item.get("candidate")),
                }
            )

        return {
            "totalRoutes": total,
            "stageCounts": {
                "rawPositive": raw_count,
                "afterFeePositive": fee_count,
                "afterSlippagePositive": slippage_count,
                "afterLatencyPositive": latency_count,
                "finalCandidates": candidate_count,
            },
            "stageRatesPct": {
                "rawPositive": pct(raw_count),
                "afterFeePositive": pct(fee_count),
                "afterSlippagePositive": pct(slippage_count),
                "afterLatencyPositive": pct(latency_count),
                "finalCandidates": pct(candidate_count),
            },
            "skewTiers": skew_tiers,
            "topDropReasons": top_drop_reasons,
        }

    def _is_better_route(self, candidate: dict, current: dict) -> bool:
        candidate_key = (
            1 if candidate.get("candidate") else 0,
            self._route_score(candidate),
            -self._drop_priority(candidate.get("droppedReason")),
        )
        current_key = (
            1 if current.get("candidate") else 0,
            self._route_score(current),
            -self._drop_priority(current.get("droppedReason")),
        )
        return candidate_key > current_key

    def _route_score(self, item: dict) -> float:
        for key in ["profitAfterLatency", "profitAfterSlippage", "profitAfterFee", "rawSpread"]:
            value = self._to_float(item.get(key))
            if value is not None:
                return value
        return float("-inf")

    def _drop_priority(self, reason: str | None) -> int:
        order = {
            None: 8,
            "PROFIT_AFTER_LATENCY<=0": 7,
            "PROFIT_AFTER_SLIPPAGE<=0": 6,
            "PROFIT<=0": 5,
            "RAW_SPREAD<=0": 4,
            "QUOTE_SKEW": 3,
            "INSUFFICIENT_DEPTH": 2,
            "BELOW_MIN_NOTIONAL": 1,
            "LOT_SIZE_MISMATCH": 1,
            "PRICE_TICK_MISMATCH": 1,
            "MAPPING_ERROR": 0,
            "INSTRUMENT_MISMATCH": 0,
        }
        return order.get(reason, 0)

    def _resolve_depth_snapshot(self, venue_quotes: dict[str, dict], venue_symbol: str) -> dict | None:
        normalized = str(venue_symbol or "").strip().upper()
        if not normalized:
            return None
        return (
            venue_quotes.get(normalized)
            or venue_quotes.get(normalized.replace("-", ""))
            or venue_quotes.get(normalized.replace("_", ""))
        )

    def _build_depth_coverage(self, venue_depth: dict[str, dict[str, dict]]) -> dict[str, int]:
        coverage: dict[str, int] = {}
        for venue, snapshots in venue_depth.items():
            seen_symbols: set[str] = set()
            for key, snapshot in snapshots.items():
                symbol = str((snapshot or {}).get("symbol") or key).strip().upper()
                if symbol:
                    seen_symbols.add(symbol)
            coverage[venue] = len(seen_symbols)
        return coverage

    def _depth_cache_status(self) -> dict:
        now_ms = self._now_ms()
        active_entries = 0
        oldest_age_ms = 0
        with self._depth_cache_lock:
            for cached in self._depth_cache.values():
                cached_at_ms = int(cached.get("cachedAtMs") or 0)
                age_ms = max(0, now_ms - cached_at_ms)
                if age_ms <= DEPTH_CACHE_TTL_MS:
                    active_entries += 1
                    oldest_age_ms = max(oldest_age_ms, age_ms)
        return {
            "ttlMs": DEPTH_CACHE_TTL_MS,
            "activeEntries": active_entries,
            "oldestActiveAgeMs": oldest_age_ms,
        }

    def _empty_evaluation(
        self,
        *,
        symbol: str,
        buy_venue: str,
        sell_venue: str,
        dropped_reason: str,
        canonical_symbol: str | None = None,
        base_asset: str | None = None,
        quote_asset: str | None = None,
        instrument_type: str | None = None,
    ) -> dict:
        return {
            "symbol": symbol,
            "canonicalSymbol": canonical_symbol,
            "baseAsset": base_asset,
            "quoteAsset": quote_asset,
            "instrumentType": instrument_type,
            "buyVenue": buy_venue,
            "sellVenue": sell_venue,
            "buyVenueSymbol": None,
            "sellVenueSymbol": None,
            "bidA": None,
            "askA": None,
            "bidB": None,
            "askB": None,
            "tsA": None,
            "tsB": None,
            "timeSkewMs": None,
            "quoteAgeMs": None,
            "assumedExecutionDelayMs": DEFAULT_ASSUMED_EXECUTION_DELAY_MS,
            "rawSpread": None,
            "rawSpreadPct": None,
            "buyVwap": None,
            "sellVwap": None,
            "executableQty": None,
            "roundedQty": None,
            "executableNotionalUsdt": None,
            "consumedLevelsBuy": 0,
            "consumedLevelsSell": 0,
            "depthInsufficient": False,
            "slippageCost": None,
            "slippagePct": None,
            "feeCost": None,
            "profitAfterFee": None,
            "estimatedProfitAfterFee": None,
            "latencyPenaltyUsdt": None,
            "profitAfterSlippage": None,
            "profitAfterLatency": None,
            "minNotionalUsdt": DEFAULT_MIN_NOTIONAL_USDT,
            "qtyStep": DEFAULT_LOT_SIZE_STEP,
            "priceTick": DEFAULT_PRICE_TICK_SIZE,
            "candidateRaw": False,
            "candidateAfterFee": False,
            "candidateAfterSlippage": False,
            "candidateAfterLatency": False,
            "candidate": False,
            "droppedReason": dropped_reason,
        }

    def _to_float(self, value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_int(self, value) -> int | None:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _now_ms(self) -> int:
        return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


arbitrage_candidate_service = ArbitrageCandidateService()
