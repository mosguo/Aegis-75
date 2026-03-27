from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TRADING_PAIR_FILE = BASE_DIR / "data" / "trading_pairs.json"
TZ_TAIPEI = timezone(timedelta(hours=8))


class TradingPairService:
    def __init__(self, file_path: Path = TRADING_PAIR_FILE) -> None:
        self.file_path = file_path

    def _read(self) -> dict:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Trading pair file not found: {self.file_path}")
        with self.file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, payload: dict) -> None:
        backup = self.file_path.with_suffix(self.file_path.suffix + ".bak")
        if self.file_path.exists():
            backup.write_text(self.file_path.read_text(encoding="utf-8"), encoding="utf-8")
        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def list_pairs(self) -> list[dict]:
        data = self._read()
        return data.get("pairs", [])

    def update_pair(
        self,
        symbol: str,
        spread_threshold: float | None = None,
        auto_trigger: bool | None = None,
        execution_mode: str | None = None,
    ) -> dict:
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
            if spread_threshold < 0:
                raise ValueError("spreadThreshold must be >= 0")
            target["spreadThreshold"] = spread_threshold

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


trading_pair_service = TradingPairService()
