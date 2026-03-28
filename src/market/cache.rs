use std::{fs, path::PathBuf, sync::Arc};

use chrono::Utc;
use serde::Deserialize;
use tokio::sync::RwLock;
use tracing::{info, warn};

use crate::{core::config::Config, market::price::fetch_pair_prices};

use super::types::{MarketCache, PairSnapshot, VenueQuote};

pub type SharedMarketCache = Arc<RwLock<MarketCache>>;

pub fn default_symbols() -> Vec<String> {
    let configured = load_tracked_symbols();
    if !configured.is_empty() {
        return configured;
    }

    vec![
        "BTCUSDT".to_string(),
        "ETHUSDT".to_string(),
        "SOLUSDT".to_string(),
    ]
}

pub fn new_shared_cache(refresh_interval_secs: u64) -> SharedMarketCache {
    Arc::new(RwLock::new(MarketCache::bootstrap(
        &default_symbols(),
        refresh_interval_secs,
    )))
}

pub fn spawn_market_refresh(config: Config, cache: SharedMarketCache) {
    tokio::spawn(async move {
        let refresh_interval_secs = {
            let guard = cache.read().await;
            guard.refresh_interval_secs.max(2)
        };

        let mut interval =
            tokio::time::interval(std::time::Duration::from_secs(refresh_interval_secs));

        loop {
            interval.tick().await;

            match refresh_once(&config, &cache).await {
                Ok(count) => info!(
                    refresh_interval_secs,
                    pairs = count,
                    "[RUNTIME][FEED] market cache refresh completed"
                ),
                Err(err) => warn!("[RUNTIME][FEED] market cache refresh failed: {err}"),
            }
        }
    });
}

async fn refresh_once(config: &Config, cache: &SharedMarketCache) -> anyhow::Result<usize> {
    let tracked_symbols = load_tracked_symbols();
    let symbols = {
        let guard = cache.read().await;
        let existing = guard
            .pairs
            .iter()
            .map(|p| p.symbol.clone())
            .collect::<Vec<_>>();
        if tracked_symbols.is_empty() {
            existing
        } else {
            tracked_symbols
        }
    };

    let mut refreshed = Vec::with_capacity(symbols.len());
    let mut warning: Option<String> = None;

    for symbol in symbols {
        match fetch_pair_prices(&symbol).await {
            Ok(prices) => refreshed.push(prices),
            Err(e) => {
                warning = Some(format!("price refresh failed for {symbol}: {e}"));
                refreshed.push(PairSnapshot {
                    symbol: symbol.clone(),
                    binance: VenueQuote {
                        price: None,
                        updated_at: None,
                        age_ms: None,
                        status: "down".to_string(),
                    },
                    okx: VenueQuote {
                        price: None,
                        updated_at: None,
                        age_ms: None,
                        status: "down".to_string(),
                    },
                    spread_abs: None,
                    spread_pct: None,
                    threshold: 2.0,
                    arbitrage: None,
                    decision: "NO_DATA".to_string(),
                    note: format!("real price fetch failed: {e}"),
                    last_refresh_utc: Utc::now(),
                });
            }
        }
    }

    let status = if refreshed.iter().any(|p| p.arbitrage.is_some()) {
        "ok"
    } else {
        "degraded"
    };

    let mut guard = cache.write().await;
    guard.feed_status = status.to_string();
    guard.last_cycle_utc = Some(Utc::now());
    guard.warning = warning;
    guard.pairs = refreshed;

    let _ = config; // reserved for future config-driven filters

    Ok(guard.pairs.len())
}

const DEFAULT_PAIR_CONFIG_PATH: &str = "python/data/trading_pairs.json";

#[derive(Debug, Deserialize)]
struct TradingPairFile {
    #[serde(default)]
    pairs: Vec<TradingPairConfig>,
}

#[derive(Debug, Deserialize)]
struct TradingPairConfig {
    symbol: String,
}

fn load_tracked_symbols() -> Vec<String> {
    let path = pair_config_path();
    let Ok(raw) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(payload) = serde_json::from_str::<TradingPairFile>(&raw) else {
        return Vec::new();
    };

    payload
        .pairs
        .into_iter()
        .map(|pair| pair.symbol.trim().to_ascii_uppercase())
        .filter(|symbol| !symbol.is_empty())
        .collect()
}

fn pair_config_path() -> PathBuf {
    if let Ok(path) = std::env::var("AEGIS_PAIR_CONFIG_PATH") {
        let trimmed = path.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    PathBuf::from(DEFAULT_PAIR_CONFIG_PATH)
}
