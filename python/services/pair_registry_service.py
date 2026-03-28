from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.pair_registry_cache import PairRegistryCache

BASE_DIR = Path(__file__).resolve().parent.parent
PAIR_REGISTRY_FILE = BASE_DIR / "data" / "pair_registry.json"
PAIR_REGISTRY_RUNTIME_FILE = BASE_DIR / "data" / "pair_registry_runtime.json"
TZ_TAIPEI = timezone(timedelta(hours=8))


class PairRegistryService:
    def __init__(
        self,
        static_file_path: Path = PAIR_REGISTRY_FILE,
        runtime_file_path: Path = PAIR_REGISTRY_RUNTIME_FILE,
    ) -> None:
        self.static_file_path = static_file_path
        self.runtime_file_path = runtime_file_path
        self.cache = PairRegistryCache(runtime_file_path)
        self._cached_pairs: list[dict] | None = None
        self._cached_index: dict[str, dict] | None = None
        self._cached_products_by_venue: dict[str, list[dict]] | None = None
        self._cached_product_index: dict[tuple[str, str], dict] | None = None
        self._cache_signature: tuple[float | None, float | None] | None = None

    def list_pairs(self) -> list[dict]:
        self._refresh_cache_if_needed()
        return list(self._cached_pairs or [])

    def get_sync_status(self) -> dict:
        runtime_payload = self._read_runtime_payload()
        metadata = runtime_payload.get("metadata", {})
        return {
            "source": metadata.get("source", "binance.exchangeInfo"),
            "lastSyncedAt": metadata.get("lastSyncedAt"),
            "pairCount": int(metadata.get("pairCount", 0) or 0),
            "intervalSeconds": int(metadata.get("intervalSeconds", 21600) or 21600),
            "status": metadata.get("status", "idle"),
            "note": metadata.get("note", ""),
            "cacheBackend": metadata.get("cacheBackend", self.cache.cache_backend_label()),
            "venues": metadata.get("venues", {}),
        }

    def list_venue_products(self, venue: str) -> list[dict]:
        self._refresh_cache_if_needed()
        normalized_venue = venue.strip().lower()
        return list((self._cached_products_by_venue or {}).get(normalized_venue, []))

    def get_venue_product(self, venue: str, symbol: str) -> dict | None:
        self._refresh_cache_if_needed()
        normalized_venue = venue.strip().lower()
        normalized_symbol = symbol.strip().upper()
        return deepcopy((self._cached_product_index or {}).get((normalized_venue, normalized_symbol)))

    def get_by_dashboard_symbol(self, symbol: str) -> dict | None:
        normalized_symbol = symbol.strip().upper()
        self._refresh_cache_if_needed()
        if self._cached_index and normalized_symbol in self._cached_index:
            return deepcopy(self._cached_index[normalized_symbol])
        return self._build_fallback_entry(normalized_symbol)

    def attach_to_pair(self, pair: dict) -> dict:
        symbol = str(pair.get("symbol", "")).strip().upper()
        entry = self.get_by_dashboard_symbol(symbol)
        if not entry:
            pair["canonicalPair"] = None
            pair["supportedVenues"] = []
            pair["venueSymbolMap"] = {}
            pair["registryStatus"] = "UNMAPPED"
            pair["isRegistryTradable"] = False
            pair["mappedVenueCount"] = 0
            pair["mappedVenueLabels"] = []
            pair["binanceSymbol"] = None
            pair["okxSymbol"] = None
            pair["cexAName"] = None
            pair["cexBName"] = None
            return pair

        pair["canonicalPair"] = entry.get("canonicalPair")
        pair["supportedVenues"] = entry.get("supportedVenues", [])
        pair["venueSymbolMap"] = entry.get("venueSymbolMap", {})
        pair["registryStatus"] = entry.get("status", "ACTIVE")
        pair["registrySource"] = entry.get("source", "static")
        pair["baseAsset"] = pair.get("baseAsset") or entry.get("baseAsset")
        pair["quoteAsset"] = pair.get("quoteAsset") or entry.get("quoteAsset")
        pair["mappedVenueCount"] = len(entry.get("supportedVenues", []))
        pair["mappedVenueLabels"] = [str(item).strip().lower() for item in entry.get("supportedVenues", [])]
        pair["binanceSymbol"] = entry.get("venueSymbolMap", {}).get("binance")
        pair["okxSymbol"] = entry.get("venueSymbolMap", {}).get("okx")
        pair["cexAName"] = "binance" if entry.get("venueSymbolMap", {}).get("binance") else None
        pair["cexBName"] = "okx" if entry.get("venueSymbolMap", {}).get("okx") else None
        pair["isRegistryTradable"] = self._is_registry_tradable(entry)
        return pair

    def _refresh_cache_if_needed(self) -> None:
        signature = self._current_signature()
        if self._cached_pairs is not None and self._cached_index is not None and self._cache_signature == signature:
            return

        static_pairs = self._read_pairs(self.static_file_path)
        runtime_payload = self._read_runtime_payload()
        runtime_pairs = runtime_payload.get("pairs", [])

        merged_by_symbol: dict[str, dict] = {}
        for entry in static_pairs:
            normalized = self._normalize_entry(entry, source="static")
            merged_by_symbol[normalized["dashboardSymbol"]] = normalized

        for entry in runtime_pairs:
            normalized = self._normalize_entry(entry, source="runtime")
            existing = merged_by_symbol.get(normalized["dashboardSymbol"])
            if existing:
                merged_by_symbol[normalized["dashboardSymbol"]] = self._merge_entries(existing, normalized)
            else:
                merged_by_symbol[normalized["dashboardSymbol"]] = normalized

        sorted_pairs = sorted(merged_by_symbol.values(), key=lambda item: item["dashboardSymbol"])
        self._cached_pairs = sorted_pairs
        self._cached_index = {item["dashboardSymbol"]: item for item in sorted_pairs}
        self._cached_products_by_venue, self._cached_product_index = self._build_product_indexes(runtime_payload)
        self._cache_signature = signature

    def upsert_runtime_pairs(
        self,
        pairs: list[dict],
        *,
        products_by_venue: dict[str, list[dict]],
        venue_status: dict[str, dict],
        source: str,
        note: str,
        interval_seconds: int,
        status: str,
    ) -> dict:
        normalized_pairs = [self._normalize_entry(pair, source="runtime") for pair in pairs if isinstance(pair, dict)]
        payload = {
            "metadata": {
                "source": source,
                "lastSyncedAt": datetime.now(TZ_TAIPEI).isoformat(),
                "pairCount": len(normalized_pairs),
                "intervalSeconds": interval_seconds,
                "status": status,
                "note": note,
                "cacheBackend": self.cache.cache_backend_label(),
                "venues": venue_status,
            },
            "pairs": normalized_pairs,
            "productsByVenue": products_by_venue,
        }
        return self.cache.save(payload)

    def mark_runtime_sync_failed(self, *, source: str, note: str, interval_seconds: int) -> dict:
        payload = self._read_runtime_payload()
        metadata = payload.get("metadata", {})
        metadata.update(
            {
                "source": source,
                "intervalSeconds": interval_seconds,
                "status": "degraded",
                "note": note,
            }
        )
        if not metadata.get("lastSyncedAt"):
            metadata["lastSyncedAt"] = datetime.now(TZ_TAIPEI).isoformat()
        metadata["cacheBackend"] = self.cache.cache_backend_label()
        payload["metadata"] = metadata
        return self.cache.save(payload)

    def should_refresh(self, interval_seconds: int) -> bool:
        status = self.get_sync_status()
        last_synced_at = status.get("lastSyncedAt")
        if not last_synced_at:
            return True
        try:
            last_sync = datetime.fromisoformat(last_synced_at)
        except ValueError:
            return True
        return datetime.now(TZ_TAIPEI) - last_sync >= timedelta(seconds=interval_seconds)

    def _current_signature(self) -> tuple[float | None, float | None]:
        static_mtime = self.static_file_path.stat().st_mtime if self.static_file_path.exists() else None
        runtime_mtime = self.runtime_file_path.stat().st_mtime if self.runtime_file_path.exists() else None
        return static_mtime, runtime_mtime

    def _read_pairs(self, file_path: Path) -> list[dict]:
        if not file_path.exists():
            if file_path == self.runtime_file_path:
                return []
            raise FileNotFoundError(f"Pair registry file not found: {file_path}")
        with file_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            raise ValueError(f"Pair registry payload must be a JSON object: {file_path}")
        pairs = payload.get("pairs", [])
        if not isinstance(pairs, list):
            raise ValueError(f"Pair registry payload must contain a pairs array: {file_path}")
        return pairs

    def _read_runtime_payload(self) -> dict:
        payload = self.cache.load()
        if payload is None:
            return {
                "metadata": {
                    "source": "binance.exchangeInfo",
                    "lastSyncedAt": None,
                    "pairCount": 0,
                    "intervalSeconds": 21600,
                    "status": "idle",
                    "note": "runtime registry not synced yet",
                    "cacheBackend": self.cache.cache_backend_label(),
                    "venues": {},
                },
                "pairs": [],
                "productsByVenue": {},
            }

        if not isinstance(payload, dict):
            raise ValueError("Runtime pair registry payload must be a JSON object")
        if not isinstance(payload.get("pairs", []), list):
            raise ValueError("Runtime pair registry payload must contain a pairs array")
        if not isinstance(payload.get("metadata", {}), dict):
            raise ValueError("Runtime pair registry payload must contain a metadata object")
        if not isinstance(payload.get("productsByVenue", {}), dict):
            raise ValueError("Runtime pair registry payload must contain a productsByVenue object")
        return payload

    def _build_product_indexes(self, runtime_payload: dict) -> tuple[dict[str, list[dict]], dict[tuple[str, str], dict]]:
        products_by_venue_payload = runtime_payload.get("productsByVenue", {})
        venue_map: dict[str, list[dict]] = {}
        product_index: dict[tuple[str, str], dict] = {}
        for venue, raw_products in dict(products_by_venue_payload).items():
            normalized_venue = str(venue).strip().lower()
            products: list[dict] = []
            for item in raw_products or []:
                if not isinstance(item, dict):
                    continue
                normalized = {
                    "venue": normalized_venue,
                    "symbol": item.get("symbol"),
                    "canonicalPair": item.get("canonicalPair"),
                    "baseAsset": item.get("baseAsset"),
                    "quoteAsset": item.get("quoteAsset"),
                    "status": item.get("status", "UNKNOWN"),
                    "marketType": item.get("marketType", "spot"),
                }
                products.append(normalized)
                symbol = str(normalized.get("symbol") or "").strip().upper()
                if symbol:
                    product_index[(normalized_venue, symbol)] = normalized
            venue_map[normalized_venue] = products
        return venue_map, product_index

    def _normalize_entry(self, entry: dict, *, source: str) -> dict:
        dashboard_symbol = str(entry.get("dashboardSymbol", "")).strip().upper()
        base_asset = str(entry.get("baseAsset", "")).strip().upper()
        quote_asset = str(entry.get("quoteAsset", "")).strip().upper()
        canonical_pair = entry.get("canonicalPair") or (
            f"{base_asset}/{quote_asset}" if base_asset and quote_asset else dashboard_symbol
        )
        supported_venues = [
            str(venue).strip().lower()
            for venue in entry.get("supportedVenues", [])
            if str(venue).strip()
        ]
        venue_symbol_map = {
            str(venue).strip().lower(): str(symbol).strip()
            for venue, symbol in dict(entry.get("venueSymbolMap", {})).items()
            if str(venue).strip() and str(symbol).strip()
        }

        return {
            "dashboardSymbol": dashboard_symbol,
            "canonicalPair": canonical_pair,
            "baseAsset": base_asset,
            "quoteAsset": quote_asset,
            "status": str(entry.get("status", "ACTIVE")).strip().upper(),
            "supportedVenues": supported_venues,
            "venueSymbolMap": venue_symbol_map,
            "source": str(entry.get("source", source)).strip().lower(),
        }

    def _merge_entries(self, base: dict, overlay: dict) -> dict:
        merged = deepcopy(base)
        if overlay.get("supportedVenues"):
            merged["supportedVenues"] = sorted(set(base.get("supportedVenues", [])) | set(overlay["supportedVenues"]))
        merged["venueSymbolMap"] = {
            **base.get("venueSymbolMap", {}),
            **overlay.get("venueSymbolMap", {}),
        }
        for field in ["canonicalPair", "baseAsset", "quoteAsset"]:
            if overlay.get(field):
                merged[field] = overlay[field]
        if overlay.get("status"):
            merged["status"] = overlay["status"]
        merged["source"] = overlay.get("source", base.get("source", "static"))
        return merged

    def _build_fallback_entry(self, symbol: str) -> dict | None:
        if not symbol:
            return None
        if symbol.endswith("USDT") and len(symbol) > 4:
            base_asset = symbol[:-4]
            quote_asset = "USDT"
            return {
                "dashboardSymbol": symbol,
                "canonicalPair": f"{base_asset}/{quote_asset}",
                "baseAsset": base_asset,
                "quoteAsset": quote_asset,
                "status": "DISCOVERED",
                "supportedVenues": ["binance", "okx"],
                "venueSymbolMap": {
                    "binance": symbol,
                    "okx": f"{base_asset}-{quote_asset}",
                },
                "source": "derived",
            }
        return None

    def _is_registry_tradable(self, entry: dict) -> bool:
        supported_venues = set(entry.get("supportedVenues", []))
        venue_symbol_map = entry.get("venueSymbolMap", {})
        return (
            entry.get("status") in {"ACTIVE", "DISCOVERED"}
            and len(supported_venues) >= 2
            and sum(1 for value in venue_symbol_map.values() if value) >= 2
        )


pair_registry_service = PairRegistryService()
