from __future__ import annotations

import os
from dataclasses import dataclass

from services.order_routing_service import order_routing_service


@dataclass
class OrderRequest:
    symbol: str
    side: str
    quantity: float
    price: float | None = None
    order_type: str = "MARKET"
    exchange: str | None = None
    exchange_symbol: str | None = None


class ExchangeExecutor:
    def __init__(self) -> None:
        self.live_enabled = os.getenv("AEGIS75_ENABLE_LIVE_TRADING", "false").lower() == "true"
        self.exchange_name = os.getenv("AEGIS75_EXCHANGE", "binance")
        self.api_key = os.getenv("AEGIS75_EXCHANGE_API_KEY", "")
        self.api_secret = os.getenv("AEGIS75_EXCHANGE_API_SECRET", "")

    def execute(self, request: OrderRequest, execution_mode: str = "SIMULATION") -> dict:
        mode = execution_mode.upper()
        route = order_routing_service.resolve_order_route(request.symbol, request.exchange or self.exchange_name)
        if not route.get("ok"):
            return {
                "ok": False,
                "mode": mode,
                "exchange": request.exchange or self.exchange_name,
                "message": route.get("reason", "Pair mapping unavailable."),
                "order": request.__dict__,
                "route": route,
            }

        request.exchange = route.get("exchange")
        request.exchange_symbol = route.get("exchangeSymbol")
        if mode != "LIVE":
            return {
                "ok": True,
                "mode": "SIMULATION",
                "exchange": request.exchange,
                "message": "Simulated order accepted.",
                "order": request.__dict__,
                "route": route,
            }

        if not self.live_enabled:
            return {
                "ok": False,
                "mode": "LIVE",
                "exchange": request.exchange,
                "message": "Live trading disabled by AEGIS75_ENABLE_LIVE_TRADING=false",
                "order": request.__dict__,
                "route": route,
            }

        if not self.api_key or not self.api_secret:
            return {
                "ok": False,
                "mode": "LIVE",
                "exchange": request.exchange,
                "message": "Missing exchange API credentials.",
                "order": request.__dict__,
                "route": route,
            }

        return self._submit_live_order(request)

    def _submit_live_order(self, request: OrderRequest) -> dict:
        return {
            "ok": False,
            "mode": "LIVE",
            "exchange": request.exchange or self.exchange_name,
            "message": "Live order placeholder only. Real exchange submission is not implemented in Level 3.",
            "order": request.__dict__,
        }
