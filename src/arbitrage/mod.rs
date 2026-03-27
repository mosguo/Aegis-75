use tracing::info;

use crate::market::price::fetch_btcusdt_prices;

pub async fn evaluate() -> anyhow::Result<serde_json::Value> {
    let prices = fetch_btcusdt_prices().await?;

    let spread = (prices.binance_price - prices.okx_price).abs();
    let threshold = 2.0_f64;

    let (decision, arbitrage) = if spread > threshold {
        if prices.binance_price > prices.okx_price {
            ("BUY_OKX_SELL_BINANCE", true)
        } else {
            ("BUY_BINANCE_SELL_OKX", true)
        }
    } else {
        ("NO_ACTION", false)
    };

    info!(
        "[RUNTIME][ARBITRAGE] symbol=BTCUSDT binance={} okx={} spread={} threshold={} decision={}",
        prices.binance_price,
        prices.okx_price,
        spread,
        threshold,
        decision
    );

    Ok(serde_json::json!({
        "symbol": "BTCUSDT",
        "binance_price": prices.binance_price,
        "okx_price": prices.okx_price,
        "spread": spread,
        "threshold": threshold,
        "arbitrage": arbitrage,
        "decision": decision,
        "execution_mode": "paper",
        "note": "real-price arbitrage evaluated; execution remains simulated only"
    }))
}