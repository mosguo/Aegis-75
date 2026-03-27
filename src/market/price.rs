use anyhow::{anyhow, Context, Result};
use serde::Deserialize;

#[derive(Debug)]
pub struct BtcUsdtPrices {
    pub binance_price: f64,
    pub okx_price: f64,
}

#[derive(Debug, Deserialize)]
struct BinanceTickerPriceResponse {
    price: String,
}

#[derive(Debug, Deserialize)]
struct OkxTickerResponse {
    data: Vec<OkxTickerItem>,
}

#[derive(Debug, Deserialize)]
struct OkxTickerItem {
    last: String,
}

pub async fn fetch_btcusdt_prices() -> Result<BtcUsdtPrices> {
    let mut builder = reqwest::Client::builder().user_agent("aegis-75/0.1");

    if let Ok(proxy_url) = std::env::var("HTTPS_PROXY").or_else(|_| std::env::var("https_proxy")) {
        builder = builder.proxy(
            reqwest::Proxy::https(&proxy_url)
                .map_err(|e| anyhow!("invalid HTTPS proxy '{}': {}", proxy_url, e))?,
        );
    }

    if let Ok(proxy_url) = std::env::var("HTTP_PROXY").or_else(|_| std::env::var("http_proxy")) {
        builder = builder.proxy(
            reqwest::Proxy::http(&proxy_url)
                .map_err(|e| anyhow!("invalid HTTP proxy '{}': {}", proxy_url, e))?,
        );
    }

    let client = builder
        .build()
        .context("failed to build reqwest client")?;

    let binance_price = fetch_binance_btcusdt(&client).await?;
    let okx_price = fetch_okx_btcusdt(&client).await?;

    Ok(BtcUsdtPrices {
        binance_price,
        okx_price,
    })
}

async fn fetch_binance_btcusdt(client: &reqwest::Client) -> Result<f64> {
    let resp = client
        .get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
        .send()
        .await
        .map_err(|e| anyhow!("failed to call Binance ticker API: {e}"))?
        .error_for_status()
        .context("Binance ticker API returned non-success status")?
        .json::<BinanceTickerPriceResponse>()
        .await
        .context("failed to parse Binance ticker response")?;

    resp.price
        .parse::<f64>()
        .map_err(|e| anyhow!("failed to parse Binance price '{}' as f64: {}", resp.price, e))
}

async fn fetch_okx_btcusdt(client: &reqwest::Client) -> Result<f64> {
    let resp = client
        .get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT")
        .send()
        .await
        .map_err(|e| anyhow!("failed to call OKX ticker API: {e}"))?
        .error_for_status()
        .context("OKX ticker API returned non-success status")?
        .json::<OkxTickerResponse>()
        .await
        .context("failed to parse OKX ticker response")?;

    let first = resp
        .data
        .first()
        .ok_or_else(|| anyhow!("OKX ticker response contained no data items"))?;

    first
        .last
        .parse::<f64>()
        .map_err(|e| anyhow!("failed to parse OKX price '{}' as f64: {}", first.last, e))
}