# Aegis-75

Aegis-75 is a Rust service scaffold for an **8-node CEX + DEX simulation topology** with:

- Zeabur cloud nodes for control-plane, edge routing, monitoring, and API surface
- a **BYOH-style Data & Execution Hub profile** for low-latency ingress, analytics, archival, and future signing isolation
- a single image switched by environment variables rather than separate codebases

## Current integration state

This revision reflects your latest requirement:

- the **BYOH host identity is currently environment-defined**
- the same BYOH profile can **run on Zeabur first** for validation
- after validation, the same role/config model can be **cut over to a physical host**
- ZeroClaw remains in the **control-plane / task orchestration / alert relay** path only
- execution role switching is still controlled by `AEGIS_ROLE`

This means the repository now supports a **two-stage rollout**:

1. **Stage A — Zeabur validation**
   - run the future BYOH node profile as a Zeabur-deployed service
   - validate APIs, topology, config, alert paths, and routing behavior
2. **Stage B — Physical-host cutover**
   - move the same logical BYOH profile to your own machine room host
   - keep the same runtime semantics and logical node identity
   - only the deployment target and host runtime identity need to change

## Runtime role model

`AEGIS_ROLE` supports:

- `control-plane`
- `execution-core`
- `trading-unit`
- `hybrid`

This keeps a single project image reusable across Zeabur cloud nodes and the future BYOH host.

## New deployment and identity controls

### Deployment controls

- `AEGIS_DEPLOYMENT_TARGET=zeabur|byoh|generic`
- `AEGIS_FUTURE_DEPLOYMENT_TARGET=zeabur|byoh|generic`
- `AEGIS_MIGRATION_STAGE=...`
- `AEGIS_ZEABUR_COMPATIBLE=true|false`
- `AEGIS_BYOH_CUTOVER_READY=true|false`

### Identity controls

- `AEGIS_IDENTITY_SOURCE=environment|static`
- `AEGIS_LOGICAL_HOST_ID=...`
- `AEGIS_RUNTIME_HOST_ID=...`
- `AEGIS_LOGICAL_SITE=...`
- `AEGIS_PHYSICAL_HOST_PLANNED=true|false`
- `AEGIS_PHYSICAL_HOST_ID=...`

### Meaning of the identity split

- **logical host id**: the durable role identity you want to keep across migration
- **runtime host id**: the actual currently running instance identity

Example:

- Zeabur validation phase:
  - `AEGIS_LOGICAL_HOST_ID=byoh-hub-01`
  - `AEGIS_RUNTIME_HOST_ID=zb-byoh-hub-01`
  - `AEGIS_DEPLOYMENT_TARGET=zeabur`
  - `AEGIS_FUTURE_DEPLOYMENT_TARGET=byoh`
- Physical cutover phase:
  - `AEGIS_LOGICAL_HOST_ID=byoh-hub-01`
  - `AEGIS_RUNTIME_HOST_ID=phy-byoh-hub-01`
  - `AEGIS_DEPLOYMENT_TARGET=byoh`
  - `AEGIS_FUTURE_DEPLOYMENT_TARGET=byoh`

This preserves topology identity while allowing deployment migration.

## BYOH profile model

When `AEGIS_BYOH_ENABLED=true`, the service models the BYOH node as the **Data & Execution Hub**.

Responsibilities represented in config and API output:

1. **Low-Latency Gateway**
   - exchange WebSocket persistence
   - fixed IP expectation
   - preferred execution adjacency
2. **Hardware Acceleration Zone**
   - zero-copy requested flag
   - hugepages requested flag
   - CPU affinity requested flag
3. **Private Analytics & Archiving**
   - data lake path
   - archive responsibility exposed in topology endpoints
4. **Secure Execution Node**
   - signing mode declaration
   - future HSM boundary reserved for BYOH only

## Important engineering interpretation

At this stage, **BYOH is represented as an execution profile and logical identity first**, not as a physically attached host yet.

That matches your current decision:

- first deploy and test on Zeabur
- then migrate to the physical machine room once validation is complete

So the repository is now aligned with:

- **current reality**: Zeabur deployment
- **future target**: physical host deployment
- **stable logical architecture**: unchanged across both

## API endpoints

- `GET /healthz`
- `GET /readyz`
- `GET /v1/config`
- `GET /v1/runtime/capabilities`
- `GET /v1/topology`
- `POST /v1/order/simulate`
- `POST /v1/dex/simulate`
- `POST /v1/alert/test`

## What the endpoints now expose

The responses now include:

- active deployment target
- future deployment target
- migration stage
- logical host id
- runtime host id
- logical site
- whether a physical host is planned

That makes Zeabur validation and later cutover auditable through the service API itself.


## Runtime logging contract

Aegis-75 now emits explicit Zeabur-friendly runtime logs for both success and architecture problems.

Expected successful startup markers:

```text
[BOOT][INFO] Aegis-75 starting...
[BOOT][INFO] role=control-plane deployment=zeabur host=zb-byoh-hub-01
[BOOT][INFO] byoh_enabled=true hub_mode=data-execution-hub
[BOOT][INFO] zeroclaw_mode=disabled
[BOOT][INFO] runtime_checks=passed
[BOOT][SUCCESS] Aegis-75 READY
```

Expected warning / architecture markers:

```text
[WARN] byoh_enabled=true but running on zeabur (simulation mode)
[ERROR][ARCH] conflicting_config host_class=cloud but hub_mode=data-execution-hub
[ERROR][FATAL] runtime_checks=failed
```

Operational markers:

```text
[RUNTIME][INFO] http_server started
[RUNTIME][ORDER] simulate cex=binance pair=BTCUSDT amount=0.01 mode=paper host=zb-byoh-hub-01 latency=simulated
[RUNTIME][DEX] simulate chain=arbitrum pair=ETHUSDC amount=1.25 router=auto host=zb-byoh-hub-01
[RUNTIME][HEARTBEAT] service heartbeat
```

Controls:

- `AEGIS_LOG_LEVEL=info|debug|warn|error`
- `AEGIS_HEARTBEAT_ENABLED=true|false`
- `AEGIS_HEARTBEAT_INTERVAL_SECS=30`

## Quick start

```bash
cp .env.example .env
set -a; source .env; set +a
cargo run
```

Health:

```bash
curl http://127.0.0.1:8080/healthz
```

Capabilities:

```bash
curl http://127.0.0.1:8080/v1/runtime/capabilities
```

Topology:

```bash
curl http://127.0.0.1:8080/v1/topology
```

CEX simulate:

```bash
curl -X POST http://127.0.0.1:8080/v1/order/simulate \
  -H 'content-type: application/json' \
  -d '{
    "symbol":"BTCUSDT",
    "side":"buy",
    "amount":0.01,
    "venue_preference":"binance",
    "kind":"market"
  }'
```

DEX simulate:

```bash
curl -X POST http://127.0.0.1:8080/v1/dex/simulate \
  -H 'content-type: application/json' \
  -d '{
    "symbol":"ETHUSDC",
    "amount":1.25,
    "network":"arbitrum",
    "router":"auto"
  }'
```

## Recommended initial posture

For your current stage, the most consistent environment choice is:

- `AEGIS_DEPLOYMENT_TARGET=zeabur`
- `AEGIS_FUTURE_DEPLOYMENT_TARGET=byoh`
- `AEGIS_BYOH_ENABLED=true`
- `AEGIS_HOST_CLASS=byoh`
- `AEGIS_HUB_MODE=data-execution-hub`
- `AEGIS_SIGNING_MODE=local-env`
- `AEGIS_EXECUTION_MODE=paper`
- `AEGIS_BYOH_CUTOVER_READY=false`

This gives you a **BYOH-semantic node running on Zeabur** until the physical host is ready.

## Recommended 8-node layout

| Node | Region | Host class | Active target | Future target | Primary role |
|---|---|---|---|---|---|
| byoh-hub-01 | private-dc-profile | byoh | zeabur | byoh | hybrid |
| tk-01 | Tokyo | cloud | zeabur | zeabur | trading-unit |
| sg-01 | Singapore | cloud | zeabur | zeabur | trading-unit |
| hk-01 | Hong Kong | cloud | zeabur | zeabur | control-plane |
| fra-01 | Frankfurt | cloud | zeabur | zeabur | trading-unit |
| lon-01 | London | cloud | zeabur | zeabur | execution-core |
| use1-01 | Virginia | cloud | zeabur | zeabur | trading-unit |
| usw-01 | US West | cloud | zeabur | zeabur | execution-core |

## Boundaries still not implemented

This scaffold still does **not** implement:

- real exchange authenticated order submission
- FIX sessions
- long-lived market-data collectors
- HSM drivers
- OS-level CPU pinning
- hugepages provisioning
- NVMe archival writers
- cross-node state replication
- actual BYOH host onboarding into Zeabur

## Honest status

I updated the source tree to represent your new rollout model, but I could not compile-test it in this environment because the container does not have a Rust toolchain installed.

So this is a **source-structure and configuration-integrated revision**, not a claimed build-verified release.
