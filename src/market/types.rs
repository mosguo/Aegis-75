use chrono::{DateTime, Utc};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct VenueQuote {
    pub price: Option<f64>,
    pub updated_at: Option<DateTime<Utc>>,
    pub age_ms: Option<i64>,
    pub status: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct PairSnapshot {
    pub symbol: String,
    pub binance: VenueQuote,
    pub okx: VenueQuote,
    pub spread_abs: Option<f64>,
    pub spread_pct: Option<f64>,
    pub threshold: f64,
    pub arbitrage: Option<bool>,
    pub decision: String,
    pub note: String,
    pub last_refresh_utc: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MarketCache {
    pub feed_status: String,
    pub refresh_interval_secs: u64,
    pub last_cycle_utc: Option<DateTime<Utc>>,
    pub pairs: Vec<PairSnapshot>,
    pub warning: Option<String>,
}

impl MarketCache {
    pub fn bootstrap(symbols: &[String], refresh_interval_secs: u64) -> Self {
        let now = Utc::now();
        Self {
            feed_status: "bootstrapping".to_string(),
            refresh_interval_secs,
            last_cycle_utc: None,
            pairs: symbols
                .iter()
                .map(|s| PairSnapshot {
                    symbol: s.clone(),
                    binance: VenueQuote {
                        price: None,
                        updated_at: None,
                        age_ms: None,
                        status: "pending".to_string(),
                    },
                    okx: VenueQuote {
                        price: None,
                        updated_at: None,
                        age_ms: None,
                        status: "pending".to_string(),
                    },
                    spread_abs: None,
                    spread_pct: None,
                    threshold: 2.0,
                    arbitrage: None,
                    decision: "NO_DATA".to_string(),
                    note: "waiting for first market refresh".to_string(),
                    last_refresh_utc: now,
                })
                .collect(),
            warning: None,
        }
    }
}
