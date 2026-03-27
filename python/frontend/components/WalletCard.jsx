import { useEffect, useMemo, useState } from "react";

const translations = {
  "zh-TW": {
    wallet: "錢包",
    user: "使用者",
    walletId: "錢包編號",
    balance: "餘額",
    status: "狀態",
    updated: "更新時間",
    depositCurrency: "儲值幣種",
    depositNetwork: "儲值網路",
    depositAddress: "儲值位址",
    addressTag: "地址標籤",
    copyAddress: "複製位址",
    copied: "已複製",
    active: "啟用中",
    loading: "載入中..."
  },
  en: {
    wallet: "Wallet",
    user: "User",
    walletId: "Wallet ID",
    balance: "Balance",
    status: "Status",
    updated: "Updated",
    depositCurrency: "Deposit Currency",
    depositNetwork: "Deposit Network",
    depositAddress: "Deposit Address",
    addressTag: "Address Tag",
    copyAddress: "Copy Address",
    copied: "Copied",
    active: "Active",
    loading: "Loading..."
  }
};

export default function WalletCard({ language = "zh-TW" }) {
  const [wallet, setWallet] = useState(null);
  const [copied, setCopied] = useState(false);
  const t = useMemo(() => translations[language] || translations["zh-TW"], [language]);

  useEffect(() => {
    fetch("/api/dashboard/wallet")
      .then((res) => res.json())
      .then((data) => setWallet(data))
      .catch((err) => console.error("Failed to load wallet:", err));
  }, []);

  const copyAddress = async () => {
    if (!wallet?.depositAddress) return;
    await navigator.clipboard.writeText(wallet.depositAddress);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  const renderStatus = (status) => {
    if (status === "ACTIVE") return t.active;
    return status;
  };

  if (!wallet) return <div>{t.loading}</div>;

  return (
    <div style={{ border: "1px solid #ccc", borderRadius: "12px", padding: "16px", width: "360px" }}>
      <h3>{t.wallet}</h3>
      <div><strong>{t.user}:</strong> {wallet.userId}</div>
      <div><strong>{t.walletId}:</strong> {wallet.walletId}</div>
      <div><strong>{t.balance}:</strong> {wallet.currency} {Number(wallet.balance).toLocaleString()}</div>
      <div><strong>{t.status}:</strong> {renderStatus(wallet.status)}</div>
      <div><strong>{t.updated}:</strong> {wallet.updatedAt}</div>
      <hr />
      <div><strong>{t.depositCurrency}:</strong> {wallet.depositCurrency}</div>
      <div><strong>{t.depositNetwork}:</strong> {wallet.depositNetwork || "-"}</div>
      <div style={{ marginTop: "8px" }}>
        <strong>{t.depositAddress}:</strong>
        <div style={{ marginTop: "6px", padding: "10px", border: "1px solid #ddd", borderRadius: "8px", background: "#fafafa", wordBreak: "break-all", fontFamily: "monospace" }}>
          {wallet.depositAddress || "-"}
        </div>
      </div>
      <div style={{ marginTop: "8px" }}>
        <button onClick={copyAddress} style={{ border: "1px solid #ccc", borderRadius: "8px", padding: "8px 12px", cursor: "pointer" }}>
          {copied ? t.copied : t.copyAddress}
        </button>
      </div>
      {!!wallet.addressTag && <div style={{ marginTop: "8px" }}><strong>{t.addressTag}:</strong> {wallet.addressTag}</div>}
    </div>
  );
}
