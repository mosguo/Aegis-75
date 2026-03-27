use chrono::Utc;
use tracing::{info, warn};
use uuid::Uuid;

use crate::{
    core::config::{Config, ExecutionMode, Role},
    types::orders::{OrderIntent, OrderPlan, OrderSimulationResponse, RouteDecision},
};

#[derive(Clone)]
pub struct ExecutionRouter {
    config: Config,
}

impl ExecutionRouter {
    pub fn new(config: Config) -> Self {
        Self { config }
    }

    pub fn simulate(&self, intent: OrderIntent) -> OrderSimulationResponse {
        let route = self.pick_route(&intent);
        let accepted = match self.config.role {
            Role::ControlPlane => false,
            Role::ExecutionCore | Role::TradingUnit | Role::Hybrid => true,
        };

        let mode = match self.config.execution_mode {
            ExecutionMode::Paper => "paper",
            ExecutionMode::Live => "live",
        };

        let note = if accepted {
            if self.config.byoh.enabled && self.config.deployment.active_target.to_string() == "zeabur" {
                "simulated successfully; BYOH profile is currently validated on Zeabur and can later cut over to the physical host without changing runtime role semantics".to_string()
            } else if self.config.byoh.enabled {
                "simulated successfully; BYOH data & execution hub is the preferred signing and low-latency path".to_string()
            } else {
                "simulated successfully".to_string()
            }
        } else {
            "role is control-plane; order accepted only for validation, not for execution".to_string()
        };

        if accepted {
            info!(
                "[RUNTIME][ORDER] simulate cex={} pair={} amount={} mode={} host={} latency=simulated",
                route.venue,
                intent.symbol,
                intent.amount,
                mode,
                self.config.identity.runtime_host_id
            );
        } else {
            warn!(
                "[RUNTIME][ORDER] validation-only pair={} role={} host={}",
                intent.symbol,
                self.config.role,
                self.config.identity.runtime_host_id
            );
        }

        OrderSimulationResponse {
            request_id: Uuid::new_v4(),
            accepted,
            accepted_by_role: self.config.role.to_string(),
            execution_mode: mode.to_string(),
            timestamp_utc: Utc::now(),
            plan: OrderPlan {
                symbol: intent.symbol,
                side: intent.side,
                amount: intent.amount,
                kind: intent.kind,
                route,
            },
            note,
        }
    }

    fn pick_route(&self, intent: &OrderIntent) -> RouteDecision {
        let requested = intent.venue_preference.clone();
        let venue = requested
            .filter(|p| self.config.exchanges.contains(p))
            .unwrap_or_else(|| self.config.exchanges.first().cloned().unwrap_or_else(|| "binance".to_string()));

        let reason = if self.config.byoh.enabled && self.config.deployment.active_target.to_string() == "zeabur" {
            "selected from configured CEX list; BYOH hub semantics are active, but the node is still running on Zeabur for pre-cutover validation".to_string()
        } else if self.config.byoh.enabled {
            "selected from configured CEX list; BYOH hub preferred for websocket persistence, signing, and low-latency execution".to_string()
        } else {
            "selected from configured CEX list and current runtime role".to_string()
        };

        RouteDecision {
            venue,
            node_id: self.config.node_id.clone(),
            region: self.config.region.clone(),
            cluster: self.config.cluster.clone(),
            market_scope: self.config.market_scope.clone(),
            host_class: self.config.byoh.host_class.to_string(),
            hub_mode: self.config.byoh.hub_mode.to_string(),
            deployment_target: self.config.deployment.active_target.to_string(),
            future_target: self.config.deployment.future_target.to_string(),
            logical_host_id: self.config.identity.logical_host_id.clone(),
            runtime_host_id: self.config.identity.runtime_host_id.clone(),
            reason,
        }
    }
}
