from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class OrderRequest:
    symbol: str
    side: str
    quantity: float
    price: float | None = None
    order_type: str = "MARKET"


class ExchangeExecutor:
    def __init__(self) -> None:
        self.live_enabled = os.getenv("AEGIS75_ENABLE_LIVE_TRADING", "false").lower() == "true"
        self.exchange_name = os.getenv("AEGIS75_EXCHANGE", "binance")
        self.api_key = os.getenv("AEGIS75_EXCHANGE_API_KEY", "")
        self.api_secret = os.getenv("AEGIS75_EXCHANGE_API_SECRET", "")

    def execute(self, request: OrderRequest, execution_mode: str = "SIMULATION") -> dict:
        mode = execution_mode.upper()
        if mode != "LIVE":
            return {
                "ok": True,
                "mode": "SIMULATION",
                "exchange": self.exchange_name,
                "message": "Simulated order accepted.",
                "order": request.__dict__,
            }

        if not self.live_enabled:
            return {
                "ok": False,
                "mode": "LIVE",
                "exchange": self.exchange_name,
                "message": "Live trading disabled by AEGIS75_ENABLE_LIVE_TRADING=false",
                "order": request.__dict__,
            }

        if not self.api_key or not self.api_secret:
            return {
                "ok": False,
                "mode": "LIVE",
                "exchange": self.exchange_name,
                "message": "Missing exchange API credentials.",
                "order": request.__dict__,
            }

        return self._submit_live_order(request)

    def _submit_live_order(self, request: OrderRequest) -> dict:
        return {
            "ok": True,
            "mode": "LIVE",
            "exchange": self.exchange_name,
            "message": "Live order submitted placeholder. Implement exchange API here.",
            "order": request.__dict__,
        }
