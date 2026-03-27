pub fn dashboard_html() -> String {
    r#"<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Aegis-75 Dashboard</title>
<style>
body { margin:0; padding:24px; font-family: Inter, Arial, sans-serif; background:#0b1020; color:#eef2ff; }
h1 { margin:0 0 8px; font-size:28px; }
.small { color:#93a0bd; font-size:13px; }
.grid { display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap:16px; margin-top:16px; }
.card { background:#121933; border:1px solid #26304f; border-radius:16px; padding:16px; box-shadow: 0 8px 24px rgba(0,0,0,.2); }
.card h2 { margin:0 0 10px; font-size:14px; color:#9fb0d8; text-transform:uppercase; letter-spacing:.06em; }
.kv { display:grid; grid-template-columns: 1fr auto; gap:8px; font-size:14px; }
.kv div:nth-child(odd) { color:#9fb0d8; }
.value { font-size:24px; font-weight:700; }
.ok { color:#4ade80; }
.warn { color:#fbbf24; }
.bad { color:#f87171; }
table { width:100%; border-collapse:collapse; margin-top:16px; background:#121933; border-radius:16px; overflow:hidden; }
th, td { padding:12px 10px; border-bottom:1px solid #26304f; text-align:left; font-size:14px; }
th { color:#9fb0d8; background:#0f1730; }
.badge { padding:4px 8px; border-radius:999px; font-size:12px; font-weight:700; display:inline-block; }
.badge.ok { background:rgba(74,222,128,.15); }
.badge.warn { background:rgba(251,191,36,.15); }
.badge.bad { background:rgba(248,113,113,.15); }
.footer { margin-top:12px; }
@media (max-width: 960px) { .grid { grid-template-columns:1fr; } }
</style>
</head>
<body>
<h1>Aegis-75 Dashboard</h1>
<div class="small">Live operator console for real-price paper arbitrage validation.</div>
<div class="small" id="updatedAt">Updated: -</div>
<div class="grid">
  <div class="card">
    <h2>System</h2>
    <div class="kv">
      <div>Status</div><div id="statusText">-</div>
      <div>Role</div><div id="role">-</div>
      <div>Execution</div><div id="executionMode">-</div>
      <div>Market Scope</div><div id="marketScope">-</div>
    </div>
  </div>
  <div class="card">
    <h2>Topology</h2>
    <div class="kv">
      <div>Deployment</div><div id="deploymentTarget">-</div>
      <div>Future Target</div><div id="futureTarget">-</div>
      <div>Host Class</div><div id="hostClass">-</div>
      <div>Hub Mode</div><div id="hubMode">-</div>
      <div>Logical Host</div><div id="logicalHost">-</div>
      <div>Runtime Host</div><div id="runtimeHost">-</div>
    </div>
  </div>
  <div class="card">
    <h2>Feeds</h2>
    <div class="kv">
      <div>Feed Status</div><div id="feedStatus">-</div>
      <div>Refresh Interval</div><div id="refreshInterval">-</div>
      <div>Last Cycle</div><div id="lastCycle">-</div>
      <div>Warning</div><div id="warning">-</div>
    </div>
  </div>
</div>
<table>
  <thead>
    <tr>
      <th>Pair</th>
      <th>Binance</th>
      <th>OKX</th>
      <th>Spread</th>
      <th>Spread %</th>
      <th>Decision</th>
      <th>Arbitrage</th>
      <th>Age (ms)</th>
      <th>Last Refresh</th>
    </tr>
  </thead>
  <tbody id="pairsBody"></tbody>
</table>
<div class="footer small" id="note">-</div>
<script>
function num(v, digits=4){ return v===null||v===undefined?'-':Number(v).toFixed(digits); }
function clsFromStatus(v){ if(v===true||v==='ok'||v==='connected') return 'ok'; if(v===false||v==='degraded'||v==='down') return 'bad'; return 'warn'; }
function badge(text, cls){ return `<span class="badge ${cls}">${text}</span>`; }
function render(summary){
  document.getElementById('updatedAt').textContent = 'Updated: ' + summary.timestamp;
  document.getElementById('statusText').innerHTML = badge(summary.status, clsFromStatus(summary.status));
  document.getElementById('role').textContent = summary.system.role;
  document.getElementById('executionMode').textContent = summary.system.execution_mode;
  document.getElementById('marketScope').textContent = summary.system.market_scope;
  document.getElementById('deploymentTarget').textContent = summary.topology.deployment_target;
  document.getElementById('futureTarget').textContent = summary.topology.future_target;
  document.getElementById('hostClass').textContent = summary.topology.host_class;
  document.getElementById('hubMode').textContent = summary.topology.hub_mode;
  document.getElementById('logicalHost').textContent = summary.topology.logical_host_id;
  document.getElementById('runtimeHost').textContent = summary.topology.runtime_host_id;
  document.getElementById('feedStatus').innerHTML = badge(summary.feeds.status, clsFromStatus(summary.feeds.status));
  document.getElementById('refreshInterval').textContent = summary.feeds.refresh_interval_secs + ' sec';
  document.getElementById('lastCycle').textContent = summary.feeds.last_cycle_utc ?? '-';
  document.getElementById('warning').textContent = summary.feeds.warning ?? '-';
  document.getElementById('note').textContent = summary.note ?? '-';
  const tbody = document.getElementById('pairsBody');
  tbody.innerHTML = '';
  for (const pair of summary.pairs) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${pair.symbol}</td>
      <td>${num(pair.binance_price, 4)}</td>
      <td>${num(pair.okx_price, 4)}</td>
      <td>${num(pair.spread_abs, 4)}</td>
      <td>${num(pair.spread_pct, 4)}</td>
      <td>${pair.decision}</td>
      <td>${pair.arbitrage === null ? badge('NO DATA', 'warn') : pair.arbitrage ? badge('YES', 'ok') : badge('NO', 'bad')}</td>
      <td>${pair.age_ms ?? '-'}</td>
      <td>${pair.last_refresh_utc}</td>`;
    tbody.appendChild(tr);
  }
}
async function bootstrap(){
  try {
    const res = await fetch('/v1/dashboard/summary');
    render(await res.json());
  } catch(err){ console.error(err); }
  const es = new EventSource('/v1/dashboard/stream');
  es.onmessage = (ev) => {
    try { render(JSON.parse(ev.data)); } catch(err) { console.error(err); }
  };
  es.onerror = () => { console.warn('dashboard stream disconnected'); };
}
bootstrap();
</script>
</body>
</html>"#.to_string()
}
