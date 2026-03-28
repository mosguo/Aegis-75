use std::{collections::HashMap, fs, path::PathBuf};

use serde::Deserialize;

const DEFAULT_PAIR_CONFIG_PATH: &str = "python/data/trading_pairs.json";

#[derive(Debug, Clone, Deserialize)]
struct TradingPairFile {
    #[serde(default)]
    pairs: Vec<TradingPairConfig>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TradingPairConfig {
    pub symbol: String,
    #[serde(rename = "spreadThreshold")]
    pub spread_threshold: Option<f64>,
    #[serde(rename = "autoTrigger")]
    pub auto_trigger: Option<bool>,
    #[serde(rename = "executionMode")]
    pub execution_mode: Option<String>,
    pub status: Option<String>,
}

pub fn load_pair_configs() -> HashMap<String, TradingPairConfig> {
    let path = pair_config_path();
    let Ok(raw) = fs::read_to_string(&path) else {
        return HashMap::new();
    };

    let Ok(file) = serde_json::from_str::<TradingPairFile>(&raw) else {
        return HashMap::new();
    };

    file.pairs
        .into_iter()
        .map(|pair| (pair.symbol.to_ascii_uppercase(), pair))
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
