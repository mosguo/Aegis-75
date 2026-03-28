from __future__ import annotations

from services.exchange_executor import ExchangeExecutor, OrderRequest
from services.order_routing_service import order_routing_service


class ArbitrageEngine:
    def __init__(self) -> None:
        self.executor = ExchangeExecutor()

    def evaluate_and_execute(self, pair: dict, price_a: float, price_b: float, quantity: float = 0.001) -> dict:
        resolved = order_routing_service.resolve_pair(pair.get("symbol", ""))
        spread = price_b - price_a
        threshold = float(pair.get("spreadThreshold", 0))
        auto_trigger = bool(pair.get("autoTrigger", False))
        execution_mode = pair.get("executionMode", "SIMULATION")
        buy_exchange = "binance" if price_a <= price_b else "okx"
        sell_exchange = "okx" if buy_exchange == "binance" else "binance"

        result = {
            "symbol": pair.get("symbol"),
            "canonicalPair": resolved.get("canonicalPair"),
            "mappingOk": resolved.get("ok", False),
            "mappingReason": resolved.get("reason"),
            "venueSymbolMap": resolved.get("venueSymbolMap"),
            "priceA": price_a,
            "priceB": price_b,
            "spread": spread,
            "threshold": threshold,
            "autoTrigger": auto_trigger,
            "executionMode": execution_mode,
            "triggered": False,
            "buyResult": None,
            "sellResult": None,
        }

        if not resolved.get("ok"):
            result["message"] = resolved.get("reason", "Pair mapping unavailable.")
            return result

        if not auto_trigger:
            result["message"] = "Auto trigger disabled."
            return result

        if spread < threshold:
            result["message"] = "Spread below threshold."
            return result

        result["triggered"] = True
        buy_req = OrderRequest(
            symbol=pair["symbol"],
            side="BUY",
            quantity=quantity,
            order_type="MARKET",
            exchange=buy_exchange,
        )
        sell_req = OrderRequest(
            symbol=pair["symbol"],
            side="SELL",
            quantity=quantity,
            order_type="MARKET",
            exchange=sell_exchange,
        )

        result["buyResult"] = self.executor.execute(buy_req, execution_mode=execution_mode)
        result["sellResult"] = self.executor.execute(sell_req, execution_mode=execution_mode)
        result["route"] = {
            "buyExchange": buy_exchange,
            "sellExchange": sell_exchange,
            "buyExchangeSymbol": resolved.get("venueSymbolMap", {}).get(buy_exchange),
            "sellExchangeSymbol": resolved.get("venueSymbolMap", {}).get(sell_exchange),
        }
        result["message"] = "Arbitrage execution attempted with registry-aware routing."
        return result


arbitrage_engine = ArbitrageEngine()
