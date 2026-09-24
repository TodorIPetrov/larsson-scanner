let allSymbols = [];
let pendingSetups = [];
let portfolioData = {};
let portfolioPaperData = {};
let portfolioRealData = {};
let currentPortfolioMode = localStorage.getItem('larsson_portfolio_mode') || 'REAL';
let currentFilter = 'ALL';
let currentClass = 'ALL';
let currentTfFilter = 'ALL';
let currentTechFilter = 'ALL';
let currentFundFilter = 'ALL';
let currentSetupFilter = 'ALL';
let currentQueuePriority = 'ALL';
let currentQueueTier = 'ALL';
let currentSearch = '';
let currentView = localStorage.getItem('larsson_view_mode') || 'table';
let currentTab = localStorage.getItem('larsson_active_tab') || 'scanner';

let currentSortColumn = null;
let currentSortDir = 'asc';
let currentModalItem = null;

// Active chart state
let activeChart = null; // modal chart instance
let activeTicker = '';
let activeTf = '1D';
let activeClass = '';

// Live on-page chart state
let liveActiveChart = null;
let liveTicker = 'BTCUSDT';
let liveTf = '1D';
let liveClass = 'crypto';
let liveChartInitialized = false;

function getTvInterval(tf) {
  if (!tf) return 'D';
  const upper = tf.toUpperCase();
  if (upper === '4H') return '240';
  if (upper === '1H') return '60';
  if (upper === '1W' || upper === 'W') return 'W';
  if (upper === '1M' || upper === 'M') return 'M';
  return 'D';
}

function getTvSymbol(item, ticker, assetClass) {
  if (item && item.tv_symbol) return item.tv_symbol;
  if (assetClass === 'crypto' || (ticker && ticker.endsWith('USDT'))) {
    return `BINANCE:${ticker}`;
  }
  return ticker;
}

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

// =============================================================================
// THREE-PILLAR CELL RENDERERS (TECHNICAL / FUNDAMENTAL / SYNTHESIS)
// =============================================================================

function renderTechCell(tech, item) {
  if (!tech) {
    return `<div class="tech-cell"><span class="tech-badge tech-badge-wait">⏳ N/A</span></div>`;
  }
  const action = tech.action || 'WAIT';
  let badgeClass = 'tech-badge-wait';
  if (action === 'BUY') badgeClass = 'tech-badge-buy';
  else if (action === 'ACCUMULATE') badgeClass = 'tech-badge-hold';
  else if (action === 'TAKE_PROFIT') badgeClass = 'tech-badge-profit';
  else if (action === 'EXIT') badgeClass = 'tech-badge-exit';

  const spreadVal = item.spread_pct !== undefined ? item.spread_pct : 0.0;
  const spreadSign = spreadVal > 0 ? '+' : '';
  const spreadClass = spreadVal > 0 ? 'spread-pos' : (spreadVal < 0 ? 'spread-neg' : 'spread-neu');
  const spreadLabel = `${spreadSign}${spreadVal.toFixed(2)}%`;

  let tagClass = 'tag-neutral';
  if (item.state === 'GOLD') tagClass = 'tag-gold';
  else if (item.state === 'BLUE') tagClass = 'tag-blue';

  const hasS1 = item.s1 !== null && item.s1 !== undefined;
  const s1Txt = hasS1 ? `S1: $${formatShortPrice(item.s1)}` : '';

  return `
    <div class="tech-cell">
      <span class="tech-badge ${badgeClass}" title="${tech.thesis || ''}">
        ${tech.label_bg || action}
      </span>
      <div class="tech-sub-info">
        <span class="tech-ribbon-tag ${tagClass}">${item.state} (${spreadLabel})</span>
        ${hasS1 ? `<span title="Подкрепа S1: $${item.s1} (-${item.s1_dist_pct}%)">${s1Txt}</span>` : ''}
      </div>
    </div>
  `;
}

function renderFundCell(fund, item) {
  if (!fund) {
    return `<div class="fund-cell"><span class="fund-badge fund-badge-speculative">⚪ N/A</span></div>`;
  }
  const action = fund.action || 'SPECULATIVE_NA';
  let badgeClass = 'fund-badge-speculative';
  if (action === 'STRONG_BUY') badgeClass = 'fund-badge-strong-buy';
  else if (action === 'BUY') badgeClass = 'fund-badge-buy';
  else if (action === 'HOLD') badgeClass = 'fund-badge-hold';
  else if (action === 'REDUCE') badgeClass = 'fund-badge-reduce';
  else badgeClass = 'fund-badge-speculative';

  let moatPill = '';
  if (fund.moat === 'Wide') {
    moatPill = `<span class="fund-moat-chip moat-wide" title="Wide Economic Moat (Конкурентно предимство)">💎 Wide</span>`;
  } else if (fund.moat === 'Narrow') {
    moatPill = `<span class="fund-moat-chip moat-narrow" title="Narrow Economic Moat">🏰 Narrow</span>`;
  }

  let dcfChip = '';
  if (fund.fair_value) {
    const mosTxt = (fund.mos_pct !== null && fund.mos_pct !== undefined) ? ` | MoS: ${fund.mos_pct}%` : '';
    dcfChip = `<span class="fund-dcf-chip" title="DCF Справедлива стойност: $${formatShortPrice(fund.fair_value)}${mosTxt}">DCF: $${formatShortPrice(fund.fair_value)}</span>`;
  }

  return `
    <div class="fund-cell">
      <span class="fund-badge ${badgeClass}" title="${fund.thesis_bg || fund.thesis || ''}">
        ${fund.label_bg || '⚪ МАКРО / СПЕКУЛАТИВЕН'}
      </span>
      <div class="fund-sub-row">
        ${dcfChip}
        ${moatPill}
      </div>
    </div>
  `;
}

function renderSynthesisCell(synth, ts, item) {
  const s = synth || (ts ? {
    setup_type: ts.setup_type,
    action: ts.action,
    badge_bg: ts.synthesis_badge_bg,
    label_bg: ts.synthesis_label_bg,
    entry: ts.entry,
    sl: ts.sl,
    tp1: ts.tp1,
    tp2: ts.tp2,
    rr: ts.rr,
    tier: ts.tier,
    score: ts.score
  } : null);

  if (!s || s.action === 'WAIT') {
    if (s && (s.setup_type === 'VALUE_TRAP_WARNING')) {
      return `
        <div class="synth-cell">
          <span class="synth-badge synth-badge-trap" title="${s.label_bg || 'Предупреждение за капан на стойността'}">
            ${s.badge_bg || '⏳ VALUE TRAP'}
          </span>
          <div class="synth-params-row"><span>Изчакай технически обръщащ сигнал</span></div>
        </div>
      `;
    }
    return `
      <div class="synth-cell">
        <span class="synth-badge synth-badge-wait" title="${s ? s.label_bg : 'Изчакване на структура'}">
          ${(s && s.badge_bg) || '⏳ WAIT'}
        </span>
      </div>
    `;
  }

  let badgeClass = 'synth-badge-buy';
  if (s.setup_type === 'QUANTAMENTAL_ALPHA_BUY') badgeClass = 'synth-badge-alpha';
  else if (s.setup_type === 'VALUE_TRAP_WARNING') badgeClass = 'synth-badge-trap';
  else if (s.setup_type === 'QUALITY_HOLD_ACCUMULATION') badgeClass = 'synth-badge-accumulate';
  else if (s.setup_type && s.setup_type.includes('SPECULATIVE')) badgeClass = 'synth-badge-speculative';
  else if (s.action === 'SPOT_BUY') badgeClass = 'synth-badge-buy';
  else if (s.action === 'TAKE_PROFIT') badgeClass = 'synth-badge-profit';
  else if (s.action === 'EXIT_PROTECT') badgeClass = 'synth-badge-protect';

  const hasEntry = s.entry !== null && s.entry !== undefined;
  const rrTxt = s.rr ? `1:${s.rr}` : '';

  return `
    <div class="synth-cell">
      <span class="synth-badge ${badgeClass}" title="${s.label_bg || (ts && ts.reason_bg) || ''}">
        ${s.badge_bg || s.action}
      </span>
      ${hasEntry ? `
      <div class="synth-params-row">
        <span>Вход: <strong>$${formatShortPrice(s.entry)}</strong></span>
        ${s.sl ? `<span>SL: <strong>$${formatShortPrice(s.sl)}</strong></span>` : ''}
        ${rrTxt ? `<span class="synth-rr-pill">${rrTxt}</span>` : ''}
      </div>
      ` : ''}
    </div>
  `;
}

function renderTradeSuggestionCell(ts, item) {
  return renderSynthesisCell(item ? item.synthesis : null, ts, item);
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
    pendingSetups = data.pending_setups || [];
    portfolioData = data.portfolio || {};
    portfolioPaperData = data.portfolio_paper || { summary: portfolioData, positions: [], history: [], journal: [] };
    portfolioRealData = data.portfolio_real || { summary: {}, positions: [], history: [], journal: [] };

    // Sync any custom positions or cash saved locally in this browser
    syncLocalRealStorage();

    renderOverview(data);
    renderQueueView();
    initPortfolioController();
    switchPortfolioMode(currentPortfolioMode);
    initPageCalculator();
    switchTab(currentTab);
  } catch (err) {
    console.error('Error loading data.json:', err);
    const isFileProtocol = window.location.protocol === 'file:';
    const errorHtml = isFileProtocol ? `
      <div style="padding: 24px; text-align: center; line-height: 1.6;">
        <h3 style="color: #f59e0b; margin-bottom: 8px;">⚠️ Браузърът блокира зареждането през file:// протокол (CORS)</h3>
        <p style="color: var(--text-muted); margin-bottom: 16px;">
          За сигурност уеб браузърите не позволяват четене на JSON данни при директно отваряне с двоен клик на файла.
        </p>
        <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
          <a href="http://localhost:8080" class="btn btn-refresh" style="text-decoration: none; padding: 10px 18px; font-weight: 600;">
            🚀 Отвори през Localhost:8080
          </a>
          <a href="https://todoripetrov.github.io/larsson-scanner/" target="_blank" rel="noopener" class="btn btn-refresh" style="text-decoration: none; padding: 10px 18px; font-weight: 600; background: rgba(234, 179, 8, 0.15); border-color: #eab308; color: #facc15;">
            🌐 Отвори в GitHub Pages
          </a>
        </div>
      </div>
    ` : `⚠️ Failed to load <code>data.json</code>. Run a scan first: <code>python src/main.py --scan</code>`;

    document.getElementById('assetsTableBody').innerHTML = `
      <tr>
        <td colspan="14" class="loading-state" style="color: #ef4444;">
          ${errorHtml}
        </td>
      </tr>
    `;
    const cards = document.getElementById('cardsGrid');
    if (cards) cards.innerHTML = `<div class="loading-state" style="grid-column: 1/-1;">${errorHtml}</div>`;
    return;
  }

  try {
    renderAllViews();
    initLiveChart();
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
    // 1. Asset Class Filter
    const matchesClass = (currentClass === 'ALL') || (item.asset_class === currentClass);
    // 2. Timeframe Filter
    const matchesTf = (currentTfFilter === 'ALL') || (item.timeframe === currentTfFilter);

    // 3. Technical Filter
    const tech = item.technical;
    let matchesTech = true;
    if (currentTechFilter === 'GOLD') {
      matchesTech = item.state === 'GOLD';
    } else if (currentTechFilter === 'BLUE') {
      matchesTech = item.state === 'BLUE';
    } else if (currentTechFilter === 'BUY') {
      matchesTech = tech && (tech.action === 'BUY' || tech.action === 'ACCUMULATE');
    } else if (currentTechFilter === 'EXIT') {
      matchesTech = tech && (tech.action === 'EXIT' || tech.action === 'TAKE_PROFIT');
    }

    // 4. Fundamental Filter
    const fund = item.fundamental;
    let matchesFund = true;
    if (currentFundFilter === 'UNDERVALUED') {
      matchesFund = fund && (fund.action === 'STRONG_BUY' || fund.action === 'BUY' || (fund.mos_pct && fund.mos_pct > 0) || (fund.upside_pct && fund.upside_pct > 0));
    } else if (currentFundFilter === 'WIDE_MOAT') {
      matchesFund = fund && fund.moat === 'Wide';
    } else if (currentFundFilter === 'OVERVALUED') {
      matchesFund = fund && (fund.action === 'REDUCE' || (fund.verdict && fund.verdict.includes('REDUCE')) || (fund.mos_pct && fund.mos_pct < -20));
    } else if (currentFundFilter === 'SPECULATIVE') {
      matchesFund = fund && (fund.action === 'SPECULATIVE_NA' || item.asset_class === 'crypto' || item.asset_class === 'commodities');
    }

    // 5. Quantamental Synthesis Filter
    const synth = item.synthesis;
    const ts = item.trade_suggestion;
    let matchesSetup = true;
    if (currentSetupFilter === 'QUANTAMENTAL_ALPHA') {
      matchesSetup = (synth && synth.setup_type === 'QUANTAMENTAL_ALPHA_BUY') ||
                     (ts && (ts.setup_type === 'QUANTAMENTAL_ALPHA_BUY' || ts.quantamental_tag === 'INSTITUTIONAL_ALPHA'));
    } else if (currentSetupFilter === 'VALUE_TRAP') {
      matchesSetup = (synth && synth.setup_type === 'VALUE_TRAP_WARNING') ||
                     (ts && (ts.setup_type === 'VALUE_TRAP_WARNING' || ts.quantamental_tag === 'VALUE_TRAP_RISK'));
    } else if (currentSetupFilter === 'QUALITY_HOLD') {
      matchesSetup = (synth && synth.setup_type === 'QUALITY_HOLD_ACCUMULATION') ||
                     (ts && (ts.setup_type === 'QUALITY_HOLD_ACCUMULATION' || ts.quantamental_tag === 'CORE_QUALITY_HOLD'));
    } else if (currentSetupFilter === 'SPOT_BUY') {
      matchesSetup = (synth && (synth.action === 'SPOT_BUY' || (synth.setup_type && synth.setup_type.includes('BUY')))) ||
                     (ts && (ts.action === 'SPOT_BUY' || (ts.setup_type && ts.setup_type.includes('BUY'))));
    }

    // 6. Search Filter
    const matchesSearch = !q ||
      item.ticker.toLowerCase().includes(q) ||
      (item.name && item.name.toLowerCase().includes(q));

    return matchesClass && matchesTf && matchesTech && matchesFund && matchesSetup && matchesSearch;
  });

  if (currentSortColumn) {
    const stateRanks = { 'GOLD': 3, 'NEUTRAL': 2, 'BLUE': 1 };
    const fundRanks = { 'STRONG_BUY': 4, 'BUY': 3, 'HOLD': 2, 'REDUCE': 1, 'SPECULATIVE_NA': 0 };

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
      } else if (currentSortColumn === 'fund_verdict') {
        const fA = a.fundamental ? (fundRanks[a.fundamental.action] || 0) : 0;
        const fB = b.fundamental ? (fundRanks[b.fundamental.action] || 0) : 0;
        valA = fA * 1000 + ((a.fundamental && a.fundamental.mos_pct) || 0);
        valB = fB * 1000 + ((b.fundamental && b.fundamental.mos_pct) || 0);
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
    document.getElementById('lastUpdated').textContent = `Обновено: ${d.toLocaleTimeString()} (${d.toLocaleDateString()})`;
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
        <td colspan="9" class="loading-state">Няма намерени активи по избраните критерии.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map(item => {
    const tfCode = getTvInterval(item.timeframe);
    const tvSym = getTvSymbol(item, item.ticker, item.asset_class);
    const tvUrl = `https://www.tradingview.com/chart/?symbol=${tvSym}&interval=${tfCode}`;

    const priceFormatted = item.price >= 1000 
      ? `$${item.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : `$${item.price.toFixed(item.price >= 1 ? 2 : 5)}`;

    const classLabel = CLASS_LABELS[item.asset_class] || item.asset_class;

    // S/R Cell Rendering
    let srCellHtml = '';
    const hasS1 = item.s1 !== null && item.s1 !== undefined;
    const hasR1 = item.r1 !== null && item.r1 !== undefined;
    if (hasS1 || hasR1) {
      const s1Txt = hasS1 ? `🟢 S1: $${formatShortPrice(item.s1)} (-${item.s1_dist_pct}%)` : '';
      const r1Txt = hasR1 ? `🔴 R1: $${formatShortPrice(item.r1)} (+${item.r1_dist_pct}%)` : '';
      srCellHtml = `
        <div class="sr-cell">
          ${hasR1 ? `<span class="sr-pill sr-res" title="Съпротива R1: $${item.r1} (${item.r1_touches} теста)">${r1Txt}</span>` : ''}
          ${hasS1 ? `<span class="sr-pill sr-sup" title="Подкрепа S1: $${item.s1} (${item.s1_touches} теста)">${s1Txt}</span>` : ''}
        </div>
      `;
    } else {
      srCellHtml = `<span class="sr-pill sr-na">Няма нива</span>`;
    }

    return `
      <tr class="asset-row ${item.ticker === liveTicker && item.timeframe === liveTf ? 'row-active' : ''}"
          data-ticker="${item.ticker}"
          data-tf="${item.timeframe}"
          onclick="selectLiveAsset('${item.ticker}', '${item.timeframe}', '${item.asset_class}')">
        <td>
          <div class="symbol-cell">
            <a href="${tvUrl}" target="_blank" rel="noopener" class="ticker-link" onclick="event.stopPropagation()" title="Отвори ${tvSym} в TradingView">
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
        <td class="price-cell">${priceFormatted}</td>
        <td>${renderTechCell(item.technical, item)}</td>
        <td>${renderFundCell(item.fundamental, item)}</td>
        <td>${renderSynthesisCell(item.synthesis, item.trade_suggestion, item)}</td>
        <td>${srCellHtml}</td>
        <td>
          <div style="display: flex; gap: 6px; align-items: center;">
            <button class="btn-view-chart" onclick="event.stopPropagation(); openChartModal('${item.ticker}', '${item.timeframe}', '${item.asset_class}')" title="Интерактивна графика и тристепенен анализ">
              📊 S/R
            </button>
            <a href="${tvUrl}" target="_blank" rel="noopener" class="tv-link-btn" onclick="event.stopPropagation()" title="Отвори в TradingView">
              TV ↗
            </a>
          </div>
        </td>
      </tr>
    `;
  }).join('');
  updateActiveRowHighlight();
}

function renderCards() {
  const container = document.getElementById('cardsGrid');
  const filtered = getFilteredSymbols();

  if (filtered.length === 0) {
    container.innerHTML = `<div class="loading-state" style="grid-column: 1/-1;">Няма намерени активи по избраните критерии.</div>`;
    return;
  }

  container.innerHTML = filtered.map(item => {
    const tfCode = getTvInterval(item.timeframe);
    const tvSym = getTvSymbol(item, item.ticker, item.asset_class);
    const tvUrl = `https://www.tradingview.com/chart/?symbol=${tvSym}&interval=${tfCode}`;
    
    let cardClass = 'card-neutral';
    if (item.state === 'GOLD') cardClass = 'card-gold';
    else if (item.state === 'BLUE') cardClass = 'card-blue';

    const priceFormatted = item.price >= 1000 
      ? `$${item.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : `$${item.price.toFixed(item.price >= 1 ? 2 : 5)}`;

    const classLabel = CLASS_LABELS[item.asset_class] || item.asset_class;

    const hasS1 = item.s1 !== null && item.s1 !== undefined;
    const hasR1 = item.r1 !== null && item.r1 !== undefined;

    return `
      <div class="asset-card ${cardClass} ${item.ticker === liveTicker && item.timeframe === liveTf ? 'card-active' : ''}"
           data-ticker="${item.ticker}"
           data-tf="${item.timeframe}"
           onclick="selectLiveAsset('${item.ticker}', '${item.timeframe}', '${item.asset_class}')">
        <div class="card-top">
          <div class="card-identity">
            <a href="${tvUrl}" target="_blank" rel="noopener" class="card-ticker-link" onclick="event.stopPropagation()" title="Отвори TradingView">
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
          <div class="card-price">${priceFormatted}</div>
        </div>

        <!-- 3 Pillars Separation in Card -->
        <div class="card-pillar-box" style="display: flex; flex-direction: column; gap: 8px;">
          <div>
            <div style="font-size: 0.6875rem; color: #38bdf8; font-weight: 700; margin-bottom: 3px;">📐 ТЕХНИЧЕСКИ АНАЛИЗ</div>
            ${renderTechCell(item.technical, item)}
          </div>
          <div>
            <div style="font-size: 0.6875rem; color: #34d399; font-weight: 700; margin-bottom: 3px;">🏢 ФУНДАМЕНТАЛЕН АНАЛИЗ</div>
            ${renderFundCell(item.fundamental, item)}
          </div>
          <div>
            <div style="font-size: 0.6875rem; color: #fbbf24; font-weight: 700; margin-bottom: 3px;">🎯 СИНТЕЗИРАНА СТРАТЕГИЯ</div>
            ${renderSynthesisCell(item.synthesis, item.trade_suggestion, item)}
          </div>
        </div>

        ${hasS1 || hasR1 ? `
          <div style="display: flex; gap: 8px; margin-top: 4px; flex-wrap: wrap;">
            ${hasR1 ? `<span class="sr-pill sr-res">🔴 R1: $${formatShortPrice(item.r1)} (+${item.r1_dist_pct}%)</span>` : ''}
            ${hasS1 ? `<span class="sr-pill sr-sup">🟢 S1: $${formatShortPrice(item.s1)} (-${item.s1_dist_pct}%)</span>` : ''}
          </div>
        ` : ''}

        <div class="card-footer" style="margin-top: 6px;">
          <span class="card-change">Променено: ${item.last_change ? new Date(item.last_change).toLocaleDateString() : 'N/A'}</span>
          <div style="display: flex; gap: 6px; align-items: center;">
            <button class="btn-view-chart" onclick="event.stopPropagation(); openChartModal('${item.ticker}', '${item.timeframe}', '${item.asset_class}')">📊 S/R</button>
            <a href="${tvUrl}" target="_blank" rel="noopener" class="card-chart-btn" onclick="event.stopPropagation()">TV ↗</a>
          </div>
        </div>
      </div>
    `;
  }).join('');
  updateActiveRowHighlight();
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

// =============================================================================
// UNIFIED CHART ENGINE (LIGHTWEIGHT CHARTS + BULLETPROOF TRADINGVIEW IFRAME)
// =============================================================================

function renderTradingViewIframe(container, tvSymbol, timeframe) {
  const tvInterval = getTvInterval(timeframe);
  const iframeSrc = `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(tvSymbol)}&interval=${tvInterval}&theme=dark&style=1&timezone=Etc%2FUTC&withdateranges=1&hide_side_toolbar=0&allow_symbol_change=1&save_image=0`;
  container.innerHTML = `
    <iframe 
      src="${iframeSrc}" 
      style="width: 100%; height: 100%; min-height: 360px; border: none; border-radius: 8px;" 
      title="TradingView Chart - ${tvSymbol}"
      loading="lazy"
      allowtransparency="true" 
      scrolling="no" 
      allowfullscreen>
    </iframe>
  `;
}

function renderLightweightChart(container, candles, item, height = 480) {
  container.innerHTML = '';
  const chartHeight = container.clientHeight || height;
  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth || 1000,
    height: chartHeight,
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

  const s1Val = sr.s1 ? sr.s1.core : (item ? item.s1 : null);
  const r1Val = sr.r1 ? sr.r1.core : (item ? item.r1 : null);

  const s1Dist = s1Val ? Math.abs(((lastPrice - s1Val) / lastPrice) * 100).toFixed(1) : null;
  const r1Dist = r1Val ? Math.abs(((r1Val - lastPrice) / lastPrice) * 100).toFixed(1) : null;

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

  // 4. Trade Setup Lines
  const ts = item ? item.trade_suggestion : null;
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

  // 5. DCF Fair Value Line
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

  chart.timeScale().fitContent();
  return chart;
}

async function loadChart(container, ticker, timeframe, assetClass, height = 500) {
  const item = allSymbols.find(s => s.ticker === ticker && s.timeframe === timeframe) || 
               allSymbols.find(s => s.ticker === ticker) || {};
  const tvSym = getTvSymbol(item, ticker, assetClass);
  const isCrypto = assetClass === 'crypto' || (ticker && ticker.endsWith('USDT'));

  let chartInstance = null;
  let candles = [];

  if (isCrypto && window.LightweightCharts) {
    const binanceInterval = (timeframe || '1D').toLowerCase();
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
      console.warn(`Binance klines fetch failed for ${ticker}:`, e);
    }
  }

  if (candles.length > 30) {
    chartInstance = renderLightweightChart(container, candles, item, height);
  } else {
    renderTradingViewIframe(container, tvSym, timeframe);
  }

  return chartInstance;
}

// =============================================================================
// LIVE ON-PAGE SHOWCASE ENGINE
// =============================================================================

function updateActiveRowHighlight() {
  document.querySelectorAll('#assetsTableBody tr').forEach(tr => {
    const isAct = tr.dataset.ticker === liveTicker && tr.dataset.tf === liveTf;
    tr.classList.toggle('row-active', isAct);
  });
  document.querySelectorAll('#cardsGrid .asset-card').forEach(card => {
    const isAct = card.dataset.ticker === liveTicker && card.dataset.tf === liveTf;
    card.classList.toggle('card-active', isAct);
  });
}

function updateLiveChartHud(item, ticker, timeframe, assetClass) {
  const tvSym = getTvSymbol(item, ticker, assetClass);
  const tvInterval = getTvInterval(timeframe);

  const liveTickerEl = document.getElementById('liveTicker');
  if (liveTickerEl) liveTickerEl.textContent = ticker;

  const liveClassEl = document.getElementById('liveClassBadge');
  if (liveClassEl) {
    liveClassEl.textContent = CLASS_LABELS[assetClass] || assetClass;
    liveClassEl.className = `class-badge class-${assetClass}`;
  }

  const livePriceEl = document.getElementById('livePrice');
  if (livePriceEl) {
    const p = item.price || 0;
    livePriceEl.textContent = p >= 1000 
      ? `$${p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` 
      : `$${p.toFixed(p >= 1 ? 2 : 5)}`;
  }

  const liveStateEl = document.getElementById('liveStateBadge');
  if (liveStateEl) {
    const sEmoji = item.state === 'GOLD' ? '🟡' : (item.state === 'BLUE' ? '🔵' : '⚪');
    liveStateEl.textContent = `${sEmoji} ${item.state || 'NEUTRAL'}`;
    liveStateEl.className = `badge ${item.state === 'GOLD' ? 'badge-gold' : (item.state === 'BLUE' ? 'badge-blue' : 'badge-neutral')}`;
  }

  const tvLinkEl = document.getElementById('liveTvLink');
  if (tvLinkEl) {
    tvLinkEl.href = `https://www.tradingview.com/chart/?symbol=${tvSym}&interval=${tvInterval}`;
  }

  // 3-Pillar Compact Strip
  const tech = item.technical || {};
  const fund = item.fundamental || {};
  const synth = item.synthesis || {};
  const ts = item.trade_suggestion || {};

  const techActionEl = document.getElementById('liveTechAction');
  const techSpreadEl = document.getElementById('liveTechSpread');
  if (techActionEl) techActionEl.textContent = tech.label_bg || (item.state === 'GOLD' ? '🟢 Бичи тренд' : '⚪ Изчакване');
  if (techSpreadEl) {
    const spreadVal = item.spread_pct !== undefined ? item.spread_pct : (tech.spread_pct || 0.0);
    const sign = spreadVal > 0 ? '+' : '';
    techSpreadEl.textContent = `Spread: ${sign}${spreadVal.toFixed(2)}%`;
  }

  const fundActionEl = document.getElementById('liveFundAction');
  const fundMoatEl = document.getElementById('liveFundMoat');
  if (fundActionEl) fundActionEl.textContent = fund.label_bg || (item.asset_class === 'crypto' ? '⚪ МАКРО / ХАЛВИНГ' : '⚪ Неоценен');
  if (fundMoatEl) {
    if (fund.moat) fundMoatEl.textContent = `${fund.moat} Moat (DCF: $${formatShortPrice(fund.fair_value)})`;
    else if (item.asset_class === 'crypto') fundMoatEl.textContent = '🪙 Network Effect';
    else fundMoatEl.textContent = 'No Moat';
  }

  const synthBadgeEl = document.getElementById('liveSynthBadge');
  const synthLevelsEl = document.getElementById('liveSynthLevels');
  if (synthBadgeEl) {
    synthBadgeEl.textContent = synth.badge_bg || (ts.action === 'WAIT' ? '⏳ WAIT' : ts.action || '⏳ WAIT');
  }
  if (synthLevelsEl) {
    const entry = ts.entry ? `$${formatShortPrice(ts.entry)}` : `$${formatShortPrice(item.price || 0)}`;
    const sl = ts.sl ? `$${formatShortPrice(ts.sl)}` : 'N/A';
    synthLevelsEl.textContent = `Вход: ${entry} | SL: ${sl} | RR: ${ts.rr ? '1:' + ts.rr : 'N/A'}`;
  }
}

async function selectLiveAsset(ticker, timeframe, assetClass) {
  liveTicker = ticker || 'BTCUSDT';
  liveTf = timeframe || liveTf || '1D';
  liveClass = assetClass || liveClass || 'crypto';

  updateActiveRowHighlight();

  // Update quick pills
  document.querySelectorAll('#liveQuickPills .quick-pill').forEach(pill => {
    pill.classList.toggle('active', pill.dataset.ticker === liveTicker);
  });

  // Update timeframe buttons
  document.querySelectorAll('#liveTfGroup .live-tf-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tf === liveTf);
  });

  // Find item
  const item = allSymbols.find(s => s.ticker === liveTicker && s.timeframe === liveTf) ||
               allSymbols.find(s => s.ticker === liveTicker) || {};

  // Update header and HUD strip
  updateLiveChartHud(item, liveTicker, liveTf, liveClass);

  // Render chart in #liveChartCanvas
  const container = document.getElementById('liveChartCanvas');
  if (container) {
    if (liveActiveChart) {
      try { liveActiveChart.remove(); } catch (e) {}
      liveActiveChart = null;
    }
    const h = container.clientHeight || 520;
    liveActiveChart = await loadChart(container, liveTicker, liveTf, liveClass, h);
  }
}

function initLiveChart() {
  if (allSymbols.length === 0) return;
  if (!liveChartInitialized) {
    liveChartInitialized = true;
    const top = getFilteredSymbols()[0] || allSymbols.find(s => s.ticker === 'BTCUSDT') || allSymbols[0];
    if (top) {
      liveTicker = top.ticker;
      liveTf = top.timeframe || '1D';
      liveClass = top.asset_class || 'crypto';
    }
    selectLiveAsset(liveTicker, liveTf, liveClass);
  } else {
    updateActiveRowHighlight();
  }
}

// =============================================================================
// MODAL ENGINE (FULL SCREEN WITH CALCULATOR & DUAL HUD)
// =============================================================================

async function openChartModal(ticker, timeframe, assetClass) {
  activeTicker = ticker;
  activeTf = timeframe || '1D';
  activeClass = assetClass || 'crypto';

  const modal = document.getElementById('chartModal');
  const loading = document.getElementById('chartLoading');
  if (modal) modal.style.display = 'flex';
  if (loading) loading.style.display = 'flex';

  // Reset scroll position to top so chart is immediately visible
  const modalBody = document.getElementById('chartModalBody');
  if (modalBody) modalBody.scrollTop = 0;

  // Reset active nav tab to Chart
  document.querySelectorAll('#modalNavTabs .modal-nav-tab').forEach((t, i) => {
    t.classList.toggle('active', i === 0);
  });

  const item = allSymbols.find(s => s.ticker === ticker && s.timeframe === activeTf) || 
               allSymbols.find(s => s.ticker === ticker) || {};

  const modalTickerEl = document.getElementById('modalTicker');
  if (modalTickerEl) modalTickerEl.textContent = ticker;
  const modalClassEl = document.getElementById('modalClass');
  if (modalClassEl) modalClassEl.textContent = CLASS_LABELS[assetClass] || assetClass;

  const tvInterval = getTvInterval(activeTf);
  const tvSym = getTvSymbol(item, ticker, assetClass);
  const modalTvBtn = document.getElementById('modalTvBtn');
  if (modalTvBtn) {
    modalTvBtn.href = `https://www.tradingview.com/chart/?symbol=${tvSym}&interval=${tvInterval}`;
  }

  // Update Active TF Buttons in Modal
  document.querySelectorAll('#modalTfGroup .modal-tf-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tf === activeTf);
  });

  // Clear previous chart
  const container = document.getElementById('chartCanvas');
  if (container) {
    if (activeChart) {
      try { activeChart.remove(); } catch(e) {}
      activeChart = null;
    }
    container.innerHTML = '';
  }

  // Update price in modal header
  const p = item.price || 0;
  const modalPriceEl = document.getElementById('modalPrice');
  if (modalPriceEl) {
    modalPriceEl.textContent = p >= 1000 
      ? `$${p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` 
      : `$${p.toFixed(p >= 1 ? 2 : 5)}`;
  }

  // Update S/R lines in dual hud if present
  const modalS1El = document.getElementById('modalS1');
  if (modalS1El) {
    modalS1El.textContent = item.s1 ? `$${formatShortPrice(item.s1)} (-${item.s1_dist_pct}%)` : 'None';
  }
  const modalR1El = document.getElementById('modalR1');
  if (modalR1El) {
    modalR1El.textContent = item.r1 ? `$${formatShortPrice(item.r1)} (+${item.r1_dist_pct}%)` : 'None';
  }

  // Update Modal strips & calculator
  updateModalTradeSuggestionStrip(item.trade_suggestion, item);

  // Load chart into modal
  if (container) {
    activeChart = await loadChart(container, ticker, activeTf, assetClass, container.clientHeight || 480);
  }

  if (loading) loading.style.display = 'none';
}

function updateModalTradeSuggestionStrip(ts, item) {
  if (!item) return;

  const tech = item.technical || {};
  const fund = item.fundamental || {};
  const synth = item.synthesis || {};

  // 1. Technical HUD Card
  const techStateBadge = document.getElementById('modalTechStateBadge');
  const techActionEl = document.getElementById('modalTechAction');
  const techSpreadEl = document.getElementById('modalTechSpread');
  const techThesisEl = document.getElementById('modalTechThesis');

  if (techStateBadge) {
    const sEmoji = item.state === 'GOLD' ? '🟡' : (item.state === 'BLUE' ? '🔵' : '⚪');
    techStateBadge.textContent = `${sEmoji} ${item.state}`;
    techStateBadge.className = `badge ${item.state === 'GOLD' ? 'badge-gold' : (item.state === 'BLUE' ? 'badge-blue' : 'badge-neutral')}`;
  }

  const modalStateBadge = document.getElementById('modalStateBadge');
  if (modalStateBadge) {
    const sEmoji = item.state === 'GOLD' ? '🟡' : (item.state === 'BLUE' ? '🔵' : '⚪');
    modalStateBadge.textContent = `${sEmoji} ${item.state}`;
    modalStateBadge.className = `badge ${item.state === 'GOLD' ? 'badge-gold' : (item.state === 'BLUE' ? 'badge-blue' : 'badge-neutral')}`;
  }

  const spreadVal = item.spread_pct !== undefined ? item.spread_pct : (tech.spread_pct || 0.0);
  const spreadSign = spreadVal > 0 ? '+' : '';
  const spreadLabel = `${spreadSign}${spreadVal.toFixed(2)}%`;
  if (techSpreadEl) techSpreadEl.textContent = spreadLabel;

  if (techActionEl) {
    techActionEl.textContent = tech.label_bg || (ts && ts.tech_label_bg) || (item.state === 'GOLD' ? '🟢 Бичи Възходящ Тренд' : '⚪ Изчакване');
  }
  if (techThesisEl) {
    techThesisEl.textContent = tech.thesis || (ts && ts.tech_thesis_bg) || 'Панделката определя макро тренда и динамичните зони на стойност.';
  }

  // 2. Fundamental HUD Card
  const fundActionEl = document.getElementById('modalFundAction');
  const fundFvEl = document.getElementById('modalFundFairValue');
  const fundMosEl = document.getElementById('modalFundMos');
  const fundMoatEl = document.getElementById('modalFundMoat');
  const fundMoatPill = document.getElementById('modalFundMoatPill');
  const fundZEl = document.getElementById('modalFundZScore');
  const fundThesisEl = document.getElementById('modalFundThesis');

  const fAction = fund.label_bg || (ts && ts.fund_label_bg) || (item.asset_class === 'crypto' ? '⚪ МАКРО / СПЕКУЛАТИВЕН' : '⚪ Неоценен');
  if (fundActionEl) fundActionEl.textContent = fAction;

  if (fundFvEl) {
    fundFvEl.textContent = fund.fair_value ? '$' + formatShortPrice(fund.fair_value) : (item.asset_class === 'crypto' ? 'Пазарна цена (N/A)' : 'Неоценена');
  }
  if (fundMosEl) {
    fundMosEl.textContent = (fund.mos_pct !== null && fund.mos_pct !== undefined) ? `${fund.mos_pct > 0 ? '+' : ''}${Math.round(fund.mos_pct)}%` : 'N/A';
  }
  if (fundMoatEl) {
    fundMoatEl.textContent = fund.moat ? `${fund.moat} Moat` : (item.asset_class === 'crypto' ? 'Мрежов ефект' : 'None');
  }
  if (fundMoatPill) {
    if (fund.moat === 'Wide') {
      fundMoatPill.textContent = '💎 Wide Moat';
      fundMoatPill.className = 'fund-moat-pill fund-moat-wide';
      fundMoatPill.style.display = 'inline-block';
    } else if (fund.moat === 'Narrow') {
      fundMoatPill.textContent = '🏰 Narrow Moat';
      fundMoatPill.className = 'fund-moat-pill fund-moat-narrow';
      fundMoatPill.style.display = 'inline-block';
    } else if (item.asset_class === 'crypto') {
      fundMoatPill.textContent = '🪙 Network Effect';
      fundMoatPill.className = 'fund-moat-pill';
      fundMoatPill.style.display = 'inline-block';
    } else {
      fundMoatPill.style.display = 'none';
    }
  }
  if (fundZEl) {
    fundZEl.textContent = fund.z_score ? `${fund.z_score.toFixed(2)} (${fund.z_score >= 2.99 ? 'Safe' : 'Grey'})` : 'Safe Metric';
  }
  if (fundThesisEl) {
    fundThesisEl.textContent = fund.thesis_bg || (ts && ts.fund_thesis_bg) || fund.thesis || (item.asset_class === 'crypto' ? 'Крипто актив без DCF модел. Движи се от ликвидност и халвинг цикли.' : 'Фундаментален анализ на паричните потоци.');
  }

  // 3. Quantamental Synthesis Banner
  const synthBadgeEl = document.getElementById('modalSetupAction');
  const synthTierEl = document.getElementById('modalSetupTier');
  const synthTypeEl = document.getElementById('modalSetupType');
  const synthConfluenceEl = document.getElementById('modalSynthConfluence');
  const entryEl = document.getElementById('modalSetupEntry');
  const slEl = document.getElementById('modalSetupSl');
  const tp1El = document.getElementById('modalSetupTp1');
  const tp2El = document.getElementById('modalSetupTp2');
  const rrEl = document.getElementById('modalSetupRr');
  const reasonEl = document.getElementById('modalSetupReason');

  const s = synth.action ? synth : (ts || {});
  const badgeText = synth.badge_bg || (ts && ts.synthesis_badge_bg) || (s.action === 'WAIT' ? '⏳ WAIT' : s.action || '⏳ WAIT');

  if (synthBadgeEl) {
    synthBadgeEl.textContent = badgeText;
    let bClass = 'synth-badge-wait';
    if (s.setup_type === 'QUANTAMENTAL_ALPHA_BUY') bClass = 'synth-badge-alpha';
    else if (s.setup_type === 'VALUE_TRAP_WARNING') bClass = 'synth-badge-trap';
    else if (s.setup_type === 'QUALITY_HOLD_ACCUMULATION') bClass = 'synth-badge-accumulate';
    else if (s.setup_type && s.setup_type.includes('SPECULATIVE')) bClass = 'synth-badge-speculative';
    else if (s.action === 'SPOT_BUY') bClass = 'synth-badge-buy';
    else if (s.action === 'TAKE_PROFIT') bClass = 'synth-badge-profit';
    else if (s.action === 'EXIT_PROTECT') bClass = 'synth-badge-protect';
    synthBadgeEl.className = `synth-badge ${bClass}`;
  }

  if (synthTierEl) {
    if (s.tier && s.tier !== 'NONE') {
      synthTierEl.textContent = `🏆 Tier ${s.tier} (${s.score || 0}/100)`;
      synthTierEl.style.display = 'inline-block';
    } else {
      synthTierEl.style.display = 'none';
    }
  }

  if (synthTypeEl) {
    synthTypeEl.textContent = (s.setup_type ? s.setup_type.replace(/_/g, ' ') : '');
  }

  if (synthConfluenceEl) {
    synthConfluenceEl.textContent = synth.confluence_thesis || (ts && ts.confluence_thesis) || (synth.label_bg || 'Синтезирана квантова оценка.');
  }

  if (entryEl) entryEl.textContent = s.entry ? '$' + formatShortPrice(s.entry) : '$' + formatShortPrice(item.price || 0);
  if (slEl) slEl.textContent = s.sl ? '$' + formatShortPrice(s.sl) : 'N/A';
  if (tp1El) tp1El.textContent = s.tp1 ? '$' + formatShortPrice(s.tp1) : 'N/A';
  if (tp2El) tp2El.textContent = s.tp2 ? '$' + formatShortPrice(s.tp2) : 'N/A';
  if (rrEl) rrEl.textContent = s.rr ? `1 : ${s.rr}` : 'N/A';
  if (reasonEl) reasonEl.textContent = (ts && (ts.reason_bg || ts.reason_en)) || synth.label_bg || 'Няма допълнителни бележки.';

  updateModalPositionCalculator(ts, item);
}

function closeChartModal() {
  const modal = document.getElementById('chartModal');
  if (modal) modal.style.display = 'none';
  if (activeChart) {
    try { activeChart.remove(); } catch(e) {}
    activeChart = null;
  }
}

// Event Listeners for Modal
const closeModalBtn = document.getElementById('closeModalBtn');
if (closeModalBtn) closeModalBtn.addEventListener('click', closeChartModal);

const chartModalBackdrop = document.getElementById('chartModal');
if (chartModalBackdrop) {
  chartModalBackdrop.addEventListener('click', (e) => {
    if (e.target.id === 'chartModal') closeChartModal();
  });
}

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

// Modal Section Navigation Tabs
document.querySelectorAll('#modalNavTabs .modal-nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const targetId = tab.dataset.target;
    const targetEl = document.getElementById(targetId);
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      document.querySelectorAll('#modalNavTabs .modal-nav-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
    }
  });
});

// Scroll Hint Bar (Jump to Analysis)
const scrollHintBar = document.getElementById('chartScrollHintBar');
if (scrollHintBar) {
  scrollHintBar.addEventListener('click', () => {
    const synth = document.getElementById('modalSynthBanner');
    if (synth) synth.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

// Back to Chart Bar
const backToTopBar = document.getElementById('modalBackToTopBar');
if (backToTopBar) {
  backToTopBar.addEventListener('click', () => {
    const chartContainer = document.getElementById('chartCanvasContainer');
    if (chartContainer) chartContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

// Sync Nav Tab Active State with Scroll
const modalBodyEl = document.getElementById('chartModalBody');
if (modalBodyEl) {
  modalBodyEl.addEventListener('scroll', () => {
    const sections = [
      { id: 'chartCanvasContainer', tabIdx: 0 },
      { id: 'modalSynthBanner', tabIdx: 1 },
      { id: 'modalDualHud', tabIdx: 2 },
      { id: 'modalPosCalcStrip', tabIdx: 3 }
    ];
    const bodyRect = modalBodyEl.getBoundingClientRect();
    let currentIdx = 0;
    for (const sec of sections) {
      const el = document.getElementById(sec.id);
      if (el) {
        const rect = el.getBoundingClientRect();
        if (rect.top <= bodyRect.top + 90) {
          currentIdx = sec.tabIdx;
        }
      }
    }
    const tabs = document.querySelectorAll('#modalNavTabs .modal-nav-tab');
    tabs.forEach((tab, i) => tab.classList.toggle('active', i === currentIdx));
  });
}

// Live Chart Quick Switcher and Controls Listeners
document.querySelectorAll('#liveQuickPills .quick-pill').forEach(pill => {
  pill.addEventListener('click', (e) => {
    const t = e.currentTarget.dataset.ticker;
    const tf = e.currentTarget.dataset.tf || '1D';
    const ac = e.currentTarget.dataset.class || 'crypto';
    selectLiveAsset(t, tf, ac);
  });
});

document.querySelectorAll('#liveTfGroup .live-tf-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    const tf = e.currentTarget.dataset.tf;
    if (tf && tf !== liveTf) {
      selectLiveAsset(liveTicker, tf, liveClass);
    }
  });
});

const liveExpBtn = document.getElementById('liveExpandBtn');
if (liveExpBtn) {
  liveExpBtn.addEventListener('click', () => {
    openChartModal(liveTicker, liveTf, liveClass);
  });
}

// Responsive resize for Lightweight Charts (both live and modal)
window.addEventListener('resize', () => {
  const modalContainer = document.getElementById('chartCanvas');
  if (activeChart && modalContainer && modalContainer.clientWidth) {
    activeChart.applyOptions({ 
      width: modalContainer.clientWidth,
      height: modalContainer.clientHeight || 480
    });
  }
  const liveContainer = document.getElementById('liveChartCanvas');
  if (liveActiveChart && liveContainer && liveContainer.clientWidth) {
    liveActiveChart.applyOptions({ 
      width: liveContainer.clientWidth,
      height: liveContainer.clientHeight || 480
    });
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

document.querySelectorAll('#techFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#techFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentTechFilter = e.target.dataset.tech;
    renderAllViews();
  });
});

document.querySelectorAll('#fundFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#fundFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentFundFilter = e.target.dataset.fund;
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

// =============================================================================
// MASTER TAB NAVIGATION & SPECIALIZED VIEWS
// =============================================================================

function switchTab(tabName) {
  currentTab = tabName;
  localStorage.setItem('larsson_active_tab', tabName);

  document.querySelectorAll('#mainNavTabs .nav-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });

  const tabMap = {
    'scanner': 'tabContentScanner',
    'queue': 'tabContentQueue',
    'portfolio': 'tabContentPortfolio',
    'calculator': 'tabContentCalculator'
  };

  Object.keys(tabMap).forEach(key => {
    const el = document.getElementById(tabMap[key]);
    if (el) {
      if (key === tabName) {
        el.style.display = 'block';
        el.classList.add('active');
      } else {
        el.style.display = 'none';
        el.classList.remove('active');
      }
    }
  });

  if (tabName === 'scanner' && liveActiveChart) {
    const liveContainer = document.getElementById('liveChartCanvas');
    if (liveContainer && liveContainer.clientWidth) {
      liveActiveChart.applyOptions({ width: liveContainer.clientWidth });
    }
  }
}

document.querySelectorAll('#mainNavTabs .nav-tab-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    const tab = e.currentTarget.dataset.tab;
    if (tab) switchTab(tab);
  });
});

// =============================================================================
// TAB 2: SETUPS QUEUE RENDERER
// =============================================================================

function renderQueueView() {
  const badge = document.getElementById('queueCountBadge');
  if (badge) badge.textContent = pendingSetups.length;

  const container = document.getElementById('queueCardsGrid');
  if (!container) return;

  let filtered = pendingSetups.filter(s => {
    const matchesPrio = (currentQueuePriority === 'ALL') || (s.priority === currentQueuePriority);
    const matchesTier = (currentQueueTier === 'ALL') || (s.tier === currentQueueTier);
    return matchesPrio && matchesTier;
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1/-1; padding: 40px; text-align: center; color: var(--text-muted); background: var(--bg-card); border-radius: var(--radius-md); border: 1px dashed var(--border-color);">
        <h3>⏳ Няма намерени очаквани сделки по тези критерии</h3>
        <p style="margin-top: 8px;">Системата следи непрекъснато пазара за Imminent Gold, Dip Buy, S/R приближаване и Дивергенции.</p>
      </div>
    `;
    return;
  }

  const typeLabels = {
    'IMMINENT_GOLD': { emoji: '🔥', title: 'Imminent Gold Ribbon' },
    'QUALITY_DIP_BUY': { emoji: '💎', title: 'Quality Dip Buy (Weekly Gold)' },
    'SR_APPROACH': { emoji: '🎯', title: 'S/R Approach (Подкрепа / Съпротива)' },
    'ACCUMULATION_PATTERN': { emoji: '📦', title: 'Quiet Consolidation Squeeze' },
    'DIVERGENCE_FORMING': { emoji: '📉', title: 'RSI Divergence Forming' }
  };

  const tierEmoji = { 'S': '💎 S', 'A': '⭐ A', 'B': '🔵 B', 'C': '⚪ C' };

  container.innerHTML = filtered.map(s => {
    const prioClass = s.priority === 'HIGH' ? 'queue-card-prio-high' : (s.priority === 'MEDIUM' ? 'queue-card-prio-med' : 'queue-card-prio-low');
    const prioBadgeClass = s.priority === 'HIGH' ? 'queue-prio-high' : (s.priority === 'MEDIUM' ? 'queue-prio-med' : 'queue-prio-low');
    const typeInfo = typeLabels[s.setup_type] || { emoji: '⚡', title: s.setup_type };
    const tEmoji = tierEmoji[s.tier] || s.tier;

    let metTags = [];
    try {
      metTags = typeof s.conditions_met === 'string' ? JSON.parse(s.conditions_met) : (s.conditions_met || []);
    } catch(e) { metTags = []; }

    let pendingTags = [];
    try {
      pendingTags = typeof s.conditions_pending === 'string' ? JSON.parse(s.conditions_pending) : (s.conditions_pending || []);
    } catch(e) { pendingTags = []; }

    const entryStr = s.target_entry ? `$${formatShortPrice(s.target_entry)}` : (s.current_price ? `$${formatShortPrice(s.current_price)}` : 'N/A');
    const keyLvlStr = s.key_level ? `$${formatShortPrice(s.key_level)}` : 'N/A';
    const triggerStr = s.estimated_trigger || '1-3 бара';

    return `
      <div class="queue-card ${prioClass}">
        <div class="queue-card-header">
          <div class="queue-card-title-group">
            <span class="queue-card-ticker">
              ${s.symbol} <span class="class-badge">${CLASS_LABELS[s.asset_class] || s.asset_class}</span>
            </span>
            <div class="queue-card-setup-title">
              <span>${typeInfo.emoji}</span> ${typeInfo.title}
            </div>
          </div>
          <div class="queue-card-badges">
            <span class="queue-prio-badge ${prioBadgeClass}">${s.priority}</span>
            <span class="class-badge" style="background: rgba(168, 85, 247, 0.15); color: #c084fc; border-color: rgba(168, 85, 247, 0.3);">${tEmoji}</span>
          </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="queue-card-trigger-est">⏱️ Очакван тригер: <strong>${triggerStr}</strong></span>
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.8125rem; color: #38bdf8; font-weight: 700;">
            Скор: ${(s.quality_score * 100).toFixed(0)}/100
          </span>
        </div>

        <div class="queue-card-desc">
          ${s.description_bg || s.description_en || 'Предстоящ сетъп за вход.'}
        </div>

        <div class="queue-checklist-block">
          <span class="checklist-title">Условия за валидация:</span>
          <div class="checklist-tags">
            ${metTags.map(m => `<span class="chk-tag chk-met">✅ ${m}</span>`).join('')}
            ${pendingTags.map(p => `<span class="chk-tag chk-pending">⏳ ${p}</span>`).join('')}
          </div>
        </div>

        <div class="queue-card-levels">
          <div class="queue-lvl-col">
            <span class="queue-lvl-lbl">Текуща Цена</span>
            <span class="queue-lvl-val">$${formatShortPrice(s.current_price)}</span>
          </div>
          <div class="queue-lvl-col">
            <span class="queue-lvl-lbl">Входна Зона</span>
            <span class="queue-lvl-val" style="color: #38bdf8;">${entryStr}</span>
          </div>
          <div class="queue-lvl-col">
            <span class="queue-lvl-lbl">Ключово Ниво</span>
            <span class="queue-lvl-val" style="color: #fbbf24;">${keyLvlStr}</span>
          </div>
        </div>

        <div class="queue-card-actions">
          <button class="btn-queue-calc" onclick="quickFillCalculator('${s.symbol}', ${s.target_entry || s.current_price || 0}, ${s.target_sl || 0}, ${s.target_tp1 || 0}, 0, '${s.tier}')">
            🧮 Зареди в Калкулатора
          </button>
        </div>
      </div>
    `;
  }).join('');
}

document.querySelectorAll('#queuePriorityFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#queuePriorityFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentQueuePriority = e.target.dataset.queuePrio;
    renderQueueView();
  });
});

document.querySelectorAll('#queueTierFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#queueTierFilters .filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    currentQueueTier = e.target.dataset.queueTier;
    renderQueueView();
  });
});

// =============================================================================
// TAB 3: DUAL PORTFOLIO CONTROLLER (REAL MONEY VS VIRTUAL / PAPER SIMULATION)
// =============================================================================

function syncLocalRealStorage() {
  try {
    const localPositions = JSON.parse(localStorage.getItem('larsson_custom_real_positions') || '[]');
    const localCash = localStorage.getItem('larsson_custom_real_cash');
    const localClosed = JSON.parse(localStorage.getItem('larsson_custom_real_closed') || '[]');

    if (!portfolioRealData.positions) portfolioRealData.positions = [];
    if (!portfolioRealData.journal) portfolioRealData.journal = [];
    if (!portfolioRealData.summary) portfolioRealData.summary = {};

    // Merge any locally added real positions not already in server list
    const existingIds = new Set(portfolioRealData.positions.map(p => p.position_id || p.symbol));
    localPositions.forEach(p => {
      const id = p.position_id || p.symbol;
      if (!existingIds.has(id)) {
        portfolioRealData.positions.push(p);
        existingIds.add(id);
      }
    });

    // Merge any locally closed positions into journal
    const existingJournals = new Set(portfolioRealData.journal.map(j => (j.position_id || '') + (j.created_at || '')));
    localClosed.forEach(c => {
      const key = (c.position_id || '') + (c.created_at || '');
      if (!existingJournals.has(key)) {
        portfolioRealData.journal.unshift(c);
        existingJournals.add(key);
      }
    });

    if (localCash !== null && localCash !== undefined) {
      const cashVal = parseFloat(localCash);
      if (!isNaN(cashVal)) {
        portfolioRealData.summary.available_cash = cashVal;
      }
    }
  } catch(e) {
    console.warn('Error reading local real portfolio storage:', e);
  }
}

function initPortfolioController() {
  const realBtn = document.getElementById('portModeRealBtn');
  const paperBtn = document.getElementById('portModePaperBtn');
  if (realBtn) {
    realBtn.addEventListener('click', () => switchPortfolioMode('REAL'));
  }
  if (paperBtn) {
    paperBtn.addEventListener('click', () => switchPortfolioMode('PAPER'));
  }

  // Real Modal Open/Close Triggers
  const openAddBtn = document.getElementById('openAddRealModalBtn');
  const addModal = document.getElementById('addRealModal');
  const closeAddBtn = document.getElementById('closeAddRealModalBtn');
  const cancelAddBtn = document.getElementById('cancelAddRealModalBtn');

  if (openAddBtn && addModal) {
    openAddBtn.addEventListener('click', () => {
      addModal.style.display = 'flex';
      const tickerInput = document.getElementById('realTicker');
      if (tickerInput) tickerInput.focus();
    });
  }
  const hideAddModal = () => { if (addModal) addModal.style.display = 'none'; };
  if (closeAddBtn) closeAddBtn.addEventListener('click', hideAddModal);
  if (cancelAddBtn) cancelAddBtn.addEventListener('click', hideAddModal);

  // Cash Modal Open/Close Triggers
  const openCashBtn = document.getElementById('openSetCashModalBtn');
  const cashModal = document.getElementById('setCashModal');
  const closeCashBtn = document.getElementById('closeSetCashModalBtn');
  const cancelCashBtn = document.getElementById('cancelSetCashModalBtn');

  if (openCashBtn && cashModal) {
    openCashBtn.addEventListener('click', () => {
      cashModal.style.display = 'flex';
      const cInput = document.getElementById('realCashAmount');
      if (cInput) {
        cInput.value = (portfolioRealData.summary && portfolioRealData.summary.available_cash) || 0;
        cInput.focus();
      }
    });
  }
  const hideCashModal = () => { if (cashModal) cashModal.style.display = 'none'; };
  if (closeCashBtn) closeCashBtn.addEventListener('click', hideCashModal);
  if (cancelCashBtn) cancelCashBtn.addEventListener('click', hideCashModal);

  // Close Position Modal Triggers
  const closePosModal = document.getElementById('closeRealModal');
  const closeClosePosBtn = document.getElementById('closeCloseRealModalBtn');
  const cancelClosePosBtn = document.getElementById('cancelCloseRealModalBtn');
  const hideClosePosModal = () => { if (closePosModal) closePosModal.style.display = 'none'; };
  if (closeClosePosBtn) closeClosePosBtn.addEventListener('click', hideClosePosModal);
  if (cancelClosePosBtn) cancelClosePosBtn.addEventListener('click', hideClosePosModal);

  // Add Real Position Form Submit
  const addForm = document.getElementById('addRealPositionForm');
  if (addForm) {
    addForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const ticker = (document.getElementById('realTicker')?.value || '').trim().toUpperCase();
      const assetClass = document.getElementById('realAssetClass')?.value || 'crypto';
      const broker = (document.getElementById('realBroker')?.value || 'Interactive Brokers').trim();
      const entryPrice = parseFloat(document.getElementById('realEntryPrice')?.value || 0);
      const units = parseFloat(document.getElementById('realUnits')?.value || 0);
      const fee = parseFloat(document.getElementById('realFee')?.value || 0) || 0;
      const sl = parseFloat(document.getElementById('realSl')?.value || 0) || null;
      const tp1 = parseFloat(document.getElementById('realTp1')?.value || 0) || null;
      const notes = (document.getElementById('realNotes')?.value || '').trim();

      if (!ticker || entryPrice <= 0 || units <= 0) {
        alert('Моля въведете валиден тикер, входна цена и количество!');
        return;
      }

      const posId = `real_${ticker}_${Date.now()}`;
      const nowIso = new Date().toISOString();
      const posSize = entryPrice * units;

      const newPos = {
        position_id: posId,
        symbol: ticker,
        direction: 'LONG',
        entry_price: entryPrice,
        current_price: entryPrice,
        units: units,
        position_size_usd: posSize,
        current_value: posSize,
        unrealized_pnl: 0.0,
        unrealized_pnl_pct: 0.0,
        stop_loss: sl,
        tp1: tp1,
        tp2: null,
        duration_days: 0,
        opened_at: nowIso,
        tier: 'A',
        asset_class: assetClass,
        portfolio_type: 'REAL',
        broker_exchange: broker,
        notes: notes,
        fee_paid_usd: fee
      };

      if (!portfolioRealData.positions) portfolioRealData.positions = [];
      portfolioRealData.positions.unshift(newPos);

      // Deduct from cash
      const curCash = (portfolioRealData.summary && portfolioRealData.summary.available_cash) || 0;
      portfolioRealData.summary.available_cash = Math.max(0, curCash - (posSize + fee));
      localStorage.setItem('larsson_custom_real_cash', portfolioRealData.summary.available_cash.toString());

      // Save custom positions to localStorage
      try {
        const saved = JSON.parse(localStorage.getItem('larsson_custom_real_positions') || '[]');
        saved.unshift(newPos);
        localStorage.setItem('larsson_custom_real_positions', JSON.stringify(saved));
      } catch(err) {
        console.error('Failed to save to localStorage:', err);
      }

      // Add to Journal
      const journalEntry = {
        position_id: posId,
        ticker: ticker,
        action: 'OPEN',
        price: entryPrice,
        units: units,
        pnl_usd: 0.0,
        pnl_pct: 0.0,
        broker_exchange: broker,
        reason: notes || `Real Buy on ${broker}`,
        created_at: nowIso,
        portfolio_type: 'REAL'
      };
      if (!portfolioRealData.journal) portfolioRealData.journal = [];
      portfolioRealData.journal.unshift(journalEntry);

      hideAddModal();
      addForm.reset();
      renderPortfolioView();
    });
  }

  // Set Cash Form Submit
  const cashForm = document.getElementById('setRealCashForm');
  if (cashForm) {
    cashForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const amount = parseFloat(document.getElementById('realCashAmount')?.value || 0);
      if (isNaN(amount) || amount < 0) {
        alert('Моля въведете валидна неотрицателна сума за кеш!');
        return;
      }
      if (!portfolioRealData.summary) portfolioRealData.summary = {};
      portfolioRealData.summary.available_cash = amount;
      portfolioRealData.summary.initial_balance = amount;
      localStorage.setItem('larsson_custom_real_cash', amount.toString());
      hideCashModal();
      renderPortfolioView();
    });
  }

  // Close Position Form Submit
  const closeForm = document.getElementById('closeRealPositionForm');
  if (closeForm) {
    closeForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const posId = document.getElementById('closeRealPosId')?.value;
      const exitPrice = parseFloat(document.getElementById('closeRealExitPrice')?.value || 0);
      const fee = parseFloat(document.getElementById('closeRealFee')?.value || 0) || 0;
      const notes = (document.getElementById('closeRealNotes')?.value || '').trim();

      if (!posId || exitPrice <= 0) {
        alert('Моля въведете валидна цена на изход!');
        return;
      }

      const idx = (portfolioRealData.positions || []).findIndex(p => p.position_id === posId);
      if (idx === -1) {
        alert('Позицията не беше намерена сред активните.');
        return;
      }

      const target = portfolioRealData.positions[idx];
      const entry = target.entry_price;
      const units = target.units;
      const grossPnl = (exitPrice - entry) * units;
      const netPnl = grossPnl - fee;
      const pnlPct = entry > 0 ? ((exitPrice - entry) / entry * 100) : 0;
      const nowIso = new Date().toISOString();

      // Add proceeds to cash
      const curCash = (portfolioRealData.summary && portfolioRealData.summary.available_cash) || 0;
      portfolioRealData.summary.available_cash = curCash + (units * exitPrice) - fee;
      localStorage.setItem('larsson_custom_real_cash', portfolioRealData.summary.available_cash.toString());

      // Update realized stats
      if (!portfolioRealData.summary) portfolioRealData.summary = {};
      portfolioRealData.summary.total_realized_pnl = (portfolioRealData.summary.total_realized_pnl || 0) + netPnl;
      if (netPnl > 0) {
        portfolioRealData.summary.wins = (portfolioRealData.summary.wins || 0) + 1;
      } else {
        portfolioRealData.summary.losses = (portfolioRealData.summary.losses || 0) + 1;
      }

      // Record to journal
      const journalItem = {
        position_id: posId,
        ticker: target.symbol,
        action: 'CLOSE',
        entry_price: entry,
        exit_price: exitPrice,
        price: exitPrice,
        units: units,
        pnl_usd: netPnl,
        pnl_pct: pnlPct,
        broker_exchange: target.broker_exchange || 'Real Broker',
        reason: notes || 'Ръчно затваряне на реална позиция',
        created_at: nowIso,
        hold_duration_days: target.duration_days || 0,
        portfolio_type: 'REAL'
      };

      if (!portfolioRealData.journal) portfolioRealData.journal = [];
      portfolioRealData.journal.unshift(journalItem);

      // Remove from open positions
      portfolioRealData.positions.splice(idx, 1);

      // Update local storage
      try {
        let saved = JSON.parse(localStorage.getItem('larsson_custom_real_positions') || '[]');
        saved = saved.filter(p => p.position_id !== posId);
        localStorage.setItem('larsson_custom_real_positions', JSON.stringify(saved));

        const savedClosed = JSON.parse(localStorage.getItem('larsson_custom_real_closed') || '[]');
        savedClosed.unshift(journalItem);
        localStorage.setItem('larsson_custom_real_closed', JSON.stringify(savedClosed));
      } catch(err) {
        console.error('Storage update error:', err);
      }

      hideClosePosModal();
      closeForm.reset();
      renderPortfolioView();
    });
  }
}

function openCloseRealModal(posId, ticker, currentPrice, units) {
  const modal = document.getElementById('closeRealModal');
  const summaryBox = document.getElementById('closePosSummary');
  const idInput = document.getElementById('closeRealPosId');
  const tickerInput = document.getElementById('closeRealTicker');
  const priceInput = document.getElementById('closeRealExitPrice');

  if (modal && summaryBox && idInput && tickerInput && priceInput) {
    idInput.value = posId;
    tickerInput.value = ticker;
    priceInput.value = currentPrice || '';
    summaryBox.innerHTML = `
      <div><strong>Актив:</strong> ${ticker}</div>
      <div><strong>Количество:</strong> ${units} бр.</div>
      <div><strong>Текуща пазарна оценка:</strong> ~$${formatShortPrice(currentPrice * units)}</div>
    `;
    modal.style.display = 'flex';
    priceInput.focus();
  }
}

function switchPortfolioMode(mode) {
  currentPortfolioMode = mode;
  localStorage.setItem('larsson_portfolio_mode', mode);

  const container = document.getElementById('tabContentPortfolio');
  const realBtn = document.getElementById('portModeRealBtn');
  const paperBtn = document.getElementById('portModePaperBtn');
  const bannerBadge = document.getElementById('portBannerBadge');
  const bannerDesc = document.getElementById('portBannerDesc');
  const bannerActions = document.getElementById('portBannerActions');
  const posHeading = document.getElementById('portPositionsHeading');
  const journalHeading = document.getElementById('portJournalHeading');

  if (container) {
    if (mode === 'REAL') {
      container.classList.remove('port-mode-paper');
      container.classList.add('port-mode-real');
    } else {
      container.classList.remove('port-mode-real');
      container.classList.add('port-mode-paper');
    }
  }

  if (realBtn) realBtn.classList.toggle('active', mode === 'REAL');
  if (paperBtn) paperBtn.classList.toggle('active', mode === 'PAPER');

  if (mode === 'REAL') {
    if (bannerBadge) bannerBadge.innerHTML = '🟢 РЕАЛНИ СРЕДСТВА &amp; БРОКЕРИ';
    if (bannerDesc) bannerDesc.textContent = 'Управление на действителни сделки от брокери (Binance, Interactive Brokers, Revolut). Всички метрики показват реален финансов капитал.';
    if (bannerActions) bannerActions.style.display = 'flex';
    if (posHeading) posHeading.textContent = '📈 Отворени Реални Позиции (Live Mark-to-Market)';
    if (journalHeading) journalHeading.textContent = '📖 Търговски Дневник: Реални Сделки & Изпълнения';
  } else {
    if (bannerBadge) bannerBadge.innerHTML = '🧪 ТЕСТОВ СИМУЛАТОР (PAPER TRADING)';
    if (bannerDesc) bannerDesc.textContent = 'Автономен симулатор на Larsson стратегии. Управлява се без реален финансов риск с автоматичен 50% TP1 и Breakeven Stop-Loss.';
    if (bannerActions) bannerActions.style.display = 'none';
    if (posHeading) posHeading.textContent = '📈 Отворени Тестови Позиции (Paper Simulation)';
    if (journalHeading) journalHeading.textContent = '📖 Търговски Дневник: Тестова Симулация & Бот';
  }

  renderPortfolioView();
}

function renderPortfolioView() {
  const isReal = (currentPortfolioMode === 'REAL');
  const bundle = isReal ? (portfolioRealData || {}) : (portfolioPaperData || {});
  const s = bundle.summary || {};
  let positions = bundle.positions || [];
  let journal = bundle.journal || bundle.history || [];

  // Update current prices and mark-to-market for positions from allSymbols if available
  let totalInvested = 0.0;
  let unrealizedPnl = 0.0;
  positions.forEach(pos => {
    const symObj = allSymbols.find(item => item.ticker === pos.symbol || item.ticker === pos.ticker);
    if (symObj && symObj.price) {
      pos.current_price = symObj.price;
    }
    const curP = pos.current_price || pos.entry_price || 0;
    const entryP = pos.entry_price || 0;
    const units = pos.units || 0;
    const sizeUsd = pos.position_size_usd || (entryP * units);
    const curVal = curP * units;
    const uPnl = curVal - sizeUsd;
    const uPct = sizeUsd > 0 ? (uPnl / sizeUsd * 100) : 0;

    pos.current_value = curVal;
    pos.unrealized_pnl = uPnl;
    pos.unrealized_pnl_pct = uPct;

    totalInvested += sizeUsd;
    unrealizedPnl += uPnl;
  });

  const availableCash = s.available_cash !== undefined ? s.available_cash : (isReal ? 0.0 : 10000.0);
  const totalEquity = availableCash + (totalInvested + unrealizedPnl);
  const initialBalance = s.initial_balance !== undefined ? s.initial_balance : (isReal ? availableCash : 10000.0);
  const totalRealizedPnl = s.total_realized_pnl || 0.0;
  const wins = s.wins || 0;
  const losses = s.losses || 0;
  const totalTrades = wins + losses;
  const winRate = totalTrades > 0 ? (wins / totalTrades * 100) : (s.win_rate || 0.0);
  const unrealizedPct = totalInvested > 0 ? (unrealizedPnl / totalInvested * 100) : 0.0;

  // 1. Metric Cards
  const totalEquityEl = document.getElementById('portTotalEquity');
  if (totalEquityEl) totalEquityEl.textContent = `$${totalEquity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const initBalEl = document.getElementById('portInitialBalance');
  if (initBalEl) initBalEl.textContent = `Базов: $${initialBalance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const cashEl = document.getElementById('portAvailableCash');
  if (cashEl) cashEl.textContent = `$${availableCash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const cashAllocEl = document.getElementById('portCashAlloc');
  if (cashAllocEl) {
    const cashPct = totalEquity > 0 ? ((availableCash / totalEquity) * 100).toFixed(0) : 100;
    cashAllocEl.textContent = `${cashPct}% ликвиден капитал`;
  }

  const investedEl = document.getElementById('portInvested');
  if (investedEl) investedEl.textContent = `$${totalInvested.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const openCountEl = document.getElementById('portOpenCount');
  if (openCountEl) openCountEl.textContent = `${positions.length} активни позиции`;

  const unrealizedEl = document.getElementById('portUnrealizedPnl');
  const unrealizedPctEl = document.getElementById('portUnrealizedPct');
  if (unrealizedEl) {
    const sign = unrealizedPnl >= 0 ? '+' : '';
    unrealizedEl.textContent = `${sign}$${unrealizedPnl.toFixed(2)}`;
    unrealizedEl.style.color = unrealizedPnl >= 0 ? '#10b981' : '#ef4444';
  }
  if (unrealizedPctEl) {
    const sign = unrealizedPct >= 0 ? '+' : '';
    unrealizedPctEl.textContent = `(${sign}${unrealizedPct.toFixed(2)}%)`;
    unrealizedPctEl.style.color = unrealizedPct >= 0 ? '#10b981' : '#ef4444';
  }

  const realizedEl = document.getElementById('portRealizedPnl');
  if (realizedEl) {
    const sign = totalRealizedPnl >= 0 ? '+' : '';
    realizedEl.textContent = `${sign}$${totalRealizedPnl.toFixed(2)}`;
    realizedEl.style.color = totalRealizedPnl >= 0 ? '#10b981' : '#ef4444';
  }

  const winRateEl = document.getElementById('portWinRate');
  if (winRateEl) winRateEl.textContent = `Win Rate: ${winRate.toFixed(1)}% (${wins}W / ${losses}L)`;

  // 2. Positions Table
  const activeBadge = document.getElementById('portActiveBadge');
  if (activeBadge) {
    activeBadge.textContent = `${positions.length} Активни`;
    activeBadge.className = `badge ${isReal ? 'badge-gold' : 'badge-blue'}`;
  }

  const posBody = document.getElementById('portPositionsBody');
  if (posBody) {
    if (positions.length === 0) {
      posBody.innerHTML = `
        <tr>
          <td colspan="10" class="loading-state" style="padding: 30px; text-align: center;">
            ${isReal 
              ? '🟢 Няма отворени реални позиции. Натиснете <strong>"➕ Добави Реална Позиция"</strong>, за да регистрирате покупка от вашия брокер.'
              : '🧪 Няма активни тестови позиции. Алгоритъмът изчаква нов A+ Quantamental сигнал за автоматичен симулиран вход.'}
          </td>
        </tr>
      `;
    } else {
      posBody.innerHTML = positions.map(p => {
        const uSign = (p.unrealized_pnl || 0) >= 0 ? '+' : '';
        const uColor = (p.unrealized_pnl || 0) >= 0 ? '#34d399' : '#f87171';
        const broker = p.broker_exchange || (isReal ? 'Manual / Broker' : 'Paper Engine');
        const brokerClass = isReal ? 'broker-pill' : 'broker-pill broker-pill-paper';
        const unitsFormatted = p.units < 1 ? p.units.toFixed(4) : p.units.toFixed(2);
        const posValue = p.current_value || (p.current_price * p.units) || p.position_size_usd;

        const slText = p.stop_loss ? `$${formatShortPrice(p.stop_loss)}` : '<span style="color:var(--text-muted)">Няма</span>';
        const tpText = p.tp1 ? `$${formatShortPrice(p.tp1)}` : '<span style="color:var(--text-muted)">Няма</span>';

        const actionBtns = isReal ? `
          <div style="display:flex; gap:6px;">
            <button class="btn-close-real-trade" onclick="openCloseRealModal('${p.position_id}', '${p.symbol}', ${p.current_price || p.entry_price}, ${p.units})">
              🔴 Затвори
            </button>
            <button class="btn-table-action" onclick="openChartModal('${p.symbol}', '1D', '${p.asset_class}')" title="Графика">
              📊
            </button>
          </div>
        ` : `
          <button class="btn-table-action" onclick="openChartModal('${p.symbol}', '1D', '${p.asset_class}')">
            📊 Графика
          </button>
        `;

        return `
          <tr>
            <td>
              <div class="ticker-cell" style="cursor: pointer;" onclick="openChartModal('${p.symbol}', '1D', '${p.asset_class}')">
                <span class="ticker-symbol">${p.symbol}</span>
                <span class="asset-class-tag">${CLASS_LABELS[p.asset_class] || p.asset_class}</span>
              </div>
            </td>
            <td>
              <span class="tier-badge tier-${p.tier || 'A'}">Tier ${p.tier || 'A'}</span>
            </td>
            <td>
              <span class="${brokerClass}">${broker}</span>
            </td>
            <td><strong>$${formatShortPrice(p.entry_price)}</strong></td>
            <td><strong>$${formatShortPrice(p.current_price)}</strong></td>
            <td>
              <div>${unitsFormatted} бр.</div>
              <small style="color: var(--text-muted);">$${formatShortPrice(posValue)}</small>
            </td>
            <td><strong style="color: #f87171;">${slText}</strong></td>
            <td><strong style="color: #34d399;">${tpText}</strong></td>
            <td>
              <strong style="color: ${uColor};">${uSign}$${(p.unrealized_pnl || 0).toFixed(2)}</strong>
              <div style="font-size: 0.75rem; color: ${uColor};">(${uSign}${(p.unrealized_pnl_pct || 0).toFixed(2)}%)</div>
            </td>
            <td>${actionBtns}</td>
          </tr>
        `;
      }).join('');
    }
  }

  // 3. Trade Journal Table
  const journalCountBadge = document.getElementById('portJournalCountBadge');
  if (journalCountBadge) journalCountBadge.textContent = `${journal.length} Сделки`;

  const journalBody = document.getElementById('portJournalBody');
  if (journalBody) {
    if (journal.length === 0) {
      journalBody.innerHTML = `
        <tr>
          <td colspan="9" class="loading-state" style="padding: 24px; text-align: center;">
            ${isReal 
              ? 'Няма записани сделки в дневника за реално портфолио.'
              : 'Няма приключени тестови сделки в симулационния дневник.'}
          </td>
        </tr>
      `;
    } else {
      journalBody.innerHTML = journal.map(j => {
        const pnl = j.pnl_usd || 0.0;
        const pnlPct = j.pnl_pct || 0.0;
        const sign = pnl >= 0 ? '+' : '';
        const color = pnl >= 0 ? '#34d399' : '#f87171';
        const dateStr = (j.created_at || j.exit_date || j.entry_date || '').replace('T', ' ').substring(0, 16);
        const action = j.action || 'TRADE';
        const actionClass = (action === 'BUY' || action === 'OPEN') ? 'badge-gold' : (pnl >= 0 ? 'badge-real' : 'badge-ruby');
        const broker = j.broker_exchange || (isReal ? 'Real Broker' : 'Paper Engine');
        const brokerClass = isReal ? 'broker-pill' : 'broker-pill broker-pill-paper';

        return `
          <tr>
            <td><small style="font-family: 'JetBrains Mono', monospace; color: var(--text-muted);">${dateStr || 'N/A'}</small></td>
            <td><strong>${j.ticker || j.symbol || 'N/A'}</strong></td>
            <td><span class="${brokerClass}">${broker}</span></td>
            <td><span class="badge ${actionClass}">${action}</span></td>
            <td>$${formatShortPrice(j.entry_price || j.price)}</td>
            <td>${j.exit_price ? `$${formatShortPrice(j.exit_price)}` : '—'}</td>
            <td>
              ${action === 'OPEN' || action === 'BUY' ? '—' : `<strong style="color: ${color};">${sign}$${pnl.toFixed(2)} (${sign}${pnlPct.toFixed(1)}%)</strong>`}
            </td>
            <td>${j.hold_duration_days !== undefined ? `${j.hold_duration_days} дни` : '—'}</td>
            <td><small style="color: var(--text-secondary);">${j.reason || j.notes || j.exit_reason || ''}</small></td>
          </tr>
        `;
      }).join('');
    }
  }
}

// =============================================================================
// TAB 4: ADVANCED INSTITUTIONAL TRADE CALCULATOR CONTROLLER
// =============================================================================

function initPageCalculator() {
  const capInput = document.getElementById('pageCalcCapital');
  const tickerInput = document.getElementById('pageCalcTicker');
  const tierSelect = document.getElementById('pageCalcTier');
  const entryInput = document.getElementById('pageCalcEntry');
  const slInput = document.getElementById('pageCalcSl');
  const tp1Input = document.getElementById('pageCalcTp1');
  const tp2Input = document.getElementById('pageCalcTp2');

  const recalc = () => {
    const capital = parseFloat(capInput ? capInput.value : 10000) || 10000;
    const activeRiskBtn = document.querySelector('#pageRiskPresets .preset-btn.active');
    const riskPct = activeRiskBtn ? parseFloat(activeRiskBtn.dataset.risk) : 1.0;
    const tier = tierSelect ? tierSelect.value : 'A';
    const tierMultiplier = { 'S': 1.0, 'A': 0.85, 'B': 0.6, 'C': 0.3 }[tier] || 0.85;

    const entry = parseFloat(entryInput ? entryInput.value : 100) || 100;
    let sl = parseFloat(slInput ? slInput.value : 95) || (entry * 0.95);
    const tp1 = parseFloat(tp1Input ? tp1Input.value : 110) || 0;
    const tp2 = parseFloat(tp2Input ? tp2Input.value : 120) || 0;

    const baseRiskUsd = capital * (riskPct / 100.0);
    const riskUsd = baseRiskUsd * tierMultiplier;
    const riskPerUnit = Math.abs(entry - sl);

    if (riskPerUnit > 0 && entry > 0) {
      const units = riskUsd / riskPerUnit;
      const posValue = units * entry;
      const riskPctOfPrice = ((riskPerUnit / entry) * 100.0).toFixed(2);

      const rr1 = tp1 > entry ? ((tp1 - entry) / riskPerUnit).toFixed(2) : '1.0';
      const rr2 = tp2 > entry ? ((tp2 - entry) / riskPerUnit).toFixed(2) : null;

      const tp1Profit = tp1 > entry ? (units * 0.5 * (tp1 - entry)) : 0;
      const tp2Profit = tp2 > entry ? (units * 0.5 * (tp2 - entry)) : 0;

      const unitsEl = document.getElementById('pageCalcUnits');
      if (unitsEl) unitsEl.textContent = `${units < 1 ? units.toFixed(4) : units.toFixed(2)} бр.`;

      const valEl = document.getElementById('pageCalcVal');
      if (valEl) valEl.textContent = `Стойност: $${posValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

      const riskUsdEl = document.getElementById('pageCalcRiskUsd');
      if (riskUsdEl) riskUsdEl.textContent = `-$${riskUsd.toFixed(2)}`;

      const riskPctEl = document.getElementById('pageCalcRiskPct');
      if (riskPctEl) riskPctEl.textContent = `-${riskPctOfPrice}% от цената (Риск: ${riskPct}% * Tier ${tier})`;

      const tp1ProfitEl = document.getElementById('pageCalcTp1Profit');
      if (tp1ProfitEl) tp1ProfitEl.textContent = `+$${tp1Profit.toFixed(2)}`;

      const tp2ProfitEl = document.getElementById('pageCalcTp2Profit');
      if (tp2ProfitEl) tp2ProfitEl.textContent = `+$${tp2Profit.toFixed(2)}`;

      const rrBadge = document.getElementById('pageCalcRrBadge');
      if (rrBadge) rrBadge.textContent = `R:R 1:${rr1}${rr2 ? ` (TP2 1:${rr2})` : ''}`;

      const dca1 = document.getElementById('pageDcaStep1');
      if (dca1) dca1.textContent = `Пазарен вход на $${entry.toFixed(2)} (${(units * 0.5).toFixed(2)} бр. = $${(posValue * 0.5).toFixed(2)})`;

      const dca2 = document.getElementById('pageDcaStep2');
      if (dca2) dca2.textContent = `Лимитна поръчка на S1 подкрепа (${(units * 0.5).toFixed(2)} бр. = $${(posValue * 0.5).toFixed(2)})`;

      // Compound growth calculations
      const monthlyReturnPct = 0.04; // conservative ~4% monthly expectancy
      const m3 = capital * Math.pow(1 + monthlyReturnPct, 3);
      const m6 = capital * Math.pow(1 + monthlyReturnPct, 6);
      const m12 = capital * Math.pow(1 + monthlyReturnPct, 12);

      const c3 = document.getElementById('compound3m');
      if (c3) c3.textContent = `$${Math.round(m3).toLocaleString('en-US')}`;
      const c6 = document.getElementById('compound6m');
      if (c6) c6.textContent = `$${Math.round(m6).toLocaleString('en-US')}`;
      const c12 = document.getElementById('compound12m');
      if (c12) c12.textContent = `$${Math.round(m12).toLocaleString('en-US')}`;
    }
  };

  [capInput, tickerInput, tierSelect, entryInput, slInput, tp1Input, tp2Input].forEach(el => {
    if (el) el.addEventListener('input', recalc);
  });

  document.querySelectorAll('#pageRiskPresets .preset-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('#pageRiskPresets .preset-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      recalc();
    });
  });

  recalc();
}

function quickFillCalculator(ticker, entry, sl, tp1, tp2, tier) {
  switchTab('calculator');
  const tInput = document.getElementById('pageCalcTicker');
  if (tInput) tInput.value = ticker;
  const eInput = document.getElementById('pageCalcEntry');
  if (eInput && entry) eInput.value = entry;
  const sInput = document.getElementById('pageCalcSl');
  if (sInput && sl) sInput.value = sl;
  const p1Input = document.getElementById('pageCalcTp1');
  if (p1Input && tp1) p1Input.value = tp1;
  const p2Input = document.getElementById('pageCalcTp2');
  if (p2Input && tp2) p2Input.value = tp2;
  const tierSel = document.getElementById('pageCalcTier');
  if (tierSel && tier) tierSel.value = tier;

  initPageCalculator();
}

// Initialize
loadDashboardData();

