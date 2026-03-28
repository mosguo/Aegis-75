from __future__ import annotations

from services.pair_registry_service import pair_registry_service


class OrderRoutingService:
    def resolve_pair(self, symbol: str) -> dict:
        entry = pair_registry_service.get_by_dashboard_symbol(symbol)
        if not entry:
            return {
                "ok": False,
                "symbol": symbol,
                "reason": "pair not found in registry",
                "route": None,
            }

        is_tradable = (
            entry.get("status") in {"ACTIVE", "DISCOVERED"}
            and bool(entry.get("venueSymbolMap", {}).get("binance"))
            and bool(entry.get("venueSymbolMap", {}).get("okx"))
        )

        return {
            "ok": is_tradable,
            "symbol": symbol,
            "canonicalPair": entry.get("canonicalPair"),
            "supportedVenues": entry.get("supportedVenues", []),
            "venueSymbolMap": entry.get("venueSymbolMap", {}),
            "registryStatus": entry.get("status"),
            "reason": None if is_tradable else "pair mapping incomplete; discarded for efficiency",
        }

    def resolve_order_route(self, symbol: str, preferred_exchange: str | None = None) -> dict:
        resolved = self.resolve_pair(symbol)
        if not resolved.get("ok"):
            return resolved

        venue_symbol_map = resolved["venueSymbolMap"]
        supported_venues = resolved["supportedVenues"]
        exchange = (preferred_exchange or "binance").strip().lower()
        if exchange not in supported_venues:
            exchange = supported_venues[0]

        return {
            **resolved,
            "exchange": exchange,
            "exchangeSymbol": venue_symbol_map.get(exchange),
        }


order_routing_service = OrderRoutingService()
