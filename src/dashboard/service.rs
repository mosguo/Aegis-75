use std::collections::HashMap;

use chrono::Utc;
use serde::Serialize;

use crate::{
    core::app::AppState,
    dashboard::pair_config::{load_pair_configs, TradingPairConfig},
    market::types::PairSnapshot,
};

const DEFAULT_EXECUTION_SPREAD_MULTIPLIER: f64 = 1.2;

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
    pub trade_notional_usdt: f64,
    pub estimated_profit_usdt: Option<f64>,
    pub minimum_spread_pct: f64,
    pub execution_spread_pct: f64,
    pub fee_cost_usdt: f64,
    pub threshold: f64,
    pub arbitrage: Option<bool>,
    pub decision: String,
    pub live_arbitrage: Option<bool>,
    pub live_decision: String,
    pub auto_trigger: bool,
    pub execution_mode: String,
    pub age_ms: Option<i64>,
    pub last_refresh_utc: String,
    pub note: String,
}

pub async fn build_summary(state: &AppState) -> DashboardSummary {
    let now = Utc::now().to_rfc3339();
    let cache = state.market_cache.read().await;
    let pair_configs = load_pair_configs();
    let status = if cache.feed_status == "ok" { "ok" } else { "degraded" }.to_string();
    let pairs = cache
        .pairs
        .iter()
        .map(|pair| pair_to_view(pair, &pair_configs))
        .collect::<Vec<_>>();
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

fn pair_to_view(p: &PairSnapshot, pair_configs: &HashMap<String, TradingPairConfig>) -> PairView {
    let age_ms = match (p.binance.age_ms, p.okx.age_ms) {
        (Some(a), Some(b)) => Some(a.max(b)),
        (Some(a), None) => Some(a),
        (None, Some(b)) => Some(b),
        (None, None) => None,
    };
    let config = pair_configs.get(&p.symbol.to_ascii_uppercase());
    let trade_notional_usdt = 300.0;
    let threshold = config
        .and_then(|cfg| cfg.spread_threshold)
        .unwrap_or(p.threshold);
    let auto_trigger = config.and_then(|cfg| cfg.auto_trigger).unwrap_or(false);
    let execution_mode = config
        .and_then(|cfg| cfg.execution_mode.clone())
        .unwrap_or_else(|| "SIMULATION".to_string());
    let status = config
        .and_then(|cfg| cfg.status.as_deref())
        .unwrap_or("ACTIVE");
    let minimum_spread_pct = combined_minimum_spread_pct("binance", "okx");
    let execution_spread_pct = minimum_spread_pct * DEFAULT_EXECUTION_SPREAD_MULTIPLIER;
    let fee_cost_usdt = trade_notional_usdt * (minimum_spread_pct / 100.0);
    let estimated_profit_usdt = estimate_profit_usdt(p, trade_notional_usdt, fee_cost_usdt);
    let (decision, arbitrage) =
        resolve_effective_signal(p, threshold, status, execution_spread_pct, estimated_profit_usdt);
    let note = build_note(p, config, &decision);

    PairView {
        symbol: p.symbol.clone(),
        binance_price: p.binance.price,
        okx_price: p.okx.price,
        spread_abs: p.spread_abs,
        spread_pct: p.spread_pct,
        trade_notional_usdt,
        estimated_profit_usdt,
        minimum_spread_pct,
        execution_spread_pct,
        fee_cost_usdt,
        threshold,
        arbitrage,
        decision,
        live_arbitrage: p.arbitrage,
        live_decision: p.decision.clone(),
        auto_trigger,
        execution_mode,
        age_ms,
        last_refresh_utc: p.last_refresh_utc.to_rfc3339(),
        note,
    }
}

fn estimate_profit_usdt(pair: &PairSnapshot, trade_notional_usdt: f64, fee_cost_usdt: f64) -> Option<f64> {
    let binance_price = pair.binance.price?;
    let okx_price = pair.okx.price?;
    let spread_abs = pair.spread_abs?;

    let entry_price = binance_price.min(okx_price);
    if entry_price <= 0.0 {
        return None;
    }

    let gross_profit = if spread_abs > 0.0 {
        (trade_notional_usdt / entry_price) * spread_abs
    } else {
        0.0
    };
    Some(gross_profit - fee_cost_usdt)
}

fn resolve_effective_signal(
    pair: &PairSnapshot,
    _threshold: f64,
    status: &str,
    execution_spread_pct: f64,
    estimated_profit_usdt: Option<f64>,
) -> (String, Option<bool>) {
    let Some(binance_price) = pair.binance.price else {
        return ("NO_DATA".to_string(), None);
    };
    let Some(okx_price) = pair.okx.price else {
        return ("NO_DATA".to_string(), None);
    };
    let Some(spread_abs) = pair.spread_abs else {
        return ("NO_DATA".to_string(), None);
    };

    if !status.eq_ignore_ascii_case("ACTIVE") {
        return ("INACTIVE".to_string(), Some(false));
    }
    if spread_abs <= 0.0 {
        return ("NO_ACTION".to_string(), Some(false));
    }
    if pair.spread_pct.unwrap_or_default() < execution_spread_pct {
        return ("NO_ACTION".to_string(), Some(false));
    }
    if estimated_profit_usdt.unwrap_or_default() <= 0.0 {
        return ("NO_ACTION".to_string(), Some(false));
    }
    if binance_price > okx_price {
        return ("BUY_OKX_SELL_BINANCE".to_string(), Some(true));
    }
    if okx_price > binance_price {
        return ("BUY_BINANCE_SELL_OKX".to_string(), Some(true));
    }

    ("NO_ACTION".to_string(), Some(false))
}

fn combined_minimum_spread_pct(cex_a_name: &str, cex_b_name: &str) -> f64 {
    venue_minimum_spread_pct(cex_a_name) + venue_minimum_spread_pct(cex_b_name)
}

fn venue_minimum_spread_pct(venue_name: &str) -> f64 {
    match venue_name {
        "binance" => 0.1,
        "bybit" => 0.06,
        "okx" => 0.05,
        "coinbase" => 0.6,
        "kraken" => 0.26,
        "bitget" => 0.1,
        _ => 0.1,
    }
}

fn build_note(pair: &PairSnapshot, config: Option<&TradingPairConfig>, decision: &str) -> String {
    let threshold_note = config
        .and_then(|cfg| cfg.spread_threshold)
        .map(|value| format!("pair config threshold applied={value:.4}"))
        .unwrap_or_else(|| format!("default threshold applied={:.4}", pair.threshold));

    format!(
        "{}; live_decision={}; effective_decision={decision}",
        threshold_note, pair.decision
    )
}
