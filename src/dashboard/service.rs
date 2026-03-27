use chrono::Utc;
use serde::Serialize;

use crate::{core::app::AppState, market::types::PairSnapshot};

#[derive(Debug, Clone, Serialize)]
pub struct DashboardSummary {
    pub service: &'static str,
    pub status: String,
    pub timestamp: String,
    pub system: SystemInfo,
    pub topology: TopologyInfo,
    pub feeds: FeedInfo,
    pub pairs: Vec<PairView>,
    pub note: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SystemInfo {
    pub role: String,
    pub execution_mode: String,
    pub market_scope: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct TopologyInfo {
    pub deployment_target: String,
    pub future_target: String,
    pub host_class: String,
    pub hub_mode: String,
    pub logical_host_id: String,
    pub runtime_host_id: String,
    pub logical_site: String,
    pub region: String,
    pub node_id: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct FeedInfo {
    pub status: String,
    pub refresh_interval_secs: u64,
    pub last_cycle_utc: Option<String>,
    pub warning: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PairView {
    pub symbol: String,
    pub binance_price: Option<f64>,
    pub okx_price: Option<f64>,
    pub spread_abs: Option<f64>,
    pub spread_pct: Option<f64>,
    pub threshold: f64,
    pub arbitrage: Option<bool>,
    pub decision: String,
    pub age_ms: Option<i64>,
    pub last_refresh_utc: String,
    pub note: String,
}

pub async fn build_summary(state: &AppState) -> DashboardSummary {
    let now = Utc::now().to_rfc3339();
    let cache = state.market_cache.read().await;
    let status = if cache.feed_status == "ok" { "ok" } else { "degraded" }.to_string();
    let pairs = cache.pairs.iter().map(pair_to_view).collect::<Vec<_>>();
    let note = cache.warning.clone().unwrap_or_else(|| "live cache ready".to_string());

    DashboardSummary {
        service: "aegis-75",
        status,
        timestamp: now,
        system: SystemInfo {
            role: state.config.role.to_string(),
            execution_mode: state.config.execution_mode.to_string(),
            market_scope: state.config.market_scope.clone(),
        },
        topology: TopologyInfo {
            deployment_target: state.config.deployment.active_target.to_string(),
            future_target: state.config.deployment.future_target.to_string(),
            host_class: state.config.byoh.host_class.to_string(),
            hub_mode: state.config.byoh.hub_mode.to_string(),
            logical_host_id: state.config.identity.logical_host_id.clone(),
            runtime_host_id: state.config.identity.runtime_host_id.clone(),
            logical_site: state.config.identity.logical_site.clone(),
            region: state.config.region.clone(),
            node_id: state.config.node_id.clone(),
        },
        feeds: FeedInfo {
            status: cache.feed_status.clone(),
            refresh_interval_secs: cache.refresh_interval_secs,
            last_cycle_utc: cache.last_cycle_utc.map(|ts| ts.to_rfc3339()),
            warning: cache.warning.clone(),
        },
        pairs,
        note,
    }
}

fn pair_to_view(p: &PairSnapshot) -> PairView {
    let age_ms = match (p.binance.age_ms, p.okx.age_ms) {
        (Some(a), Some(b)) => Some(a.max(b)),
        (Some(a), None) => Some(a),
        (None, Some(b)) => Some(b),
        (None, None) => None,
    };

    PairView {
        symbol: p.symbol.clone(),
        binance_price: p.binance.price,
        okx_price: p.okx.price,
        spread_abs: p.spread_abs,
        spread_pct: p.spread_pct,
        threshold: p.threshold,
        arbitrage: p.arbitrage,
        decision: p.decision.clone(),
        age_ms,
        last_refresh_utc: p.last_refresh_utc.to_rfc3339(),
        note: p.note.clone(),
    }
}
