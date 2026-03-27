import { useEffect, useMemo, useState } from "react";

function Switch({ checked, onChange }) {
  return (
    <div
      onClick={() => onChange(!checked)}
      style={{ width: "50px", height: "26px", borderRadius: "13px", backgroundColor: checked ? "#4CAF50" : "#ccc", position: "relative", cursor: "pointer", transition: "0.2s" }}
    >
      <div
        style={{ width: "22px", height: "22px", borderRadius: "50%", backgroundColor: "#fff", position: "absolute", top: "2px", left: checked ? "26px" : "2px", transition: "0.2s" }}
      />
    </div>
  );
}

const translations = {
  "zh-TW": {
    tradingPair: "交易對",
    symbol: "代號",
    threshold: "觸發價差",
    autoTrigger: "自動觸發",
    executionMode: "執行模式",
    save: "儲存",
    active: "啟用中",
    simulation: "模擬",
    live: "實盤",
    saved: "已儲存"
  },
  en: {
    tradingPair: "Trading Pair",
    symbol: "Symbol",
    threshold: "Spread Threshold",
    autoTrigger: "Auto Trigger",
    executionMode: "Execution Mode",
    save: "Save",
    active: "Active",
    simulation: "Simulation",
    live: "Live",
    saved: "Saved"
  }
};

export default function TradingPairTable({ language = "zh-TW" }) {
  const [pairs, setPairs] = useState([]);
  const [savedSymbol, setSavedSymbol] = useState("");
  const t = useMemo(() => translations[language] || translations["zh-TW"], [language]);

  useEffect(() => {
    fetch("/api/dashboard/trading-pairs")
      .then((res) => res.json())
      .then((data) => setPairs(data.pairs || []))
      .catch((err) => console.error("Failed to load pairs:", err));
  }, []);

  const updateLocal = (symbol, patch) => {
    setPairs((prev) => prev.map((p) => (p.symbol === symbol ? { ...p, ...patch } : p)));
  };

  const savePair = async (pair) => {
    const res = await fetch("/api/dashboard/trading-pairs/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: pair.symbol,
        spreadThreshold: Number(pair.spreadThreshold),
        autoTrigger: !!pair.autoTrigger,
        executionMode: pair.executionMode
      })
    });
    if (!res.ok) {
      const err = await res.json();
      alert(err.detail || "Save failed");
      return;
    }
    setSavedSymbol(pair.symbol);
    setTimeout(() => setSavedSymbol(""), 1200);
  };

  return (
    <div style={{ border: "1px solid #ccc", borderRadius: "12px", padding: "16px" }}>
      <h3>{t.tradingPair}</h3>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th align="left">{t.symbol}</th>
            <th align="left">{t.threshold}</th>
            <th align="left">{t.autoTrigger}</th>
            <th align="left">{t.executionMode}</th>
            <th align="left">Status</th>
            <th align="left">Action</th>
          </tr>
        </thead>
        <tbody>
          {pairs.map((pair) => (
            <tr key={pair.symbol}>
              <td style={{ padding: "10px 6px" }}>{pair.symbol}</td>
              <td style={{ padding: "10px 6px" }}>
                <input type="number" min="0" value={pair.spreadThreshold} onChange={(e) => updateLocal(pair.symbol, { spreadThreshold: e.target.value })} style={{ width: "100px" }} />
              </td>
              <td style={{ padding: "10px 6px" }}>
                <Switch checked={!!pair.autoTrigger} onChange={(value) => updateLocal(pair.symbol, { autoTrigger: value })} />
              </td>
              <td style={{ padding: "10px 6px" }}>
                <select value={pair.executionMode || "SIMULATION"} onChange={(e) => updateLocal(pair.symbol, { executionMode: e.target.value })}>
                  <option value="SIMULATION">{t.simulation}</option>
                  <option value="LIVE">{t.live}</option>
                </select>
              </td>
              <td style={{ padding: "10px 6px" }}>{pair.status === "ACTIVE" ? t.active : pair.status}</td>
              <td style={{ padding: "10px 6px" }}>
                <button onClick={() => savePair(pair)} style={{ border: "1px solid #ccc", borderRadius: "8px", padding: "8px 12px", cursor: "pointer" }}>
                  {savedSymbol === pair.symbol ? t.saved : t.save}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
