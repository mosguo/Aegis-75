use std::sync::Arc;

use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde_json::json;
use tracing::{error, info};

use crate::{
    core::app::AppState,
    types::{
        alerts::TestAlertRequest,
        orders::{DexSimulationRequest, OrderIntent},
    },
};

pub fn build_router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/readyz", get(readyz))
        .route("/v1/config", get(show_config))
        .route("/v1/runtime/capabilities", get(show_runtime_capabilities))
        .route("/v1/topology", get(show_topology))
        .route("/v1/order/simulate", post(simulate_order))
        .route("/v1/dex/simulate", post(simulate_dex))
        .route("/v1/alert/test", post(test_alert))
        .with_state(state)
}

async fn healthz(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    info!("[RUNTIME][INFO] healthz ok host={} role={}", state.config.identity.runtime_host_id, state.config.role);
    Json(json!({
        "status": "ok",
        "service": "aegis-75",
        "role": state.config.role.to_string(),
        "node_id": state.config.node_id,
        "host_class": state.config.byoh.host_class.to_string(),
        "hub_mode": state.config.byoh.hub_mode.to_string(),
        "deployment_target": state.config.deployment.active_target.to_string(),
        "logical_host_id": state.config.identity.logical_host_id,
        "runtime_host_id": state.config.identity.runtime_host_id,
        "time": Utc::now(),
    }))
}

async fn readyz(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    info!("[RUNTIME][INFO] readyz ready={} host={}", true, state.config.identity.runtime_host_id);
    Json(json!({
        "ready": true,
        "zeroclaw_enabled": state.config.zeroclaw_enabled,
        "execution_mode": state.config.execution_mode.to_string(),
        "market_scope": state.config.market_scope,
        "byoh_enabled": state.config.byoh.enabled,
        "deployment_target": state.config.deployment.active_target.to_string(),
        "future_target": state.config.deployment.future_target.to_string(),
        "migration_stage": state.config.deployment.migration_stage,
        "signing_mode": state.config.byoh.signing_mode.to_string(),
    }))
}

async fn show_config(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(json!({
        "role": state.config.role,
        "node_id": state.config.node_id,
        "region": state.config.region,
        "cluster": state.config.cluster,
        "public_base": state.config.public_base,
        "execution_mode": state.config.execution_mode,
        "market_scope": state.config.market_scope,
        "exchanges": state.config.exchanges,
        "dex_networks": state.config.dex_networks,
        "zeroclaw_enabled": state.config.zeroclaw_enabled,
        "deployment": state.config.deployment,
        "identity": state.config.identity,
        "byoh": state.config.byoh,
        "tuning": state.config.tuning,
    }))
}

async fn show_runtime_capabilities(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(state.runtime_capabilities())
}

async fn show_topology(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(json!({
        "deployment": {
            "active_target": state.config.deployment.active_target,
            "future_target": state.config.deployment.future_target,
            "migration_stage": state.config.deployment.migration_stage,
            "zeabur_compatible": state.config.deployment.zeabur_compatible,
            "byoh_cutover_ready": state.config.deployment.byoh_cutover_ready,
        },
        "identity": {
            "source": state.config.identity.source,
            "logical_host_id": state.config.identity.logical_host_id,
            "runtime_host_id": state.config.identity.runtime_host_id,
            "logical_site": state.config.identity.logical_site,
            "physical_host_planned": state.config.identity.physical_host_planned,
            "physical_host_id": state.config.identity.physical_host_id,
        },
        "control_plane": {
            "zeroclaw_enabled": state.config.zeroclaw_enabled,
            "host_class": "cloud/byoh mixed",
            "responsibilities": [
                "task orchestration",
                "alert relay",
                "web ui / api surface",
                "global edge monitoring"
            ]
        },
        "data_execution_hub": {
            "enabled": state.config.byoh.enabled,
            "physical_site": state.config.byoh.physical_site,
            "current_runtime_location": state.config.deployment.active_target,
            "target_runtime_location": state.config.deployment.future_target,
            "responsibilities": [
                "low-latency websocket ingress",
                "private analytics and archival",
                "signing enclave / hsm integration",
                "preferred execution path"
            ]
        },
        "market_scope": state.config.market_scope,
        "cex_exchanges": state.config.exchanges,
        "dex_networks": state.config.dex_networks,
    }))
}

async fn simulate_order(
    State(state): State<Arc<AppState>>,
    Json(payload): Json<OrderIntent>,
) -> impl IntoResponse {
    let result = state.execution.simulate(payload);
    (StatusCode::OK, Json(result))
}

async fn simulate_dex(
    State(state): State<Arc<AppState>>,
    Json(payload): Json<DexSimulationRequest>,
) -> impl IntoResponse {
    let result = state.dex.simulate(payload);
    (StatusCode::OK, Json(result))
}

async fn test_alert(
    State(state): State<Arc<AppState>>,
    Json(payload): Json<TestAlertRequest>,
) -> impl IntoResponse {
    match state.notify_alert(&payload.title, &payload.body).await {
        Ok(_) => {
            info!("[RUNTIME][INFO] test alert sent host={}", state.config.identity.runtime_host_id);
            (StatusCode::OK, Json(json!({"sent": true}))).into_response()
        }
        Err(err) => {
            error!("[ERROR] test alert failed error={}", err);
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({"sent": false, "error": err.to_string()})),
            )
                .into_response()
        }
    }
}
