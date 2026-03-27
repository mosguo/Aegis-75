from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
import os

BASE_DIR = Path(__file__).resolve().parent.parent
TRADING_PAIR_FILE = BASE_DIR / "data" / "trading_pairs.json"
TZ_TAIPEI = timezone(timedelta(hours=8))
DEFAULT_RUST_API_BASE_URL = "http://127.0.0.1:8080"


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
        live_pairs = self._fetch_live_pairs()
        if not live_pairs:
            return pairs

        live_by_symbol = {pair.get("symbol"): pair for pair in live_pairs if pair.get("symbol")}
        merged_pairs: list[dict] = []

        for pair in pairs:
            symbol = pair.get("symbol")
            live_pair = live_by_symbol.get(symbol)
            if not live_pair:
                merged_pairs.append(pair)
                continue

            merged = dict(pair)
            merged.update(
                {
                    "binancePrice": live_pair.get("binancePrice"),
                    "okxPrice": live_pair.get("okxPrice"),
                    "spreadAbs": live_pair.get("spreadAbs"),
                    "spreadPct": live_pair.get("spreadPct"),
                    "decision": live_pair.get("decision"),
                    "arbitrage": live_pair.get("arbitrage"),
                    "ageMs": live_pair.get("ageMs"),
                    "lastRefresh": live_pair.get("lastRefresh"),
                    "note": live_pair.get("note"),
                }
            )
            merged_pairs.append(merged)

        known_symbols = {pair.get("symbol") for pair in merged_pairs}
        for symbol, live_pair in live_by_symbol.items():
            if symbol in known_symbols:
                continue
            merged_pairs.append(
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
                    "decision": live_pair.get("decision"),
                    "arbitrage": live_pair.get("arbitrage"),
                    "ageMs": live_pair.get("ageMs"),
                    "lastRefresh": live_pair.get("lastRefresh"),
                    "note": live_pair.get("note"),
                }
            )

        return merged_pairs

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
        return target

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
            "threshold": pair.get("threshold"),
            "arbitrage": pair.get("arbitrage"),
            "decision": pair.get("decision"),
            "ageMs": pair.get("age_ms"),
            "lastRefresh": pair.get("last_refresh_utc"),
            "note": pair.get("note"),
        }


trading_pair_service = TradingPairService()
