let allSymbols = [];
let currentFilter = 'ALL';
let currentClass = 'ALL';
let currentTfFilter = 'ALL';
let currentTechFilter = 'ALL';
let currentFundFilter = 'ALL';
let currentSetupFilter = 'ALL';
let currentSearch = '';
let currentView = localStorage.getItem('larsson_view_mode') || 'table';

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
    renderOverview(data);
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
      style="width: 100%; height: 100%; min-height: 480px; border: none; border-radius: 8px;" 
      title="TradingView Chart - ${tvSymbol}"
      loading="lazy"
      allowtransparency="true" 
      scrolling="no" 
      allowfullscreen>
    </iframe>
  `;
}

function renderLightweightChart(container, candles, item, height = 500) {
  container.innerHTML = '';
  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth || 1000,
    height: height,
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
    activeChart = await loadChart(container, ticker, activeTf, assetClass, 500);
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
    activeChart.applyOptions({ width: modalContainer.clientWidth });
  }
  const liveContainer = document.getElementById('liveChartCanvas');
  if (liveActiveChart && liveContainer && liveContainer.clientWidth) {
    liveActiveChart.applyOptions({ width: liveContainer.clientWidth });
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

// Initialize
loadDashboardData();
