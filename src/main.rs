mod control;
mod core;
mod dex;
mod execution;
mod http;
mod types;

use std::{net::SocketAddr, sync::Arc, time::Duration};

use anyhow::Context;
use axum::Router;
use tracing::{error, info, warn};

use crate::{
    control::zeroclaw::ZeroClawClient,
    core::{app::AppState, config::Config},
    dex::router::DexRouter,
    execution::router::ExecutionRouter,
    http::routes::build_router,
};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // 先用 stdout/stderr 打，避免 tracing 尚未初始化前錯誤被吃掉
    println!("[BOOT][INFO] Aegis-75 starting...");

    let config = match Config::from_env() {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("[ERROR][FATAL] failed to load config from environment: {e:#}");
            std::process::exit(1);
        }
    };

    init_tracing(&config.logging.level);

    info!(
        "[BOOT][INFO] role={} deployment={} host={}",
        config.role,
        config.deployment.active_target,
        config.identity.runtime_host_id
    );
    info!(
        "[BOOT][INFO] byoh_enabled={} hub_mode={}",
        config.byoh.enabled,
        config.byoh.hub_mode
    );
    info!(
        "[BOOT][INFO] zeroclaw_mode={}",
        if config.zeroclaw_enabled {
            "control-plane"
        } else {
            "disabled"
        }
    );

    let startup = config.startup_checks();

    for warning_message in &startup.warnings {
        warn!("[WARN] {warning_message}");
    }

    for arch_error in &startup.architecture_errors {
        error!("[ERROR][ARCH] {arch_error}");
    }

    // 關鍵：不要因 startup check 失敗直接退出，先讓服務活著以利觀測
    if startup.passed() {
        info!("[BOOT][INFO] runtime_checks=passed");
    } else {
        error!("[ERROR][ARCH] runtime_checks=failed, continuing in degraded mode");
    }

    let zeroclaw = if config.zeroclaw_enabled {
        match ZeroClawClient::from_config(&config) {
            Ok(client) => Some(client),
            Err(e) => {
                error!("[ERROR][ARCH] zeroclaw initialization failed: {e:#}");
                None
            }
        }
    } else {
        None
    };

    let state = Arc::new(AppState::new(
        config.clone(),
        ExecutionRouter::new(config.clone()),
        DexRouter::new(config.clone()),
        zeroclaw,
    ));

    announce_mode(&state).await;
    spawn_heartbeat(state.clone());

    let app: Router = build_router(state);

    let addr = resolve_bind_addr(&config)?;
    info!(
        %addr,
        role=%config.role,
        region=%config.region,
        node=%config.node_id,
        host_class=%config.byoh.host_class,
        hub_mode=%config.byoh.hub_mode,
        deployment_target=%config.deployment.active_target,
        logical_host_id=%config.identity.logical_host_id,
        runtime_host_id=%config.identity.runtime_host_id,
        "[RUNTIME][INFO] http_server started"
    );

    let listener = match tokio::net::TcpListener::bind(addr).await {
        Ok(listener) => listener,
        Err(e) => {
            error!("[ERROR][FATAL] failed to bind listener on {}: {}", addr, e);
            return Err(e).context("failed to bind TCP listener");
        }
    };

    info!("[BOOT][SUCCESS] Aegis-75 READY");

    if let Err(e) = axum::serve(listener, app).await {
        error!("[ERROR][FATAL] axum server terminated: {e}");
        return Err(e).context("axum server terminated unexpectedly");
    }

    Ok(())
}

fn init_tracing(level: &str) {
    let filter = std::env::var("AEGIS_LOG")
        .or_else(|_| std::env::var("RUST_LOG"))
        .unwrap_or_else(|_| level.to_string());

    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(false)
        .compact()
        .init();
}

fn resolve_bind_addr(config: &Config) -> anyhow::Result<SocketAddr> {
    // 優先順序：
    // 1. config.bind_addr
    // 2. PORT -> 0.0.0.0:{PORT}
    // 3. fallback 0.0.0.0:8080
    let raw_addr = if !config.bind_addr.trim().is_empty() {
        config.bind_addr.clone()
    } else if let Ok(port) = std::env::var("PORT") {
        format!("0.0.0.0:{port}")
    } else {
        "0.0.0.0:8080".to_string()
    };

    match raw_addr.parse::<SocketAddr>() {
        Ok(addr) => Ok(addr),
        Err(primary_err) => {
            warn!(
                "[WARN] invalid bind address '{}': {} ; falling back to 0.0.0.0:8080",
                raw_addr, primary_err
            );
            "0.0.0.0:8080"
                .parse::<SocketAddr>()
                .context("failed to parse fallback bind address")
        }
    }
}

async fn announce_mode(state: &Arc<AppState>) {
    info!(
        role=%state.config.role,
        execution_mode=%state.config.execution_mode,
        market_scope=%state.config.market_scope,
        host_class=%state.config.byoh.host_class,
        hub_mode=%state.config.byoh.hub_mode,
        signing_mode=%state.config.byoh.signing_mode,
        deployment_target=%state.config.deployment.active_target,
        future_target=%state.config.deployment.future_target,
        migration_stage=%state.config.deployment.migration_stage,
        logical_host_id=%state.config.identity.logical_host_id,
        runtime_host_id=%state.config.identity.runtime_host_id,
        "[RUNTIME][INFO] runtime configuration loaded"
    );

    if state.config.zeroclaw_enabled && state.zeroclaw.is_none() {
        warn!("[WARN] ZEROCLAW_ENABLED was set but client could not be initialized");
    }

    if state.config.byoh.enabled {
        info!(
            physical_site=%state.config.byoh.physical_site,
            fixed_ip_expected=state.config.byoh.fixed_ip_expected,
            low_latency_gateway=state.config.byoh.low_latency_gateway_enabled,
            analytics_archive=state.config.byoh.analytics_archive_enabled,
            "[RUNTIME][INFO] BYOH mode enabled"
        );
    }

    if state.config.deployment.active_target.to_string() == "zeabur" && state.config.byoh.enabled {
        warn!(
            future_target=%state.config.deployment.future_target,
            byoh_cutover_ready=state.config.deployment.byoh_cutover_ready,
            physical_host_planned=%state.config.identity.physical_host_planned,
            "[WARN] byoh_enabled=true but running on zeabur (simulation mode)"
        );
    }

    info!(
        "[RUNTIME][INFO] cex_adapter initialized mode={} exchanges={:?}",
        state.config.execution_mode,
        state.config.exchanges
    );

    info!(
        "[RUNTIME][INFO] dex_adapter initialized chains={:?}",
        state.config.dex_networks
    );

    if state.config.zeroclaw_enabled {
        info!("[RUNTIME][INFO] zeroclaw gateway configured");
        let _ = state
            .notify_alert("aegis-75 boot", "Aegis-75 node started successfully")
            .await;
    } else {
        warn!("[RUNTIME][WARN] zeroclaw disabled");
    }
}

fn spawn_heartbeat(state: Arc<AppState>) {
    if !state.config.logging.heartbeat_enabled {
        warn!("[RUNTIME][WARN] heartbeat disabled");
        return;
    }

    let interval_secs = state.config.logging.heartbeat_interval_secs.max(5);

    tokio::spawn(async move {
        let mut interval = tokio::time::interval(Duration::from_secs(interval_secs));
        loop {
            interval.tick().await;
            info!(
                role=%state.config.role,
                deployment=%state.config.deployment.active_target,
                host=%state.config.identity.runtime_host_id,
                status="ok",
                "[RUNTIME][HEARTBEAT] service heartbeat"
            );
        }
    });
}