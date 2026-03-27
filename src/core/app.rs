use std::sync::Arc;

use chrono::Utc;
use serde_json::json;
use tracing::{info, warn};

use crate::{
    control::zeroclaw::ZeroClawClient,
    dex::router::DexRouter,
    execution::router::ExecutionRouter,
    market::cache::SharedMarketCache,
    types::alerts::AlertPayload,
};

use super::config::Config;

#[derive(Clone)]
pub struct AppState {
    pub config: Config,
    pub execution: ExecutionRouter,
    pub dex: DexRouter,
    pub zeroclaw: Option<Arc<ZeroClawClient>>,
    pub market_cache: SharedMarketCache,
}

impl AppState {
    pub fn new(
        config: Config,
        execution: ExecutionRouter,
        dex: DexRouter,
        zeroclaw: Option<ZeroClawClient>,
        market_cache: SharedMarketCache,
    ) -> Self {
        Self {
            config,
            execution,
            dex,
            zeroclaw: zeroclaw.map(Arc::new),
            market_cache,
        }
    }

    pub async fn notify_alert(&self, title: &str, body: &str) -> anyhow::Result<()> {
        let Some(client) = &self.zeroclaw else {
            warn!("alert requested but zeroclaw is disabled");
            return Ok(());
        };

        let payload = AlertPayload {
            node_id: self.config.node_id.clone(),
            region: self.config.region.clone(),
            channel: self.config.zeroclaw_channel.clone(),
            title: title.to_string(),
            body: body.to_string(),
            timestamp_utc: Utc::now(),
            metadata: json!({
                "role": self.config.role.to_string(),
                "cluster": self.config.cluster,
                "market_scope": self.config.market_scope,
                "host_class": self.config.byoh.host_class.to_string(),
                "hub_mode": self.config.byoh.hub_mode.to_string(),
                "signing_mode": self.config.byoh.signing_mode.to_string(),
                "deployment_target": self.config.deployment.active_target.to_string(),
                "future_target": self.config.deployment.future_target.to_string(),
                "migration_stage": self.config.deployment.migration_stage,
                "logical_host_id": self.config.identity.logical_host_id,
                "runtime_host_id": self.config.identity.runtime_host_id,
                "logical_site": self.config.identity.logical_site,
            }),
        };

        info!(title, "sending alert through zeroclaw gateway");
        client.send_alert(payload).await
    }

    pub fn runtime_capabilities(&self) -> serde_json::Value {
        json!({
            "service": "aegis-75",
            "role": self.config.role.to_string(),
            "execution_mode": self.config.execution_mode.to_string(),
            "host_class": self.config.byoh.host_class.to_string(),
            "hub_mode": self.config.byoh.hub_mode.to_string(),
            "deployment_target": self.config.deployment.active_target.to_string(),
            "future_target": self.config.deployment.future_target.to_string(),
            "migration_stage": self.config.deployment.migration_stage,
            "zeabur_compatible": self.config.deployment.zeabur_compatible,
            "byoh_cutover_ready": self.config.deployment.byoh_cutover_ready,
            "identity_source": self.config.identity.source.to_string(),
            "logical_host_id": self.config.identity.logical_host_id,
            "runtime_host_id": self.config.identity.runtime_host_id,
            "logical_site": self.config.identity.logical_site,
            "physical_host_planned": self.config.identity.physical_host_planned,
            "physical_host_id": self.config.identity.physical_host_id,
            "low_latency_gateway": self.config.byoh.low_latency_gateway_enabled,
            "market_data_ws": self.config.byoh.market_data_ws_enabled,
            "private_analytics_archive": self.config.byoh.analytics_archive_enabled,
            "signing_mode": self.config.byoh.signing_mode.to_string(),
            "zero_copy_requested": self.config.tuning.zero_copy_requested,
            "hugepages_requested": self.config.tuning.hugepages_requested,
            "cpu_affinity_requested": self.config.tuning.cpu_affinity_requested,
            "cpu_affinity_cores": self.config.tuning.cpu_affinity_cores,
            "data_lake_path": self.config.byoh.data_lake_path,
            "zeroclaw_enabled": self.config.zeroclaw_enabled,
        })
    }
}
