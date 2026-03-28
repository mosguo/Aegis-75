from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
import os

from services.pair_registry_service import pair_registry_service

BASE_DIR = Path(__file__).resolve().parent.parent
TRADING_PAIR_FILE = BASE_DIR / "data" / "trading_pairs.json"
TZ_TAIPEI = timezone(timedelta(hours=8))
DEFAULT_RUST_API_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_FEE_BUFFER_RATE = 0.002
DEFAULT_SLIPPAGE_BUFFER_RATE = 0.003
DEFAULT_BASE_QTY_BUFFER_RATE = 0.01
DEFAULT_EXECUTION_SPREAD_MULTIPLIER = 1.2
DEFAULT_TRADE_NOTIONAL_USDT = 300.0
VENUE_MIN_SPREAD_PCT = {
    "binance": 0.1,
    "bybit": 0.06,
    "okx": 0.05,
    "coinbase": 0.6,
    "kraken": 0.26,
    "bitget": 0.1,
}
BYBIT_TICKERS_URL = "https://api.bybit.com/v5/market/tickers?category=spot"
BITGET_TICKERS_URL = "https://api.bitget.com/api/v2/spot/market/tickers"


class TradingPairService:
    def __init__(self, file_path: Path = TRADING_PAIR_FILE) -> None:
        self.file_path = file_path

    def _read(self) -> dict:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Trading pair file not found: {self.file_path}")
        with self.file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Trading pair payload must be a JSON object")
        pairs = data.get("pairs", [])
        if not isinstance(pairs, list):
            raise ValueError("Trading pair payload must contain a pairs array")
        return data

    def _write(self, payload: dict) -> None:
        backup = self.file_path.with_suffix(self.file_path.suffix + ".bak")
        if self.file_path.exists():
            backup.write_text(self.file_path.read_text(encoding="utf-8"), encoding="utf-8")
        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def list_pairs(self) -> list[dict]:
        data = self._read()
        pairs = data.get("pairs", [])
        watched_symbols = {
            str(pair.get("symbol", "")).strip().upper()
            for pair in pairs
            if str(pair.get("symbol", "")).strip()
        }
        live_pairs = self._fetch_live_pairs()
        auxiliary_quotes = self._fetch_auxiliary_quotes()
        if not live_pairs:
            return [
                self._apply_order_summary(
                    self._apply_watchlist_flag(self._apply_registry(dict(pair)), watched_symbols),
                    auxiliary_quotes,
                )
                for pair in pairs
            ]

        live_by_symbol = {pair.get("symbol"): pair for pair in live_pairs if pair.get("symbol")}
        merged_pairs: list[dict] = []

        for pair in pairs:
            symbol = pair.get("symbol")
            live_pair = live_by_symbol.get(symbol)
            if not live_pair:
                merged_pairs.append(
                    self._apply_order_summary(
                        self._apply_watchlist_flag(self._apply_registry(dict(pair)), watched_symbols),
                        auxiliary_quotes,
                    )
                )
                continue

            merged = self._apply_watchlist_flag(self._apply_registry(dict(pair)), watched_symbols)
            merged.update(
                {
                    "binancePrice": live_pair.get("binancePrice"),
                    "okxPrice": live_pair.get("okxPrice"),
                    "spreadAbs": live_pair.get("spreadAbs"),
                    "spreadPct": live_pair.get("spreadPct"),
                    "tradeNotionalUsdt": live_pair.get("tradeNotionalUsdt"),
                    "estimatedProfitUsdt": live_pair.get("estimatedProfitUsdt"),
                    "liveDecision": live_pair.get("liveDecision"),
                    "liveArbitrage": live_pair.get("liveArbitrage"),
                    "ageMs": live_pair.get("ageMs"),
                    "lastRefresh": live_pair.get("lastRefresh"),
                    "note": live_pair.get("note"),
                }
            )
            merged_pairs.append(self._apply_order_summary(merged, auxiliary_quotes))

        known_symbols = {pair.get("symbol") for pair in merged_pairs}
        for symbol, live_pair in live_by_symbol.items():
            if symbol in known_symbols:
                continue
            merged_pairs.append(
                self._apply_order_summary(
                    self._apply_watchlist_flag(
                        self._apply_registry(
                        {
                            "symbol": symbol,
                            "baseAsset": symbol.replace("USDT", ""),
                            "quoteAsset": "USDT" if symbol.endswith("USDT") else "",
                            "status": "ACTIVE",
                            "spreadThreshold": live_pair.get("threshold", 0.0),
                            "autoTrigger": False,
                            "executionMode": "SIMULATION",
                            "updatedAt": live_pair.get("lastRefresh"),
                            "binancePrice": live_pair.get("binancePrice"),
                            "okxPrice": live_pair.get("okxPrice"),
                            "spreadAbs": live_pair.get("spreadAbs"),
                            "spreadPct": live_pair.get("spreadPct"),
                            "tradeNotionalUsdt": live_pair.get("tradeNotionalUsdt"),
                            "estimatedProfitUsdt": live_pair.get("estimatedProfitUsdt"),
                            "liveDecision": live_pair.get("liveDecision"),
                            "liveArbitrage": live_pair.get("liveArbitrage"),
                            "ageMs": live_pair.get("ageMs"),
                            "lastRefresh": live_pair.get("lastRefresh"),
                            "note": live_pair.get("note"),
                        }
                    ),
                    watched_symbols,
                    ),
                    auxiliary_quotes,
                )
            )
            known_symbols.add(symbol)

        for registry_pair in pair_registry_service.list_pairs():
            symbol = registry_pair.get("dashboardSymbol")
            if not symbol or symbol in known_symbols:
                continue
            venue_symbol_map = registry_pair.get("venueSymbolMap", {})
            if not venue_symbol_map.get("binance") or not venue_symbol_map.get("okx"):
                continue
            if registry_pair.get("quoteAsset") != "USDT":
                continue

            merged_pairs.append(
                self._apply_order_summary(
                    self._apply_watchlist_flag(
                        self._apply_registry(
                        {
                            "symbol": symbol,
                            "baseAsset": registry_pair.get("baseAsset"),
                            "quoteAsset": registry_pair.get("quoteAsset"),
                            "status": "ACTIVE",
                            "spreadThreshold": 0.0,
                            "autoTrigger": False,
                            "executionMode": "SIMULATION",
                            "updatedAt": None,
                            "binancePrice": None,
                            "okxPrice": None,
                            "spreadAbs": None,
                            "spreadPct": None,
                            "tradeNotionalUsdt": DEFAULT_TRADE_NOTIONAL_USDT,
                            "estimatedProfitUsdt": 0.0,
                            "liveDecision": "NO_DATA",
                            "liveArbitrage": None,
                            "ageMs": None,
                            "lastRefresh": None,
                            "note": "registry-paired placeholder awaiting live quote",
                        }
                    ),
                    watched_symbols,
                    ),
                    auxiliary_quotes,
                )
            )
            known_symbols.add(symbol)

        return sorted(merged_pairs, key=self._pair_sort_key)

    def get_pair_quote(self, symbol: str) -> dict:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")

        for pair in self.list_pairs():
            if str(pair.get("symbol", "")).upper() == normalized:
                return {
                    "symbol": pair.get("symbol"),
                    "canonicalPair": pair.get("canonicalPair"),
                    "quoteStatus": pair.get("quoteStatus"),
                    "cexAName": pair.get("cexAName"),
                    "cexBName": pair.get("cexBName"),
                    "cexAPrice": pair.get("cexAPrice"),
                    "cexBPrice": pair.get("cexBPrice"),
                    "binancePrice": pair.get("binancePrice"),
                    "okxPrice": pair.get("okxPrice"),
                    "bybitPrice": pair.get("bybitPrice"),
                    "bitgetPrice": pair.get("bitgetPrice"),
                    "spreadAbs": pair.get("spreadAbs"),
                    "spreadPct": pair.get("spreadPct"),
                    "threshold": pair.get("spreadThreshold"),
                    "decision": pair.get("liveDecision"),
                    "effectiveDecision": pair.get("effectiveDecision"),
                    "arbitrage": pair.get("liveArbitrage"),
                    "effectiveArbitrage": pair.get("effectiveArbitrage"),
                    "tradeNotionalUsdt": pair.get("tradeNotionalUsdt"),
                    "estimatedProfitUsdt": pair.get("estimatedProfitUsdt"),
                    "minimumSpreadPct": pair.get("minimumSpreadPct"),
                    "executionSpreadPct": pair.get("executionSpreadPct"),
                    "gapToExecutePct": pair.get("gapToExecutePct"),
                    "feeCostUsdt": pair.get("feeCostUsdt"),
                    "reserveRequirement": pair.get("reserveRequirement"),
                    "ageMs": pair.get("ageMs"),
                    "lastRefresh": pair.get("lastRefresh"),
                    "registryStatus": pair.get("registryStatus"),
                    "supportedVenues": pair.get("supportedVenues"),
                    "venueSymbolMap": pair.get("venueSymbolMap"),
                }

        raise ValueError(f"Trading pair not found: {normalized}")

    def add_to_watchlist(self, symbol: str) -> dict:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")

        data = self._read()
        pairs = data.get("pairs", [])
        for pair in pairs:
            if str(pair.get("symbol", "")).strip().upper() == normalized:
                pair["updatedAt"] = datetime.now(TZ_TAIPEI).isoformat()
                self._write(data)
                return {"symbol": normalized, "added": False, "alreadyWatched": True}

        pair_seed = None
        for pair in self.list_pairs():
            if str(pair.get("symbol", "")).strip().upper() == normalized:
                pair_seed = pair
                break
        if pair_seed is None:
            raise ValueError(f"Trading pair not found: {normalized}")

        new_pair = {
            "symbol": normalized,
            "baseAsset": pair_seed.get("baseAsset") or normalized.replace("USDT", ""),
            "quoteAsset": pair_seed.get("quoteAsset") or ("USDT" if normalized.endswith("USDT") else ""),
            "status": "ACTIVE",
            "spreadThreshold": self._to_float(pair_seed.get("spreadThreshold")) or 0.0,
            "autoTrigger": bool(pair_seed.get("autoTrigger")),
            "executionMode": str(pair_seed.get("executionMode") or "SIMULATION").upper(),
            "updatedAt": datetime.now(TZ_TAIPEI).isoformat(),
        }
        pairs.append(new_pair)
        data["pairs"] = pairs
        self._write(data)
        return {"symbol": normalized, "added": True, "alreadyWatched": False}

    def get_reserve_summary(self) -> dict:
        pairs = self.list_pairs()
        actionable_pairs = []
        total_quote_by_exchange: dict[str, float] = {}
        total_base_by_exchange_asset: dict[str, float] = {}
        total_estimated_profit_usdt = 0.0

        for pair in pairs:
            if not pair.get("autoTrigger"):
                continue

            reserve = pair.get("reserveRequirement") or {}
            if not reserve.get("isActionable"):
                continue

            symbol = str(pair.get("symbol") or "-")
            buy_exchange = str(reserve.get("buyExchange") or "").lower()
            sell_exchange = str(reserve.get("sellExchange") or "").lower()
            quote_asset = str(reserve.get("requiredQuoteAsset") or "USDT").upper()
            base_asset = str(reserve.get("requiredBaseAsset") or "").upper()
            required_quote_amount = self._to_float(reserve.get("requiredQuoteAmount")) or 0.0
            required_base_amount = self._to_float(reserve.get("requiredBaseAmount")) or 0.0
            estimated_profit_usdt = self._to_float(pair.get("estimatedProfitUsdt")) or 0.0

            if buy_exchange:
                quote_key = f"{buy_exchange}:{quote_asset}"
                total_quote_by_exchange[quote_key] = total_quote_by_exchange.get(quote_key, 0.0) + required_quote_amount

            if sell_exchange and base_asset:
                base_key = f"{sell_exchange}:{base_asset}"
                total_base_by_exchange_asset[base_key] = total_base_by_exchange_asset.get(base_key, 0.0) + required_base_amount

            actionable_pairs.append(
                {
                    "symbol": symbol,
                    "effectiveDecision": pair.get("effectiveDecision"),
                    "buyExchange": buy_exchange or None,
                    "sellExchange": sell_exchange or None,
                    "requiredQuoteAsset": quote_asset,
                    "requiredQuoteAmount": round(required_quote_amount, 4),
                    "requiredBaseAsset": base_asset,
                    "requiredBaseAmount": round(required_base_amount, 8),
                    "estimatedProfitUsdt": round(estimated_profit_usdt, 4),
                }
            )
            total_estimated_profit_usdt += estimated_profit_usdt

        return {
            "activePairCount": len(actionable_pairs),
            "pairs": actionable_pairs,
            "quoteReserves": [
                {
                    "exchange": key.split(":", 1)[0],
                    "asset": key.split(":", 1)[1],
                    "amount": round(value, 4),
                    "label": f"{key.split(':', 1)[0].upper()} {key.split(':', 1)[1]} {value:.4f}",
                }
                for key, value in sorted(total_quote_by_exchange.items())
            ],
            "baseReserves": [
                {
                    "exchange": key.split(":", 1)[0],
                    "asset": key.split(":", 1)[1],
                    "amount": round(value, 8),
                    "label": f"{key.split(':', 1)[0].upper()} {key.split(':', 1)[1]} {value:.8f}",
                }
                for key, value in sorted(total_base_by_exchange_asset.items())
            ],
            "totalEstimatedProfitUsdt": round(total_estimated_profit_usdt, 4),
        }

    def update_pair(
        self,
        symbol: str,
        spread_threshold: float | None = None,
        auto_trigger: bool | None = None,
        execution_mode: str | None = None,
    ) -> dict:
        symbol = symbol.strip()
        if not symbol:
            raise ValueError("symbol is required")

        data = self._read()
        pairs = data.get("pairs", [])
        target = None
        for pair in pairs:
            if pair.get("symbol") == symbol:
                target = pair
                break

        if target is None:
            raise ValueError(f"Trading pair not found: {symbol}")

        if spread_threshold is not None:
            if not isinstance(spread_threshold, (int, float)):
                raise ValueError("spreadThreshold must be numeric")
            if spread_threshold < 0:
                raise ValueError("spreadThreshold must be >= 0")
            target["spreadThreshold"] = float(spread_threshold)

        if auto_trigger is not None:
            target["autoTrigger"] = auto_trigger

        if execution_mode is not None:
            normalized = execution_mode.upper()
            if normalized not in {"SIMULATION", "LIVE"}:
                raise ValueError("executionMode must be SIMULATION or LIVE")
            target["executionMode"] = normalized

        target["updatedAt"] = datetime.now(TZ_TAIPEI).isoformat()
        self._write(data)
        return self._apply_registry(target)

    def _apply_watchlist_flag(self, pair: dict, watched_symbols: set[str]) -> dict:
        symbol = str(pair.get("symbol", "")).strip().upper()
        pair["isLiveWatched"] = symbol in watched_symbols
        return pair

    def _fetch_live_pairs(self) -> list[dict]:
        base_url = os.getenv("AEGIS_RUST_API_BASE_URL", DEFAULT_RUST_API_BASE_URL).rstrip("/")
        summary_url = f"{base_url}/v1/dashboard/summary"

        try:
            with urlopen(summary_url, timeout=2.5) as response:
                payload = json.load(response)
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            return []

        pairs = payload.get("pairs", [])
        if not isinstance(pairs, list):
            return []

        return [self._normalize_live_pair(pair) for pair in pairs if isinstance(pair, dict)]

    def _normalize_live_pair(self, pair: dict) -> dict:
        return {
            "symbol": pair.get("symbol"),
            "binancePrice": pair.get("binance_price"),
            "okxPrice": pair.get("okx_price"),
            "spreadAbs": pair.get("spread_abs"),
            "spreadPct": pair.get("spread_pct"),
            "tradeNotionalUsdt": pair.get("trade_notional_usdt"),
            "estimatedProfitUsdt": pair.get("estimated_profit_usdt"),
            "threshold": pair.get("threshold"),
            "liveArbitrage": pair.get("arbitrage"),
            "liveDecision": pair.get("decision"),
            "ageMs": pair.get("age_ms"),
            "lastRefresh": pair.get("last_refresh_utc"),
            "note": pair.get("note"),
        }

    def _apply_order_summary(self, pair: dict, auxiliary_quotes: dict[str, dict[str, float]]) -> dict:
        threshold = self._to_float(pair.get("spreadThreshold"))
        trade_notional_usdt = self._to_float(pair.get("tradeNotionalUsdt")) or DEFAULT_TRADE_NOTIONAL_USDT
        estimated_profit_usdt = self._to_float(pair.get("estimatedProfitUsdt"))
        auto_trigger = bool(pair.get("autoTrigger"))
        status = str(pair.get("status", "")).upper()
        is_registry_tradable = bool(pair.get("isRegistryTradable"))
        live_decision = str(pair.get("liveDecision") or pair.get("decision") or "")
        live_arbitrage = pair.get("liveArbitrage", pair.get("arbitrage"))
        pair_quotes = self._merge_pair_quotes(pair, auxiliary_quotes)
        cex_a_name, cex_a_price, cex_b_name, cex_b_price = self._best_two_venues(pair_quotes)
        binance_price = self._to_float(pair_quotes.get("binance"))
        okx_price = self._to_float(pair_quotes.get("okx"))
        bybit_price = self._to_float(pair_quotes.get("bybit"))
        bitget_price = self._to_float(pair_quotes.get("bitget"))
        spread_abs = None
        spread_pct = None
        if cex_a_price is not None and cex_b_price is not None:
            spread_abs = max(0.0, cex_b_price - cex_a_price)
            if cex_a_price > 0:
                spread_pct = spread_abs / cex_a_price * 100.0
        minimum_spread_pct = self._combined_minimum_spread_pct(cex_a_name, cex_b_name)
        execution_spread_pct = minimum_spread_pct * DEFAULT_EXECUTION_SPREAD_MULTIPLIER
        fee_cost_usdt = trade_notional_usdt * (minimum_spread_pct / 100.0)

        entry_price = cex_a_price
        if estimated_profit_usdt is None:
            estimated_profit_usdt = self._estimate_profit_usdt(
                trade_notional_usdt=trade_notional_usdt,
                entry_price=entry_price,
                spread_abs=spread_abs,
                fee_cost_usdt=fee_cost_usdt,
            )

        effective_decision, effective_arbitrage = self._resolve_effective_signal(
            buy_price=cex_a_price,
            sell_price=cex_b_price,
            buy_exchange=cex_a_name,
            sell_exchange=cex_b_name,
            spread_abs=spread_abs,
            spread_pct=spread_pct,
            threshold=threshold,
            status=status,
            is_registry_tradable=is_registry_tradable,
            execution_spread_pct=execution_spread_pct,
            estimated_profit_usdt=estimated_profit_usdt,
        )

        pair["quoteStatus"] = self._quote_status(pair, binance_price, okx_price, bybit_price, bitget_price)
        pair["liveDecision"] = live_decision or None
        pair["liveArbitrage"] = live_arbitrage
        pair["effectiveDecision"] = effective_decision
        pair["effectiveArbitrage"] = effective_arbitrage
        pair["decisionSource"] = "python-local-threshold"
        pair["decision"] = effective_decision
        pair["arbitrage"] = effective_arbitrage
        pair["binancePrice"] = binance_price
        pair["okxPrice"] = okx_price
        pair["bybitPrice"] = bybit_price
        pair["bitgetPrice"] = bitget_price
        pair["cexAName"] = cex_a_name
        pair["cexBName"] = cex_b_name
        pair["cexAPrice"] = cex_a_price
        pair["cexBPrice"] = cex_b_price
        pair["spreadAbs"] = spread_abs
        pair["spreadPct"] = spread_pct
        pair["minimumSpreadPct"] = minimum_spread_pct
        pair["executionSpreadPct"] = execution_spread_pct
        pair["gapToExecutePct"] = max(0.0, execution_spread_pct - (spread_pct or 0.0))
        pair["feeCostUsdt"] = fee_cost_usdt
        triggered = (
            is_registry_tradable
            and effective_decision not in {"NO_DATA", "UNMAPPED", "DISCARDED", "INACTIVE"}
            and status == "ACTIVE"
            and auto_trigger
            and spread_abs is not None
            and spread_abs > 0
            and entry_price is not None
            and (estimated_profit_usdt or 0.0) > 0.0
        )

        pair["tradeNotionalUsdt"] = trade_notional_usdt
        pair["estimatedProfitUsdt"] = estimated_profit_usdt
        pair["reserveRequirement"] = self._build_reserve_requirement(
            pair=pair,
            trade_notional_usdt=trade_notional_usdt,
            entry_price=entry_price,
            effective_decision=effective_decision,
        )
        pair["openOrderCount"] = 1 if triggered else 0
        pair["openOrderNotionalUsdt"] = trade_notional_usdt if triggered else 0.0
        pair["openOrderQty"] = round(trade_notional_usdt / entry_price, 8) if triggered and entry_price else 0.0
        return pair

    def _apply_registry(self, pair: dict) -> dict:
        return pair_registry_service.attach_to_pair(pair)

    def _to_float(self, value) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed

    def _estimate_profit_usdt(
        self,
        trade_notional_usdt: float,
        entry_price: float | None,
        spread_abs: float | None,
        fee_cost_usdt: float,
    ) -> float:
        if entry_price is None or entry_price <= 0:
            return 0.0
        if spread_abs is None:
            return 0.0
        gross_profit = 0.0
        if spread_abs > 0:
            gross_profit = (trade_notional_usdt / entry_price) * spread_abs
        return gross_profit - fee_cost_usdt

    def _pair_sort_key(self, pair: dict) -> tuple:
        has_live_quote = self._to_float(pair.get("binancePrice")) is not None and self._to_float(pair.get("okxPrice")) is not None
        spread_abs = self._to_float(pair.get("spreadAbs")) or 0.0
        decision = str(pair.get("decision") or "")
        is_no_data = decision == "NO_DATA"
        return (
            0 if has_live_quote else 1,
            0 if not is_no_data else 1,
            -spread_abs,
            str(pair.get("symbol") or ""),
        )

    def _resolve_effective_signal(
        self,
        *,
        buy_price: float | None,
        sell_price: float | None,
        buy_exchange: str | None,
        sell_exchange: str | None,
        spread_abs: float | None,
        spread_pct: float | None,
        threshold: float | None,
        status: str,
        is_registry_tradable: bool,
        execution_spread_pct: float,
        estimated_profit_usdt: float | None,
    ) -> tuple[str, bool | None]:
        if buy_price is None or sell_price is None or spread_abs is None:
            return ("NO_DATA", None)
        if not is_registry_tradable:
            return ("UNMAPPED", None)
        if status != "ACTIVE":
            return ("INACTIVE", False)

        if spread_abs <= 0:
            return ("NO_ACTION", False)
        if spread_pct is None or spread_pct < execution_spread_pct:
            return ("NO_ACTION", False)
        if estimated_profit_usdt is None or estimated_profit_usdt <= 0:
            return ("NO_ACTION", False)
        if not buy_exchange or not sell_exchange or buy_exchange == sell_exchange:
            return ("NO_ACTION", False)

        return (f"BUY_{buy_exchange.upper()}_SELL_{sell_exchange.upper()}", True)

    def _combined_minimum_spread_pct(self, cex_a_name: str, cex_b_name: str) -> float:
        return self._venue_minimum_spread_pct(cex_a_name) + self._venue_minimum_spread_pct(cex_b_name)

    def _venue_minimum_spread_pct(self, venue_name: str) -> float:
        return VENUE_MIN_SPREAD_PCT.get(str(venue_name or "").strip().lower(), 0.2)

    def _build_reserve_requirement(
        self,
        *,
        pair: dict,
        trade_notional_usdt: float,
        entry_price: float | None,
        effective_decision: str,
    ) -> dict:
        base_asset = str(pair.get("baseAsset") or "").upper() or str(pair.get("symbol") or "").replace("USDT", "")
        quote_asset = str(pair.get("quoteAsset") or "USDT").upper()
        quote_buffer_rate = DEFAULT_FEE_BUFFER_RATE + DEFAULT_SLIPPAGE_BUFFER_RATE
        required_quote_amount = round(trade_notional_usdt * (1 + quote_buffer_rate), 4)

        if entry_price is not None and entry_price > 0:
            base_amount = (trade_notional_usdt / entry_price) * (1 + DEFAULT_BASE_QTY_BUFFER_RATE)
            required_base_amount = round(base_amount, 8)
        else:
            required_base_amount = 0.0

        buy_exchange = None
        sell_exchange = None
        if effective_decision == "BUY_OKX_SELL_BINANCE":
            buy_exchange = "okx"
            sell_exchange = "binance"
        elif effective_decision == "BUY_BINANCE_SELL_OKX":
            buy_exchange = "binance"
            sell_exchange = "okx"
        elif effective_decision.startswith("BUY_") and "_SELL_" in effective_decision:
            buy_exchange, sell_exchange = self._parse_decision_route(effective_decision)

        is_actionable = effective_decision in {"BUY_OKX_SELL_BINANCE", "BUY_BINANCE_SELL_OKX"}
        if effective_decision.startswith("BUY_") and "_SELL_" in effective_decision:
            is_actionable = True

        return {
            "isActionable": is_actionable,
            "buyExchange": buy_exchange,
            "sellExchange": sell_exchange,
            "requiredQuoteAsset": quote_asset,
            "requiredQuoteAmount": required_quote_amount,
            "requiredBaseAsset": base_asset,
            "requiredBaseAmount": required_base_amount,
            "buyReserveLabel": f"{quote_asset} {required_quote_amount:.4f}",
            "sellReserveLabel": f"{base_asset} {required_base_amount:.8f}",
            "quoteBufferRate": quote_buffer_rate,
            "baseBufferRate": DEFAULT_BASE_QTY_BUFFER_RATE,
        }

    def _quote_status(
        self,
        pair: dict,
        binance_price: float | None,
        okx_price: float | None,
        bybit_price: float | None,
        bitget_price: float | None,
    ) -> str:
        age_ms = pair.get("ageMs")
        live_count = sum(1 for value in [binance_price, okx_price, bybit_price, bitget_price] if value is not None)
        if live_count >= 2:
            try:
                if age_ms is not None and int(age_ms) > 15_000:
                    return "STALE"
            except (TypeError, ValueError):
                pass
            return "LIVE"
        if pair.get("isRegistryTradable"):
            return "MAPPED"
        return "UNMAPPED"

    def _fetch_auxiliary_quotes(self) -> dict[str, dict[str, float]]:
        return {
            "bybit": self._fetch_bybit_quotes(),
            "bitget": self._fetch_bitget_quotes(),
        }

    def _fetch_bybit_quotes(self) -> dict[str, float]:
        try:
            with urlopen(BYBIT_TICKERS_URL, timeout=2.5) as response:
                payload = json.load(response)
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            return {}

        items = (((payload or {}).get("result") or {}).get("list") or [])
        quotes = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip().upper()
            last_price = self._to_float(item.get("lastPrice"))
            if symbol and last_price is not None:
                quotes[symbol] = last_price
        return quotes

    def _fetch_bitget_quotes(self) -> dict[str, float]:
        try:
            with urlopen(BITGET_TICKERS_URL, timeout=2.5) as response:
                payload = json.load(response)
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            return {}

        items = (payload or {}).get("data") or []
        quotes = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip().upper()
            last_price = self._to_float(item.get("lastPr"))
            if symbol and last_price is not None:
                quotes[symbol] = last_price
        return quotes

    def _merge_pair_quotes(self, pair: dict, auxiliary_quotes: dict[str, dict[str, float]]) -> dict[str, float]:
        quotes: dict[str, float] = {}
        symbol = str(pair.get("symbol") or "").strip().upper()

        for venue_name, pair_key in [("binance", "binancePrice"), ("okx", "okxPrice")]:
            value = self._to_float(pair.get(pair_key))
            if value is not None:
                quotes[venue_name] = value

        for venue_name in ["bybit", "bitget"]:
            venue_quotes = auxiliary_quotes.get(venue_name, {})
            value = self._to_float(venue_quotes.get(symbol))
            if value is not None:
                quotes[venue_name] = value

        return quotes

    def _best_two_venues(self, quotes: dict[str, float]) -> tuple[str | None, float | None, str | None, float | None]:
        valid_quotes = [(venue, price) for venue, price in quotes.items() if price is not None and price > 0]
        if len(valid_quotes) < 2:
            return ("binance", quotes.get("binance"), "okx", quotes.get("okx"))

        buy_exchange, buy_price = min(valid_quotes, key=lambda item: item[1])
        sell_exchange, sell_price = max(valid_quotes, key=lambda item: item[1])
        if buy_exchange == sell_exchange:
            return (buy_exchange, buy_price, None, None)
        return (buy_exchange, buy_price, sell_exchange, sell_price)

    def _parse_decision_route(self, decision: str) -> tuple[str | None, str | None]:
        normalized = str(decision or "").strip().upper()
        if not normalized.startswith("BUY_") or "_SELL_" not in normalized:
            return (None, None)
        buy_part, sell_part = normalized[4:].split("_SELL_", 1)
        return (buy_part.lower(), sell_part.lower())


trading_pair_service = TradingPairService()
