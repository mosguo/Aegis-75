from __future__ import annotations

import importlib
import json
import os
from pathlib import Path


class PairRegistryCache:
    def __init__(self, runtime_file_path: Path) -> None:
        self.runtime_file_path = runtime_file_path
        self.backend = os.getenv("AEGIS_PAIR_REGISTRY_CACHE_BACKEND", "file").strip().lower()
        self.redis_url = os.getenv("AEGIS_PAIR_REGISTRY_REDIS_URL", "redis://127.0.0.1:6379/0").strip()
        self.redis_key = os.getenv("AEGIS_PAIR_REGISTRY_REDIS_KEY", "aegis75:pair_registry:runtime").strip()

    def load(self) -> dict | None:
        if self.backend == "redis":
            payload = self._load_from_redis()
            if payload is not None:
                return payload
        return self._load_from_file()

    def save(self, payload: dict) -> dict:
        self._save_to_file(payload)
        if self.backend == "redis":
            self._save_to_redis(payload)
        return payload

    def cache_backend_label(self) -> str:
        if self.backend != "redis":
            return "file"
        return "redis" if self._redis_client() is not None else "file-fallback"

    def _load_from_file(self) -> dict | None:
        if not self.runtime_file_path.exists():
            return None
        with self.runtime_file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save_to_file(self, payload: dict) -> None:
        self.runtime_file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_from_redis(self) -> dict | None:
        client = self._redis_client()
        if client is None:
            return None
        try:
            raw = client.get(self.redis_key)
        except Exception:
            return None
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _save_to_redis(self, payload: dict) -> None:
        client = self._redis_client()
        if client is None:
            return
        try:
            client.set(self.redis_key, json.dumps(payload, ensure_ascii=False))
        except Exception:
            return

    def _redis_client(self):
        try:
            redis_module = importlib.import_module("redis")
        except Exception:
            return None
        try:
            return redis_module.from_url(self.redis_url, decode_responses=True)
        except Exception:
            return None

