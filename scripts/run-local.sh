#!/usr/bin/env bash
set -euo pipefail
export AEGIS_ROLE="${AEGIS_ROLE:-hybrid}"
export PORT="${PORT:-8080}"
export AEGIS_NODE_ID="${AEGIS_NODE_ID:-dev-01}"
export AEGIS_REGION="${AEGIS_REGION:-local}"
export AEGIS_CLUSTER="${AEGIS_CLUSTER:-dev}"
export ZEROCLAW_ENABLED="${ZEROCLAW_ENABLED:-false}"
cargo run
