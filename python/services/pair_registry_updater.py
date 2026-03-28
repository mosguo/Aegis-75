from __future__ import annotations

import asyncio
import json
import os
from urllib.request import Request, urlopen

from services.pair_registry_service import pair_registry_service

DEFAULT_REGISTRY_UPDATE_INTERVAL_SECONDS = 6 * 60 * 60

VENUE_CONFIG = {
    "binance": {
        "url": "https://api.binance.com/api/v3/exchangeInfo",
        "label": "Binance",
    },
    "coinbase": {
        "url": "https://api.exchange.coinbase.com/products",
        "label": "Coinbase",
    },
    "okx": {
        "url": "https://www.okx.com/api/v5/public/instruments?instType=SPOT",
        "label": "OKX",
    },
    "bybit": {
        "url": "https://api.bybit.com/v5/market/instruments-info?category=spot&limit=1000",
        "label": "Bybit",
    },
    "kraken": {
        "url": "https://api.kraken.com/0/public/AssetPairs",
        "label": "Kraken",
    },
    "bitget": {
        "url": "https://api.bitget.com/api/v2/spot/public/symbols",
        "label": "Bitget",
    },
}


class PairRegistryUpdater:
    def __init__(self, *, interval_seconds: int = DEFAULT_REGISTRY_UPDATE_INTERVAL_SECONDS) -> None:
        self.interval_seconds = interval_seconds

    def enabled(self) -> bool:
        value = os.getenv("AEGIS_PAIR_REGISTRY_UPDATER_ENABLED", "true").strip().lower()
        return value not in {"0", "false", "off", "no"}

    def should_refresh(self) -> bool:
        return pair_registry_service.should_refresh(self.interval_seconds)

    def sync_once(self, force: bool = False) -> dict:
        if not self.enabled():
            return pair_registry_service.mark_runtime_sync_failed(
                source="multi-venue.catalog",
                note="pair registry updater disabled",
                interval_seconds=self.interval_seconds,
            )

        if not force and not self.should_refresh():
            return {"ok": True, "skipped": True, "status": pair_registry_service.get_sync_status()}

        products_by_venue: dict[str, list[dict]] = {}
        venue_status: dict[str, dict] = {}
        merged_pairs: dict[str, dict] = {}
        total_products = 0

        for venue, config in VENUE_CONFIG.items():
            try:
                products = self._fetch_venue_products(venue, config["url"])
                products_by_venue[venue] = products
                venue_status[venue] = {
                    "status": "ok",
                    "productCount": len(products),
                    "label": config["label"],
                }
                total_products += len(products)
                for product in products:
                    self._merge_product_into_pairs(merged_pairs, venue, product)
            except Exception as exc:
                products_by_venue[venue] = []
                venue_status[venue] = {
                    "status": "degraded",
                    "productCount": 0,
                    "label": config["label"],
                    "note": str(exc),
                }

        final_pairs = sorted(merged_pairs.values(), key=lambda item: item["dashboardSymbol"])
        overall_status = "ok" if any(v.get("status") == "ok" for v in venue_status.values()) else "degraded"
        return pair_registry_service.upsert_runtime_pairs(
            final_pairs,
            products_by_venue=products_by_venue,
            venue_status=venue_status,
            source="multi-venue.catalog",
            note=f"synced {len(final_pairs)} canonical pairs from {total_products} products across 6 venues",
            interval_seconds=self.interval_seconds,
            status=overall_status,
        )

    async def run_periodic_sync(self, stop_event: asyncio.Event) -> None:
        if not self.enabled():
            return

        while not stop_event.is_set():
            await asyncio.to_thread(self.sync_once)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

    def _fetch_venue_products(self, venue: str, url: str) -> list[dict]:
        request = Request(
            url,
            headers={
                "User-Agent": "Aegis-75/1.0 product-registry-sync",
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)

        if venue == "binance":
            return self._parse_binance_products(payload)
        if venue == "coinbase":
            return self._parse_coinbase_products(payload)
        if venue == "okx":
            return self._parse_okx_products(payload)
        if venue == "bybit":
            return self._parse_bybit_products(payload)
        if venue == "kraken":
            return self._parse_kraken_products(payload)
        if venue == "bitget":
            return self._parse_bitget_products(payload)
        raise ValueError(f"Unsupported venue: {venue}")

    def _parse_binance_products(self, payload: dict) -> list[dict]:
        symbols = payload.get("symbols", [])
        products: list[dict] = []
        for item in symbols:
            if not isinstance(item, dict):
                continue
            if not item.get("isSpotTradingAllowed", False):
                continue
            symbol = str(item.get("symbol", "")).strip().upper()
            base_asset = str(item.get("baseAsset", "")).strip().upper()
            quote_asset = str(item.get("quoteAsset", "")).strip().upper()
            if not symbol or not base_asset or not quote_asset:
                continue
            products.append(self._build_product("binance", symbol, base_asset, quote_asset, item.get("status", "UNKNOWN")))
        return products

    def _parse_coinbase_products(self, payload) -> list[dict]:
        products: list[dict] = []
        if not isinstance(payload, list):
            return products
        for item in payload:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("id", "")).strip().upper()
            base_asset = str(item.get("base_currency", "")).strip().upper()
            quote_asset = str(item.get("quote_currency", "")).strip().upper()
            if not symbol or not base_asset or not quote_asset:
                continue
            status = "ACTIVE" if not item.get("trading_disabled", False) else "DISABLED"
            products.append(self._build_product("coinbase", symbol, base_asset, quote_asset, status))
        return products

    def _parse_okx_products(self, payload: dict) -> list[dict]:
        rows = payload.get("data", [])
        products: list[dict] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("instId", "")).strip().upper()
            base_asset = str(item.get("baseCcy", "")).strip().upper()
            quote_asset = str(item.get("quoteCcy", "")).strip().upper()
            if not symbol or not base_asset or not quote_asset:
                continue
            products.append(self._build_product("okx", symbol, base_asset, quote_asset, item.get("state", "UNKNOWN")))
        return products

    def _parse_bybit_products(self, payload: dict) -> list[dict]:
        rows = (((payload.get("result") or {}).get("list")) or [])
        products: list[dict] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "")).strip().upper()
            base_asset = str(item.get("baseCoin", "")).strip().upper()
            quote_asset = str(item.get("quoteCoin", "")).strip().upper()
            if not symbol or not base_asset or not quote_asset:
                continue
            products.append(self._build_product("bybit", symbol, base_asset, quote_asset, item.get("status", "UNKNOWN")))
        return products

    def _parse_kraken_products(self, payload: dict) -> list[dict]:
        rows = payload.get("result", {})
        products: list[dict] = []
        if not isinstance(rows, dict):
            return products
        for item in rows.values():
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("wsname") or item.get("altname") or "").strip().upper()
            base_asset = str(item.get("base", "")).strip().upper().removeprefix("X").removeprefix("Z")
            quote_asset = str(item.get("quote", "")).strip().upper().removeprefix("X").removeprefix("Z")
            if "/" in symbol:
                base_asset, quote_asset = [part.strip().upper() for part in symbol.split("/", 1)]
            if not symbol or not base_asset or not quote_asset:
                continue
            products.append(self._build_product("kraken", symbol, base_asset, quote_asset, "ACTIVE"))
        return products

    def _parse_bitget_products(self, payload: dict) -> list[dict]:
        rows = payload.get("data", [])
        products: list[dict] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "")).strip().upper()
            base_asset = str(item.get("baseCoin", "")).strip().upper()
            quote_asset = str(item.get("quoteCoin", "")).strip().upper()
            if not symbol or not base_asset or not quote_asset:
                continue
            products.append(self._build_product("bitget", symbol, base_asset, quote_asset, item.get("status", "UNKNOWN")))
        return products

    def _build_product(self, venue: str, symbol: str, base_asset: str, quote_asset: str, status: str) -> dict:
        return {
            "venue": venue,
            "symbol": symbol,
            "canonicalPair": f"{base_asset}/{quote_asset}",
            "baseAsset": base_asset,
            "quoteAsset": quote_asset,
            "status": str(status or "UNKNOWN").strip().upper(),
            "marketType": "spot",
        }

    def _merge_product_into_pairs(self, merged_pairs: dict[str, dict], venue: str, product: dict) -> None:
        base_asset = str(product.get("baseAsset", "")).strip().upper()
        quote_asset = str(product.get("quoteAsset", "")).strip().upper()
        if not base_asset or not quote_asset:
            return
        dashboard_symbol = f"{base_asset}{quote_asset}"
        existing = merged_pairs.get(dashboard_symbol)
        if not existing:
            merged_pairs[dashboard_symbol] = {
                "dashboardSymbol": dashboard_symbol,
                "canonicalPair": product["canonicalPair"],
                "baseAsset": base_asset,
                "quoteAsset": quote_asset,
                "status": "ACTIVE" if product.get("status") not in {"DISABLED", "OFFLINE"} else "PARTIAL",
                "supportedVenues": [venue],
                "venueSymbolMap": {venue: product["symbol"]},
                "source": "multi-venue",
            }
            return

        existing["supportedVenues"] = sorted(set(existing.get("supportedVenues", [])) | {venue})
        existing.setdefault("venueSymbolMap", {})[venue] = product["symbol"]
        if product.get("status") in {"DISABLED", "OFFLINE"}:
            existing["status"] = existing.get("status", "ACTIVE")


pair_registry_updater = PairRegistryUpdater()
