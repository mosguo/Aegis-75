use chrono::Utc;
use tracing::info;
use uuid::Uuid;

use crate::{core::config::Config, types::orders::{DexSimulationRequest, DexSimulationResponse}};

#[derive(Clone)]
pub struct DexRouter {
    config: Config,
}

impl DexRouter {
    pub fn new(config: Config) -> Self {
        Self { config }
    }

    pub fn simulate(&self, request: DexSimulationRequest) -> DexSimulationResponse {
        let network = request
            .network
            .clone()
            .filter(|n| self.config.dex_networks.contains(n))
            .unwrap_or_else(|| self.config.dex_networks.first().cloned().unwrap_or_else(|| "ethereum".to_string()));

        let note = if self.config.byoh.enabled && self.config.deployment.active_target.to_string() == "zeabur" {
            "DEX path simulated only; BYOH semantics are enabled through environment-defined identity while the service still runs on Zeabur before physical-host migration.".to_string()
        } else if self.config.byoh.enabled {
            "DEX path simulated only; no on-chain transaction is signed in this scaffold. BYOH hub is reserved for private analytics, signing, and archival workloads.".to_string()
        } else {
            "DEX path simulated only; no on-chain transaction is signed in this scaffold".to_string()
        };

        info!(
            "[RUNTIME][DEX] simulate chain={} pair={} amount={} router={} host={}",
            network,
            request.symbol,
            request.amount,
            request.router.clone().unwrap_or_else(|| "auto".to_string()),
            self.config.identity.runtime_host_id
        );

        DexSimulationResponse {
            request_id: Uuid::new_v4(),
            timestamp_utc: Utc::now(),
            network,
            node_id: self.config.node_id.clone(),
            region: self.config.region.clone(),
            host_class: self.config.byoh.host_class.to_string(),
            hub_mode: self.config.byoh.hub_mode.to_string(),
            deployment_target: self.config.deployment.active_target.to_string(),
            future_target: self.config.deployment.future_target.to_string(),
            logical_host_id: self.config.identity.logical_host_id.clone(),
            runtime_host_id: self.config.identity.runtime_host_id.clone(),
            router: request.router.unwrap_or_else(|| "auto".to_string()),
            symbol: request.symbol,
            amount: request.amount,
            note,
        }
    }
}
