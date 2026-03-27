use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlertPayload {
    pub node_id: String,
    pub region: String,
    pub channel: String,
    pub title: String,
    pub body: String,
    pub timestamp_utc: DateTime<Utc>,
    pub metadata: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestAlertRequest {
    pub title: String,
    pub body: String,
}
