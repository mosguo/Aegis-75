use std::sync::Arc;

use axum::{
    extract::State,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde::Serialize;

use crate::{
    arbitrage,
    core::app::AppState,
    types::orders::{DexSimulationRequest, OrderIntent},
};

pub fn build_router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/", get(root))
        .route("/healthz", get(healthz))
        .route("/readyz", get(readyz))
        .route("/v1/config", get(config_view))
        .route("/v1/runtime/capabilities", get(runtime_capabilities))
        .route("/v1/topology", get(topology))
        .route("/v1/order/simulate", post(simulate_order))
        .route("/v1/dex/simulate", post(simulate_dex))
        .route("/v1/arbitrage/btcusdt", get(arbitrage_btcusdt))
        .with_state(state)
}

#[derive(Serialize)]
struct RootResponse {
    service: &'static str,
    status: &'static str,
    message: &'static str,
}

async fn root() -> impl IntoResponse {
    Json(RootResponse {
        service: "aegis-75",
        status: "ok",
        message: "Aegis-75 is reachable",
    })
}

#[derive(Serialize)]
struct HealthResponse<'a> {
    status: &'a str,
    service: &'a str,
    role: String,
    deployment: String,
}

async fn healthz(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(HealthResponse {
        status: "ok",
        service: "aegis-75",
        role: state.config.role.to_string(),
        deployment: state.config.deployment.active_target.to_string(),
    })
}

#[derive(Serialize)]
struct ReadyModules {
    http: bool,
    config: bool,
    zeroclaw: bool,
    byoh_profile: bool,
}

#[derive(Serialize)]
struct ReadyResponse {
    ready: bool,
    service: &'static str,
    modules: ReadyModules,
}

async fn readyz(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    let zeroclaw_ready = !state.config.zeroclaw_enabled || state.zeroclaw.is_some();

    let modules = ReadyModules {
        http: true,
        config: true,
        zeroclaw: zeroclaw_ready,
        byoh_profile: true,
    };

    let ready = modules.http && modules.config && modules.byoh_profile;

    Json(ReadyResponse {
        ready,
        service: "aegis-75",
        modules,
    })
}

async fn simulate_order(
    State(state): State<Arc<AppState>>,
    Json(intent): Json<OrderIntent>,
) -> impl IntoResponse {
    Json(state.execution.simulate(intent))
}

async fn simulate_dex(
    State(state): State<Arc<AppState>>,
    Json(req): Json<DexSimulationRequest>,
) -> impl IntoResponse {
    Json(state.dex.simulate(req))
}

async fn arbitrage_btcusdt() -> impl IntoResponse {
    match arbitrage::evaluate().await {
        Ok(result) => Json(result),
        Err(e) => Json(serde_json::json!({
            "error": e.to_string(),
            "note": "failed to evaluate arbitrage with real price sources"
        })),
    }
}

#[derive(Serialize)]
struct ConfigView {
    role: String,
    node_id: String,
    region: String,
    cluster: String,
    bind_addr: String,
    execution_mode: String,
    market_scope: String,
    exchanges: Vec<String>,
    dex_networks: Vec<String>,
    zeroclaw_enabled: bool,
    zeroclaw_gateway_configured: bool,
    deployment: DeploymentView,
    identity: IdentityView,
    byoh: ByohView,
    logging: LoggingView,
    tuning: TuningView,
}

#[derive(Serialize)]
struct DeploymentView {
    active_target: String,
    future_target: String,
    migration_stage: String,
    zeabur_compatible: bool,
    byoh_cutover_ready: bool,
}

#[derive(Serialize)]
struct IdentityView {
    logical_host_id: String,
    runtime_host_id: String,
    logical_site: String,
    physical_host_planned: bool,
    physical_host_id: Option<String>,
}

#[derive(Serialize)]
struct ByohView {
    enabled: bool,
    host_class: String,
    hub_mode: String,
    physical_site: String,
    low_latency_gateway_enabled: bool,
    analytics_archive_enabled: bool,
    signing_mode: String,
    market_data_ws_enabled: bool,
    fixed_ip_expected: bool,
    data_lake_path: String,
    telemetry_label: String,
}

#[derive(Serialize)]
struct LoggingView {
    level: String,
    heartbeat_enabled: bool,
    heartbeat_interval_secs: u64,
}

#[derive(Serialize)]
struct TuningView {
    zero_copy_requested: bool,
    hugepages_requested: bool,
    cpu_affinity_requested: bool,
    cpu_affinity_cores: Vec<usize>,
}

async fn config_view(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(ConfigView {
        role: state.config.role.to_string(),
        node_id: state.config.node_id.clone(),
        region: state.config.region.clone(),
        cluster: state.config.cluster.clone(),
        bind_addr: state.config.bind_addr.clone(),
        execution_mode: state.config.execution_mode.to_string(),
        market_scope: state.config.market_scope.clone(),
        exchanges: state.config.exchanges.clone(),
        dex_networks: state.config.dex_networks.clone(),
        zeroclaw_enabled: state.config.zeroclaw_enabled,
        zeroclaw_gateway_configured: state.config.zeroclaw_gateway_url.is_some(),
        deployment: DeploymentView {
            active_target: state.config.deployment.active_target.to_string(),
            future_target: state.config.deployment.future_target.to_string(),
            migration_stage: state.config.deployment.migration_stage.clone(),
            zeabur_compatible: state.config.deployment.zeabur_compatible,
            byoh_cutover_ready: state.config.deployment.byoh_cutover_ready,
        },
        identity: IdentityView {
            logical_host_id: state.config.identity.logical_host_id.clone(),
            runtime_host_id: state.config.identity.runtime_host_id.clone(),
            logical_site: state.config.identity.logical_site.clone(),
            physical_host_planned: state.config.identity.physical_host_planned,
            physical_host_id: state.config.identity.physical_host_id.clone(),
        },
        byoh: ByohView {
            enabled: state.config.byoh.enabled,
            host_class: state.config.byoh.host_class.to_string(),
            hub_mode: state.config.byoh.hub_mode.to_string(),
            physical_site: state.config.byoh.physical_site.clone(),
            low_latency_gateway_enabled: state.config.byoh.low_latency_gateway_enabled,
            analytics_archive_enabled: state.config.byoh.analytics_archive_enabled,
            signing_mode: state.config.byoh.signing_mode.to_string(),
            market_data_ws_enabled: state.config.byoh.market_data_ws_enabled,
            fixed_ip_expected: state.config.byoh.fixed_ip_expected,
            data_lake_path: state.config.byoh.data_lake_path.clone(),
            telemetry_label: state.config.byoh.telemetry_label.clone(),
        },
        logging: LoggingView {
            level: state.config.logging.level.clone(),
            heartbeat_enabled: state.config.logging.heartbeat_enabled,
            heartbeat_interval_secs: state.config.logging.heartbeat_interval_secs,
        },
        tuning: TuningView {
            zero_copy_requested: state.config.tuning.zero_copy_requested,
            hugepages_requested: state.config.tuning.hugepages_requested,
            cpu_affinity_requested: state.config.tuning.cpu_affinity_requested,
            cpu_affinity_cores: state.config.tuning.cpu_affinity_cores.clone(),
        },
    })
}

#[derive(Serialize)]
struct RuntimeCapabilitiesResponse {
    role: String,
    host_class: String,
    hub_mode: String,
    deployment_target: String,
    execution_mode: String,
    market_scope: String,
    zeroclaw_enabled: bool,
    signing_mode: String,
    zero_copy_requested: bool,
    hugepages_requested: bool,
    cpu_affinity_requested: bool,
}

async fn runtime_capabilities(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(RuntimeCapabilitiesResponse {
        role: state.config.role.to_string(),
        host_class: state.config.byoh.host_class.to_string(),
        hub_mode: state.config.byoh.hub_mode.to_string(),
        deployment_target: state.config.deployment.active_target.to_string(),
        execution_mode: state.config.execution_mode.to_string(),
        market_scope: state.config.market_scope.clone(),
        zeroclaw_enabled: state.config.zeroclaw_enabled,
        signing_mode: state.config.byoh.signing_mode.to_string(),
        zero_copy_requested: state.config.tuning.zero_copy_requested,
        hugepages_requested: state.config.tuning.hugepages_requested,
        cpu_affinity_requested: state.config.tuning.cpu_affinity_requested,
    })
}

#[derive(Serialize)]
struct TopologyResponse {
    service: &'static str,
    logical_host_id: String,
    runtime_host_id: String,
    logical_site: String,
    region: String,
    cluster: String,
    deployment_target: String,
    future_target: String,
    host_class: String,
    hub_mode: String,
    byoh_enabled: bool,
    physical_host_planned: bool,
}

async fn topology(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(TopologyResponse {
        service: "aegis-75",
        logical_host_id: state.config.identity.logical_host_id.clone(),
        runtime_host_id: state.config.identity.runtime_host_id.clone(),
        logical_site: state.config.identity.logical_site.clone(),
        region: state.config.region.clone(),
        cluster: state.config.cluster.clone(),
        deployment_target: state.config.deployment.active_target.to_string(),
        future_target: state.config.deployment.future_target.to_string(),
        host_class: state.config.byoh.host_class.to_string(),
        hub_mode: state.config.byoh.hub_mode.to_string(),
        byoh_enabled: state.config.byoh.enabled,
        physical_host_planned: state.config.identity.physical_host_planned,
    })
}