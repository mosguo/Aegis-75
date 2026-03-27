from __future__ import annotations

from services.exchange_executor import ExchangeExecutor, OrderRequest


class ArbitrageEngine:
    def __init__(self) -> None:
        self.executor = ExchangeExecutor()

    def evaluate_and_execute(self, pair: dict, price_a: float, price_b: float, quantity: float = 0.001) -> dict:
        spread = price_b - price_a
        threshold = float(pair.get("spreadThreshold", 0))
        auto_trigger = bool(pair.get("autoTrigger", False))
        execution_mode = pair.get("executionMode", "SIMULATION")

        result = {
            "symbol": pair.get("symbol"),
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

        if not auto_trigger:
            result["message"] = "Auto trigger disabled."
            return result

        if spread < threshold:
            result["message"] = "Spread below threshold."
            return result

        result["triggered"] = True
        buy_req = OrderRequest(symbol=pair["symbol"], side="BUY", quantity=quantity, order_type="MARKET")
        sell_req = OrderRequest(symbol=pair["symbol"], side="SELL", quantity=quantity, order_type="MARKET")

        result["buyResult"] = self.executor.execute(buy_req, execution_mode=execution_mode)
        result["sellResult"] = self.executor.execute(sell_req, execution_mode=execution_mode)
        result["message"] = "Arbitrage execution attempted."
        return result


arbitrage_engine = ArbitrageEngine()
