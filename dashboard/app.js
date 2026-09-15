let allSymbols = [];
let currentFilter = 'ALL';
let currentClass = 'ALL';
let currentSearch = '';

const CLASS_LABELS = {
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
    renderTable();
  } catch (err) {
    console.error('Error loading dashboard:', err);
    document.getElementById('assetsTableBody').innerHTML = `
      <tr>
        <td colspan="11" class="loading-state" style="color: #ef4444;">
          ⚠️ Failed to load <code>data.json</code>. Run a scan first: <code>python src/main.py --scan</code>
        </td>
      </tr>
    `;
  }
}

function getFilteredSymbols() {
  return allSymbols.filter(item => {
    const matchesFilter = (currentFilter === 'ALL') || (item.state === currentFilter);
    const matchesClass = (currentClass === 'ALL') || (item.asset_class === currentClass);
    const matchesSearch = !currentSearch || item.ticker.toLowerCase().includes(currentSearch.toLowerCase());
    return matchesFilter && matchesClass && matchesSearch;
  });
}

function renderOverview(data) {
  // Compute sentiment on the currently active class subset
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

function renderTable() {
  const tbody = document.getElementById('assetsTableBody');
  const filtered = getFilteredSymbols();

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="11" class="loading-state">No matching assets found.</td>
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

    return `
      <tr>
        <td>
          <div class="symbol-cell">
            <span>${item.ticker}</span>
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

// Event Listeners for State Filter
document.querySelectorAll('#stateFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#stateFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentFilter = e.target.dataset.filter;
    renderTable();
  });
});

// Event Listeners for Asset Class Filter
document.querySelectorAll('#classFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#classFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentClass = e.target.dataset.class;
    renderOverview();
    renderTable();
  });
});

document.getElementById('searchInput').addEventListener('input', (e) => {
  currentSearch = e.target.value.trim();
  renderTable();
});

document.getElementById('refreshBtn').addEventListener('click', () => {
  loadDashboardData();
});

// Initial Load
loadDashboardData();
