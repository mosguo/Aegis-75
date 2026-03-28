from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from services.api_errors import error_response

from services.pair_registry_service import pair_registry_service
from services.pair_registry_updater import pair_registry_updater
from services.order_routing_service import order_routing_service
from services.wallet_service import wallet_service
from services.trading_pair_service import trading_pair_service
from services.arbitrage_candidate_service import arbitrage_candidate_service

router = APIRouter()


class TradingPairUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str = Field(min_length=1)
    spreadThreshold: float | None = None
    autoTrigger: bool | None = None
    executionMode: str | None = None


@router.get("/api/dashboard/wallet")
def get_dashboard_wallet() -> dict:
    try:
        return wallet_service.get_dashboard_wallet_summary("mosguo")
    except FileNotFoundError as e:
        return error_response(500, "wallet_file_missing", str(e))
    except ValueError as e:
        return error_response(500, "wallet_invalid", str(e))
    except Exception as e:
        return error_response(500, "wallet_unavailable", str(e))


@router.get("/api/dashboard/trading-pairs")
def get_dashboard_trading_pairs() -> dict:
    try:
        return {"pairs": trading_pair_service.list_pairs()}
    except FileNotFoundError as e:
        return error_response(500, "trading_pairs_file_missing", str(e))
    except ValueError as e:
        return error_response(500, "trading_pairs_invalid", str(e))
    except Exception as e:
        return error_response(500, "trading_pairs_unavailable", str(e))


@router.get("/api/dashboard/trading-pairs/{symbol}/quote")
def get_dashboard_trading_pair_quote(symbol: str) -> dict:
    try:
        return {"quote": trading_pair_service.get_pair_quote(symbol)}
    except ValueError as e:
        return error_response(404, "trading_pair_quote_not_found", str(e))
    except Exception as e:
        return error_response(500, "trading_pair_quote_unavailable", str(e))


@router.post("/api/dashboard/trading-pairs/{symbol}/watchlist")
def add_dashboard_trading_pair_watchlist(symbol: str) -> dict:
    try:
        result = trading_pair_service.add_to_watchlist(symbol)
        return {"ok": True, **result}
    except FileNotFoundError as e:
        return error_response(500, "trading_pairs_file_missing", str(e))
    except ValueError as e:
        return error_response(400, "trading_pair_watchlist_failed", str(e))
    except Exception as e:
        return error_response(500, "trading_pair_watchlist_unavailable", str(e))


@router.get("/api/dashboard/trading-pairs/reserve-summary")
def get_dashboard_trading_pair_reserve_summary() -> dict:
    try:
        return {"summary": trading_pair_service.get_reserve_summary()}
    except FileNotFoundError as e:
        return error_response(500, "trading_pairs_file_missing", str(e))
    except ValueError as e:
        return error_response(500, "trading_pairs_invalid", str(e))
    except Exception as e:
        return error_response(500, "trading_pair_reserve_summary_unavailable", str(e))


@router.get("/api/dashboard/arbitrage/candidates")
def get_dashboard_arbitrage_candidates(includeFees: bool = True, maxQuoteSkewMs: int = 100) -> dict:
    try:
        return {
            "result": arbitrage_candidate_service.evaluate_candidates(
                include_fees=includeFees,
                max_quote_skew_ms=maxQuoteSkewMs,
            )
        }
    except FileNotFoundError as e:
        return error_response(500, "trading_pairs_file_missing", str(e))
    except ValueError as e:
        return error_response(500, "arbitrage_candidates_invalid", str(e))
    except Exception as e:
        return error_response(500, "arbitrage_candidates_unavailable", str(e))


@router.get("/api/dashboard/pair-registry")
def get_dashboard_pair_registry() -> dict:
    try:
        return {"pairs": pair_registry_service.list_pairs()}
    except FileNotFoundError as e:
        return error_response(500, "pair_registry_file_missing", str(e))
    except ValueError as e:
        return error_response(500, "pair_registry_invalid", str(e))
    except Exception as e:
        return error_response(500, "pair_registry_unavailable", str(e))


@router.get("/api/dashboard/product-catalog/{venue}")
def get_dashboard_product_catalog(venue: str) -> dict:
    try:
        return {"venue": venue.strip().lower(), "products": pair_registry_service.list_venue_products(venue)}
    except Exception as e:
        return error_response(500, "product_catalog_unavailable", str(e))


@router.get("/api/dashboard/pair-registry/status")
def get_dashboard_pair_registry_status() -> dict:
    try:
        return pair_registry_service.get_sync_status()
    except Exception as e:
        return error_response(500, "pair_registry_status_unavailable", str(e))


@router.post("/api/dashboard/pair-registry/sync")
def sync_dashboard_pair_registry() -> dict:
    try:
        payload = pair_registry_updater.sync_once(force=True)
        return {"ok": True, "sync": payload}
    except Exception as e:
        return error_response(500, "pair_registry_sync_failed", str(e))


@router.get("/api/dashboard/pair-route/{symbol}")
def get_dashboard_pair_route(symbol: str, exchange: str | None = None) -> dict:
    try:
        return order_routing_service.resolve_order_route(symbol, exchange)
    except Exception as e:
        return error_response(500, "pair_route_unavailable", str(e))


@router.post("/api/dashboard/trading-pairs/update")
def update_dashboard_trading_pair(payload: TradingPairUpdateRequest) -> dict:
    try:
        pair = trading_pair_service.update_pair(
            symbol=payload.symbol,
            spread_threshold=payload.spreadThreshold,
            auto_trigger=payload.autoTrigger,
            execution_mode=payload.executionMode,
        )
        return {"ok": True, "pair": pair}
    except FileNotFoundError as e:
        return error_response(500, "trading_pairs_file_missing", str(e))
    except Exception as e:
        return error_response(400, "trading_pair_update_failed", str(e))
