use anyhow::{anyhow, Context, Result};
use chrono::Utc;
use serde::Deserialize;

use super::types::{PairSnapshot, VenueQuote};

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
    let snapshot = fetch_pair_prices("BTCUSDT").await?;
    Ok(BtcUsdtPrices {
        binance_price: snapshot.binance.price.ok_or_else(|| anyhow!("missing Binance BTCUSDT price"))?,
        okx_price: snapshot.okx.price.ok_or_else(|| anyhow!("missing OKX BTCUSDT price"))?,
    })
}

pub async fn fetch_pair_prices(symbol: &str) -> Result<PairSnapshot> {
    let client = build_client()?;
    let binance_price = fetch_binance_symbol(&client, symbol).await?;
    let okx_price = fetch_okx_symbol(&client, symbol).await?;

    let now = Utc::now();
    let spread_abs = (binance_price - okx_price).abs();
    let mid = (binance_price + okx_price) / 2.0;
    let spread_pct = if mid > 0.0 { Some(spread_abs / mid * 100.0) } else { None };
    let threshold = 2.0;

    let (decision, arbitrage) = if spread_abs > threshold {
        if binance_price > okx_price {
            ("BUY_OKX_SELL_BINANCE".to_string(), Some(true))
        } else {
            ("BUY_BINANCE_SELL_OKX".to_string(), Some(true))
        }
    } else {
        ("NO_ACTION".to_string(), Some(false))
    };

    Ok(PairSnapshot {
        symbol: symbol.to_string(),
        binance: VenueQuote {
            price: Some(binance_price),
            updated_at: Some(now),
            age_ms: Some(0),
            status: "connected".to_string(),
        },
        okx: VenueQuote {
            price: Some(okx_price),
            updated_at: Some(now),
            age_ms: Some(0),
            status: "connected".to_string(),
        },
        spread_abs: Some(spread_abs),
        spread_pct,
        threshold,
        arbitrage,
        decision,
        note: "real-price pair snapshot updated; execution remains simulated".to_string(),
        last_refresh_utc: now,
    })
}

fn build_client() -> Result<reqwest::Client> {
    let mut builder = reqwest::Client::builder().user_agent("aegis-75/0.2");

    if let Ok(proxy_url) = std::env::var("HTTPS_PROXY").or_else(|_| std::env::var("https_proxy")) {
        if !proxy_url.trim().is_empty() {
            builder = builder.proxy(
                reqwest::Proxy::https(&proxy_url)
                    .map_err(|e| anyhow!("invalid HTTPS proxy '{}': {}", proxy_url, e))?,
            );
        }
    }

    if let Ok(proxy_url) = std::env::var("HTTP_PROXY").or_else(|_| std::env::var("http_proxy")) {
        if !proxy_url.trim().is_empty() {
            builder = builder.proxy(
                reqwest::Proxy::http(&proxy_url)
                    .map_err(|e| anyhow!("invalid HTTP proxy '{}': {}", proxy_url, e))?,
            );
        }
    }

    builder.build().context("failed to build reqwest client")
}

async fn fetch_binance_symbol(client: &reqwest::Client, symbol: &str) -> Result<f64> {
    let url = format!("https://api.binance.com/api/v3/ticker/price?symbol={symbol}");
    let resp = client
        .get(url)
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

async fn fetch_okx_symbol(client: &reqwest::Client, symbol: &str) -> Result<f64> {
    let inst_id = okx_inst_id(symbol)?;
    let url = format!("https://www.okx.com/api/v5/market/ticker?instId={inst_id}");
    let resp = client
        .get(url)
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

fn okx_inst_id(symbol: &str) -> Result<String> {
    let upper = symbol.to_ascii_uppercase();
    if let Some((base, quote)) = upper.split_once("USDT") {
        if !base.is_empty() && quote.is_empty() {
            return Ok(format!("{base}-USDT"));
        }
    }
    Err(anyhow!("unsupported symbol for OKX instId conversion: {symbol}"))
}
