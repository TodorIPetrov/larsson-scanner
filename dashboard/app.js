let allSymbols = [];
let currentFilter = 'ALL';
let currentClass = 'ALL';
let currentSearch = '';
let currentView = localStorage.getItem('larsson_view_mode') || 'table';

const CLASS_LABELS = {
  crypto_stocks: 'Crypto Stock',
  ai_stocks: 'AI Stock',
  crypto: 'Crypto',
  us_stocks: 'US Stock',
  intl_stocks: 'Global',
  commodities: 'Commodity',
  indices: 'Index',
};

async function loadDashboardData() {
  try {
    const res = await fetch('data.json?t=' + new Date().getTime());
    if (!res.ok) {
      throw new Error(`Failed to load data.json: ${res.statusText}`);
    }
    const data = await res.json();
    allSymbols = data.symbols || [];
    renderOverview(data);
    renderAllViews();
  } catch (err) {
    console.error('Error loading dashboard:', err);
    document.getElementById('assetsTableBody').innerHTML = `
      <tr>
        <td colspan="12" class="loading-state" style="color: #ef4444;">
          ⚠️ Failed to load <code>data.json</code>. Run a scan first: <code>python src/main.py --scan</code>
        </td>
      </tr>
    `;
  }
}

function getFilteredSymbols() {
  const q = currentSearch.toLowerCase().trim();
  return allSymbols.filter(item => {
    const matchesFilter = (currentFilter === 'ALL') || (item.state === currentFilter);
    const matchesClass = (currentClass === 'ALL') || (item.asset_class === currentClass);
    const matchesSearch = !q ||
      item.ticker.toLowerCase().includes(q) ||
      (item.name && item.name.toLowerCase().includes(q));
    return matchesFilter && matchesClass && matchesSearch;
  });
}

function renderOverview(data) {
  const activeSet = currentClass === 'ALL' 
    ? allSymbols 
    : allSymbols.filter(s => s.asset_class === currentClass);

  const total = activeSet.length;
  let goldCount = 0;
  let blueCount = 0;
  let neutralCount = 0;

  activeSet.forEach(s => {
    if (s.state === 'GOLD') goldCount++;
    else if (s.state === 'BLUE') blueCount++;
    else neutralCount++;
  });

  const goldPct = total > 0 ? Math.round((goldCount / total) * 100) : 0;
  const bluePct = total > 0 ? Math.round((blueCount / total) * 100) : 0;
  const neutralPct = total > 0 ? Math.round((neutralCount / total) * 100) : 0;

  document.getElementById('totalCount').textContent = total;
  document.getElementById('goldCount').textContent = goldCount;
  document.getElementById('blueCount').textContent = blueCount;
  document.getElementById('neutralCount').textContent = neutralCount;

  document.getElementById('goldPct').textContent = `${goldPct}%`;
  document.getElementById('bluePct').textContent = `${bluePct}%`;
  document.getElementById('neutralPct').textContent = `${neutralPct}%`;

  document.getElementById('barGold').style.width = `${goldPct}%`;
  document.getElementById('barBlue').style.width = `${bluePct}%`;
  document.getElementById('barNeutral').style.width = `${neutralPct}%`;

  if (data && data.generated_at) {
    const d = new Date(data.generated_at);
    document.getElementById('lastUpdated').textContent = `Updated: ${d.toLocaleTimeString()} (${d.toLocaleDateString()})`;
  }
}

function renderAllViews() {
  renderTable();
  renderCards();
  applyViewMode();
}

function renderTable() {
  const tbody = document.getElementById('assetsTableBody');
  const filtered = getFilteredSymbols();

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="12" class="loading-state">No matching assets found.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map(item => {
    const tfCode = item.timeframe === '4H' ? '240' : item.timeframe;
    const tvUrl = `https://www.tradingview.com/chart/?symbol=${item.tv_symbol}&interval=${tfCode}`;
    
    let badgeClass = 'badge-neutral';
    let stateEmoji = '⚪';
    if (item.state === 'GOLD') {
      badgeClass = 'badge-gold';
      stateEmoji = '🟡';
    } else if (item.state === 'BLUE') {
      badgeClass = 'badge-blue';
      stateEmoji = '🔵';
    }

    const priceFormatted = item.price >= 1000 
      ? `$${item.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : `$${item.price.toFixed(item.price >= 1 ? 2 : 5)}`;

    const lastChange = item.last_change 
      ? new Date(item.last_change).toLocaleString()
      : 'N/A';

    const classLabel = CLASS_LABELS[item.asset_class] || item.asset_class;

    const spreadVal = item.spread_pct !== undefined ? item.spread_pct : 0.0;
    const spreadSign = spreadVal > 0 ? '+' : '';
    const spreadClass = spreadVal > 0 ? 'spread-pos' : (spreadVal < 0 ? 'spread-neg' : 'spread-neu');
    const spreadLabel = `${spreadSign}${spreadVal.toFixed(2)}%`;

    return `
      <tr>
        <td>
          <div class="symbol-cell">
            <a href="${tvUrl}" target="_blank" rel="noopener" class="ticker-link" title="Open ${item.tv_symbol} on TradingView">
              <span class="ticker-text">${item.ticker}</span>
              <span class="tv-badge">TV ↗</span>
            </a>
            <span class="name-text" title="${item.name || ''}">${item.name || ''}</span>
          </div>
        </td>
        <td>
          <span class="class-badge class-${item.asset_class}">${classLabel}</span>
        </td>
        <td><span class="tf-badge">${item.timeframe}</span></td>
        <td>
          <span class="badge ${badgeClass}">
            <span class="dot"></span> ${stateEmoji} ${item.state}
          </span>
        </td>
        <td class="price-cell">${priceFormatted}</td>
        <td class="spread-cell ${spreadClass}">
          <span class="spread-pill ${spreadClass}">${spreadLabel}</span>
        </td>
        <td class="num-cell">${item.v1}</td>
        <td class="num-cell">${item.m1}</td>
        <td class="num-cell">${item.m2}</td>
        <td class="num-cell">${item.v2}</td>
        <td style="color: var(--text-muted); font-size: 0.8125rem;">${lastChange}</td>
        <td>
          <a href="${tvUrl}" target="_blank" rel="noopener" class="tv-link-btn">
            Chart ↗
          </a>
        </td>
      </tr>
    `;
  }).join('');
}

function renderCards() {
  const container = document.getElementById('cardsGrid');
  const filtered = getFilteredSymbols();

  if (filtered.length === 0) {
    container.innerHTML = `<div class="loading-state" style="grid-column: 1/-1;">No matching assets found.</div>`;
    return;
  }

  container.innerHTML = filtered.map(item => {
    const tfCode = item.timeframe === '4H' ? '240' : item.timeframe;
    const tvUrl = `https://www.tradingview.com/chart/?symbol=${item.tv_symbol}&interval=${tfCode}`;
    
    let badgeClass = 'badge-neutral';
    let stateEmoji = '⚪';
    let cardClass = 'card-neutral';
    if (item.state === 'GOLD') {
      badgeClass = 'badge-gold';
      stateEmoji = '🟡';
      cardClass = 'card-gold';
    } else if (item.state === 'BLUE') {
      badgeClass = 'badge-blue';
      stateEmoji = '🔵';
      cardClass = 'card-blue';
    }

    const priceFormatted = item.price >= 1000 
      ? `$${item.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : `$${item.price.toFixed(item.price >= 1 ? 2 : 5)}`;

    const classLabel = CLASS_LABELS[item.asset_class] || item.asset_class;

    const spreadVal = item.spread_pct !== undefined ? item.spread_pct : 0.0;
    const spreadSign = spreadVal > 0 ? '+' : '';
    const spreadClass = spreadVal > 0 ? 'spread-pos' : (spreadVal < 0 ? 'spread-neg' : 'spread-neu');
    const spreadLabel = `${spreadSign}${spreadVal.toFixed(2)}%`;

    return `
      <div class="asset-card ${cardClass}">
        <div class="card-top">
          <div class="card-identity">
            <a href="${tvUrl}" target="_blank" rel="noopener" class="card-ticker-link" title="Open TradingView Chart">
              <span class="card-ticker">${item.ticker}</span>
              <span class="tv-badge">TV ↗</span>
            </a>
            <div class="card-name" title="${item.name || ''}">${item.name || ''}</div>
          </div>
          <div class="card-badges">
            <span class="class-badge class-${item.asset_class}">${classLabel}</span>
            <span class="tf-badge">${item.timeframe}</span>
          </div>
        </div>

        <div class="card-middle">
          <div>
            <div class="card-price">${priceFormatted}</div>
            <div class="card-spread ${spreadClass}">
              <span class="spread-label">Ribbon Spread:</span>
              <span class="spread-pill ${spreadClass}">${spreadLabel}</span>
            </div>
          </div>
          <span class="badge ${badgeClass}">
            <span class="dot"></span> ${stateEmoji} ${item.state}
          </span>
        </div>

        <div class="card-ribbon-metrics">
          <div class="ribbon-box"><span>v1 (15)</span><strong>${item.v1}</strong></div>
          <div class="ribbon-box"><span>m1 (19)</span><strong>${item.m1}</strong></div>
          <div class="ribbon-box"><span>m2 (25)</span><strong>${item.m2}</strong></div>
          <div class="ribbon-box"><span>v2 (29)</span><strong>${item.v2}</strong></div>
        </div>

        <div class="card-footer">
          <span class="card-change">Changed: ${item.last_change ? new Date(item.last_change).toLocaleDateString() : 'N/A'}</span>
          <a href="${tvUrl}" target="_blank" rel="noopener" class="card-chart-btn">Chart ↗</a>
        </div>
      </div>
    `;
  }).join('');
}

function applyViewMode() {
  const tableSec = document.getElementById('tableContainer');
  const cardsSec = document.getElementById('cardsContainer');
  const buttons = document.querySelectorAll('#viewToggle .toggle-btn');

  buttons.forEach(b => {
    if (b.dataset.view === currentView) {
      b.classList.add('active');
    } else {
      b.classList.remove('active');
    }
  });

  if (currentView === 'cards') {
    tableSec.style.display = 'none';
    cardsSec.style.display = 'block';
  } else {
    tableSec.style.display = 'block';
    cardsSec.style.display = 'none';
  }
}

// Event Listeners for View Toggle
document.querySelectorAll('#viewToggle .toggle-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    currentView = e.target.dataset.view;
    localStorage.setItem('larsson_view_mode', currentView);
    applyViewMode();
  });
});

// Event Listeners for State Filter
document.querySelectorAll('#stateFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#stateFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentFilter = e.target.dataset.filter;
    renderAllViews();
  });
});

// Event Listeners for Asset Class Filter
document.querySelectorAll('#classFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#classFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentClass = e.target.dataset.class;
    renderOverview();
    renderAllViews();
  });
});

document.getElementById('searchInput').addEventListener('input', (e) => {
  currentSearch = e.target.value.trim();
  renderAllViews();
});

document.getElementById('refreshBtn').addEventListener('click', () => {
  loadDashboardData();
});

// Auto-refresh every 60 seconds
setInterval(loadDashboardData, 60000);

// Initialize
loadDashboardData();
