use anyhow::{Context, Result};
use reqwest::header::{AUTHORIZATION, CONTENT_TYPE};
use serde_json::json;
use tracing::info;
use url::Url;

use crate::{core::config::Config, types::alerts::AlertPayload};

#[derive(Clone)]
pub struct ZeroClawClient {
    client: reqwest::Client,
    endpoint: Url,
    api_key: Option<String>,
    model: String,
}

impl ZeroClawClient {
    pub fn from_config(config: &Config) -> Result<Self> {
        let endpoint = config
            .zeroclaw_gateway_url
            .clone()
            .context("ZEROCLAW_GATEWAY_URL is required when ZEROCLAW_ENABLED=true")?;

        Ok(Self {
            client: reqwest::Client::new(),
            endpoint,
            api_key: config.zeroclaw_api_key.clone(),
            model: config.zeroclaw_model.clone(),
        })
    }

    pub async fn send_alert(&self, payload: AlertPayload) -> Result<()> {
        let body = json!({
            "model": self.model,
            "channel": payload.channel,
            "message": {
                "title": payload.title,
                "body": payload.body,
                "node_id": payload.node_id,
                "region": payload.region,
                "timestamp_utc": payload.timestamp_utc,
                "metadata": payload.metadata,
            }
        });

        let mut request = self
            .client
            .post(self.endpoint.clone())
            .header(CONTENT_TYPE, "application/json")
            .json(&body);

        if let Some(key) = &self.api_key {
            request = request.header(AUTHORIZATION, format!("Bearer {key}"));
        }

        let response = request.send().await?;
        info!(status=%response.status(), "zeroclaw gateway response received");
        response.error_for_status()?;
        Ok(())
    }
}
