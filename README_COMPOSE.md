# Aegis-75 V3.0.2 Compose Edition

This package separates:
- Rust gateway/runtime
- Python API/dashboard/trading layer

## Structure
- docker-compose.yml
- Dockerfile.python
- Dockerfile.rust
- .env.example
- python/

## Expected ports
- Python API: 8000
- Rust gateway: 8080

## First run
1. Copy `.env.example` to `.env`
2. Replace `python/data/wallets/mosguo.wallet.json` depositAddress with your real address
3. Start:
   ```bash
   docker compose up --build
   ```

## Notes
- API path remains unchanged, e.g. `/api/dashboard/wallet`
- Python service reads data from `/python/data`
- LIVE trading remains disabled unless:
  - `AEGIS75_ENABLE_LIVE_TRADING=true`
  - `AEGIS75_EXCHANGE_API_KEY` is set
  - `AEGIS75_EXCHANGE_API_SECRET` is set

## Important
`services/exchange_executor.py::_submit_live_order()` is still a placeholder.
You must connect your real exchange REST signing/submission there before live trading.

## If your Rust binary name is fixed
Edit `Dockerfile.rust` final CMD to the exact binary path for faster startup.
