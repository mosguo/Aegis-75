from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WALLET_FILE = BASE_DIR / "data" / "wallets" / "mosguo.wallet.json"


class WalletService:
    def __init__(self, wallet_file: Path = WALLET_FILE) -> None:
        self.wallet_file = wallet_file

    def load_wallet(self, user_id: str = "mosguo") -> dict:
        if not self.wallet_file.exists():
            raise FileNotFoundError(f"Wallet file not found: {self.wallet_file}")
        with self.wallet_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("userId") != user_id:
            raise ValueError(f"Wallet userId mismatch: expected={user_id}, actual={data.get('userId')}")
        return data

    def get_dashboard_wallet_summary(self, user_id: str = "mosguo") -> dict:
        wallet = self.load_wallet(user_id)
        return {
            "userId": wallet["userId"],
            "walletId": wallet["walletId"],
            "displayName": wallet.get("displayName", wallet["walletId"]),
            "balance": wallet["balance"],
            "currency": wallet["currency"],
            "status": wallet["status"],
            "updatedAt": wallet["updatedAt"],
            "depositCurrency": wallet.get("depositCurrency", wallet["currency"]),
            "depositNetwork": wallet.get("depositNetwork", ""),
            "depositAddress": wallet.get("depositAddress", ""),
            "addressTag": wallet.get("addressTag", ""),
            "walletType": wallet.get("walletType", "SPOT"),
        }


wallet_service = WalletService()
