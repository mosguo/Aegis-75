import { useState } from "react";
import WalletCard from "./WalletCard";
import TradingPairTable from "./TradingPairTable";

export default function Dashboard() {
  const [language, setLanguage] = useState(localStorage.getItem("dashboardLanguage") || "zh-TW");

  const onLanguageChange = (e) => {
    const value = e.target.value;
    setLanguage(value);
    localStorage.setItem("dashboardLanguage", value);
  };

  return (
    <div style={{ padding: "24px", fontFamily: "Arial, sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <h1>Aegis-75 Dashboard</h1>
        <div>
          <select value={language} onChange={onLanguageChange}>
            <option value="zh-TW">中文</option>
            <option value="en">English</option>
          </select>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: "20px" }}>
        <WalletCard language={language} />
        <TradingPairTable language={language} />
      </div>
    </div>
  );
}
