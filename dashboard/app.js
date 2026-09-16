let allSymbols = [];
let currentFilter = 'ALL';
let currentClass = 'ALL';
let currentTfFilter = 'ALL';
let currentSetupFilter = 'ALL';
let currentSearch = '';
let currentView = localStorage.getItem('larsson_view_mode') || 'table';

let currentSortColumn = null;
let currentSortDir = 'asc';
let currentModalItem = null;

// Active chart state
let activeChart = null;
let activeTicker = '';
let activeTf = '1D';
let activeClass = '';

const CLASS_LABELS = {
  crypto_stocks: 'Crypto Stock',
  ai_stocks: 'AI Stock',
  crypto: 'Crypto',
  us_stocks: 'US Stock',
  intl_stocks: 'Europe & Global',
  commodities: 'Commodity',
  indices: 'Index',
};

function formatShortPrice(val) {
  if (val === null || val === undefined || isNaN(val)) return 'N/A';
  if (val >= 10000) {
    return (val / 1000).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'k';
  } else if (val >= 1000) {
    return val.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  } else if (val >= 1) {
    return val.toFixed(2);
  } else {
    return val.toFixed(5);
  }
}

function getQuantamentalSetupRank(item) {
  if (!item) return 0;
  const ts = item.trade_suggestion;
  const fund = item.fundamental;
  if (!ts) return 0;

  let base = 0;
  if (ts.setup_type === 'QUANTAMENTAL_ALPHA_BUY' || ts.quantamental_tag === 'INSTITUTIONAL_ALPHA') {
    base = 10000;
  } else if (ts.setup_type === 'QUALITY_HOLD_ACCUMULATION' || ts.quantamental_tag === 'CORE_QUALITY_HOLD') {
    base = 8000;
  } else if (ts.action === 'SPOT_BUY' && (ts.tier === 'A+' || ts.tier === 'A')) {
    base = 7000;
  } else if (ts.action === 'SPOT_BUY' && ts.tier === 'B') {
    base = 5000;
  } else if (ts.action === 'SPOT_BUY') {
    base = 4000;
  } else if (ts.action === 'TAKE_PROFIT') {
    base = 3000;
  } else if (ts.action === 'EXIT_PROTECT') {
    base = 2000;
  } else if (ts.setup_type === 'VALUE_TRAP_WARNING' || ts.quantamental_tag === 'VALUE_TRAP_RISK') {
    base = 1000;
  } else {
    base = 0;
  }

  const scoreBonus = (ts.score || 0) * 10;
  const rrBonus = (ts.rr || 0) * 5;
  const upsideBonus = (fund && fund.upside_pct && fund.upside_pct > 0) ? Math.min(fund.upside_pct, 50) : 0;
  const spreadBonus = (item.spread_pct && item.spread_pct > 0) ? Math.min(item.spread_pct, 20) : 0;

  return base + scoreBonus + rrBonus + upsideBonus + spreadBonus;
}

function renderTradeSuggestionCell(ts, item) {
  if (!ts || ts.action === 'WAIT') {
    if (ts && (ts.setup_type === 'VALUE_TRAP_WARNING' || ts.quantamental_tag === 'VALUE_TRAP_RISK')) {
      return `<div class="ts-cell"><span class="ts-badge ts-valuetrap" title="${ts.reason_bg || ts.reason_en || ''}">⏳ VALUE TRAP RISK</span></div>`;
    }
    return `<span class="ts-badge ts-wait" title="No immediate high-conviction setup. Wait for key structural level.">⏳ Wait</span>`;
  }

  const isCrypto = item && (item.asset_class === 'crypto' || (item.ticker && item.ticker.endsWith('USDT')));
  const rrTxt = ts.rr ? `1:${ts.rr}` : '';

  let tooltip = `${ts.reason_bg || ts.reason_en || ''}\n`;
  if (ts.entry) tooltip += `Entry: $${formatShortPrice(ts.entry)}\n`;
  if (ts.sl) tooltip += `SL: $${formatShortPrice(ts.sl)}\n`;
  if (ts.tp1) tooltip += `TP1: $${formatShortPrice(ts.tp1)}\n`;
  if (ts.tp2) tooltip += `TP2: $${formatShortPrice(ts.tp2)}\n`;
  if (ts.rr) tooltip += `R:R: 1 : ${ts.rr}\n`;

  let actionBadge = '';
  if (isCrypto) {
    // 🪙 Crypto Cyber Amber & Gold Styling
    const tierPill = `<span class="ts-tier-pill tier-crypto-gold">${ts.tier}</span>`;
    if (ts.setup_type === 'QUANTAMENTAL_ALPHA_BUY') {
      actionBadge = `<span class="ts-badge ts-crypto-alpha" title="${tooltip}">🪙 ALPHA BUY ${tierPill} ${rrTxt ? `[${rrTxt}]` : ''}</span>`;
    } else if (ts.setup_type === 'QUALITY_HOLD_ACCUMULATION') {
      actionBadge = `<span class="ts-badge ts-crypto-accum" title="${tooltip}">🪙 ACCUMULATE ${tierPill}</span>`;
    } else if (ts.setup_type === 'SPECULATIVE_MOMENTUM_BUY' || ts.setup_type === 'SPECULATIVE_PULLBACK_BUY') {
      actionBadge = `<span class="ts-badge ts-crypto-speculative" title="${tooltip}">🪙⚠️ SPECULATIVE <span class="ts-tier-pill tier-b">B</span> ${rrTxt ? `[${rrTxt}]` : ''}</span>`;
    } else if (ts.action === 'SPOT_BUY') {
      actionBadge = `<span class="ts-badge ts-crypto-buy" title="${tooltip}">🪙 BUY ${tierPill} ${rrTxt ? `[${rrTxt}]` : ''}</span>`;
    } else if (ts.action === 'TAKE_PROFIT') {
      actionBadge = `<span class="ts-badge ts-crypto-profit" title="${tooltip}">🪙💰 TAKE PROFIT ${tierPill}</span>`;
    } else if (ts.action === 'EXIT_PROTECT') {
      actionBadge = `<span class="ts-badge ts-crypto-exit" title="${tooltip}">🪙🛡️ EXIT / STOP</span>`;
    } else if (ts.action === 'SHORT_2X_OPTIONAL') {
      actionBadge = `<span class="ts-badge ts-short" title="${tooltip}">🔴 SHORT 2X ${tierPill} ${rrTxt ? `[${rrTxt}]` : ''}</span>`;
    } else {
      actionBadge = `<span class="ts-badge ts-wait">⏳ Wait</span>`;
    }
  } else {
    // 🏛️ Equities & Commodities Institutional Amethyst & Emerald Styling
    const tierClass = ts.tier === 'A+' ? 'tier-equity-amethyst' : (ts.tier === 'A' ? 'tier-equity-emerald' : 'tier-b');
    const tierPill = `<span class="ts-tier-pill ${tierClass}">${ts.tier}</span>`;
    if (ts.setup_type === 'QUANTAMENTAL_ALPHA_BUY') {
      actionBadge = `<span class="ts-badge ts-equity-alpha" title="${tooltip}">🏛️ ALPHA BUY ${tierPill} ${rrTxt ? `[${rrTxt}]` : ''}</span>`;
    } else if (ts.setup_type === 'QUALITY_HOLD_ACCUMULATION') {
      actionBadge = `<span class="ts-badge ts-equity-accum" title="${tooltip}">🏛️ ACCUMULATE ${tierPill}</span>`;
    } else if (ts.setup_type === 'SPECULATIVE_MOMENTUM_BUY' || ts.setup_type === 'SPECULATIVE_PULLBACK_BUY') {
      actionBadge = `<span class="ts-badge ts-equity-speculative" title="${tooltip}">🏛️⚠️ SPECULATIVE <span class="ts-tier-pill tier-b">B</span> ${rrTxt ? `[${rrTxt}]` : ''}</span>`;
    } else if (ts.action === 'SPOT_BUY') {
      actionBadge = `<span class="ts-badge ts-equity-buy" title="${tooltip}">🏛️ BUY ${tierPill} ${rrTxt ? `[${rrTxt}]` : ''}</span>`;
    } else if (ts.action === 'TAKE_PROFIT') {
      actionBadge = `<span class="ts-badge ts-equity-profit" title="${tooltip}">🏛️💰 TAKE PROFIT ${tierPill}</span>`;
    } else if (ts.action === 'EXIT_PROTECT') {
      actionBadge = `<span class="ts-badge ts-equity-exit" title="${tooltip}">🏛️🛡️ EXIT / STOP</span>`;
    } else if (ts.action === 'SHORT_2X_OPTIONAL') {
      actionBadge = `<span class="ts-badge ts-short" title="${tooltip}">🔴 SHORT 2X ${tierPill} ${rrTxt ? `[${rrTxt}]` : ''}</span>`;
    } else {
      actionBadge = `<span class="ts-badge ts-wait">⏳ Wait</span>`;
    }
  }

  return `<div class="ts-cell">${actionBadge}</div>`;
}

async function loadDashboardData() {
  let data;
  try {
    const res = await fetch('data.json?t=' + new Date().getTime());
    if (!res.ok) {
      throw new Error(`Failed to load data.json: ${res.statusText}`);
    }
    data = await res.json();
    allSymbols = data.symbols || [];
    renderOverview(data);
  } catch (err) {
    console.error('Error loading data.json:', err);
    document.getElementById('assetsTableBody').innerHTML = `
      <tr>
        <td colspan="14" class="loading-state" style="color: #ef4444;">
          ⚠️ Failed to load <code>data.json</code>. Run a scan first: <code>python src/main.py --scan</code>
        </td>
      </tr>
    `;
    return;
  }

  try {
    renderAllViews();
  } catch (renderErr) {
    console.error('Error rendering dashboard views:', renderErr);
    document.getElementById('assetsTableBody').innerHTML = `
      <tr>
        <td colspan="14" class="loading-state" style="color: #ef4444;">
          ⚠️ Rendering error: ${renderErr.message}
        </td>
      </tr>
    `;
  }
}

function getFilteredSymbols() {
  const q = currentSearch.toLowerCase().trim();
  const filtered = allSymbols.filter(item => {
    const matchesFilter = (currentFilter === 'ALL') || (item.state === currentFilter);
    const matchesClass = (currentClass === 'ALL') || (item.asset_class === currentClass);
    const matchesTf = (currentTfFilter === 'ALL') || (item.timeframe === currentTfFilter);
    
    const ts = item.trade_suggestion;
    const fund = item.fundamental;
    let matchesSetup = true;
    if (currentSetupFilter === 'SPOT_BUY') {
      matchesSetup = ts && (ts.action === 'SPOT_BUY' || (ts.setup_type && ts.setup_type.includes('BUY')));
    } else if (currentSetupFilter === 'TAKE_PROFIT') {
      matchesSetup = ts && ts.action === 'TAKE_PROFIT';
    } else if (currentSetupFilter === 'EXIT_PROTECT') {
      matchesSetup = ts && ts.action === 'EXIT_PROTECT';
    } else if (currentSetupFilter === 'TIER_A') {
      matchesSetup = ts && (ts.tier === 'A+' || ts.tier === 'A');
    } else if (currentSetupFilter === 'QUANTAMENTAL_ALPHA') {
      matchesSetup = (ts && (ts.setup_type === 'QUANTAMENTAL_ALPHA_BUY' || ts.quantamental_tag === 'INSTITUTIONAL_ALPHA')) ||
                     (fund && (fund.verdict?.includes('STRONG BUY') || fund.verdict === 'BUY'));
    } else if (currentSetupFilter === 'WIDE_MOAT') {
      matchesSetup = fund && fund.moat === 'Wide';
    } else if (currentSetupFilter === 'VALUE_TRAP') {
      matchesSetup = ts && (ts.setup_type === 'VALUE_TRAP_WARNING' || ts.quantamental_tag === 'VALUE_TRAP_RISK');
    }

    const matchesSearch = !q ||
      item.ticker.toLowerCase().includes(q) ||
      (item.name && item.name.toLowerCase().includes(q));
    return matchesFilter && matchesClass && matchesTf && matchesSetup && matchesSearch;
  });

  if (currentSortColumn) {
    const tierRanks = { 'A+': 4, 'A': 3, 'B': 2, 'NONE': 1 };
    const stateRanks = { 'GOLD': 3, 'NEUTRAL': 2, 'BLUE': 1 };

    filtered.sort((a, b) => {
      let valA, valB;
      if (currentSortColumn === 'ticker') {
        valA = a.ticker || '';
        valB = b.ticker || '';
        return currentSortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
      } else if (currentSortColumn === 'asset_class') {
        valA = a.asset_class || '';
        valB = b.asset_class || '';
        return currentSortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
      } else if (currentSortColumn === 'state') {
        valA = stateRanks[a.state] || 0;
        valB = stateRanks[b.state] || 0;
      } else if (currentSortColumn === 'price') {
        valA = a.price || 0;
        valB = b.price || 0;
      } else if (currentSortColumn === 'spread_pct') {
        valA = a.spread_pct !== undefined ? a.spread_pct : -999;
        valB = b.spread_pct !== undefined ? b.spread_pct : -999;
      } else if (currentSortColumn === 'tier' || currentSortColumn === 'trade_setup') {
        valA = getQuantamentalSetupRank(a);
        valB = getQuantamentalSetupRank(b);
      } else if (currentSortColumn === 's1_dist') {
        valA = (a.s1_dist_pct !== null && a.s1_dist_pct !== undefined) ? a.s1_dist_pct : 9999;
        valB = (b.s1_dist_pct !== null && b.s1_dist_pct !== undefined) ? b.s1_dist_pct : 9999;
      } else {
        return 0;
      }

      if (valA < valB) return currentSortDir === 'asc' ? -1 : 1;
      if (valA > valB) return currentSortDir === 'asc' ? 1 : -1;
      return 0;
    });
  } else {
    // Default sorting in main view: Rank assets by best trade setups from combined quantamental analysis!
    filtered.sort((a, b) => {
      const rankA = getQuantamentalSetupRank(a);
      const rankB = getQuantamentalSetupRank(b);
      if (rankB !== rankA) return rankB - rankA;
      // Secondary sort: state (GOLD > NEUTRAL > BLUE)
      const stateRanks = { 'GOLD': 3, 'NEUTRAL': 2, 'BLUE': 1 };
      const sA = stateRanks[a.state] || 0;
      const sB = stateRanks[b.state] || 0;
      if (sB !== sA) return sB - sA;
      // Tertiary sort: spread_pct
      return (b.spread_pct || 0) - (a.spread_pct || 0);
    });
  }

  return filtered;
}

function renderOverview(data) {
  let activeSet = allSymbols;
  if (currentClass !== 'ALL') {
    activeSet = activeSet.filter(s => s.asset_class === currentClass);
  }
  if (currentTfFilter !== 'ALL') {
    activeSet = activeSet.filter(s => s.timeframe === currentTfFilter);
  }

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
        <td colspan="13" class="loading-state">No matching assets found.</td>
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

    // S/R Cell Rendering
    let srCellHtml = '';
    const hasS1 = item.s1 !== null && item.s1 !== undefined;
    const hasR1 = item.r1 !== null && item.r1 !== undefined;
    if (hasS1 || hasR1) {
      const s1Txt = hasS1 ? `🟢 S1: $${formatShortPrice(item.s1)} (-${item.s1_dist_pct}%)` : '';
      const r1Txt = hasR1 ? `🔴 R1: $${formatShortPrice(item.r1)} (+${item.r1_dist_pct}%)` : '';
      srCellHtml = `
        <div class="sr-cell">
          ${hasR1 ? `<span class="sr-pill sr-res" title="Resistance R1: $${item.r1} (${item.r1_touches} touches)">${r1Txt}</span>` : ''}
          ${hasS1 ? `<span class="sr-pill sr-sup" title="Support S1: $${item.s1} (${item.s1_touches} touches)">${s1Txt}</span>` : ''}
        </div>
      `;
    } else {
      srCellHtml = `<span class="sr-pill sr-na">No levels</span>`;
    }

    // Fundamental Badges
    let fundRow = '';
    if (item.fundamental) {
      const f = item.fundamental;
      let moatPill = '';
      if (f.moat === 'Wide') moatPill = `<span class="fund-moat-pill fund-moat-wide" title="Wide Economic Moat">💎 Wide Moat</span>`;
      else if (f.moat === 'Narrow') moatPill = `<span class="fund-moat-pill fund-moat-narrow" title="Narrow Economic Moat">🏰 Narrow Moat</span>`;

      let verdictPill = '';
      const v = f.verdict || '';
      const upsideTxt = (f.upside_pct !== null && f.upside_pct !== undefined) ? ` (+${Math.round(f.upside_pct)}%)` : '';
      if (v.includes('STRONG BUY') || v.includes('BUY') || v.includes('OVERWEIGHT')) {
        verdictPill = `<span class="fund-verdict-pill fund-pill-buy" title="DCF Fair Value: $${formatShortPrice(f.fair_value)} | MoS: ${f.mos_pct || 0}%\n${f.thesis || ''}">🟢 ${v.split('/')[0].trim()}${upsideTxt}</span>`;
      } else if (v.includes('HOLD') || v.includes('NEUTRAL')) {
        verdictPill = `<span class="fund-verdict-pill fund-pill-hold" title="DCF Fair Value: $${formatShortPrice(f.fair_value)}\n${f.thesis || ''}">🟡 Hold</span>`;
      } else if (v.includes('REDUCE') || v.includes('AVOID') || v.includes('UNDERPERFORM')) {
        verdictPill = `<span class="fund-verdict-pill fund-pill-reduce" title="Overvalued / Weak Fundamentals\n${f.thesis || ''}">🔴 Reduce</span>`;
      }

      if (moatPill || verdictPill) {
        fundRow = `<div class="fund-badges-row">${verdictPill}${moatPill}</div>`;
      }
    }

    return `
      <tr>
        <td>
          <div class="symbol-cell">
            <a href="${tvUrl}" target="_blank" rel="noopener" class="ticker-link" title="Open ${item.tv_symbol} on TradingView">
              <span class="ticker-text">${item.ticker}</span>
              <span class="tv-badge">TV ↗</span>
            </a>
            <span class="name-text" title="${item.name || ''}">${item.name || ''}</span>
            ${fundRow}
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
        <td>${renderTradeSuggestionCell(item.trade_suggestion, item)}</td>
        <td>${srCellHtml}</td>
        <td class="num-cell">${item.v1}</td>
        <td class="num-cell">${item.m1}</td>
        <td class="num-cell">${item.m2}</td>
        <td class="num-cell">${item.v2}</td>
        <td style="color: var(--text-muted); font-size: 0.8125rem;">${lastChange}</td>
        <td>
          <div style="display: flex; gap: 6px; align-items: center;">
            <button class="btn-view-chart" onclick="openChartModal('${item.ticker}', '${item.timeframe}', '${item.asset_class}')" title="View interactive chart with S/R levels and trade setups">
              📊 S/R
            </button>
            <a href="${tvUrl}" target="_blank" rel="noopener" class="tv-link-btn" title="Open on TradingView">
              TV ↗
            </a>
          </div>
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

    const hasS1 = item.s1 !== null && item.s1 !== undefined;
    const hasR1 = item.r1 !== null && item.r1 !== undefined;

    // Fundamental Badges
    let fundRow = '';
    if (item.fundamental) {
      const f = item.fundamental;
      let moatPill = '';
      if (f.moat === 'Wide') moatPill = `<span class="fund-moat-pill fund-moat-wide" title="Wide Economic Moat">💎 Wide Moat</span>`;
      else if (f.moat === 'Narrow') moatPill = `<span class="fund-moat-pill fund-moat-narrow" title="Narrow Economic Moat">🏰 Narrow Moat</span>`;

      let verdictPill = '';
      const v = f.verdict || '';
      const upsideTxt = (f.upside_pct !== null && f.upside_pct !== undefined) ? ` (+${Math.round(f.upside_pct)}%)` : '';
      if (v.includes('STRONG BUY') || v.includes('BUY') || v.includes('OVERWEIGHT')) {
        verdictPill = `<span class="fund-verdict-pill fund-pill-buy" title="DCF Fair Value: $${formatShortPrice(f.fair_value)} | MoS: ${f.mos_pct || 0}%\n${f.thesis || ''}">🟢 ${v.split('/')[0].trim()}${upsideTxt}</span>`;
      } else if (v.includes('HOLD') || v.includes('NEUTRAL')) {
        verdictPill = `<span class="fund-verdict-pill fund-pill-hold" title="DCF Fair Value: $${formatShortPrice(f.fair_value)}\n${f.thesis || ''}">🟡 Hold</span>`;
      } else if (v.includes('REDUCE') || v.includes('AVOID') || v.includes('UNDERPERFORM')) {
        verdictPill = `<span class="fund-verdict-pill fund-pill-reduce" title="Overvalued / Weak Fundamentals\n${f.thesis || ''}">🔴 Reduce</span>`;
      }

      if (moatPill || verdictPill) {
        fundRow = `<div class="fund-badges-row">${verdictPill}${moatPill}</div>`;
      }
    }

    return `
      <div class="asset-card ${cardClass}">
        <div class="card-top">
          <div class="card-identity">
            <a href="${tvUrl}" target="_blank" rel="noopener" class="card-ticker-link" title="Open TradingView Chart">
              <span class="card-ticker">${item.ticker}</span>
              <span class="tv-badge">TV ↗</span>
            </a>
            <div class="card-name" title="${item.name || ''}">${item.name || ''}</div>
            ${fundRow}
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

        ${item.trade_suggestion ? `
          <div style="margin-bottom: 8px;">
            ${renderTradeSuggestionCell(item.trade_suggestion, item)}
          </div>
        ` : ''}

        ${hasS1 || hasR1 ? `
          <div style="display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;">
            ${hasR1 ? `<span class="sr-pill sr-res">🔴 R1: $${formatShortPrice(item.r1)} (+${item.r1_dist_pct}%)</span>` : ''}
            ${hasS1 ? `<span class="sr-pill sr-sup">🟢 S1: $${formatShortPrice(item.s1)} (-${item.s1_dist_pct}%)</span>` : ''}
          </div>
        ` : ''}

        <div class="card-ribbon-metrics">
          <div class="ribbon-box"><span>v1 (15)</span><strong>${item.v1}</strong></div>
          <div class="ribbon-box"><span>m1 (19)</span><strong>${item.m1}</strong></div>
          <div class="ribbon-box"><span>m2 (25)</span><strong>${item.m2}</strong></div>
          <div class="ribbon-box"><span>v2 (29)</span><strong>${item.v2}</strong></div>
        </div>

        <div class="card-footer">
          <span class="card-change">Changed: ${item.last_change ? new Date(item.last_change).toLocaleDateString() : 'N/A'}</span>
          <div style="display: flex; gap: 6px; align-items: center;">
            <button class="btn-view-chart" onclick="openChartModal('${item.ticker}', '${item.timeframe}', '${item.asset_class}')">📊 S/R</button>
            <a href="${tvUrl}" target="_blank" rel="noopener" class="card-chart-btn">TV ↗</a>
          </div>
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

// =============================================================================
// INTERACTIVE CHART & S/R MODAL ENGINE
// =============================================================================

function computeSMMA(src, length) {
  const n = src.length;
  const out = new Array(n).fill(NaN);
  if (n < length) return out;
  let sum = 0;
  for (let i = 0; i < length; i++) sum += src[i];
  out[length - 1] = sum / length;
  for (let i = length; i < n; i++) {
    out[i] = (out[i - 1] * (length - 1) + src[i]) / length;
  }
  return out;
}

function computePivotsAndZones(candles, left = 5, right = 5, toleranceAtrMult = 0.35) {
  const n = candles.length;
  if (n < left + right + 1) return { atr: 0, s1: null, r1: null, zones: [] };

  // Calculate True Range & ATR(14)
  const trs = [candles[0].high - candles[0].low];
  for (let i = 1; i < n; i++) {
    const hl = candles[i].high - candles[i].low;
    const hc = Math.abs(candles[i].high - candles[i - 1].close);
    const lc = Math.abs(candles[i].low - candles[i - 1].close);
    trs.push(Math.max(hl, hc, lc));
  }

  const atrs = new Array(n).fill(0);
  let sum = 0;
  for (let i = 0; i < Math.min(14, n); i++) sum += trs[i];
  atrs[13] = sum / 14;
  for (let i = 14; i < n; i++) {
    atrs[i] = (atrs[i - 1] * 13 + trs[i]) / 14;
  }
  const currentAtr = atrs[n - 1] || (candles[n - 1].high - candles[n - 1].low);

  // Extract swing highs and swing lows
  const pivots = [];
  for (let i = left; i < n - right; i++) {
    const h = candles[i].high;
    const l = candles[i].low;

    let isHigh = true;
    for (let k = i - left; k < i; k++) { if (candles[k].high >= h) { isHigh = false; break; } }
    if (isHigh) {
      for (let k = i + 1; k <= i + right; k++) { if (candles[k].high > h) { isHigh = false; break; } }
    }
    if (isHigh) pivots.push({ price: h, type: 'HIGH', idx: i });

    let isLow = true;
    for (let k = i - left; k < i; k++) { if (candles[k].low <= l) { isLow = false; break; } }
    if (isLow) {
      for (let k = i + 1; k <= i + right; k++) { if (candles[k].low < l) { isLow = false; break; } }
    }
    if (isLow) pivots.push({ price: l, type: 'LOW', idx: i });
  }

  // 1D Density Clustering
  pivots.sort((a, b) => a.price - b.price);
  const tolerance = currentAtr * toleranceAtrMult;
  const clusters = [];
  let currentCluster = [];

  for (const p of pivots) {
    if (currentCluster.length === 0) {
      currentCluster.push(p);
    } else {
      const clusterMean = currentCluster.reduce((acc, x) => acc + x.price, 0) / currentCluster.length;
      if (Math.abs(p.price - clusterMean) <= tolerance) {
        currentCluster.push(p);
      } else {
        clusters.push(currentCluster);
        currentCluster = [p];
      }
    }
  }
  if (currentCluster.length > 0) clusters.push(currentCluster);

  const zones = clusters.map(cl => {
    const prices = cl.map(x => x.price).sort((a, b) => a - b);
    const mid = Math.floor(prices.length / 2);
    const core = prices.length % 2 !== 0 ? prices[mid] : (prices[mid - 1] + prices[mid]) / 2;
    return {
      core: core,
      lower: prices[0],
      upper: prices[prices.length - 1],
      touches: cl.length,
    };
  });

  const lastClose = candles[n - 1].close;
  const confirmed = zones.filter(z => z.touches >= 2);
  const candidatesSup = confirmed.filter(z => z.core < lastClose).length > 0 
    ? confirmed.filter(z => z.core < lastClose) 
    : zones.filter(z => z.core < lastClose);
  const candidatesRes = confirmed.filter(z => z.core > lastClose).length > 0 
    ? confirmed.filter(z => z.core > lastClose) 
    : zones.filter(z => z.core > lastClose);

  const s1 = candidatesSup.length > 0 ? candidatesSup.reduce((p, c) => c.core > p.core ? c : p) : null;
  const r1 = candidatesRes.length > 0 ? candidatesRes.reduce((p, c) => c.core < p.core ? c : p) : null;

  return { atr: currentAtr, s1, r1, zones };
}

async function openChartModal(ticker, timeframe, assetClass) {
  activeTicker = ticker;
  activeTf = timeframe || '1D';
  activeClass = assetClass || 'crypto';

  const modal = document.getElementById('chartModal');
  const loading = document.getElementById('chartLoading');
  modal.style.display = 'flex';
  loading.style.display = 'flex';

  const item = allSymbols.find(s => s.ticker === ticker) || {};
  document.getElementById('modalTicker').textContent = ticker;
  document.getElementById('modalClass').textContent = CLASS_LABELS[assetClass] || assetClass;
  
  const tfCode = activeTf === '4H' ? '240' : activeTf;
  const tvSym = item.tv_symbol || (assetClass === 'crypto' ? `BINANCE:${ticker}` : ticker);
  document.getElementById('modalTvBtn').href = `https://www.tradingview.com/chart/?symbol=${tvSym}&interval=${tfCode}`;

  // Update Active TF Buttons
  document.querySelectorAll('#modalTfGroup .modal-tf-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tf === activeTf);
  });

  // Clear previous chart
  const container = document.getElementById('chartCanvas');
  container.innerHTML = '';
  if (activeChart) {
    try { activeChart.remove(); } catch(e) {}
    activeChart = null;
  }

  // Fetch candles
  let candles = [];
  const isCrypto = assetClass === 'crypto' || ticker.endsWith('USDT');

  if (isCrypto) {
    const binanceInterval = activeTf.toLowerCase();
    try {
      const url = `https://api.binance.com/api/v3/klines?symbol=${ticker}&interval=${binanceInterval}&limit=180`;
      const res = await fetch(url);
      if (res.ok) {
        const raw = await res.json();
        candles = raw.map(k => ({
          time: Math.floor(k[0] / 1000),
          open: parseFloat(k[1]),
          high: parseFloat(k[2]),
          low: parseFloat(k[3]),
          close: parseFloat(k[4]),
          volume: parseFloat(k[5]),
        }));
      }
    } catch (e) {
      console.warn('Binance direct fetch failed:', e);
    }
  }

  // If candles fetched successfully, render with Lightweight Charts
  if (candles.length > 30) {
    renderLightweightChart(container, candles, item);
  } else {
    // Non-crypto fallback: Render embedded TradingView Advanced Widget
    renderTradingViewWidget(container, tvSym, tfCode, item);
  }

  loading.style.display = 'none';
}

function renderLightweightChart(container, candles, item) {
  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth || 1050,
    height: 500,
    layout: {
      background: { color: '#0b0e14' },
      textColor: '#94a3b8',
      fontSize: 12,
      fontFamily: "'JetBrains Mono', monospace",
    },
    grid: {
      vertLines: { color: 'rgba(36, 44, 61, 0.4)' },
      horzLines: { color: 'rgba(36, 44, 61, 0.4)' },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
    },
    rightPriceScale: {
      borderColor: '#242c3d',
      scaleMargins: { top: 0.1, bottom: 0.15 },
    },
    timeScale: {
      borderColor: '#242c3d',
      timeVisible: true,
      secondsVisible: false,
    },
  });
  activeChart = chart;

  // 1. Candlestick Series
  const candleSeries = chart.addCandlestickSeries({
    upColor: '#10b981',
    downColor: '#ef4444',
    borderVisible: false,
    wickUpColor: '#10b981',
    wickDownColor: '#ef4444',
  });
  candleSeries.setData(candles);

  // 2. Compute Larsson Ribbon (SMMAs on hl2)
  const hl2 = candles.map(c => (c.high + c.low) / 2);
  const v1 = computeSMMA(hl2, 15);
  const m1 = computeSMMA(hl2, 19);
  const m2 = computeSMMA(hl2, 25);
  const v2 = computeSMMA(hl2, 29);

  const v1Series = chart.addLineSeries({ color: '#f59e0b', lineWidth: 2, title: 'v1' });
  const m1Series = chart.addLineSeries({ color: '#f97316', lineWidth: 2, title: 'm1' });
  const m2Series = chart.addLineSeries({ color: '#3b82f6', lineWidth: 2, title: 'm2' });
  const v2Series = chart.addLineSeries({ color: '#a855f7', lineWidth: 2, title: 'v2' });

  const formatLineData = (arr) => {
    const res = [];
    for (let i = 0; i < candles.length; i++) {
      if (!isNaN(arr[i])) res.push({ time: candles[i].time, value: arr[i] });
    }
    return res;
  };

  v1Series.setData(formatLineData(v1));
  m1Series.setData(formatLineData(m1));
  m2Series.setData(formatLineData(m2));
  v2Series.setData(formatLineData(v2));

  // 3. Compute Support & Resistance Zones
  const sr = computePivotsAndZones(candles);
  const lastPrice = candles[candles.length - 1].close;

  // Use either calculated S1/R1 or item precomputed S1/R1
  const s1Val = sr.s1 ? sr.s1.core : item.s1;
  const s1Touches = sr.s1 ? sr.s1.touches : (item.s1_touches || 0);
  const r1Val = sr.r1 ? sr.r1.core : item.r1;
  const r1Touches = sr.r1 ? sr.r1.touches : (item.r1_touches || 0);

  const s1Dist = s1Val ? Math.abs(((lastPrice - s1Val) / lastPrice) * 100).toFixed(1) : null;
  const r1Dist = r1Val ? Math.abs(((r1Val - lastPrice) / lastPrice) * 100).toFixed(1) : null;

  // 4. Draw Horizontal Price Lines
  if (s1Val) {
    candleSeries.createPriceLine({
      price: s1Val,
      color: '#10b981',
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: `🟢 S1 (${s1Dist ? '-' + s1Dist + '%' : ''})`,
    });
  }

  if (r1Val) {
    candleSeries.createPriceLine({
      price: r1Val,
      color: '#ef4444',
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: `🔴 R1 (${r1Dist ? '+' + r1Dist + '%' : ''})`,
    });
  }

  // 4b. Draw Trade Setup Price Lines (Entry, SL, TP1, TP2)
  const ts = item.trade_suggestion;
  if (ts && ts.action !== 'WAIT') {
    if (ts.entry) {
      candleSeries.createPriceLine({
        price: ts.entry,
        color: '#06b6d4',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `🔹 Entry ($${formatShortPrice(ts.entry)})`,
      });
    }
    if (ts.sl) {
      candleSeries.createPriceLine({
        price: ts.sl,
        color: '#ef4444',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `🛑 SL ($${formatShortPrice(ts.sl)})`,
      });
    }
    if (ts.tp1) {
      candleSeries.createPriceLine({
        price: ts.tp1,
        color: '#10b981',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `🎯 TP1 ($${formatShortPrice(ts.tp1)})`,
      });
    }
    if (ts.tp2) {
      candleSeries.createPriceLine({
        price: ts.tp2,
        color: '#22c55e',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        axisLabelVisible: true,
        title: `🚀 TP2 ($${formatShortPrice(ts.tp2)})`,
      });
    }
  }

  // 4c. Draw DCF Fair Value Line from institutional valuation
  if (item && item.fundamental && item.fundamental.fair_value) {
    const fv = item.fundamental.fair_value;
    candleSeries.createPriceLine({
      price: fv,
      color: '#c084fc',
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: `🎯 DCF Fair Value ($${formatShortPrice(fv)})`,
    });
  }

  // Update Trade Suggestion Strip in Modal
  updateModalTradeSuggestionStrip(ts, item);

  // 5. Update S/R Metrics Strip
  document.getElementById('modalPrice').textContent = `$${lastPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById('modalS1').textContent = s1Val ? `$${s1Val.toLocaleString('en-US', { minimumFractionDigits: 2 })} (-${s1Dist}%)` : 'None';
  document.getElementById('modalS1Touches').textContent = `${s1Touches} touches`;
  document.getElementById('modalR1').textContent = r1Val ? `$${r1Val.toLocaleString('en-US', { minimumFractionDigits: 2 })} (+${r1Dist}%)` : 'Price Discovery';
  document.getElementById('modalR1Touches').textContent = `${r1Touches} touches`;
  document.getElementById('modalAtr').textContent = `$${(sr.atr || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;

  // Context Tag
  const ctxElem = document.getElementById('modalContext');
  const ctxDesc = document.getElementById('modalContextDesc');
  if (r1Dist !== null && parseFloat(r1Dist) <= 1.5) {
    ctxElem.textContent = '⚠️ NEAR RESISTANCE';
    ctxElem.style.color = '#ef4444';
    ctxDesc.textContent = `Right below R1 (+${r1Dist}%)`;
  } else if (s1Dist !== null && parseFloat(s1Dist) <= 1.5) {
    ctxElem.textContent = '🎯 NEAR SUPPORT';
    ctxElem.style.color = '#10b981';
    ctxDesc.textContent = `Right above S1 (-${s1Dist}%)`;
  } else if (!r1Val) {
    ctxElem.textContent = '🚀 ALL TIME HIGH';
    ctxElem.style.color = '#f59e0b';
    ctxDesc.textContent = 'Trading above all key resistances';
  } else {
    ctxElem.textContent = '✅ IN VALUE RANGE';
    ctxElem.style.color = '#38bdf8';
    ctxDesc.textContent = `Room to run to R1 (+${r1Dist}%)`;
  }

  chart.timeScale().fitContent();
}

function updateModalTradeSuggestionStrip(ts, item) {
  // 1. Update Fundamental Valuation Strip in Modal
  const fundStrip = document.getElementById('modalFundStrip');
  if (fundStrip) {
    if (item && item.fundamental) {
      fundStrip.style.display = 'grid';
      const f = item.fundamental;
      const verdictEl = document.getElementById('modalFundVerdict');
      const upsideEl = document.getElementById('modalFundUpside');
      const fvEl = document.getElementById('modalFundFairValue');
      const mosEl = document.getElementById('modalFundMos');
      const moatEl = document.getElementById('modalFundMoat');
      const roicEl = document.getElementById('modalFundRoic');
      const zscoreEl = document.getElementById('modalFundZScore');
      const healthEl = document.getElementById('modalFundHealthDesc');

      if (verdictEl) verdictEl.textContent = f.verdict ? f.verdict.split('/')[0].trim() : 'N/A';
      if (upsideEl) upsideEl.textContent = (f.upside_pct !== null && f.upside_pct !== undefined) ? `${f.upside_pct > 0 ? '+' : ''}${Math.round(f.upside_pct)}% Intrinsic Upside` : 'Target Aligned';
      if (fvEl) fvEl.textContent = f.fair_value ? '$' + formatShortPrice(f.fair_value) : 'Market Target';
      if (mosEl) mosEl.textContent = (f.mos_pct !== null && f.mos_pct !== undefined) ? `Margin of Safety: ${Math.round(f.mos_pct)}%` : 'MoS: Standard';
      if (moatEl) moatEl.textContent = `${f.moat || 'None'} Moat`;
      if (roicEl) roicEl.textContent = f.roic_pct ? `ROIC: ${f.roic_pct.toFixed(1)}%` : (f.moat === 'Wide' ? 'Monopoly / Network' : 'Standard Quality');
      if (zscoreEl) zscoreEl.textContent = f.z_score ? `Z-Score: ${f.z_score.toFixed(2)}` : 'Safe Metric';
      if (healthEl) healthEl.textContent = f.z_score >= 2.99 ? 'Safe Balance Sheet' : (f.z_score >= 1.81 ? 'Grey Zone' : (f.z_score ? 'Distress Risk' : 'Healthy'));
    } else {
      fundStrip.style.display = 'none';
    }
  }

  // 2. Update Trade Suggestion Strip in Modal
  const setupStrip = document.getElementById('modalSetupStrip');
  const actionElem = document.getElementById('modalSetupAction');
  const tierElem = document.getElementById('modalSetupTier');
  const typeElem = document.getElementById('modalSetupType');
  const entryElem = document.getElementById('modalSetupEntry');
  const slElem = document.getElementById('modalSetupSl');
  const tp1Elem = document.getElementById('modalSetupTp1');
  const tp2Elem = document.getElementById('modalSetupTp2');
  const rrElem = document.getElementById('modalSetupRr');
  const reasonElem = document.getElementById('modalSetupReason');

  if (!actionElem) return;

  const isCrypto = item && (item.asset_class === 'crypto' || (item.ticker && item.ticker.endsWith('USDT')));
  if (setupStrip) {
    if (isCrypto) {
      setupStrip.classList.add('strip-crypto');
      setupStrip.classList.remove('strip-equity');
    } else {
      setupStrip.classList.add('strip-equity');
      setupStrip.classList.remove('strip-crypto');
    }
  }

  if (!ts || ts.action === 'WAIT') {
    if (ts && (ts.setup_type === 'VALUE_TRAP_WARNING' || ts.quantamental_tag === 'VALUE_TRAP_RISK')) {
      actionElem.className = 'setup-action-badge ts-valuetrap';
      actionElem.textContent = '⏳ VALUE TRAP';
      tierElem.textContent = 'Wait For Pivot';
      tierElem.style.display = 'inline-block';
      tierElem.className = 'setup-tier-badge';
      typeElem.textContent = 'Downtrend Warning';
    } else {
      actionElem.className = 'setup-action-badge ts-wait';
      actionElem.textContent = '⏳ WAIT';
      tierElem.textContent = 'No Active Setup';
      tierElem.style.display = 'none';
      typeElem.textContent = 'Consolidation / Low R:R';
    }
    entryElem.textContent = '$' + formatShortPrice(item.price || 0);
    slElem.textContent = 'N/A';
    tp1Elem.textContent = 'N/A';
    tp2Elem.textContent = 'N/A';
    rrElem.textContent = 'N/A';
    reasonElem.textContent = ts && (ts.reason_bg || ts.reason_en) 
      ? (ts.reason_bg || ts.reason_en) 
      : 'Цената е в междинна зона без ясен институционален сетап. Изчакай тест на ключово ниво.';
    updateModalPositionCalculator(ts, item);
    return;
  }

  tierElem.style.display = 'inline-block';
  if (isCrypto) {
    tierElem.className = 'setup-tier-badge tier-crypto-badge';
    if (ts.setup_type === 'QUANTAMENTAL_ALPHA_BUY') {
      actionElem.className = 'setup-action-badge ts-crypto-alpha';
      actionElem.textContent = '🪙 ALPHA BUY';
    } else if (ts.setup_type === 'QUALITY_HOLD_ACCUMULATION') {
      actionElem.className = 'setup-action-badge ts-crypto-accum';
      actionElem.textContent = '🪙 ACCUMULATE';
    } else if (ts.setup_type === 'SPECULATIVE_MOMENTUM_BUY' || ts.setup_type === 'SPECULATIVE_PULLBACK_BUY') {
      actionElem.className = 'setup-action-badge ts-crypto-speculative';
      actionElem.textContent = '🪙⚠️ SPECULATIVE';
    } else if (ts.action === 'SPOT_BUY') {
      actionElem.className = 'setup-action-badge ts-crypto-buy';
      actionElem.textContent = '🪙 CRYPTO BUY';
    } else if (ts.action === 'TAKE_PROFIT') {
      actionElem.className = 'setup-action-badge ts-crypto-profit';
      actionElem.textContent = '🪙💰 TAKE PROFIT';
    } else if (ts.action === 'EXIT_PROTECT') {
      actionElem.className = 'setup-action-badge ts-crypto-exit';
      actionElem.textContent = '🪙🛡️ EXIT / STOP';
    } else if (ts.action === 'SHORT_2X_OPTIONAL') {
      actionElem.className = 'setup-action-badge ts-short';
      actionElem.textContent = '🔴 SHORT 2X';
    }
  } else {
    tierElem.className = 'setup-tier-badge tier-equity-badge';
    if (ts.setup_type === 'QUANTAMENTAL_ALPHA_BUY') {
      actionElem.className = 'setup-action-badge ts-equity-alpha';
      actionElem.textContent = '🏛️ ALPHA BUY';
    } else if (ts.setup_type === 'QUALITY_HOLD_ACCUMULATION') {
      actionElem.className = 'setup-action-badge ts-equity-accum';
      actionElem.textContent = '🏛️ ACCUMULATE';
    } else if (ts.setup_type === 'SPECULATIVE_MOMENTUM_BUY' || ts.setup_type === 'SPECULATIVE_PULLBACK_BUY') {
      actionElem.className = 'setup-action-badge ts-equity-speculative';
      actionElem.textContent = '🏛️⚠️ SPECULATIVE';
    } else if (ts.action === 'SPOT_BUY') {
      actionElem.className = 'setup-action-badge ts-equity-buy';
      actionElem.textContent = '🏛️ EQUITY BUY';
    } else if (ts.action === 'TAKE_PROFIT') {
      actionElem.className = 'setup-action-badge ts-equity-profit';
      actionElem.textContent = '🏛️💰 TAKE PROFIT';
    } else if (ts.action === 'EXIT_PROTECT') {
      actionElem.className = 'setup-action-badge ts-equity-exit';
      actionElem.textContent = '🏛️🛡️ EXIT / STOP';
    } else if (ts.action === 'SHORT_2X_OPTIONAL') {
      actionElem.className = 'setup-action-badge ts-short';
      actionElem.textContent = '🔴 SHORT 2X';
    }
  }

  tierElem.textContent = `⭐ Tier ${ts.tier} (${ts.score}/100)`;
  typeElem.textContent = ts.setup_type ? ts.setup_type.replace(/_/g, ' ') : '';
  entryElem.textContent = ts.entry ? '$' + ts.entry.toLocaleString('en-US', { minimumFractionDigits: 2 }) : 'Market';
  slElem.textContent = ts.sl ? '$' + ts.sl.toLocaleString('en-US', { minimumFractionDigits: 2 }) : 'N/A';
  tp1Elem.textContent = ts.tp1 ? '$' + ts.tp1.toLocaleString('en-US', { minimumFractionDigits: 2 }) : 'N/A';
  tp2Elem.textContent = ts.tp2 ? '$' + ts.tp2.toLocaleString('en-US', { minimumFractionDigits: 2 }) : 'N/A';
  rrElem.textContent = ts.rr ? `1 : ${ts.rr}` : 'N/A';
  reasonElem.textContent = ts.reason_bg || ts.reason_en || '';
  updateModalPositionCalculator(ts, item);
}

function renderTradingViewWidget(container, tvSymbol, tfCode, item) {
  // TradingView Advanced Chart Widget for non-crypto
  container.innerHTML = `
    <div id="tvWidgetContainer" style="width: 100%; height: 500px;"></div>
  `;

  if (!window.TradingView) {
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/tv.js';
    script.onload = () => initTvWidget(tvSymbol, tfCode);
    document.head.appendChild(script);
  } else {
    initTvWidget(tvSymbol, tfCode);
  }

  // Update strip with precomputed data from data.json
  const p = item.price || 0;
  document.getElementById('modalPrice').textContent = `$${p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById('modalS1').textContent = item.s1 ? `$${item.s1.toLocaleString('en-US', { minimumFractionDigits: 2 })} (-${item.s1_dist_pct}%)` : 'None';
  document.getElementById('modalS1Touches').textContent = `${item.s1_touches || 0} touches`;
  document.getElementById('modalR1').textContent = item.r1 ? `$${item.r1.toLocaleString('en-US', { minimumFractionDigits: 2 })} (+${item.r1_dist_pct}%)` : 'None';
  document.getElementById('modalR1Touches').textContent = `${item.r1_touches || 0} touches`;
  document.getElementById('modalAtr').textContent = 'N/A';
  document.getElementById('modalContext').textContent = item.context_flag || 'IN VALUE RANGE';
  document.getElementById('modalContextDesc').textContent = item.context_desc || '';

  // Update trade suggestion strip
  updateModalTradeSuggestionStrip(item.trade_suggestion, item);
}

function initTvWidget(tvSymbol, tfCode) {
  new TradingView.widget({
    "autosize": true,
    "symbol": tvSymbol,
    "interval": tfCode,
    "timezone": "Etc/UTC",
    "theme": "dark",
    "style": "1",
    "locale": "en",
    "toolbar_bg": "#0b0e14",
    "enable_publishing": false,
    "hide_side_toolbar": false,
    "allow_symbol_change": true,
    "container_id": "tvWidgetContainer"
  });
}

function closeChartModal() {
  document.getElementById('chartModal').style.display = 'none';
  if (activeChart) {
    try { activeChart.remove(); } catch(e) {}
    activeChart = null;
  }
}

// Event Listeners for Modal
document.getElementById('closeModalBtn').addEventListener('click', closeChartModal);
document.getElementById('chartModal').addEventListener('click', (e) => {
  if (e.target.id === 'chartModal') closeChartModal();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeChartModal();
});

// Timeframe Switcher in Modal
document.querySelectorAll('#modalTfGroup .modal-tf-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    const newTf = e.target.dataset.tf;
    if (newTf !== activeTf) {
      openChartModal(activeTicker, newTf, activeClass);
    }
  });
});

// Responsive resize for Lightweight Charts
window.addEventListener('resize', () => {
  const container = document.getElementById('chartCanvas');
  if (activeChart && container && container.clientWidth) {
    activeChart.applyOptions({ width: container.clientWidth });
  }
});

// =============================================================================
// POSITION SIZING & STAGGERED DCA CALCULATOR
// =============================================================================

function updateModalPositionCalculator(ts, item) {
  currentModalItem = item;
  const calcStrip = document.getElementById('modalPosCalcStrip');
  if (!calcStrip) return;

  const dcaPill = document.getElementById('modalDcaPill');
  const entry = (ts && ts.entry) || (item && item.price) || 0;
  const s1 = item && item.s1;

  if (dcaPill) {
    if (ts && ts.dca_plan) {
      dcaPill.textContent = `🧱 ${ts.dca_plan}`;
      dcaPill.style.display = 'inline-block';
    } else if (s1 && s1 < entry && item && item.fundamental && (item.fundamental.moat === 'Wide' || item.fundamental.moat === 'Narrow')) {
      dcaPill.textContent = `🧱 50% Market ($${formatShortPrice(entry)}) + 50% Limit S1 ($${formatShortPrice(s1)})`;
      dcaPill.style.display = 'inline-block';
    } else {
      dcaPill.style.display = 'none';
    }
  }

  recalculatePositionSize();
}

function recalculatePositionSize() {
  if (!currentModalItem) return;
  const ts = currentModalItem.trade_suggestion;
  const price = currentModalItem.price || 1.0;
  const entry = (ts && ts.entry) || price;
  let sl = (ts && ts.sl);
  const tp1 = (ts && ts.tp1);

  if (!sl || sl >= entry) {
    sl = entry * 0.95; // default 5% risk floor for calculation
  }

  const accountSizeInput = document.getElementById('calcAccountSize');
  const riskPctInput = document.getElementById('calcRiskPct');
  if (!accountSizeInput || !riskPctInput) return;

  const accountSize = parseFloat(accountSizeInput.value) || 10000;
  const riskPct = parseFloat(riskPctInput.value) || 1.0;

  const riskUsd = accountSize * (riskPct / 100);
  const riskPerUnit = Math.abs(entry - sl);

  if (riskPerUnit > 0 && entry > 0) {
    const units = riskUsd / riskPerUnit;
    const unitsFormatted = entry < 1 ? units.toFixed(4) : (entry < 50 ? units.toFixed(2) : (entry < 1000 ? units.toFixed(1) : units.toFixed(3)));
    const posValue = units * entry;
    const tp1Profit = tp1 ? units * Math.abs(tp1 - entry) : null;

    const unitsEl = document.getElementById('calcUnits');
    const posValEl = document.getElementById('calcPosValue');
    const riskUsdEl = document.getElementById('calcRiskUsd');
    const tp1UsdEl = document.getElementById('calcTp1Usd');

    if (unitsEl) unitsEl.textContent = `${unitsFormatted} ${currentModalItem.asset_class === 'crypto' ? 'tokens' : 'shares'}`;
    if (posValEl) posValEl.textContent = `$${posValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (riskUsdEl) riskUsdEl.textContent = `-$${riskUsd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (tp1UsdEl) tp1UsdEl.textContent = tp1Profit ? `+$${tp1Profit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'N/A';
  }
}

function updateSortIndicators() {
  document.querySelectorAll('.th-sortable').forEach(th => {
    th.classList.remove('th-sort-asc', 'th-sort-desc');
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = '⇅';
    if (th.dataset.sort === currentSortColumn) {
      th.classList.add(currentSortDir === 'asc' ? 'th-sort-asc' : 'th-sort-desc');
      if (icon) icon.textContent = currentSortDir === 'asc' ? '▲' : '▼';
    }
  });
}

// =============================================================================
// GLOBAL EVENT LISTENERS & FILTERS
// =============================================================================

document.querySelectorAll('#viewToggle .toggle-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    currentView = e.target.dataset.view;
    localStorage.setItem('larsson_view_mode', currentView);
    applyViewMode();
  });
});

document.querySelectorAll('#stateFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#stateFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentFilter = e.target.dataset.filter;
    renderAllViews();
  });
});

document.querySelectorAll('#tfFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#tfFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentTfFilter = e.target.dataset.tf;
    renderOverview();
    renderAllViews();
  });
});

document.querySelectorAll('#setupFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#setupFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentSetupFilter = e.target.dataset.setup;
    renderAllViews();
  });
});

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

// Table Column Sorting Click Listener
document.querySelectorAll('.th-sortable').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.sort;
    if (currentSortColumn === col) {
      currentSortDir = currentSortDir === 'asc' ? 'desc' : 'asc';
    } else {
      currentSortColumn = col;
      currentSortDir = (col === 'spread_pct' || col === 'tier') ? 'desc' : 'asc';
    }
    updateSortIndicators();
    renderAllViews();
  });
});

// Position Calculator Inputs Event Listeners
const accInput = document.getElementById('calcAccountSize');
if (accInput) accInput.addEventListener('input', recalculatePositionSize);

const riskInput = document.getElementById('calcRiskPct');
if (riskInput) riskInput.addEventListener('input', recalculatePositionSize);

document.querySelectorAll('#riskPresets .risk-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#riskPresets .risk-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    const val = parseFloat(e.target.dataset.risk);
    if (riskInput) riskInput.value = val;
    recalculatePositionSize();
  });
});

document.getElementById('refreshBtn').addEventListener('click', () => {
  loadDashboardData();
});

// Auto-refresh every 60 seconds
setInterval(loadDashboardData, 60000);

// Initialize
loadDashboardData();
