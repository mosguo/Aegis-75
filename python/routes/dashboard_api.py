from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.wallet_service import wallet_service
from services.trading_pair_service import trading_pair_service

router = APIRouter()


class TradingPairUpdateRequest(BaseModel):
    symbol: str
    spreadThreshold: float | None = None
    autoTrigger: bool | None = None
    executionMode: str | None = None


@router.get("/api/dashboard/wallet")
def get_dashboard_wallet() -> dict:
    try:
        return wallet_service.get_dashboard_wallet_summary("mosguo")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dashboard/trading-pairs")
def get_dashboard_trading_pairs() -> dict:
    try:
        return {"pairs": trading_pair_service.list_pairs()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
