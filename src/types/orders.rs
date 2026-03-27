use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OrderSide {
    Buy,
    Sell,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OrderKind {
    Market,
    Limit,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderIntent {
    pub symbol: String,
    pub side: OrderSide,
    pub amount: f64,
    pub kind: OrderKind,
    #[serde(default)]
    pub venue_preference: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RouteDecision {
    pub venue: String,
    pub node_id: String,
    pub region: String,
    pub cluster: String,
    pub market_scope: String,
    pub host_class: String,
    pub hub_mode: String,
    pub deployment_target: String,
    pub future_target: String,
    pub logical_host_id: String,
    pub runtime_host_id: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderPlan {
    pub symbol: String,
    pub side: OrderSide,
    pub amount: f64,
    pub kind: OrderKind,
    pub route: RouteDecision,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderSimulationResponse {
    pub request_id: Uuid,
    pub accepted: bool,
    pub accepted_by_role: String,
    pub execution_mode: String,
    pub timestamp_utc: DateTime<Utc>,
    pub plan: OrderPlan,
    pub note: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DexSimulationRequest {
    pub symbol: String,
    pub amount: f64,
    #[serde(default)]
    pub network: Option<String>,
    #[serde(default)]
    pub router: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DexSimulationResponse {
    pub request_id: Uuid,
    pub timestamp_utc: DateTime<Utc>,
    pub network: String,
    pub node_id: String,
    pub region: String,
    pub host_class: String,
    pub hub_mode: String,
    pub deployment_target: String,
    pub future_target: String,
    pub logical_host_id: String,
    pub runtime_host_id: String,
    pub router: String,
    pub symbol: String,
    pub amount: f64,
    pub note: String,
}
