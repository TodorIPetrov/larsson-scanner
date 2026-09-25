let allSymbols = [];
let pendingSetups = [];
let pendingProposals = [];
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
let currentQueueSearch = '';
let currentView = localStorage.getItem('larsson_view_mode') || 'table';
let currentTab = localStorage.getItem('larsson_active_tab') || 'scanner';

let currentSortColumn = null;
let currentSortDir = 'asc';
let currentModalItem = null;
let currentCalcDirection = 'LONG';
let currentCalcLeverage = 1;
let currentModalLeverage = 1;

// Fundamental & DCF Hub State
let fundamentalProfiles = {};
let currentFundTicker = 'NVDA';
let fundReturnContext = 'scanner';
let currentSimBase = null;

// System Health & Scanner Polling State
let serverHealth = {
  isOnline: false,
  isScanning: false,
  scanDurationSec: 0,
  symbolsInDb: 0,
  dbHealthy: true,
  dataJsonExists: true,
  dataJsonSize: 0,
  dataJsonMtime: null,
  uptimeSec: 0,
  lastPollTime: null,
};
let isDataLoading = false;
let isDataLoaded = false;
let systemStatusTimer = null;

// Active chart state
let activeChart = null; // modal chart instance
let activeTicker = '';
let activeTf = '1D';
let activeClass = '';
let modalRatioMode = 'USD'; // 'USD' or 'BTC'

// Live on-page chart state
let liveActiveChart = null;
let liveTicker = 'BTCUSDT';
let liveTf = '1D';
let liveClass = 'crypto';
let liveRatioMode = 'USD'; // 'USD' or 'BTC'
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

const NATIVE_BINANCE_BTC_PAIRS = {
  'ETHUSDT': 'BINANCE:ETHBTC',
  'SOLUSDT': 'BINANCE:SOLBTC',
  'BNBUSDT': 'BINANCE:BNBBTC',
  'XRPUSDT': 'BINANCE:XRPBTC',
  'ADAUSDT': 'BINANCE:ADABTC',
  'AVAXUSDT': 'BINANCE:AVAXBTC',
  'DOGEUSDT': 'BINANCE:DOGEBTC',
  'LINKUSDT': 'BINANCE:LINKBTC',
  'DOTUSDT': 'BINANCE:DOTBTC',
  'NEARUSDT': 'BINANCE:NEARBTC',
  'LTCUSDT': 'BINANCE:LTCBTC',
  'BCHUSDT': 'BINANCE:BCHBTC',
  'ATOMUSDT': 'BINANCE:ATOMBTC',
};

function getTvRatioSymbol(item, ticker, assetClass) {
  if (item && item.tv_ratio_symbol) return item.tv_ratio_symbol;
  const sym = (ticker || (item && item.ticker) || '').toUpperCase();
  if (NATIVE_BINANCE_BTC_PAIRS[sym]) {
    return NATIVE_BINANCE_BTC_PAIRS[sym];
  }
  const cls = assetClass || (item && item.asset_class) || 'crypto';
  const baseSym = (item && item.tv_symbol) || sym;
  if (cls === 'crypto') {
    let clean = baseSym;
    if (!clean.startsWith('BINANCE:') && (sym.endsWith('USDT') || sym.endsWith('USDC'))) {
      clean = `BINANCE:${sym}`;
    }
    return `${clean}/BINANCE:BTCUSDT`;
  } else if (cls === 'crypto_stocks' || cls === 'us_stocks' || cls === 'ai_stocks') {
    const clean = baseSym.includes(':') ? baseSym : `NASDAQ:${sym}`;
    return `${clean}/BINANCE:BTCUSDT`;
  }
  return `${baseSym}/BINANCE:BTCUSDT`;
}

function getTvRatioLink(item, ticker, assetClass, timeframe) {
  if (item && item.tv_ratio_url) return item.tv_ratio_url;
  const ratioSym = getTvRatioSymbol(item, ticker, assetClass);
  const tfCode = getTvInterval(timeframe || (item && item.timeframe) || '1D');
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(ratioSym)}&interval=${tfCode}`;
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

function renderBtcBadge(btcRel) {
  if (!btcRel || !btcRel.badge_bg) return '';
  let cls = 'btc-badge-neutral';
  if (btcRel.ratio_state === 'GOLD' || (btcRel.alpha_30d_pct > 0 && btcRel.leverage_allowed)) {
    cls = 'btc-badge-gold';
  } else if (btcRel.ratio_state === 'BLUE' || !btcRel.leverage_allowed) {
    cls = 'btc-badge-blue';
  }
  const title = (btcRel.thesis_bg || '') + (btcRel.tv_ratio_url ? ' (Кликни за TradingView /BTC графика)' : '');
  if (btcRel.tv_ratio_url) {
    return `<a href="${btcRel.tv_ratio_url}" target="_blank" rel="noopener" class="btc-alpha-badge ${cls}" style="text-decoration: none;" onclick="event.stopPropagation()" title="${title}">${btcRel.badge_bg} ↗</a>`;
  }
  return `<span class="btc-alpha-badge ${cls}" title="${title}">${btcRel.badge_bg}</span>`;
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
  const ticker = item ? (item.ticker || item.symbol || '') : '';
  if (!fund) {
    return `<div class="fund-cell fund-cell-interactive" onclick="event.stopPropagation(); openFundamentalTab('${escapeHtml(ticker)}', 'scanner');" title="🏢 Кликнете за пълен фундаментален анализ и DCF оценка"><span class="fund-badge fund-badge-speculative">⚪ N/A</span></div>`;
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
    <div class="fund-cell fund-cell-interactive" onclick="event.stopPropagation(); openFundamentalTab('${escapeHtml(ticker)}', 'scanner');" title="🏢 Кликнете за пълен фундаментален анализ и DCF оценка">
      <span class="fund-badge ${badgeClass}" title="${escapeHtml(fund.thesis_bg || fund.thesis || '')}">
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

// =============================================================================
// LIVE SYSTEM HEALTH & SCANNER DIAGNOSTICS (THINKING / IDLE / OFFLINE DETECTOR)
// =============================================================================

async function checkServerStatus() {
  const badge = document.getElementById('systemStatusBadge');
  const dot = document.getElementById('systemStatusDot');
  const text = document.getElementById('systemStatusText');
  if (!badge || !dot || !text) return;

  const isFile = window.location.protocol === 'file:';
  if (isFile) {
    serverHealth.isOnline = false;
    dot.className = 'status-indicator-dot offline';
    text.textContent = '⚠️ file:// (Няма CORS)';
    badge.title = 'Отворено през file:// протокол. Браузърът блокира API заявки. Отворете http://localhost:8080';
    return;
  }

  try {
    const res = await fetch('/api/status', { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      serverHealth.isOnline = true;
      serverHealth.isScanning = Boolean(data.is_scanning);
      serverHealth.scanDurationSec = data.scan_duration_sec || 0;
      serverHealth.symbolsInDb = data.symbols_in_db || 0;
      serverHealth.dbHealthy = data.db_healthy !== false;
      serverHealth.dataJsonExists = data.data_json_exists;
      serverHealth.dataJsonSize = data.data_json_size || 0;
      serverHealth.dataJsonMtime = data.data_json_mtime;
      serverHealth.uptimeSec = data.server_uptime_sec || 0;
      serverHealth.lastPollTime = new Date();

      updateSystemHealthBadge();
      updateDiagnosticsModalUI();

      // If server was scanning and just finished, reload dashboard data automatically!
      if (window._wasScanning && !serverHealth.isScanning) {
        window._wasScanning = false;
        loadDashboardData();
      }
      if (serverHealth.isScanning) {
        window._wasScanning = true;
      }
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    const isCloud = window.location.hostname.includes('github.io') || 
                   (window.location.protocol === 'https:' && !window.location.port);
    if (isCloud && isDataLoaded && allSymbols.length > 0) {
      serverHealth.isOnline = true;
      serverHealth.isCloud = true;
      serverHealth.symbolsInDb = allSymbols.length;
      serverHealth.dbHealthy = true;
      serverHealth.dataJsonExists = true;
      serverHealth.lastPollTime = new Date();
      updateSystemHealthBadge();
      updateDiagnosticsModalUI();
      return;
    }

    serverHealth.isOnline = false;
    serverHealth.isCloud = false;
    dot.className = 'status-indicator-dot offline';
    text.textContent = '🔴 Няма връзка със сървъра';
    badge.title = 'Сървърът на localhost:8080 не отговаря. Уверете се, че server.py е стартиран.';
    updateDiagnosticsModalUI();
  }
}

function updateSystemHealthBadge() {
  const badge = document.getElementById('systemStatusBadge');
  const dot = document.getElementById('systemStatusDot');
  const text = document.getElementById('systemStatusText');
  if (!badge || !dot || !text) return;

  if (serverHealth.isScanning) {
    dot.className = 'status-indicator-dot scanning';
    const durTxt = serverHealth.scanDurationSec > 0 ? ` (${serverHealth.scanDurationSec}s)` : '';
    text.textContent = `⚡ Сканира пазара${durTxt}... (Мисли)`;
    badge.title = 'Скенерът мисли и анализира пазарните данни в реално време!';
    return;
  }

  if (serverHealth.isOnline) {
    const filteredCount = getFilteredSymbols().length;
    const totalCount = allSymbols.length;

    if (totalCount > 0 && filteredCount < totalCount) {
      dot.className = 'status-indicator-dot filtered';
      text.textContent = `🟡 ${filteredCount} от ${totalCount} (Филтриран)`;
      badge.title = `Има активни филтри: показват се ${filteredCount} от общо ${totalCount} инструмента. Кликнете за диагностика.`;
    } else if (serverHealth.isCloud) {
      dot.className = 'status-indicator-dot online';
      text.textContent = `☁️ Облачен Скенер (${totalCount} актива)`;
      badge.title = `Работи на живо в GitHub Pages. Автономно сканиране на ${totalCount} актива на всеки 4 часа през GitHub Actions.`;
    } else {
      dot.className = 'status-indicator-dot online';
      const count = totalCount || serverHealth.symbolsInDb || 659;
      text.textContent = `🟢 Свързан (${count} актива)`;
      badge.title = `Сървърът и базата данни са активни. ${count} актива са готови. Кликнете за диагностика.`;
    }
  }
}

function toggleSystemStatusModal() {
  const modal = document.getElementById('systemStatusModal');
  if (!modal) return;
  const isHidden = modal.style.display === 'none' || !modal.style.display;
  if (isHidden) {
    openSystemStatusModal();
  } else {
    closeSystemStatusModal();
  }
}
window.toggleSystemStatusModal = toggleSystemStatusModal;

function openSystemStatusModal() {
  const modal = document.getElementById('systemStatusModal');
  if (!modal) return;
  updateDiagnosticsModalUI();
  modal.style.display = 'flex';
  checkServerStatus();
}
window.openSystemStatusModal = openSystemStatusModal;

function closeSystemStatusModal() {
  const modal = document.getElementById('systemStatusModal');
  if (modal) modal.style.display = 'none';
}
window.closeSystemStatusModal = closeSystemStatusModal;

function updateDiagnosticsModalUI() {
  const modal = document.getElementById('systemStatusModal');
  if (!modal || modal.style.display === 'none') return;

  const dot = document.getElementById('modalStatusDot');
  const hero = document.getElementById('diagStatusHero');
  const icon = document.getElementById('diagHeroIcon');
  const title = document.getElementById('diagHeroTitle');
  const subtitle = document.getElementById('diagHeroSubtitle');

  const serverVal = document.getElementById('diagServerVal');
  const uptimeVal = document.getElementById('diagUptimeVal');
  const scannerVal = document.getElementById('diagScannerVal');
  const scanElapsedVal = document.getElementById('diagScanElapsedVal');
  const dbVal = document.getElementById('diagDbVal');
  const dbHealthVal = document.getElementById('diagDbHealthVal');
  const jsonVal = document.getElementById('diagJsonVal');
  const jsonMtimeVal = document.getElementById('diagJsonMtimeVal');
  const chipsContainer = document.getElementById('diagFilterChips');
  const resetBtn = document.getElementById('btnDiagResetFilters');

  const isFile = window.location.protocol === 'file:';

  if (isFile) {
    if (dot) dot.className = 'status-indicator-dot offline';
    if (hero) hero.className = 'diag-status-hero hero-offline';
    if (icon) icon.textContent = '⚠️';
    if (title) title.textContent = 'Отворено през file:// протокол (CORS ограничение)';
    if (subtitle) subtitle.textContent = 'Уеб браузърите забраняват зареждане на JSON файлове директно от локалния диск. Моля отворете http://localhost:8080';
    if (serverVal) serverVal.textContent = 'file:// (Локален файл)';
    if (uptimeVal) uptimeVal.textContent = 'Няма връзка с localhost';
  } else if (!serverHealth.isOnline) {
    if (dot) dot.className = 'status-indicator-dot offline';
    if (hero) hero.className = 'diag-status-hero hero-offline';
    if (icon) icon.textContent = '🔴';
    if (title) title.textContent = 'Няма връзка със сървъра';
    if (subtitle) subtitle.textContent = 'Сървърът на localhost:8080 не отговаря. Стартирайте python src/dashboard/server.py 8080';
    if (serverVal) serverVal.textContent = 'Прекъсната (Offline)';
    if (uptimeVal) uptimeVal.textContent = 'Проверете конзолата';
  } else if (serverHealth.isCloud) {
    if (dot) dot.className = 'status-indicator-dot online';
    if (hero) hero.className = 'diag-status-hero hero-online';
    if (icon) icon.textContent = '☁️';
    const totalCount = allSymbols.length || 664;
    if (title) title.textContent = 'Скенерът работи в Облачен Режим (GitHub Pages)';
    if (subtitle) subtitle.textContent = `Пазарните данни и сигнали за ${totalCount} актива се обновяват автономно на всеки 4 часа през GitHub Actions.`;
    if (serverVal) serverVal.textContent = 'GitHub Pages (24/7 Cloud)';
    if (uptimeVal) uptimeVal.textContent = 'GitHub Actions Scheduler (Cron)';
    if (scannerVal) scannerVal.textContent = '24/7 Автономен Скенер';
    if (scanElapsedVal) scanElapsedVal.textContent = 'График: На всеки 4 часа';
    if (dbVal) dbVal.textContent = `${totalCount} пазарни актива`;
    if (dbHealthVal) dbHealthVal.textContent = '✅ Облачна база данни (Здрава)';
    if (jsonVal) jsonVal.textContent = '✅ Зареден успешно';
    if (jsonMtimeVal) jsonMtimeVal.textContent = 'GitHub Pages Live';
  } else if (serverHealth.isScanning) {
    if (dot) dot.className = 'status-indicator-dot scanning';
    if (hero) hero.className = 'diag-status-hero hero-scanning';
    if (icon) icon.textContent = '⚡';
    if (title) title.textContent = 'Скенерът мисли и сканира пазара в момента...';
    if (subtitle) subtitle.textContent = `Изпълнява се дълбок анализ на Larsson панделките и се генерират нови търговски предложения (${serverHealth.scanDurationSec}s).`;
    if (serverVal) serverVal.textContent = 'Свързан (localhost:8080)';
    if (uptimeVal) uptimeVal.textContent = `Uptime: ${Math.round(serverHealth.uptimeSec / 60)} min`;
    if (scannerVal) scannerVal.textContent = `⚡ Сканира (${serverHealth.scanDurationSec}s)...`;
    if (scanElapsedVal) scanElapsedVal.textContent = 'Статус: Активно изчисление';
  } else {
    if (dot) dot.className = 'status-indicator-dot online';
    if (hero) hero.className = 'diag-status-hero';
    if (icon) icon.textContent = '🟢';
    const totalCount = allSymbols.length || serverHealth.symbolsInDb || 659;
    if (title) title.textContent = 'Системата работи нормално и е напълно готова';
    if (subtitle) subtitle.textContent = `${totalCount} пазарни актива са заредени в паметта и достъпни за филтриране и графичен анализ.`;
    if (serverVal) serverVal.textContent = 'Свързан (localhost:8080)';
    if (uptimeVal) uptimeVal.textContent = `Uptime: ${Math.round(serverHealth.uptimeSec / 60)} min`;
    if (scannerVal) scannerVal.textContent = 'В покой (Готов)';
    if (scanElapsedVal) scanElapsedVal.textContent = 'Статус: Изчаква заявка';
  }

  if (serverHealth.isOnline) {
    if (dbVal) dbVal.textContent = `${serverHealth.symbolsInDb || allSymbols.length} инструмента`;
    if (dbHealthVal) dbHealthVal.textContent = serverHealth.dbHealthy ? 'Статус: SQLite WAL изряден' : 'Грешка при четене на БД';

    const sizeMb = serverHealth.dataJsonSize ? (serverHealth.dataJsonSize / (1024 * 1024)).toFixed(2) : '4.93';
    if (jsonVal) jsonVal.textContent = `${sizeMb} MB`;
    if (jsonMtimeVal) {
      if (serverHealth.dataJsonMtime) {
        const d = new Date(serverHealth.dataJsonMtime);
        jsonMtimeVal.textContent = `Обновен: ${d.toLocaleTimeString()}`;
      } else {
        jsonMtimeVal.textContent = 'Наличен';
      }
    }
  }

  // Active filters list
  if (chipsContainer) {
    const activeFilters = [];
    if (currentSearch) activeFilters.push({ label: `Търсене: "${currentSearch}"`, type: 'search' });
    if (currentClass !== 'ALL') activeFilters.push({ label: `Пазар: ${CLASS_LABELS[currentClass] || currentClass}`, type: 'class' });
    if (currentTfFilter !== 'ALL') activeFilters.push({ label: `ТФ: ${currentTfFilter}`, type: 'tf' });
    if (currentTechFilter !== 'ALL') activeFilters.push({ label: `Техника: ${currentTechFilter}`, type: 'tech' });
    if (currentFundFilter !== 'ALL') activeFilters.push({ label: `Фундамент: ${currentFundFilter}`, type: 'fund' });
    if (currentSetupFilter !== 'ALL') activeFilters.push({ label: `Синтез: ${currentSetupFilter}`, type: 'setup' });

    if (activeFilters.length === 0) {
      chipsContainer.innerHTML = '<span style="color: var(--text-muted); font-size: 0.8rem;">Няма активни филтри — показват се всички активи.</span>';
      if (resetBtn) resetBtn.style.display = 'none';
    } else {
      chipsContainer.innerHTML = activeFilters.map(f => `
        <span class="diag-chip">
          ${escapeHtml(f.label)}
        </span>
      `).join('');
      if (resetBtn) resetBtn.style.display = 'inline-block';
    }
  }
}

function getZeroStateHtml() {
  if (allSymbols.length === 0) {
    if (isDataLoading) {
      return `
        <div class="zero-state-banner">
          <div class="spinner" style="width: 32px; height: 32px; border-width: 3px;"></div>
          <div class="zero-state-content">
            <h4>Зареждане на пазарните данни...</h4>
            <p>Системата извлича 659 актива и Larsson панделки от локалната база данни. Моля изчакайте секунда...</p>
          </div>
        </div>
      `;
    }
    const isFile = window.location.protocol === 'file:';
    if (isFile) {
      return `
        <div class="zero-state-banner" style="border-color: #f59e0b;">
          <div class="zero-state-icon">⚠️</div>
          <div class="zero-state-content">
            <h4 style="color: #f59e0b;">Браузърът блокира data.json (CORS при file:// протокол)</h4>
            <p>За сигурност уеб браузърите не позволяват зареждане на JSON файлове при директно отваряне с двоен клик на файла. Моля отворете адреса през локалния уеб сървър:</p>
            <div class="zero-state-actions">
              <a href="http://localhost:8080" class="btn btn-primary-action">🚀 Отвори през Localhost:8080</a>
              <a href="https://todoripetrov.github.io/larsson-scanner/" target="_blank" rel="noopener" class="btn btn-secondary-action">🌐 GitHub Pages</a>
            </div>
          </div>
        </div>
      `;
    }
    return `
      <div class="zero-state-banner">
        <div class="zero-state-icon">⚡</div>
        <div class="zero-state-content">
          <h4>Няма заредени данни в скенера</h4>
          <p>Базата данни може би се сканира в момента или сървърът е стартиран наскоро.</p>
          <div class="zero-state-actions">
            <button class="btn btn-primary-action" onclick="runNewTradeAnalysis()">⚡ Стартирай Анализ</button>
            <button class="btn btn-secondary-action" onclick="loadDashboardData()">↻ Презареди</button>
            <button class="btn btn-secondary-action" onclick="toggleSystemStatusModal()">🔍 Системна Диагностика</button>
          </div>
        </div>
      </div>
    `;
  }

  // Case: allSymbols.length > 0, but active filters reduced to 0
  const activeTags = [];
  if (currentSearch) activeTags.push(`Търсене: "${escapeHtml(currentSearch)}"`);
  if (currentClass !== 'ALL') activeTags.push(`Пазар: ${CLASS_LABELS[currentClass] || currentClass}`);
  if (currentTfFilter !== 'ALL') activeTags.push(`Времева рамка: ${currentTfFilter}`);
  if (currentTechFilter !== 'ALL') activeTags.push(`Техника: ${currentTechFilter}`);
  if (currentFundFilter !== 'ALL') activeTags.push(`Фундамент: ${currentFundFilter}`);
  if (currentSetupFilter !== 'ALL') activeTags.push(`Синтез: ${currentSetupFilter}`);

  const tagsHtml = activeTags.map(t => `<span class="zero-state-tag">${t}</span>`).join('');

  return `
    <div class="zero-state-banner">
      <div class="zero-state-icon">🔍</div>
      <div class="zero-state-content">
        <h4>Няма намерени активи за текущите филтри</h4>
        <p>В системата има <strong>${allSymbols.length} активни пазарни инструмента</strong>, но активните критерии скриват всички резултати:</p>
        <div class="zero-state-tags">
          ${tagsHtml || '<span class="zero-state-tag">Активен филтър</span>'}
        </div>
        <div class="zero-state-actions">
          <button class="btn btn-primary-action" onclick="resetAllFilters()">✕ Нулирай всички филтри (${allSymbols.length} актива)</button>
          <button class="btn btn-secondary-action" onclick="toggleSystemStatusModal()">🔍 Системна Диагностика</button>
        </div>
      </div>
    </div>
  `;
}

function renderTradeSuggestionCell(ts, item) {
  return renderSynthesisCell(item ? item.synthesis : null, ts, item);
}

async function loadDashboardData() {
  let data;
  isDataLoading = true;
  try {
    const res = await fetch('data.json?t=' + new Date().getTime());
    if (!res.ok) {
      throw new Error(`Failed to load data.json: ${res.statusText}`);
    }
    data = await res.json();
    window.lastLoadedDashboardData = data;
    allSymbols = data.symbols || [];
    fundamentalProfiles = data.fundamental_profiles || {};
    pendingSetups = data.pending_setups || [];
    pendingProposals = data.pending_proposals || [];
    portfolioData = data.portfolio || {};
    portfolioPaperData = data.portfolio_paper || { summary: portfolioData, positions: [], history: [], journal: [] };
    portfolioRealData = data.portfolio_real || { summary: {}, positions: [], history: [], journal: [] };
    isDataLoaded = true;
    isDataLoading = false;

    // Sync any custom positions or cash saved locally in this browser
    syncLocalPaperStorage();
    syncLocalRealStorage();

    renderOverview(data);
    renderQueueView();
    renderProposalsBanner(pendingProposals);
    initPortfolioController();
    switchPortfolioMode(currentPortfolioMode);
    initPageCalculator();
    switchTab(currentTab);
    checkServerStatus();
  } catch (err) {
    isDataLoading = false;
    console.error('Error loading data.json:', err);
    checkServerStatus();
    const errorHtml = getZeroStateHtml();

    const tbody = document.getElementById('assetsTableBody');
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="14" style="padding: 0;">
            ${errorHtml}
          </td>
        </tr>
      `;
    }
    const cards = document.getElementById('cardsGrid');
    if (cards) cards.innerHTML = `<div style="grid-column: 1/-1;">${errorHtml}</div>`;
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

// =============================================================================
// ADVANCED SMART SEARCH ENGINE (Multi-token, Normalization, Cyrillic & Ranking)
// =============================================================================

const BG_SEMANTIC_ALIASES = {
  'биткойн': ['btc', 'bitcoin'],
  'биткоин': ['btc', 'bitcoin'],
  'бикойн': ['btc', 'bitcoin'],
  'бтк': ['btc'],
  'етериум': ['eth', 'ethereum'],
  'етер': ['eth', 'ethereum'],
  'етириум': ['eth'],
  'солана': ['sol', 'solana'],
  'солано': ['sol', 'solana'],
  'накамото': ['naka', 'nakamoto'],
  'нака': ['naka'],
  'злато': ['gold', 'paxg', 'gc=f'],
  'златен': ['gold'],
  'златни': ['gold'],
  'сребро': ['silver', 'si=f'],
  'сребърен': ['silver'],
  'петрол': ['oil', 'cl=f'],
  'нефт': ['oil', 'cl=f'],
  'газ': ['gas', 'ng=f'],
  'тесла': ['tsla', 'tesla'],
  'микростратеджи': ['mstr', 'microstrategy'],
  'микростратегия': ['mstr', 'microstrategy'],
  'метапланет': ['metaplanet', '3350'],
  'ябълка': ['aapl', 'apple'],
  'ейпъл': ['aapl', 'apple'],
  'апл': ['aapl', 'apple'],
  'нвидиа': ['nvda', 'nvidia'],
  'енвидиа': ['nvda', 'nvidia'],
  'майкрософт': ['msft', 'microsoft'],
  'гугъл': ['goog', 'google', 'alphabet'],
  'алфабет': ['goog', 'alphabet'],
  'амазон': ['amzn', 'amazon'],
  'койнбейс': ['coin', 'coinbase'],
  'коинбейс': ['coin', 'coinbase'],
  'риот': ['riot'],
  'мара': ['mara'],
  'крипто': ['crypto'],
  'акции': ['stocks'],
  'индекси': ['indices', 'spx', 'ndx', 'dji']
};

const BG_PHONETIC_MAP = {
  'а': 'a', 'б': 'b', 'в': 'w', 'г': 'g', 'д': 'd', 'е': 'e', 'ж': 'v',
  'з': 'z', 'и': 'i', 'й': 'j', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
  'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f',
  'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sht', 'ъ': 'y', 'ь': 'x',
  'ю': 'yu', 'я': 'ya'
};

function transliterateBg(str) {
  if (!str) return '';
  let res = '';
  for (const ch of str.toLowerCase()) {
    res += BG_PHONETIC_MAP[ch] !== undefined ? BG_PHONETIC_MAP[ch] : ch;
  }
  return res;
}

function normalizeSearchStr(str) {
  if (!str) return '';
  return String(str).toLowerCase().replace(/[\/\-_.:=\s\\,()]+/g, '');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function calculateSearchScore(item, rawQuery, variants, tokens) {
  const rawTicker = (item.ticker || '').toLowerCase();
  const normTicker = normalizeSearchStr(item.ticker);
  const rawName = (item.name || '').toLowerCase();
  const normName = normalizeSearchStr(item.name);
  const normTv = normalizeSearchStr(item.tv_symbol || '');
  const rawClass = (item.asset_class || '').toLowerCase();
  const rawTf = (item.timeframe || '').toLowerCase();
  const rawState = (item.state || '').toLowerCase();
  const techAction = (item.technical && item.technical.action || '').toLowerCase();
  const fundAction = (item.fundamental && item.fundamental.action || '').toLowerCase();
  const synthSetup = (item.synthesis && item.synthesis.setup_type || '').toLowerCase();
  const btcVerdict = (item.btc_relative && item.btc_relative.verdict || '').toLowerCase();
  const qClean = rawQuery.toLowerCase().trim();
  const qNorm = normalizeSearchStr(rawQuery);

  let score = 0;

  // 1. Direct ticker exact match or direct USD/USDT pair match
  if (rawTicker === qClean || normTicker === qNorm) {
    score += 2500;
  } else if (normTicker === qNorm + 'usdt' || normTicker === qNorm + 'usd' || rawTicker === qClean + '-usd') {
    score += 2000;
  } else if (normTicker.startsWith(qNorm) || rawTicker.startsWith(qClean)) {
    score += 600;
  } else if (normTicker.includes(qNorm) || rawTicker.includes(qClean)) {
    score += 350;
  }

  // 2. Direct name exact or prefix match
  if (rawName === qClean || normName === qNorm) {
    score += 1500;
  } else if (normName.startsWith(qNorm) || rawName.startsWith(qClean)) {
    score += 500;
  } else if (normName.includes(qNorm) || rawName.includes(qClean)) {
    score += 250;
  }

  // 3. Variant matches (Cyrillic aliases / Bulgarian transliteration)
  for (const v of variants) {
    if (!v) continue;
    if (normTicker === v || rawTicker === v) score += 1200;
    else if (normTicker === v + 'usdt' || normTicker === v + 'usd' || rawTicker === v + '-usd') score += 1100;
    else if (normTicker.startsWith(v)) score += 400;
    else if (normTicker.includes(v)) score += 200;

    if (normName === v || rawName === v) score += 900;
    else if (normName.startsWith(v)) score += 350;
    else if (normName.includes(v)) score += 150;
  }

  // 4. Token multi-match across fields
  let matchedAllTokens = true;
  for (const tok of tokens) {
    const nTok = normalizeSearchStr(tok);
    let tokMatch = false;

    if (rawTicker.includes(tok) || normTicker.includes(nTok)) tokMatch = true;
    else if (rawName.includes(tok) || normName.includes(nTok)) tokMatch = true;
    else if (normTv.includes(nTok)) tokMatch = true;
    else if (rawClass.includes(tok)) tokMatch = true;
    else if (rawTf === tok) tokMatch = true;
    else if (rawState === tok) tokMatch = true;
    else if (techAction.includes(tok)) tokMatch = true;
    else if (fundAction.includes(tok)) tokMatch = true;
    else if (synthSetup.includes(tok)) tokMatch = true;
    else if (tok.length >= 4 && (tok.includes('alpha') || tok.includes('bleed') || tok.includes('sat')) && btcVerdict.includes(tok)) tokMatch = true;

    if (!tokMatch) {
      matchedAllTokens = false;
      break;
    }
  }

  if (tokens.length > 1 && matchedAllTokens) {
    score += 450;
  }

  // Bonus for 1D timeframe (standard daily timeframe)
  if (score > 0 && rawTf === '1d') score += 10;

  return score;
}

function isRecentGoldFlip(item) {
  if (item.state !== 'GOLD') return false;
  if (item.is_gold_flip !== undefined) return Boolean(item.is_gold_flip);
  if (item.technical && item.technical.is_gold_flip !== undefined) return Boolean(item.technical.is_gold_flip);

  // Dynamic fallback evaluation ONLY if explicitly recent and healthy spread
  if (item.last_change) {
    const diffHours = (Date.now() - new Date(item.last_change).getTime()) / (1000 * 3600);
    const tf = item.timeframe || '1D';
    const sPct = item.spread_pct !== null && item.spread_pct !== undefined ? item.spread_pct : 999;
    if (tf === '4H' && diffHours <= 6 && sPct >= 0 && sPct <= 6.0) return true;
    if (tf === '1D' && diffHours <= 28 && sPct >= 0 && sPct <= 6.0) return true;
  }
  return false;
}

function renderGoldFlipBadge(item) {
  if (!isRecentGoldFlip(item)) return '';
  const barsTxt = (item.gold_flip_bars || (item.technical && item.technical.gold_flip_bars)) ? ` ${item.gold_flip_bars || item.technical.gold_flip_bars}б` : '';
  return `<span class="badge-gold-flip" title="Пресен пробив в Gold Ribbon (${barsTxt ? barsTxt.trim() + ' назад' : '1-5 бара'}). Ранна входна фаза на разширение!">✨ GOLD FLIP${barsTxt}</span>`;
}

function getFilteredSymbols() {
  const q = currentSearch.toLowerCase().trim();
  const qNorm = normalizeSearchStr(q);

  let searchVariants = new Set();
  let queryTokens = [];
  if (q) {
    if (qNorm) searchVariants.add(qNorm);

    for (const [bgKey, aliases] of Object.entries(BG_SEMANTIC_ALIASES)) {
      if (q.includes(bgKey) || bgKey.includes(q)) {
        aliases.forEach(a => {
          searchVariants.add(a.toLowerCase());
          searchVariants.add(normalizeSearchStr(a));
        });
      }
    }

    const translit = transliterateBg(q);
    if (translit !== q) {
      searchVariants.add(translit);
      searchVariants.add(normalizeSearchStr(translit));
    }

    queryTokens = q.split(/\s+/).filter(Boolean);
  }

  const scoredItems = [];

  for (const item of allSymbols) {
    // 1. Asset Class Filter
    const matchesClass = (currentClass === 'ALL') || (item.asset_class === currentClass);
    // 2. Timeframe Filter
    const matchesTf = (currentTfFilter === 'ALL') || (item.timeframe === currentTfFilter);

    // 3. Technical Filter
    const tech = item.technical;
    let matchesTech = true;
    if (currentTechFilter === 'GOLD') {
      matchesTech = item.state === 'GOLD';
    } else if (currentTechFilter === 'RECENT_GOLD_FLIP') {
      matchesTech = isRecentGoldFlip(item);
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
    } else if (currentSetupFilter === 'BTC_ALPHA') {
      matchesSetup = item.btc_relative && (item.btc_relative.ratio_state === 'GOLD' || item.btc_relative.alpha_30d_pct > 0);
    } else if (currentSetupFilter === 'BTC_BLEED') {
      matchesSetup = item.btc_relative && (item.btc_relative.ratio_state === 'BLUE' || !item.btc_relative.leverage_allowed);
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

    if (!matchesClass || !matchesTf || !matchesTech || !matchesFund || !matchesSetup) {
      continue;
    }

    let searchScore = 0;
    if (q) {
      searchScore = calculateSearchScore(item, q, searchVariants, queryTokens);
      if (searchScore <= 0) continue;
    }

    scoredItems.push({ item, score: searchScore });
  }

  // Sorting
  if (currentSortColumn) {
    const stateRanks = { 'GOLD': 3, 'NEUTRAL': 2, 'BLUE': 1 };
    const fundRanks = { 'STRONG_BUY': 4, 'BUY': 3, 'HOLD': 2, 'REDUCE': 1, 'SPECULATIVE_NA': 0 };

    scoredItems.sort((aObj, bObj) => {
      const a = aObj.item;
      const b = bObj.item;
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
  } else if (q) {
    // Rank by relevance score when searching
    scoredItems.sort((a, b) => b.score - a.score);
  } else {
    // Default sorting in main view: Rank assets by best trade setups from combined quantamental analysis!
    scoredItems.sort((aObj, bObj) => {
      const a = aObj.item;
      const b = bObj.item;
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

  return scoredItems.map(s => s.item);
}

function renderOverview(data) {
  if (data) window.lastLoadedDashboardData = data;
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

  const totalEl = document.getElementById('totalCount');
  if (totalEl) {
    if (allSymbols.length === 0) {
      if (isDataLoading) {
        totalEl.innerHTML = '<span class="stat-loading-dots">...</span>';
      } else {
        totalEl.textContent = '0';
      }
    } else if (total < allSymbols.length) {
      totalEl.innerHTML = `${total} <span class="filter-hint" title="Филтрирано по пазар/времева рамка">(от ${allSymbols.length})</span>`;
    } else {
      totalEl.textContent = total;
    }
  }

  const goldEl = document.getElementById('goldCount');
  if (goldEl) goldEl.textContent = goldCount;
  const blueEl = document.getElementById('blueCount');
  if (blueEl) blueEl.textContent = blueCount;
  const neutralEl = document.getElementById('neutralCount');
  if (neutralEl) neutralEl.textContent = neutralCount;

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

  updateSystemHealthBadge();
}

function updateSearchControls(filteredCount) {
  const clearBtn = document.getElementById('searchClearBtn');
  const kbdHint = document.getElementById('searchKbdHint');
  const countBadge = document.getElementById('searchCountBadge');

  if (clearBtn) {
    clearBtn.style.display = currentSearch ? 'flex' : 'none';
  }
  if (kbdHint) {
    kbdHint.style.display = currentSearch ? 'none' : 'inline-block';
  }
  if (countBadge) {
    if (currentSearch) {
      countBadge.style.display = 'inline-block';
      countBadge.textContent = `${filteredCount} намерени`;
      countBadge.className = filteredCount > 0 ? 'search-badge' : 'search-badge badge-empty';
    } else {
      countBadge.style.display = 'none';
    }
  }
}

function renderAllViews() {
  const filtered = getFilteredSymbols();
  renderTable(filtered);
  renderCards(filtered);
  applyViewMode();
  updateSearchControls(filtered.length);
  updateSystemHealthBadge();
}

function renderTable(filteredSymbols) {
  const tbody = document.getElementById('assetsTableBody');
  const filtered = filteredSymbols || getFilteredSymbols();

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9" style="padding: 0;">${getZeroStateHtml()}</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map(item => {
    const tfCode = getTvInterval(item.timeframe);
    const tvSym = getTvSymbol(item, item.ticker, item.asset_class);
    const tvUrl = `https://www.tradingview.com/chart/?symbol=${tvSym}&interval=${tfCode}`;
    const tvRatioUrl = item.tv_ratio_url || getTvRatioLink(item, item.ticker, item.asset_class, item.timeframe);
    const tvRatioSym = item.tv_ratio_symbol || getTvRatioSymbol(item, item.ticker, item.asset_class);
    const hasBtcRatio = (item.asset_class === 'crypto' || item.asset_class === 'crypto_stocks') && !item.ticker.startsWith('BTC');

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
            ${renderGoldFlipBadge(item)}
            ${renderBtcBadge(item.btc_relative)}
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
            ${hasBtcRatio ? `
            <a href="${tvRatioUrl}" target="_blank" rel="noopener" class="tv-link-btn tv-btc-link" style="background: rgba(247, 147, 26, 0.15); border-color: #f7931a; color: #f7931a;" onclick="event.stopPropagation()" title="Отвори ${tvRatioSym} в TradingView">
              🪙 /BTC ↗
            </a>` : ''}
          </div>
        </td>
      </tr>
    `;
  }).join('');
  updateActiveRowHighlight();
}

function renderCards(filteredSymbols) {
  const container = document.getElementById('cardsGrid');
  const filtered = filteredSymbols || getFilteredSymbols();

  if (filtered.length === 0) {
    container.innerHTML = `<div style="grid-column: 1/-1;">${getZeroStateHtml()}</div>`;
    return;
  }

  container.innerHTML = filtered.map(item => {
    const tfCode = getTvInterval(item.timeframe);
    const tvSym = getTvSymbol(item, item.ticker, item.asset_class);
    const tvUrl = `https://www.tradingview.com/chart/?symbol=${tvSym}&interval=${tfCode}`;
    const tvRatioUrl = item.tv_ratio_url || getTvRatioLink(item, item.ticker, item.asset_class, item.timeframe);
    const tvRatioSym = item.tv_ratio_symbol || getTvRatioSymbol(item, item.ticker, item.asset_class);
    const hasBtcRatio = (item.asset_class === 'crypto' || item.asset_class === 'crypto_stocks') && !item.ticker.startsWith('BTC');
    
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
            ${renderGoldFlipBadge(item)}
            ${renderBtcBadge(item.btc_relative)}
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
            ${hasBtcRatio ? `
            <a href="${tvRatioUrl}" target="_blank" rel="noopener" class="card-chart-btn" style="background: rgba(247, 147, 26, 0.15); border-color: #f7931a; color: #f7931a;" onclick="event.stopPropagation()" title="Отвори ${tvRatioSym} в TradingView">/BTC ↗</a>` : ''}
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

function renderLightweightChart(container, candles, item, height = 480, isRatio = false) {
  container.innerHTML = '';
  if (isRatio && item) {
    const banner = document.createElement('div');
    banner.className = 'ratio-indicator-banner';
    banner.innerHTML = `<span>₿ Графика на съотношението спрямо Bitcoin: <b>${item.ticker} / BTC</b> (Larsson Ribbon панделката следи дали активът бие BTC)</span>`;
    container.appendChild(banner);
  }

  const chartHeight = Math.max(340, (container.clientHeight || height) - (isRatio ? 38 : 0));
  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth || 1000,
    height: chartHeight,
    layout: {
      background: { color: '#0b0e14' },
      textColor: '#94a3b8',
      fontSize: 12,
      fontFamily: "'JetBrains Mono', monospace",
    },
    localization: {
      priceFormatter: p => isRatio 
        ? `${p.toFixed(p < 0.0001 ? 8 : (p < 0.01 ? 6 : 5))} ₿` 
        : `$${p >= 1000 ? p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : p.toFixed(p >= 1 ? 2 : 4)}`,
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

  const s1Val = sr.s1 ? sr.s1.core : (!isRatio && item ? item.s1 : null);
  const r1Val = sr.r1 ? sr.r1.core : (!isRatio && item ? item.r1 : null);

  const s1Dist = s1Val ? Math.abs(((lastPrice - s1Val) / lastPrice) * 100).toFixed(1) : null;
  const r1Dist = r1Val ? Math.abs(((r1Val - lastPrice) / lastPrice) * 100).toFixed(1) : null;

  if (s1Val) {
    candleSeries.createPriceLine({
      price: s1Val,
      color: '#10b981',
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: isRatio ? `🟢 S1 Ratio` : `🟢 S1 (${s1Dist ? '-' + s1Dist + '%' : ''})`,
    });
  }

  if (r1Val) {
    candleSeries.createPriceLine({
      price: r1Val,
      color: '#ef4444',
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: isRatio ? `🔴 R1 Ratio` : `🔴 R1 (${r1Dist ? '+' + r1Dist + '%' : ''})`,
    });
  }

  // 4. Trade Setup Lines (USD mode only)
  const ts = (!isRatio && item) ? item.trade_suggestion : null;
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

  // 5. DCF Fair Value Line (USD mode only)
  if (!isRatio && item && item.fundamental && item.fundamental.fair_value) {
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

async function loadChart(container, ticker, timeframe, assetClass, height = 500, ratioMode = 'USD') {
  const item = allSymbols.find(s => s.ticker === ticker && s.timeframe === timeframe) || 
               allSymbols.find(s => s.ticker === ticker) || {};
  const isCrypto = assetClass === 'crypto' || (ticker && ticker.endsWith('USDT'));
  const isCryptoStock = assetClass === 'crypto_stocks';
  const isBtcSelf = ticker === 'BTCUSDT' || ticker === 'BTC-USD' || ticker === 'BTC';

  let chartInstance = null;
  let candles = [];

  if (ratioMode === 'BTC' && !isBtcSelf) {
    if (isCrypto && window.LightweightCharts) {
      const cleanBase = ticker.endsWith('USDT') ? ticker.slice(0, -4) : ticker;
      const btcPair = `${cleanBase}BTC`;
      const binanceInterval = (timeframe || '1D').toLowerCase();
      try {
        const url = `https://api.binance.com/api/v3/klines?symbol=${btcPair}&interval=${binanceInterval}&limit=180`;
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
        console.warn(`Binance ${btcPair} fetch failed:`, e);
      }

      if (candles.length > 30) {
        chartInstance = renderLightweightChart(container, candles, item, height, true);
        return chartInstance;
      } else {
        const ratioSym = getTvRatioSymbol(item, ticker, assetClass);
        renderTradingViewIframe(container, ratioSym, timeframe);
        return null;
      }
    } else if (isCryptoStock || assetClass === 'crypto') {
      const ratioSym = getTvRatioSymbol(item, ticker, assetClass);
      renderTradingViewIframe(container, ratioSym, timeframe);
      return null;
    }
  }

  // Standard USD Mode:
  const tvSym = getTvSymbol(item, ticker, assetClass);
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
    chartInstance = renderLightweightChart(container, candles, item, height, false);
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
  const tvBtcLinkEl = document.getElementById('liveTvBtcLink');
  const isEligibleRatio = (assetClass === 'crypto' || assetClass === 'crypto_stocks') && !ticker.startsWith('BTC');
  const tvRatioUrl = item.tv_ratio_url || getTvRatioLink(item, ticker, assetClass, timeframe);
  const tvRatioSym = item.tv_ratio_symbol || getTvRatioSymbol(item, ticker, assetClass);
  const tvUsdUrl = `https://www.tradingview.com/chart/?symbol=${tvSym}&interval=${tvInterval}`;

  if (tvLinkEl) {
    if (liveRatioMode === 'BTC' && isEligibleRatio) {
      tvLinkEl.href = tvRatioUrl;
      tvLinkEl.title = `Отвори ${tvRatioSym} в TradingView`;
      tvLinkEl.innerHTML = `🪙 TV /BTC ↗`;
    } else {
      tvLinkEl.href = tvUsdUrl;
      tvLinkEl.title = `Отвори ${tvSym} в TradingView`;
      tvLinkEl.innerHTML = `TV ↗`;
    }
  }

  if (tvBtcLinkEl) {
    if (isEligibleRatio) {
      tvBtcLinkEl.style.display = 'inline-block';
      tvBtcLinkEl.href = tvRatioUrl;
      tvBtcLinkEl.title = `Отвори ${tvRatioSym} в TradingView`;
    } else {
      tvBtcLinkEl.style.display = 'none';
    }
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

  // 4. BTC Relative HUD Column & Ratio Switcher in Live Chart
  const btcCol = document.getElementById('liveHudBtc');
  const btcBadge = document.getElementById('liveBtcBadge');
  const btcAlpha = document.getElementById('liveBtcAlpha');
  const ratioGroup = document.getElementById('liveRatioGroup');

  const isEligibleRatio = (assetClass === 'crypto' || assetClass === 'crypto_stocks') && !ticker.startsWith('BTC');

  if (ratioGroup) {
    ratioGroup.style.display = isEligibleRatio ? 'inline-flex' : 'none';
    ratioGroup.querySelectorAll('.live-ratio-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.ratio === liveRatioMode);
    });
  }

  const btcRel = item.btc_relative || (ts && ts.btc_relative);
  if (btcRel && btcCol && btcBadge && btcAlpha) {
    btcCol.style.display = 'flex';
    btcBadge.textContent = btcRel.badge_bg;
    const a30 = btcRel.alpha_30d_pct || 0;
    const sign = a30 > 0 ? '+' : '';
    btcAlpha.textContent = `Alpha: ${sign}${a30.toFixed(1)}% (${btcRel.ratio_state})`;
    btcBadge.title = btcRel.thesis_bg || '';
  } else if (btcCol) {
    btcCol.style.display = 'none';
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
    liveActiveChart = await loadChart(container, liveTicker, liveTf, liveClass, h, liveRatioMode);
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
  const isEligibleRatio = (assetClass === 'crypto' || assetClass === 'crypto_stocks') && !ticker.startsWith('BTC');
  const tvRatioUrl = item.tv_ratio_url || getTvRatioLink(item, ticker, assetClass, activeTf);
  const tvRatioSym = item.tv_ratio_symbol || getTvRatioSymbol(item, ticker, assetClass);
  const tvUsdUrl = `https://www.tradingview.com/chart/?symbol=${tvSym}&interval=${tvInterval}`;

  const modalTvBtn = document.getElementById('modalTvBtn');
  if (modalTvBtn) {
    if (modalRatioMode === 'BTC' && isEligibleRatio) {
      modalTvBtn.href = tvRatioUrl;
      modalTvBtn.title = `Отвори ${tvRatioSym} в TradingView`;
      modalTvBtn.innerHTML = `🪙 TV /BTC ↗`;
    } else {
      modalTvBtn.href = tvUsdUrl;
      modalTvBtn.title = `Отвори ${tvSym} в TradingView`;
      modalTvBtn.innerHTML = `TV ↗`;
    }
  }

  const modalTvBtcBtn = document.getElementById('modalTvBtcBtn');
  if (modalTvBtcBtn) {
    if (isEligibleRatio) {
      modalTvBtcBtn.style.display = 'inline-block';
      modalTvBtcBtn.href = tvRatioUrl;
      modalTvBtcBtn.title = `Отвори ${tvRatioSym} в TradingView`;
    } else {
      modalTvBtcBtn.style.display = 'none';
    }
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
    activeChart = await loadChart(container, ticker, activeTf, assetClass, container.clientHeight || 480, modalRatioMode);
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

  // 3. ₿ Bitcoin Relative Strength HUD Card
  const btcHudCard = document.getElementById('modalBtcHudCard');
  const btcStateBadge = document.getElementById('modalBtcStateBadge');
  const btcActionEl = document.getElementById('modalBtcAction');
  const btcAlpha30El = document.getElementById('modalBtcAlpha30d');
  const btcAlpha7El = document.getElementById('modalBtcAlpha7d');
  const btcSpreadEl = document.getElementById('modalBtcSpread');
  const btcLevEl = document.getElementById('modalBtcLevStatus');
  const btcThesisEl = document.getElementById('modalBtcThesis');

  const btcRel = item.btc_relative || (ts && ts.btc_relative);
  if (btcHudCard) {
    if (btcRel) {
      btcHudCard.style.display = 'flex';
      if (btcStateBadge) {
        const rEmoji = btcRel.ratio_state === 'GOLD' ? '🟡' : (btcRel.ratio_state === 'BLUE' ? '🔵' : '⚪');
        btcStateBadge.textContent = `${rEmoji} ${btcRel.ratio_state} RATIO`;
        btcStateBadge.className = `badge ${btcRel.ratio_state === 'GOLD' ? 'badge-gold' : (btcRel.ratio_state === 'BLUE' ? 'badge-blue' : 'badge-neutral')}`;
      }
      if (btcActionEl) btcActionEl.textContent = `${btcRel.badge_bg} - ${btcRel.verdict || ''}`;
      if (btcAlpha30El) {
        const a30 = btcRel.alpha_30d_pct || 0;
        btcAlpha30El.textContent = `${a30 > 0 ? '+' : ''}${a30.toFixed(2)}%`;
        btcAlpha30El.style.color = a30 > 0 ? '#34d399' : '#f87171';
      }
      if (btcAlpha7El) {
        const a7 = btcRel.alpha_7d_pct || 0;
        btcAlpha7El.textContent = `${a7 > 0 ? '+' : ''}${a7.toFixed(2)}%`;
        btcAlpha7El.style.color = a7 > 0 ? '#34d399' : '#f87171';
      }
      if (btcSpreadEl) {
        const sp = btcRel.ratio_spread_pct || 0;
        btcSpreadEl.textContent = `${sp > 0 ? '+' : ''}${sp.toFixed(2)}%`;
      }
      if (btcLevEl) {
        btcLevEl.textContent = btcRel.leverage_allowed ? '🟢 Разрешен 2x-3x' : '🔴 1x Spot Only';
        btcLevEl.style.color = btcRel.leverage_allowed ? '#34d399' : '#f87171';
      }
      if (btcThesisEl) btcThesisEl.textContent = btcRel.thesis_bg || 'Анализ на относителната сила спрямо BTC.';
    } else {
      btcHudCard.style.display = 'none';
    }
  }

  // Modal Ratio Switcher Toggle Display
  const modalRatioGroup = document.getElementById('modalRatioGroup');
  const isEligibleRatio = (item.asset_class === 'crypto' || item.asset_class === 'crypto_stocks') && !item.ticker.startsWith('BTC');
  if (modalRatioGroup) {
    modalRatioGroup.style.display = isEligibleRatio ? 'inline-flex' : 'none';
    modalRatioGroup.querySelectorAll('.modal-ratio-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.ratio === modalRatioMode);
    });
  }

  // 4. Quantamental Synthesis Banner
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

  const matrixStrip = document.getElementById('modalLevMatrixStrip');
  if (matrixStrip) {
    const entryVal = s.entry || item.price || 0;
    const slVal = s.sl || (entryVal * 0.95);
    const recLev = (ts && ts.recommended_leverage) || 1;
    const maxLev = (ts && ts.max_leverage) || (item.asset_class === 'crypto' ? 3 : (['us_stocks', 'ai_stocks'].includes(item.asset_class) ? 2 : 1));
    const matrixData = (ts && ts.leverage_matrix && ts.leverage_matrix.length > 0)
      ? ts.leverage_matrix
      : [1, 2, 3].filter(l => l <= maxLev).map(l => {
          const isL = (ts && ts.direction === 'SHORT') ? false : true;
          const liq = l === 1 ? null : (isL ? entryVal * (1.0 - 1.0/l + 0.005) : entryVal * (1.0 + 1.0/l - 0.005));
          const distPct = liq ? (Math.abs(entryVal - liq) / entryVal * 100).toFixed(1) : null;
          return {
            leverage: l,
            label: l === 1 ? '1x Spot' : `${l}x Isolated`,
            margin_usd: 1000 / l,
            liquidation_price: liq,
            dist_to_liq_pct: distPct,
            sl_pct_margin: ((Math.abs(entryVal - slVal) / entryVal) * l * 100).toFixed(1)
          };
        });

    matrixStrip.innerHTML = matrixData.map(m => {
      const isRec = (m.leverage === recLev);
      const liqText = m.liquidation_price ? `$${formatShortPrice(m.liquidation_price)}` : '🛡️ Без Liq';
      const bufText = m.dist_to_liq_pct ? `${m.dist_to_liq_pct}% буфер` : 'Безопасно';
      return `
        <div class="modal-lev-card ${isRec ? 'recommended' : ''}">
          <div class="modal-lev-card-title">
            <span>${m.label || (m.leverage + 'x')}</span>
            ${isRec ? '<span style="color:var(--color-gold); font-size:0.7rem;">⭐ Препоръчан</span>' : ''}
          </div>
          <div><span style="color:var(--text-muted)">Маржин:</span> <strong>$${formatShortPrice(m.margin_usd)}</strong></div>
          <div><span style="color:var(--text-muted)">Ликвидация:</span> <strong style="color:${m.liquidation_price ? '#f87171' : '#34d399'}">${liqText}</strong></div>
          <div><span style="color:var(--text-muted)">Буфер:</span> <small>${bufText}</small></div>
        </div>
      `;
    }).join('');
  }

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

// Ratio Switcher in Modal (USD vs vs BTC)
document.querySelectorAll('#modalRatioGroup .modal-ratio-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    modalRatioMode = e.currentTarget.dataset.ratio;
    document.querySelectorAll('#modalRatioGroup .modal-ratio-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.ratio === modalRatioMode);
    });
    openChartModal(activeTicker, activeTf, activeClass);
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

// Ratio Switcher in Live Chart (USD vs vs BTC)
document.querySelectorAll('#liveRatioGroup .live-ratio-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    liveRatioMode = e.currentTarget.dataset.ratio;
    document.querySelectorAll('#liveRatioGroup .live-ratio-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.ratio === liveRatioMode);
    });
    selectLiveAsset(liveTicker, liveTf, liveClass);
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

let modalCalcEventsBound = false;

function bindModalCalcEvents() {
  if (modalCalcEventsBound) return;
  modalCalcEventsBound = true;

  document.querySelectorAll('#modalCalcLevGroup .modal-lev-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('#modalCalcLevGroup .modal-lev-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      currentModalLeverage = parseInt(e.target.dataset.lev, 10);
      recalculatePositionSize();
    });
  });

  const execPaperBtn = document.getElementById('btnModalExecPaper');
  if (execPaperBtn) {
    execPaperBtn.addEventListener('click', () => {
      if (!currentModalItem) return;
      const ts = currentModalItem.trade_suggestion || {};
      const entry = ts.entry || currentModalItem.price || 100;
      const sl = ts.sl || (entry * 0.95);
      const tp1 = ts.tp1 || (entry * 1.1);
      const direction = ts.direction || (ts.action === 'EXIT_PROTECT' ? 'SHORT' : 'LONG');
      const leverage = currentModalLeverage || 1;
      const accountSize = parseFloat(document.getElementById('calcAccountSize')?.value || 10000) || 10000;
      const riskPct = parseFloat(document.getElementById('calcRiskPct')?.value || 1.0) || 1.0;
      const riskUsd = accountSize * (riskPct / 100);
      const riskPerUnit = Math.abs(entry - sl);
      const units = riskPerUnit > 0 ? (riskUsd / riskPerUnit) : 1;
      const notional = units * entry;
      const margin = notional / leverage;
      const isLong = (direction === 'LONG');
      const liqPrice = leverage > 1 
        ? (isLong ? entry * (1.0 - 1.0/leverage + 0.005) : entry * (1.0 + 1.0/leverage - 0.005))
        : null;

      const newPos = {
        position_id: `paper_modal_${currentModalItem.ticker}_${Date.now()}`,
        symbol: currentModalItem.ticker,
        direction: direction,
        leverage: leverage,
        entry_price: entry,
        current_price: entry,
        units: units,
        position_size_usd: notional,
        margin_usd: margin,
        liquidation_price: liqPrice,
        current_value: notional,
        unrealized_pnl: 0.0,
        unrealized_pnl_pct: 0.0,
        stop_loss: sl,
        tp1: tp1,
        tp2: ts.tp2 || null,
        duration_days: 0,
        opened_at: new Date().toISOString(),
        tier: ts.tier || 'A',
        asset_class: currentModalItem.asset_class || 'crypto',
        portfolio_type: 'PAPER',
        broker_exchange: `Paper ${leverage}x Isolated`,
        notes: `Сделка от графиката (${leverage}x ${direction})`
      };

      if (!portfolioPaperData.positions) portfolioPaperData.positions = [];
      portfolioPaperData.positions.unshift(newPos);

      const curCash = (portfolioPaperData.summary && portfolioPaperData.summary.available_cash) || 10000;
      portfolioPaperData.summary.available_cash = Math.max(0, curCash - margin);
      localStorage.setItem('larsson_custom_paper_cash', portfolioPaperData.summary.available_cash.toString());

      try {
        const saved = JSON.parse(localStorage.getItem('larsson_custom_paper_positions') || '[]');
        saved.unshift(newPos);
        localStorage.setItem('larsson_custom_paper_positions', JSON.stringify(saved));
      } catch(err) {
        console.error(err);
      }

      closeChartModal();
      switchTab('portfolio');
      switchPortfolioMode('PAPER');
      alert(`🧪 Позицията ${currentModalItem.ticker} (${leverage}x ${direction}, маржин: $${margin.toFixed(2)}) бе отворена в симулатора!`);
    });
  }

  const execRealBtn = document.getElementById('btnModalExecReal');
  if (execRealBtn) {
    execRealBtn.addEventListener('click', () => {
      if (!currentModalItem) return;
      const ts = currentModalItem.trade_suggestion || {};
      const entry = ts.entry || currentModalItem.price || 100;
      const sl = ts.sl || (entry * 0.95);
      const tp1 = ts.tp1 || (entry * 1.1);
      const direction = ts.direction || (ts.action === 'EXIT_PROTECT' ? 'SHORT' : 'LONG');
      const leverage = currentModalLeverage || 1;
      const accountSize = parseFloat(document.getElementById('calcAccountSize')?.value || 10000) || 10000;
      const riskPct = parseFloat(document.getElementById('calcRiskPct')?.value || 1.0) || 1.0;
      const riskUsd = accountSize * (riskPct / 100);
      const riskPerUnit = Math.abs(entry - sl);
      const units = riskPerUnit > 0 ? (riskUsd / riskPerUnit) : 1;

      closeChartModal();
      switchTab('portfolio');
      switchPortfolioMode('REAL');
      const modal = document.getElementById('addRealModal');
      if (modal) {
        modal.style.display = 'flex';
        const t = document.getElementById('realTicker');
        const c = document.getElementById('realAssetClass');
        const e = document.getElementById('realEntryPrice');
        const u = document.getElementById('realUnits');
        const d = document.getElementById('realDirection');
        const l = document.getElementById('realLeverage');
        const s = document.getElementById('realSl');
        const p = document.getElementById('realTp1');
        if (t) t.value = currentModalItem.ticker;
        if (c && currentModalItem.asset_class) c.value = currentModalItem.asset_class;
        if (e) e.value = entry;
        if (u) u.value = units < 1 ? units.toFixed(4) : units.toFixed(2);
        if (d) d.value = direction;
        if (l) l.value = leverage.toString();
        if (s) s.value = sl;
        if (p) p.value = tp1;
      }
    });
  }
}

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

  // Set recommended leverage as initial selection if available
  const recLev = (ts && ts.recommended_leverage) || 1;
  currentModalLeverage = recLev;
  document.querySelectorAll('#modalCalcLevGroup .modal-lev-btn').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.dataset.lev, 10) === recLev);
  });

  bindModalCalcEvents();
  recalculatePositionSize();
}

function recalculatePositionSize() {
  if (!currentModalItem) return;
  const ts = currentModalItem.trade_suggestion;
  const price = currentModalItem.price || 1.0;
  const entry = (ts && ts.entry) || price;
  let sl = (ts && ts.sl);
  const tp1 = (ts && ts.tp1);
  const isLong = (ts && ts.direction === 'SHORT') ? false : true;

  if (!sl) {
    sl = isLong ? entry * 0.95 : entry * 1.05;
  }

  const accountSizeInput = document.getElementById('calcAccountSize');
  const riskPctInput = document.getElementById('calcRiskPct');
  if (!accountSizeInput || !riskPctInput) return;

  const accountSize = parseFloat(accountSizeInput.value) || 10000;
  const riskPct = parseFloat(riskPctInput.value) || 1.0;
  const leverage = currentModalLeverage || 1;

  const riskUsd = accountSize * (riskPct / 100);
  const riskPerUnit = Math.abs(entry - sl);

  if (riskPerUnit > 0 && entry > 0) {
    const units = riskUsd / riskPerUnit;
    const unitsFormatted = entry < 1 ? units.toFixed(4) : (entry < 50 ? units.toFixed(2) : (entry < 1000 ? units.toFixed(1) : units.toFixed(3)));
    const notional = units * entry;
    const marginUsd = notional / leverage;
    const tp1Profit = tp1 ? (units * 0.5 * Math.abs(tp1 - entry)) : null;
    const liqPrice = leverage > 1 
      ? (isLong ? entry * (1.0 - (1.0 / leverage) + 0.005) : entry * (1.0 + (1.0 / leverage) - 0.005))
      : null;

    const unitsEl = document.getElementById('calcUnits');
    const posValEl = document.getElementById('calcPosValue');
    const marginEl = document.getElementById('calcMarginUsd');
    const liqEl = document.getElementById('calcLiqPrice');
    const riskUsdEl = document.getElementById('calcRiskUsd');
    const tp1UsdEl = document.getElementById('calcTp1Usd');

    if (unitsEl) unitsEl.textContent = `${unitsFormatted} ${currentModalItem.asset_class === 'crypto' ? 'tokens' : 'shares'}`;
    if (posValEl) posValEl.textContent = `$${notional.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (marginEl) marginEl.textContent = `$${marginUsd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (liqEl) liqEl.textContent = liqPrice ? `$${formatShortPrice(liqPrice)}` : '— (Няма)';
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

function resetAllFilters() {
  currentClass = 'ALL';
  currentTfFilter = 'ALL';
  currentTechFilter = 'ALL';
  currentFundFilter = 'ALL';
  currentSetupFilter = 'ALL';
  currentSearch = '';

  document.querySelectorAll('#classFilters .filter-btn').forEach(b => b.classList.toggle('active', b.dataset.class === 'ALL'));
  document.querySelectorAll('#tfFilters .filter-btn').forEach(b => b.classList.toggle('active', b.dataset.tf === 'ALL'));
  document.querySelectorAll('#techFilters .filter-btn').forEach(b => b.classList.toggle('active', b.dataset.tech === 'ALL'));
  document.querySelectorAll('#fundFilters .filter-btn').forEach(b => b.classList.toggle('active', b.dataset.fund === 'ALL'));
  document.querySelectorAll('#setupFilters .filter-btn').forEach(b => b.classList.toggle('active', b.dataset.setup === 'ALL'));

  const input = document.getElementById('searchInput');
  if (input) input.value = '';
  const clearBtn = document.getElementById('searchClearBtn');
  if (clearBtn) clearBtn.style.display = 'none';
  const countBadge = document.getElementById('searchCountBadge');
  if (countBadge) countBadge.style.display = 'none';

  renderOverview(window.lastLoadedDashboardData || { symbols: allSymbols });
  renderAllViews();
  updateSystemHealthBadge();
  updateDiagnosticsModalUI();
}
window.resetAllFilters = resetAllFilters;
window.resetFiltersToAll = resetAllFilters;

window.clearSearch = function() {
  currentSearch = '';
  const input = document.getElementById('searchInput');
  if (input) {
    input.value = '';
    input.focus();
  }
  renderAllViews();
  if (pendingProposals && pendingProposals.length > 0) {
    renderProposalsBanner(pendingProposals);
  }
};

window.clearQueueSearch = function() {
  currentQueueSearch = '';
  const input = document.getElementById('queueSearchInput');
  if (input) {
    input.value = '';
    input.focus();
  }
  renderQueueView();
};

const searchInputElem = document.getElementById('searchInput');
if (searchInputElem) {
  searchInputElem.addEventListener('input', (e) => {
    const val = e.target.value;
    const trimmed = val.trim();
    // If user starts a search and had specific filters active, broaden to ALL so search isn't blocked
    if (trimmed && !currentSearch && (currentClass !== 'ALL' || currentTfFilter !== 'ALL' || currentTechFilter !== 'ALL' || currentFundFilter !== 'ALL' || currentSetupFilter !== 'ALL')) {
      resetFiltersToAll();
    }
    currentSearch = trimmed;
    renderAllViews();
    if (pendingProposals && pendingProposals.length > 0) {
      renderProposalsBanner(pendingProposals);
    }
  });

  searchInputElem.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      clearSearch();
      searchInputElem.blur();
    }
  });
}

const searchClearBtnElem = document.getElementById('searchClearBtn');
if (searchClearBtnElem) {
  searchClearBtnElem.addEventListener('click', () => {
    clearSearch();
  });
}

// Global hotkey: '/' to focus search, 'Escape' to blur/clear
document.addEventListener('keydown', (e) => {
  if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
    e.preventDefault();
    const input = document.getElementById('searchInput');
    if (input) {
      input.focus();
      input.select();
    }
  }
});

const queueInputElem = document.getElementById('queueSearchInput');
if (queueInputElem) {
  queueInputElem.addEventListener('input', (e) => {
    currentQueueSearch = e.target.value.trim();
    renderQueueView();
  });
  queueInputElem.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      clearQueueSearch();
      queueInputElem.blur();
    }
  });
}

const queueClearBtnElem = document.getElementById('queueSearchClearBtn');
if (queueClearBtnElem) {
  queueClearBtnElem.addEventListener('click', () => {
    clearQueueSearch();
  });
}

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
// MASTER TAB NAVIGATION, BROWSER HISTORY & BACK NAVIGATION
// =============================================================================

let tabHistory = ['scanner'];
let isNavigatingHistory = false;

function switchTab(tabName, pushToHistory = true) {
  if (pushToHistory && !isNavigatingHistory) {
    if (tabHistory[tabHistory.length - 1] !== tabName) {
      tabHistory.push(tabName);
    }
    try {
      history.pushState({ tab: tabName }, '', '#' + tabName);
    } catch(e) {}
  }

  const prevTab = currentTab;
  currentTab = tabName;
  localStorage.setItem('larsson_active_tab', tabName);

  document.querySelectorAll('#mainNavTabs .nav-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });

  const tabMap = {
    'scanner': 'tabContentScanner',
    'queue': 'tabContentQueue',
    'portfolio': 'tabContentPortfolio',
    'calculator': 'tabContentCalculator',
    'fundamentals': 'tabContentFundamentals'
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

  updateNavBackButtons(prevTab);

  if (tabName === 'fundamentals') {
    if (currentFundTicker) {
      renderFundamentalDossier(currentFundTicker);
    }
  }

  if (tabName === 'scanner' && liveActiveChart) {
    const liveContainer = document.getElementById('liveChartCanvas');
    if (liveContainer && liveContainer.clientWidth) {
      liveActiveChart.applyOptions({ width: liveContainer.clientWidth });
    }
  }
}

function updateNavBackButtons(fromTab) {
  const names = {
    'scanner': '(към Скенера)',
    'queue': '(към Очаквани Сделки)',
    'portfolio': '(към Портфолиото)',
    'calculator': '(към Калкулатора)',
    'fundamentals': '(към Фундамент)'
  };
  const calcTarget = document.getElementById('calcBackTargetText');
  if (calcTarget) {
    calcTarget.textContent = names[fromTab] || '(към Скенера)';
  }
  const fundTarget = document.getElementById('fundBackTargetText');
  if (fundTarget) {
    fundTarget.textContent = names[fromTab] || '(към Скенера)';
  }
}

function navigateBack() {
  const chartModal = document.getElementById('chartModal');
  if (chartModal && chartModal.style.display !== 'none') {
    closeChartModal();
    return;
  }

  if (tabHistory.length > 1) {
    tabHistory.pop(); // Remove current
    const previous = tabHistory[tabHistory.length - 1] || 'scanner';
    isNavigatingHistory = true;
    switchTab(previous, false);
    isNavigatingHistory = false;
    try {
      history.replaceState({ tab: previous }, '', '#' + previous);
    } catch(e) {}
  } else {
    isNavigatingHistory = true;
    switchTab('scanner', false);
    isNavigatingHistory = false;
  }
}

// Global Browser Back/Forward Popstate listener
window.addEventListener('popstate', (e) => {
  const chartModal = document.getElementById('chartModal');
  if (chartModal && chartModal.style.display !== 'none') {
    closeChartModal();
    return;
  }

  if (e.state && e.state.tab) {
    isNavigatingHistory = true;
    switchTab(e.state.tab, false);
    isNavigatingHistory = false;
  } else if (location.hash) {
    const hashTab = location.hash.replace('#', '').split('?')[0];
    if (['scanner', 'queue', 'portfolio', 'calculator', 'fundamentals'].includes(hashTab)) {
      isNavigatingHistory = true;
      switchTab(hashTab, false);
      isNavigatingHistory = false;
    }
  } else {
    isNavigatingHistory = true;
    switchTab('scanner', false);
    isNavigatingHistory = false;
  }
});

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

  const qClear = document.getElementById('queueSearchClearBtn');
  const qBadge = document.getElementById('queueSearchCountBadge');
  if (qClear) qClear.style.display = currentQueueSearch ? 'flex' : 'none';

  let filtered = pendingSetups.filter(s => {
    const matchesPrio = (currentQueuePriority === 'ALL') || (s.priority === currentQueuePriority);
    const matchesTier = (currentQueueTier === 'ALL') || (s.tier === currentQueueTier);
    let matchesSearch = true;
    if (currentQueueSearch) {
      const q = currentQueueSearch.toLowerCase().trim();
      const normQ = normalizeSearchStr(q);
      const sym = (s.symbol || '').toLowerCase();
      const normSym = normalizeSearchStr(s.symbol || '');
      const setupType = (s.setup_type || '').toLowerCase();
      matchesSearch = sym.includes(q) || normSym.includes(normQ) || setupType.includes(q);
    }
    return matchesPrio && matchesTier && matchesSearch;
  });

  if (qBadge) {
    if (currentQueueSearch) {
      qBadge.style.display = 'inline-block';
      qBadge.textContent = `${filtered.length} намерени`;
      qBadge.className = filtered.length > 0 ? 'search-badge' : 'search-badge badge-empty';
    } else {
      qBadge.style.display = 'none';
    }
  }

  if (filtered.length === 0) {
    const emptyMsg = currentQueueSearch
      ? `<h3>🔍 Няма намерени очаквани сделки за "<strong>${escapeHtml(currentQueueSearch)}</strong>"</h3><p style="margin-top: 8px;"><button type="button" class="btn-clear-search" onclick="clearQueueSearch()">✕ Изчисти търсенето</button></p>`
      : `<h3>⏳ Няма намерени очаквани сделки по тези критерии</h3><p style="margin-top: 8px;">Системата следи непрекъснато пазара за Imminent Gold, Dip Buy, S/R приближаване и Дивергенции.</p>`;
    container.innerHTML = `
      <div style="grid-column: 1/-1; padding: 40px; text-align: center; color: var(--text-muted); background: var(--bg-card); border-radius: var(--radius-md); border: 1px dashed var(--border-color);">
        ${emptyMsg}
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

function syncLocalPaperStorage() {
  try {
    const localPositions = JSON.parse(localStorage.getItem('larsson_custom_paper_positions') || '[]');
    const localCash = localStorage.getItem('larsson_custom_paper_cash');
    const localClosed = JSON.parse(localStorage.getItem('larsson_custom_paper_closed') || '[]');

    if (!portfolioPaperData.positions) portfolioPaperData.positions = [];
    if (!portfolioPaperData.journal) portfolioPaperData.journal = [];
    if (!portfolioPaperData.summary) portfolioPaperData.summary = {};

    const existingIds = new Set(portfolioPaperData.positions.map(p => p.position_id || p.id || p.symbol));
    localPositions.forEach(p => {
      const id = p.position_id || p.id || p.symbol;
      if (!existingIds.has(id)) {
        portfolioPaperData.positions.push(p);
        existingIds.add(id);
      }
    });

    const existingJournals = new Set(portfolioPaperData.journal.map(j => (j.position_id || '') + (j.created_at || '')));
    localClosed.forEach(c => {
      const key = (c.position_id || '') + (c.created_at || '');
      if (!existingJournals.has(key)) {
        portfolioPaperData.journal.unshift(c);
        existingJournals.add(key);
      }
    });

    if (localCash !== null && localCash !== undefined) {
      const cashVal = parseFloat(localCash);
      if (!isNaN(cashVal)) {
        portfolioPaperData.summary.available_cash = cashVal;
      }
    }
  } catch(e) {
    console.warn('Error reading local paper portfolio storage:', e);
  }
}

function closePaperPosition(posId, ticker, currentPrice, units) {
  if (!confirm(`Сигурни ли сте, че искате да затворите симулираната позиция ${ticker} на цена $${formatShortPrice(currentPrice)}?`)) {
    return;
  }
  const idx = (portfolioPaperData.positions || []).findIndex(p => (p.position_id || p.id) === posId);
  if (idx === -1) return;

  const target = portfolioPaperData.positions[idx];
  const entry = target.entry_price || currentPrice;
  const isShort = target.direction === 'SHORT';
  const grossPnl = isShort ? (entry - currentPrice) * units : (currentPrice - entry) * units;
  const netPnl = grossPnl;
  const lev = target.leverage || 1;
  const margin = target.margin_usd || ((entry * units) / lev);
  const pnlPct = margin > 0 ? (netPnl / margin * 100) : 0;
  const nowIso = new Date().toISOString();

  // Return margin + netPnl to cash
  const curCash = (portfolioPaperData.summary && portfolioPaperData.summary.available_cash) || 10000;
  portfolioPaperData.summary.available_cash = curCash + margin + netPnl;
  localStorage.setItem('larsson_custom_paper_cash', portfolioPaperData.summary.available_cash.toString());

  if (!portfolioPaperData.summary) portfolioPaperData.summary = {};
  portfolioPaperData.summary.total_realized_pnl = (portfolioPaperData.summary.total_realized_pnl || 0) + netPnl;
  if (netPnl > 0) {
    portfolioPaperData.summary.wins = (portfolioPaperData.summary.wins || 0) + 1;
  } else {
    portfolioPaperData.summary.losses = (portfolioPaperData.summary.losses || 0) + 1;
  }

  const journalItem = {
    position_id: posId,
    ticker: ticker,
    action: isShort ? 'COVER' : 'CLOSE',
    entry_price: entry,
    exit_price: currentPrice,
    price: currentPrice,
    units: units,
    pnl_usd: netPnl,
    pnl_pct: pnlPct,
    broker_exchange: target.broker_exchange || 'Paper Engine',
    reason: `Затваряне на ${lev}x ${target.direction || 'LONG'} тестова позиция`,
    created_at: nowIso,
    hold_duration_days: target.duration_days || 0,
    portfolio_type: 'PAPER'
  };

  if (!portfolioPaperData.journal) portfolioPaperData.journal = [];
  portfolioPaperData.journal.unshift(journalItem);

  portfolioPaperData.positions.splice(idx, 1);

  try {
    let saved = JSON.parse(localStorage.getItem('larsson_custom_paper_positions') || '[]');
    saved = saved.filter(p => (p.position_id || p.id) !== posId);
    localStorage.setItem('larsson_custom_paper_positions', JSON.stringify(saved));

    const savedClosed = JSON.parse(localStorage.getItem('larsson_custom_paper_closed') || '[]');
    savedClosed.unshift(journalItem);
    localStorage.setItem('larsson_custom_paper_closed', JSON.stringify(savedClosed));
  } catch(err) {
    console.error('Storage error:', err);
  }

  renderPortfolioView();
}

// =============================================================================
// ACTIVE LEVERAGE PROPOSALS BANNER CONTROLLER
// =============================================================================

function renderProposalsBanner(proposals) {
  const banner = document.getElementById('proposalsBannerSection');
  const grid = document.getElementById('proposalsCardsGrid');
  const countBadge = document.getElementById('proposalsCountBadge') || document.getElementById('proposalsCount');
  if (!banner || !grid) return;

  const resolved = JSON.parse(localStorage.getItem('larsson_resolved_proposals') || '{}');
  let activeProposals = (proposals || []).filter(p => !resolved[p.proposal_id]);
  const rejectedCount = Object.values(resolved).filter(v => v.status === 'REJECTED').length;

  updateProposalUndoUI();
  applyProposalsVisibility(isProposalsCollapsed);

  if (activeProposals.length === 0) {
    banner.style.display = 'block';
    if (countBadge) countBadge.textContent = '0 Чакащи';
    grid.innerHTML = `
      <div class="proposal-empty-card" style="grid-column: 1/-1; text-align: center; padding: 32px 20px; background: rgba(15, 23, 42, 0.55); border: 1px dashed rgba(245, 158, 11, 0.4); border-radius: 12px;">
        <div style="font-size: 2.2rem; margin-bottom: 8px;">⚡</div>
        <h3 style="font-size: 1.1rem; color: #f1f5f9; margin-bottom: 6px;">Няма активни търговски предложения в момента</h3>
        <p style="font-size: 0.875rem; color: var(--text-muted); max-width: 580px; margin: 0 auto 16px auto; line-height: 1.5;">
          Системата следи непрекъснато пазара за пресни сигнали от <b>Larsson Gold Flip</b>, <b>Quantamental Alpha</b> и <b>BTC Relative Strength</b>. Натиснете бутона по-долу, за да стартирате нов анализ за предложения (1x Spot, 2x или 3x левъридж).
        </p>
        <div style="display: flex; gap: 10px; justify-content: center; align-items: center; flex-wrap: wrap;">
          <button class="btn btn-action-analyze" onclick="runNewTradeAnalysis()" style="display: inline-flex; align-items: center; gap: 8px; cursor: pointer;">
            <span class="analyze-icon">⚡</span> Стартирай Анализ за Нови Сделки
          </button>
          ${rejectedCount > 0 ? `
            <button class="btn btn-secondary" onclick="restoreAllRejectedProposals()" style="display: inline-flex; align-items: center; gap: 6px; cursor: pointer; padding: 7px 14px; font-weight: 600;">
              <span>🔄</span> Върни отхвърлените сделки (${rejectedCount})
            </button>
          ` : ''}
        </div>
      </div>
    `;
    return;
  }

  if (currentSearch) {
    const qNorm = normalizeSearchStr(currentSearch);
    const q = currentSearch.toLowerCase().trim();
    const matching = activeProposals.filter(p => {
      const sym = (p.ticker || p.symbol || '').toLowerCase();
      const name = (p.name || '').toLowerCase();
      return sym.includes(q) || normalizeSearchStr(sym).includes(qNorm) || name.includes(q);
    });
    if (matching.length > 0) {
      activeProposals = matching;
    } else {
      banner.style.display = 'block';
      if (countBadge) countBadge.textContent = '0 Намерени';
      grid.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; padding: 24px; color: var(--text-muted); background: rgba(15, 23, 42, 0.4); border-radius: 8px; border: 1px dashed var(--border-color);">
          Няма активни предложения, отговарящи на филтъра за търсене "<b>${escapeHtml(currentSearch)}</b>".
        </div>
      `;
      return;
    }
  }

  banner.style.display = 'block';
  if (countBadge) countBadge.textContent = `${activeProposals.length} Чакащи`;

  grid.innerHTML = activeProposals.map(p => {
    const isLong = (p.direction || 'LONG') === 'LONG';
    const dirBadgeClass = isLong ? 'proposal-dir-badge long' : 'proposal-dir-badge short';
    const dirText = isLong ? '🟢 LONG' : '🔴 SHORT';
    const recLev = p.recommended_leverage || 1;
    const maxLev = p.max_leverage || (p.asset_class === 'crypto' ? 3 : (['us_stocks', 'ai_stocks'].includes(p.asset_class) ? 2 : 1));

    const entry = p.entry_price || 0;
    const notional = p.position_size_usd || 1000;
    const matrixRows = [1, 2, 3].filter(lev => lev <= Math.max(recLev, maxLev)).map(lev => {
      const margin = notional / lev;
      const liq = lev === 1 ? null : (isLong ? entry * (1.0 - 1.0/lev + 0.005) : entry * (1.0 + 1.0/lev - 0.005));
      const distPct = liq ? (Math.abs(entry - liq) / entry * 100).toFixed(1) + '%' : '∞';
      const isRec = (lev === recLev);
      return `
        <tr style="${isRec ? 'background: rgba(245, 158, 11, 0.12); font-weight: 700;' : ''}">
          <td>${lev}x ${isRec ? '⭐' : ''}</td>
          <td>$${formatShortPrice(margin)}</td>
          <td>${liq ? '$' + formatShortPrice(liq) : '—'}</td>
          <td>${distPct}</td>
        </tr>
      `;
    }).join('');

    const s = allSymbols.find(x => x.ticker === p.ticker);
    const btcRel = p.btc_relative || (s && s.btc_relative);
    const btcBadgeHtml = renderBtcBadge(btcRel);
    const isBtcBleeding = btcRel && !btcRel.leverage_allowed;

    const actionBtns = `
      <button class="btn-approve-1x" onclick="approveProposal('${p.proposal_id}', 1)">
        ${isLong ? '🟢 Spot 1x' : '🟢 Hedge 1x'}
      </button>
      ${(!isBtcBleeding && maxLev >= 2) ? `
        <button class="btn-approve-2x" onclick="approveProposal('${p.proposal_id}', 2)">
          ⚡ ${isLong ? 'Long' : 'Short'} 2x
        </button>
      ` : ''}
      ${(!isBtcBleeding && maxLev >= 3) ? `
        <button class="btn-approve-3x" onclick="approveProposal('${p.proposal_id}', 3)">
          🚀 ${isLong ? 'Long' : 'Short'} 3x
        </button>
      ` : ''}
      <button type="button" class="btn-fund-action" onclick="openFundamentalTab('${p.ticker}', 'proposals')" title="Прегледай пълен фундаментален анализ и DCF оценка">
        🏢 Фундамент
      </button>
      <button class="btn-reject" onclick="rejectProposal('${p.proposal_id}')" title="Откажи предложението">
        ✕
      </button>
    `;

    return `
      <div class="proposal-card" id="propCard_${p.proposal_id}">
        <div class="proposal-card-header">
          <div class="proposal-asset-info" onclick="openFundamentalTab('${p.ticker}', 'proposals')" style="cursor: pointer;" title="Кликнете за пълен фундаментален анализ и DCF оценка">
            <span class="proposal-ticker">${p.ticker}</span>
            <span class="${dirBadgeClass}">${dirText}</span>
            <span class="asset-class-tag">${CLASS_LABELS[p.asset_class] || p.asset_class || 'Crypto'}</span>
            ${btcBadgeHtml}
          </div>
          <span class="setup-tier-badge">🏆 Tier ${p.tier || 'A'} (${p.score || 0}/100)</span>
        </div>

        ${isBtcBleeding ? `
          <div style="color: #f87171; font-size: 0.75rem; font-weight: 700; margin: 4px 0 8px 0; padding: 4px 8px; background: rgba(239, 68, 68, 0.12); border-radius: 4px; border: 1px solid rgba(239, 68, 68, 0.35);">
            ⚠️ ₿ Bleeding Alert: Активът губи от Bitcoin (${btcRel.alpha_30d_pct ? btcRel.alpha_30d_pct.toFixed(1) : '-'}%). Левъриджът е ограничен строго до 1x Spot.
          </div>
        ` : ''}

        <div class="proposal-metrics">
          <div class="metric-item">
            <span class="metric-lbl">Вход</span>
            <span class="metric-val">$${formatShortPrice(p.entry_price)}</span>
          </div>
          <div class="metric-item">
            <span class="metric-lbl">Stop-Loss</span>
            <span class="metric-val" style="color: #f87171;">$${formatShortPrice(p.stop_loss)}</span>
          </div>
          <div class="metric-item">
            <span class="metric-lbl">Take-Profit 1</span>
            <span class="metric-val" style="color: #34d399;">$${formatShortPrice(p.tp1)}</span>
          </div>
        </div>

        <div style="font-size: 0.75rem; color: var(--text-secondary); line-height: 1.4;">
          ${p.reason || 'Сигнал за вход по тренда.'}
        </div>

        <table class="proposal-matrix-mini">
          <thead>
            <tr>
              <th>Lev</th>
              <th>Маржин</th>
              <th>Ликвидация</th>
              <th>Буфер</th>
            </tr>
          </thead>
          <tbody>
            ${matrixRows}
          </tbody>
        </table>

        <div class="proposal-actions">
          ${actionBtns}
        </div>
      </div>
    `;
  }).join('');
}

function approveProposal(proposalId, leverage) {
  const p = (pendingProposals || []).find(x => x.proposal_id === proposalId);
  if (!p) return;

  const isLong = (p.direction || 'LONG') === 'LONG';
  const entry = p.entry_price || 0;
  const notional = p.position_size_usd || 1000;
  const margin = notional / leverage;
  const liqPrice = leverage > 1 ? (isLong ? entry * (1.0 - 1.0/leverage + 0.005) : entry * (1.0 + 1.0/leverage - 0.005)) : null;
  const units = p.units || (entry > 0 ? (notional / entry) : 1);

  const newPos = {
    position_id: `paper_prop_${p.ticker}_${Date.now()}`,
    symbol: p.ticker,
    direction: p.direction || 'LONG',
    leverage: leverage,
    entry_price: entry,
    current_price: entry,
    units: units,
    position_size_usd: notional,
    margin_usd: margin,
    liquidation_price: liqPrice,
    current_value: notional,
    unrealized_pnl: 0.0,
    unrealized_pnl_pct: 0.0,
    stop_loss: p.stop_loss,
    tp1: p.tp1,
    tp2: p.tp2,
    duration_days: 0,
    opened_at: new Date().toISOString(),
    tier: p.tier || 'A',
    asset_class: p.asset_class || 'crypto',
    portfolio_type: 'PAPER',
    broker_exchange: `Paper ${leverage}x Isolated`,
    notes: `Одобрено предложение ${p.proposal_id} (${leverage}x ${p.direction || 'LONG'})`
  };

  if (!portfolioPaperData.positions) portfolioPaperData.positions = [];
  portfolioPaperData.positions.unshift(newPos);

  const curCash = (portfolioPaperData.summary && portfolioPaperData.summary.available_cash) || 10000;
  portfolioPaperData.summary.available_cash = Math.max(0, curCash - margin);
  localStorage.setItem('larsson_custom_paper_cash', portfolioPaperData.summary.available_cash.toString());

  try {
    const saved = JSON.parse(localStorage.getItem('larsson_custom_paper_positions') || '[]');
    saved.unshift(newPos);
    localStorage.setItem('larsson_custom_paper_positions', JSON.stringify(saved));

    const resolved = JSON.parse(localStorage.getItem('larsson_resolved_proposals') || '{}');
    resolved[proposalId] = { status: 'APPROVED', leverage: leverage, at: new Date().toISOString() };
    localStorage.setItem('larsson_resolved_proposals', JSON.stringify(resolved));

    pushProposalUndoAction({
      type: 'APPROVE',
      proposalId: proposalId,
      positionId: newPos.position_id,
      proposal: p,
      leverage: leverage,
      margin: margin,
      timestamp: Date.now()
    });
  } catch(err) {
    console.error(err);
  }

  renderProposalsBanner(pendingProposals);
  renderPortfolioView();
  updateProposalUndoUI();
  showProposalApproveToast(p.ticker, leverage, margin, proposalId);
}

function rejectProposal(proposalId) {
  const p = (pendingProposals || []).find(x => x.proposal_id === proposalId);
  try {
    const resolved = JSON.parse(localStorage.getItem('larsson_resolved_proposals') || '{}');
    resolved[proposalId] = { status: 'REJECTED', at: new Date().toISOString() };
    localStorage.setItem('larsson_resolved_proposals', JSON.stringify(resolved));

    pushProposalUndoAction({
      type: 'REJECT',
      proposalId: proposalId,
      proposal: p,
      timestamp: Date.now()
    });
  } catch(err) {
    console.error(err);
  }
  renderProposalsBanner(pendingProposals);
  updateProposalUndoUI();
  showProposalUndoToast(p ? p.ticker : 'актива', proposalId);
}

// =============================================================================
// PROPOSAL UNDO & REVERT ACTIONS
// =============================================================================

let proposalUndoStack = [];

function pushProposalUndoAction(action) {
  proposalUndoStack.push(action);
  updateProposalUndoUI();
}

function showProposalUndoToast(ticker, proposalId) {
  const toast = document.getElementById('analysisToast');
  if (!toast) return;

  if (analysisToastTimeout) {
    clearTimeout(analysisToastTimeout);
    analysisToastTimeout = null;
  }

  toast.className = 'analysis-toast toast-undo';
  toast.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: space-between; width: 100%; gap: 14px;">
      <span class="toast-content" style="display: flex; align-items: center; gap: 8px;">
        <span>🗑️ Отхвърлено предложение: <b>${ticker}</b></span>
      </span>
      <div style="display: flex; align-items: center; gap: 8px;">
        <button type="button" class="btn-toast-undo" onclick="undoLastProposalAction()">
          ↩️ Върни назад
        </button>
        <span class="toast-close" onclick="this.closest('.analysis-toast').style.display='none'" style="cursor:pointer; opacity:0.7; font-size:1.1rem; padding: 0 4px;">✕</span>
      </div>
    </div>
  `;
  toast.style.display = 'flex';

  analysisToastTimeout = setTimeout(() => {
    toast.style.display = 'none';
    analysisToastTimeout = null;
  }, 8000);
}

function showProposalApproveToast(ticker, leverage, margin, proposalId) {
  const toast = document.getElementById('analysisToast');
  if (!toast) return;

  if (analysisToastTimeout) {
    clearTimeout(analysisToastTimeout);
    analysisToastTimeout = null;
  }

  toast.className = 'analysis-toast toast-undo';
  toast.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: space-between; width: 100%; gap: 14px;">
      <span class="toast-content" style="display: flex; align-items: center; gap: 8px;">
        <span>✅ Одобрено: <b>${ticker}</b> (${leverage}x). Маржин: $${margin.toFixed(2)}</span>
      </span>
      <div style="display: flex; align-items: center; gap: 8px;">
        <button type="button" class="btn-toast-undo" onclick="undoLastProposalAction()">
          ↩️ Върни назад
        </button>
        <span class="toast-close" onclick="this.closest('.analysis-toast').style.display='none'" style="cursor:pointer; opacity:0.7; font-size:1.1rem; padding: 0 4px;">✕</span>
      </div>
    </div>
  `;
  toast.style.display = 'flex';

  analysisToastTimeout = setTimeout(() => {
    toast.style.display = 'none';
    analysisToastTimeout = null;
  }, 8000);
}

function undoLastProposalAction() {
  let resolved = {};
  try {
    resolved = JSON.parse(localStorage.getItem('larsson_resolved_proposals') || '{}');
  } catch(e) { resolved = {}; }

  let targetAction = null;
  let targetId = null;

  if (proposalUndoStack.length > 0) {
    targetAction = proposalUndoStack.pop();
    targetId = targetAction.proposalId;
  } else {
    const keys = Object.keys(resolved);
    if (keys.length === 0) {
      showAnalysisToast('Няма предходни действия за връщане назад.', 'info', 3000);
      return;
    }
    targetId = keys[keys.length - 1];
  }

  if (targetId && resolved[targetId]) {
    delete resolved[targetId];
    localStorage.setItem('larsson_resolved_proposals', JSON.stringify(resolved));
  }

  if (targetAction && targetAction.type === 'APPROVE') {
    if (portfolioPaperData.positions) {
      portfolioPaperData.positions = portfolioPaperData.positions.filter(p => p.position_id !== targetAction.positionId);
    }
    try {
      const saved = JSON.parse(localStorage.getItem('larsson_custom_paper_positions') || '[]');
      const filtered = saved.filter(p => p.position_id !== targetAction.positionId);
      localStorage.setItem('larsson_custom_paper_positions', JSON.stringify(filtered));
    } catch(e) {}

    if (targetAction.margin && portfolioPaperData.summary) {
      const curCash = portfolioPaperData.summary.available_cash || 10000;
      portfolioPaperData.summary.available_cash = curCash + targetAction.margin;
      localStorage.setItem('larsson_custom_paper_cash', portfolioPaperData.summary.available_cash.toString());
    }
    renderPortfolioView();
  }

  renderProposalsBanner(pendingProposals);
  updateProposalUndoUI();

  const sym = (targetAction && targetAction.proposal && targetAction.proposal.ticker) ? targetAction.proposal.ticker : (targetId ? targetId.replace('prop_', '') : '');
  showAnalysisToast(`↩️ Върнато назад: Предложението за <b>${sym}</b> бе успешно възстановено в списъка!`, 'success', 4000);
}

function restoreAllRejectedProposals() {
  try {
    const resolved = JSON.parse(localStorage.getItem('larsson_resolved_proposals') || '{}');
    let restoredCount = 0;
    Object.keys(resolved).forEach(k => {
      if (resolved[k].status === 'REJECTED') {
        delete resolved[k];
        restoredCount++;
      }
    });
    localStorage.setItem('larsson_resolved_proposals', JSON.stringify(resolved));
    proposalUndoStack = [];
    updateProposalUndoUI();
    renderProposalsBanner(pendingProposals);
    showAnalysisToast(`✅ Всички ${restoredCount} отхвърлени предложения бяха възстановени в списъка!`, 'success', 4500);
  } catch(e) {
    console.error(e);
  }
}

function updateProposalUndoUI() {
  const btnUndo = document.getElementById('btnUndoProposal');
  const btnRestore = document.getElementById('btnRestoreRejected');
  const undoCountEl = document.getElementById('undoCount');

  let resolved = {};
  try {
    resolved = JSON.parse(localStorage.getItem('larsson_resolved_proposals') || '{}');
  } catch(e) { resolved = {}; }

  const rejectedCount = Object.values(resolved).filter(v => v.status === 'REJECTED').length;
  const totalResolved = Object.keys(resolved).length;
  const stackCount = proposalUndoStack.length;

  const canUndo = stackCount > 0 || totalResolved > 0;

  if (btnUndo) {
    btnUndo.style.display = canUndo ? 'inline-flex' : 'none';
    if (undoCountEl) {
      undoCountEl.textContent = (stackCount > 0 ? stackCount : totalResolved).toString();
    }
  }

  if (btnRestore) {
    btnRestore.style.display = rejectedCount > 0 ? 'inline-flex' : 'none';
  }
}

// =============================================================================
// ON-DEMAND MARKET ANALYSIS & TRADE PROPOSALS CONTROLLER
// =============================================================================

let analysisToastTimeout = null;

function showAnalysisToast(message, type = 'info', duration = 4500) {
  const toast = document.getElementById('analysisToast');
  if (!toast) return;

  if (analysisToastTimeout) {
    clearTimeout(analysisToastTimeout);
    analysisToastTimeout = null;
  }

  toast.className = `analysis-toast toast-${type}`;
  const icon = type === 'loading' ? '<span class="analyze-icon spinning" style="font-size: 1.1rem; margin-right: 6px;">⚡</span>' : '';
  const closeBtn = type !== 'loading' ? '<span class="toast-close" onclick="this.parentElement.style.display=\'none\'" style="cursor:pointer; margin-left:14px; opacity:0.8; font-weight:bold; font-size:1.1rem;">✕</span>' : '';
  
  toast.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
      <span class="toast-content" style="display: flex; align-items: center;">${icon}${message}</span>
      ${closeBtn}
    </div>
  `;
  toast.style.display = 'flex';

  if (duration > 0) {
    analysisToastTimeout = setTimeout(() => {
      toast.style.display = 'none';
      analysisToastTimeout = null;
    }, duration);
  }
}

function synthesizeClientProposals() {
  if (!allSymbols || allSymbols.length === 0) return 0;

  // Filter high-conviction bullish candidates
  const candidates = allSymbols.filter(s => {
    if (!s.price || s.price <= 0) return false;
    const isGold = s.state === 'GOLD';
    const isFlip = isRecentGoldFlip(s);
    const hasBuySignal = (s.trade_suggestion && s.trade_suggestion.action === 'SPOT_BUY') ||
                         (s.technical && (s.technical.action === 'BUY' || s.technical.action === 'ACCUMULATE')) ||
                         (s.synthesis && (s.synthesis.action === 'SPOT_BUY' || (s.synthesis.setup_type && s.synthesis.setup_type.includes('BUY'))));
    return (isFlip || (isGold && hasBuySignal));
  });

  // Sort by quantamental rank + gold flip bonus
  candidates.sort((a, b) => {
    const scoreA = getQuantamentalSetupRank(a) + (isRecentGoldFlip(a) ? 1500 : 0);
    const scoreB = getQuantamentalSetupRank(b) + (isRecentGoldFlip(b) ? 1500 : 0);
    return scoreB - scoreA;
  });

  const resolved = JSON.parse(localStorage.getItem('larsson_resolved_proposals') || '{}');
  const existingTickers = new Set((pendingProposals || []).filter(p => !resolved[p.proposal_id]).map(p => p.ticker));

  let topCandidates = candidates.filter(c => !existingTickers.has(c.ticker)).slice(0, 6);
  if (topCandidates.length === 0 && candidates.length > 0) {
    topCandidates = candidates.slice(0, 4);
  }

  let addedCount = 0;
  const newProposals = [];

  topCandidates.forEach((s, idx) => {
    const isCrypto = s.asset_class === 'crypto';
    const isStock = ['us_stocks', 'ai_stocks'].includes(s.asset_class);
    const btcRel = s.btc_relative;
    const isBtcBleeding = isCrypto && btcRel && !btcRel.leverage_allowed;

    let maxLev = 1;
    let recLev = 1;

    if (isCrypto) {
      if (isBtcBleeding) {
        maxLev = 1;
        recLev = 1;
      } else {
        maxLev = 3;
        recLev = 2;
      }
    } else if (isStock) {
      maxLev = 2;
      recLev = 2;
    }

    const entry = s.price;
    const sl = s.s1 ? Math.min(s.s1 * 0.985, entry * 0.95) : entry * 0.94;
    const tp1 = s.r1 ? Math.max(s.r1, entry * 1.08) : entry * 1.10;
    const tp2 = s.r1 ? s.r1 * 1.10 : entry * 1.20;
    const notional = isCrypto ? 1000 : 500;
    const units = entry > 0 ? (notional / entry) : 1;
    const tier = (s.fundamental && s.fundamental.moat === 'Wide') ? 'S' : (s.tier || 'A');

    let reason = '';
    if (isRecentGoldFlip(s)) {
      reason = `✨ Пресен Gold Flip пробив (${s.gold_flip_bars || 1}б назад). Ранна фаза на разширение по тренда с висок моментум.`;
    } else if (s.trade_suggestion && s.trade_suggestion.thesis) {
      reason = s.trade_suggestion.thesis;
    } else if (s.synthesis && s.synthesis.narrative) {
      reason = s.synthesis.narrative;
    } else {
      reason = `🟢 Бичи трендов импулс с чиста подкрепа на $${formatShortPrice(sl)} и цел $${formatShortPrice(tp1)}.`;
    }

    const propId = `prop_gen_${s.ticker}_${Date.now()}_${idx}`;

    const propObj = {
      id: Date.now() + idx,
      proposal_id: propId,
      ticker: s.ticker,
      name: s.name || s.ticker,
      timeframe: s.timeframe || '1D',
      action: 'BUY',
      direction: 'LONG',
      status: 'PENDING',
      asset_class: s.asset_class || 'crypto',
      entry_price: entry,
      stop_loss: Number(sl.toFixed(entry < 1 ? 4 : 2)),
      tp1: Number(tp1.toFixed(entry < 1 ? 4 : 2)),
      tp2: Number(tp2.toFixed(entry < 1 ? 4 : 2)),
      position_size_usd: notional,
      units: Number(units.toFixed(units < 1 ? 4 : 2)),
      risk_usd: Number((Math.abs(entry - sl) * units).toFixed(2)),
      tier: tier,
      score: isRecentGoldFlip(s) ? 94 : 88,
      reason: reason,
      recommended_leverage: recLev,
      max_leverage: maxLev,
      btc_relative: btcRel || null,
      created_at: new Date().toISOString()
    };

    newProposals.push(propObj);
    addedCount++;
  });

  if (newProposals.length > 0) {
    pendingProposals = [...newProposals, ...(pendingProposals || [])];
  }
  return addedCount;
}

let isAnalyzingTrades = false;

async function runNewTradeAnalysis() {
  if (isAnalyzingTrades) return;
  isAnalyzingTrades = true;

  const btnHeader = document.getElementById('btnRunNewAnalysis');
  const btnBanner = document.getElementById('btnBannerAnalyze');

  const setButtonsLoading = (loading) => {
    [btnHeader, btnBanner].forEach(btn => {
      if (!btn) return;
      btn.disabled = loading;
      const icon = btn.querySelector('.analyze-icon');
      if (icon) {
        if (loading) icon.classList.add('spinning');
        else icon.classList.remove('spinning');
      }
    });
  };

  setButtonsLoading(true);
  showAnalysisToast('⚡ Стартиране на нов пазарен анализ за търговски предложения...', 'loading', 0);

  try {
    let apiSuccess = false;
    let apiMsg = '';
    let fetchedCount = 0;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);
      const res = await fetch('/api/scan', { 
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const json = await res.json();
        if (json.success) {
          apiSuccess = true;
          fetchedCount = json.proposals_count || 0;
          apiMsg = json.message || `Открити са ${fetchedCount} активни предложения за търговия!`;
        }
      }
    } catch(err) {
      console.warn('Backend API /api/scan not reachable, using local quantamental synthesis fallback:', err);
    }

    if (apiSuccess) {
      await loadDashboardData();
      showAnalysisToast(`✅ ${apiMsg}`, 'success', 5000);
    } else {
      // Local browser-side synthesis fallback
      const createdCount = synthesizeClientProposals();
      renderProposalsBanner(pendingProposals);
      renderOverview();
      const totalActive = (pendingProposals || []).length;
      showAnalysisToast(`✅ Анализът завърши! Генерирани са ${createdCount} нови предложения (Общо активни: ${totalActive}) на база пресен Gold Flip и Quantamental Alpha.`, 'success', 5500);
    }

    // Automatically expand proposals section if it was collapsed
    if (isProposalsCollapsed) {
      isProposalsCollapsed = false;
      localStorage.setItem('larsson_proposals_collapsed', 'false');
      applyProposalsVisibility(false);
    }

    // Scroll smoothly to proposals section
    const banner = document.getElementById('proposalsBannerSection');
    if (banner) {
      banner.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  } catch(err) {
    console.error('Error during trade analysis:', err);
    showAnalysisToast(`⚠️ Грешка при стартиране на анализ: ${err.message}`, 'error', 5000);
  } finally {
    isAnalyzingTrades = false;
    setButtonsLoading(false);
  }
}

// Attach event listeners to analysis, undo & restore buttons
document.addEventListener('DOMContentLoaded', () => {
  const btnRunNew = document.getElementById('btnRunNewAnalysis');
  if (btnRunNew) btnRunNew.addEventListener('click', runNewTradeAnalysis);
  const btnBanner = document.getElementById('btnBannerAnalyze');
  if (btnBanner) btnBanner.addEventListener('click', runNewTradeAnalysis);
  const btnUndo = document.getElementById('btnUndoProposal');
  if (btnUndo) btnUndo.addEventListener('click', undoLastProposalAction);
  const btnRestore = document.getElementById('btnRestoreRejected');
  if (btnRestore) btnRestore.addEventListener('click', restoreAllRejectedProposals);
});

// Also immediately attach in case DOM is already ready
const btnRunNewImmediate = document.getElementById('btnRunNewAnalysis');
if (btnRunNewImmediate) btnRunNewImmediate.addEventListener('click', runNewTradeAnalysis);
const btnBannerImmediate = document.getElementById('btnBannerAnalyze');
if (btnBannerImmediate) btnBannerImmediate.addEventListener('click', runNewTradeAnalysis);
const btnUndoImmediate = document.getElementById('btnUndoProposal');
if (btnUndoImmediate) btnUndoImmediate.addEventListener('click', undoLastProposalAction);
const btnRestoreImmediate = document.getElementById('btnRestoreRejected');
if (btnRestoreImmediate) btnRestoreImmediate.addEventListener('click', restoreAllRejectedProposals);

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
      const direction = document.getElementById('realDirection')?.value || 'LONG';
      const leverage = parseInt(document.getElementById('realLeverage')?.value || '1', 10);
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
      const marginUsd = posSize / leverage;
      const isShort = (direction === 'SHORT');
      const liqPrice = leverage > 1 
        ? (isShort ? entryPrice * (1.0 + (1.0 / leverage) - 0.005) : entryPrice * (1.0 - (1.0 / leverage) + 0.005))
        : null;

      const newPos = {
        position_id: posId,
        symbol: ticker,
        direction: direction,
        leverage: leverage,
        entry_price: entryPrice,
        current_price: entryPrice,
        units: units,
        position_size_usd: posSize,
        margin_usd: marginUsd,
        liquidation_price: liqPrice,
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

      // Deduct margin + fee from cash
      const curCash = (portfolioRealData.summary && portfolioRealData.summary.available_cash) || 0;
      portfolioRealData.summary.available_cash = Math.max(0, curCash - (marginUsd + fee));
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
        action: isShort ? 'SHORT' : 'OPEN',
        price: entryPrice,
        units: units,
        pnl_usd: 0.0,
        pnl_pct: 0.0,
        broker_exchange: broker,
        reason: notes || `Real ${leverage}x ${direction} on ${broker}`,
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
      const isShort = (target.direction === 'SHORT');
      const grossPnl = isShort ? (entry - exitPrice) * units : (exitPrice - entry) * units;
      const netPnl = grossPnl - fee;
      const lev = target.leverage || 1;
      const margin = target.margin_usd || ((entry * units) / lev);
      const pnlPct = margin > 0 ? (netPnl / margin * 100) : 0;
      const nowIso = new Date().toISOString();

      // Return margin + netPnl to cash
      const curCash = (portfolioRealData.summary && portfolioRealData.summary.available_cash) || 0;
      portfolioRealData.summary.available_cash = curCash + margin + netPnl;
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
        action: isShort ? 'COVER' : 'CLOSE',
        entry_price: entry,
        exit_price: exitPrice,
        price: exitPrice,
        units: units,
        pnl_usd: netPnl,
        pnl_pct: pnlPct,
        broker_exchange: target.broker_exchange || 'Real Broker',
        reason: notes || `Ръчно затваряне на ${lev}x ${target.direction || 'LONG'} позиция`,
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
    const dir = pos.direction || 'LONG';
    const lev = pos.leverage || 1;
    const isShort = (dir === 'SHORT');
    const notional = pos.position_size_usd || (entryP * units);
    const margin = pos.margin_usd || (notional / lev);

    let uPnl = 0.0;
    if (isShort) {
      uPnl = (entryP - curP) * units;
    } else {
      uPnl = (curP - entryP) * units;
    }
    const uPct = margin > 0 ? (uPnl / margin * 100) : 0;

    pos.current_value = notional;
    pos.unrealized_pnl = uPnl;
    pos.unrealized_pnl_pct = uPct;

    totalInvested += margin;
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
          <td colspan="11" class="loading-state" style="padding: 30px; text-align: center;">
            ${isReal 
              ? '🟢 Няма отворени реални позиции. Натиснете <strong>"➕ Добави Реална Позиция"</strong>, за да регистрирате покупка от вашия брокер.'
              : '🧪 Няма активни тестови позиции. Алгоритъмът изчаква ново A+ предложение или можете да отворите сделка от калкулатора.'}
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
        const dir = p.direction || 'LONG';
        const lev = p.leverage || 1;
        const isShort = (dir === 'SHORT');
        const notional = p.position_size_usd || (p.entry_price * p.units);
        const margin = p.margin_usd || (notional / lev);

        let dirBadge = '';
        if (!isShort) {
          if (lev === 3) dirBadge = `<span class="badge-dir-long-3x">🚀 3x LONG</span>`;
          else if (lev === 2) dirBadge = `<span class="badge-dir-long-2x">⚡ 2x LONG</span>`;
          else dirBadge = `<span class="badge-dir-long-1x">🟢 1x SPOT</span>`;
        } else {
          if (lev >= 2) dirBadge = `<span class="badge-dir-short-2x">⚡ ${lev}x SHORT</span>`;
          else dirBadge = `<span class="badge-dir-short-1x">🔴 1x HEDGE</span>`;
        }

        const slText = p.stop_loss ? `$${formatShortPrice(p.stop_loss)}` : '<span style="color:var(--text-muted)">Няма</span>';
        const tpText = p.tp1 ? `$${formatShortPrice(p.tp1)}` : '<span style="color:var(--text-muted)">Няма</span>';
        const liqP = p.liquidation_price || (lev > 1 ? (isShort ? p.entry_price * (1.0 + 1.0/lev - 0.005) : p.entry_price * (1.0 - 1.0/lev + 0.005)) : null);
        const liqDisplay = liqP 
          ? `<div style="font-size:0.75rem; color:#f87171;">Liq: $${formatShortPrice(liqP)}</div>`
          : `<div style="font-size:0.7rem; color:#34d399;">🛡️ Без Liq</div>`;

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
          <div style="display:flex; gap:6px;">
            <button class="btn-close-real-trade" style="background: rgba(239, 68, 68, 0.2); border-color: #ef4444; color: #f87171;" onclick="closePaperPosition('${p.position_id || p.id}', '${p.symbol}', ${p.current_price || p.entry_price}, ${p.units})">
              🔴 Затвори
            </button>
            <button class="btn-table-action" onclick="openChartModal('${p.symbol}', '1D', '${p.asset_class}')" title="Графика">
              📊
            </button>
          </div>
        `;

        return `
          <tr>
            <td>
              <div class="ticker-cell" style="cursor: pointer;" onclick="openChartModal('${p.symbol}', '1D', '${p.asset_class}')">
                <div style="display:flex; align-items:center; gap:6px;">
                  <span class="ticker-symbol">${p.symbol}</span>
                  ${dirBadge}
                </div>
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
              <small style="color: var(--text-muted);">Ноц: $${formatShortPrice(notional)}</small>
            </td>
            <td>
              <strong style="color: #60a5fa;">$${formatShortPrice(margin)}</strong>
              <div style="font-size: 0.7rem; color: var(--text-muted);">${(100 / lev).toFixed(0)}% Колатерал</div>
            </td>
            <td>
              <strong style="color: #f87171;">${slText}</strong>
              ${liqDisplay}
            </td>
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

let pageCalcEventsBound = false;

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

    const isLong = (currentCalcDirection === 'LONG');
    const leverage = currentCalcLeverage || 1;

    const entry = parseFloat(entryInput ? entryInput.value : 100) || 100;
    let sl = parseFloat(slInput ? slInput.value : (isLong ? 95 : 105)) || (isLong ? entry * 0.95 : entry * 1.05);
    const tp1 = parseFloat(tp1Input ? tp1Input.value : (isLong ? 110 : 90)) || 0;
    const tp2 = parseFloat(tp2Input ? tp2Input.value : (isLong ? 120 : 80)) || 0;

    const baseRiskUsd = capital * (riskPct / 100.0);
    const riskUsd = baseRiskUsd * tierMultiplier;
    const riskPerUnit = Math.abs(entry - sl);

    if (riskPerUnit > 0 && entry > 0) {
      const units = riskUsd / riskPerUnit;
      const notional = units * entry;
      const margin = notional / leverage;
      const riskPctOfPrice = ((riskPerUnit / entry) * 100.0).toFixed(2);

      const rr1 = isLong 
        ? (tp1 > entry ? ((tp1 - entry) / riskPerUnit).toFixed(2) : '1.0')
        : (tp1 < entry ? ((entry - tp1) / riskPerUnit).toFixed(2) : '1.0');
      const rr2 = isLong
        ? (tp2 > entry ? ((tp2 - entry) / riskPerUnit).toFixed(2) : null)
        : (tp2 < entry ? ((entry - tp2) / riskPerUnit).toFixed(2) : null);

      const tp1Profit = isLong 
        ? (tp1 > entry ? (units * 0.5 * (tp1 - entry)) : 0)
        : (tp1 < entry ? (units * 0.5 * (entry - tp1)) : 0);
      const tp2Profit = isLong
        ? (tp2 > entry ? (units * 0.5 * (tp2 - entry)) : 0)
        : (tp2 < entry ? (units * 0.5 * (entry - tp2)) : 0);

      const liqPrice = leverage > 1 
        ? (isLong ? entry * (1.0 - (1.0 / leverage) + 0.005) : entry * (1.0 + (1.0 / leverage) - 0.005))
        : null;
      const distPct = liqPrice ? (Math.abs(entry - liqPrice) / entry * 100) : null;
      const isSafe = liqPrice ? (isLong ? sl > liqPrice : sl < liqPrice) : true;

      const unitsEl = document.getElementById('pageCalcUnits');
      if (unitsEl) unitsEl.textContent = `${units < 1 ? units.toFixed(4) : units.toFixed(2)} бр.`;

      const valEl = document.getElementById('pageCalcVal');
      if (valEl) valEl.textContent = `Ноционал: $${notional.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

      const marginEl = document.getElementById('pageCalcMarginUsd');
      if (marginEl) marginEl.textContent = `$${margin.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

      const marginSubEl = document.getElementById('pageCalcMarginSub');
      if (marginSubEl) marginSubEl.textContent = `${leverage}x Isolated (${(100 / leverage).toFixed(1)}% колатерал)`;

      const riskUsdEl = document.getElementById('pageCalcRiskUsd');
      if (riskUsdEl) riskUsdEl.textContent = `-$${riskUsd.toFixed(2)}`;

      const riskPctEl = document.getElementById('pageCalcRiskPct');
      if (riskPctEl) riskPctEl.textContent = `-${riskPctOfPrice}% от входа (Риск: ${riskPct}% * Tier ${tier})`;

      const liqEl = document.getElementById('pageCalcLiqPrice');
      if (liqEl) liqEl.textContent = liqPrice ? `$${formatShortPrice(liqPrice)}` : '— (Няма при 1x)';

      const liqBufEl = document.getElementById('pageCalcLiqBuffer');
      if (liqBufEl) {
        if (!liqPrice) {
          liqBufEl.innerHTML = `<span class="liq-safe-pill">Дистанция: ∞ (Без ликвидация при 1x)</span>`;
        } else {
          const pillClass = isSafe ? 'liq-safe-pill' : 'liq-danger-pill';
          const pillIcon = isSafe ? '🛡️ SL пази преди Liq' : '⚠️ Внимание: SL е твърде близо до Liq!';
          liqBufEl.innerHTML = `<span class="${pillClass}">Дистанция: ${distPct.toFixed(1)}% (${pillIcon})</span>`;
        }
      }

      const tp1ProfitEl = document.getElementById('pageCalcTp1Profit');
      if (tp1ProfitEl) tp1ProfitEl.textContent = `+$${tp1Profit.toFixed(2)}`;

      const tp2ProfitEl = document.getElementById('pageCalcTp2Profit');
      if (tp2ProfitEl) tp2ProfitEl.textContent = `+$${tp2Profit.toFixed(2)}`;

      const rrBadge = document.getElementById('pageCalcRrBadge');
      if (rrBadge) rrBadge.textContent = `R:R 1:${rr1}${rr2 ? ` (TP2 1:${rr2})` : ''}`;

      // Render Comparative Matrix Table (1x vs 2x vs 3x)
      const matrixBody = document.getElementById('pageCalcMatrixBody');
      if (matrixBody) {
        matrixBody.innerHTML = [1, 2, 3].map(lev => {
          const mReq = notional / lev;
          const mLiq = lev === 1 ? null : (isLong ? entry * (1.0 - 1.0/lev + 0.005) : entry * (1.0 + 1.0/lev - 0.005));
          const mDist = mLiq ? (Math.abs(entry - mLiq) / entry * 100).toFixed(1) + '%' : '∞ (Няма)';
          const mRiskPct = (riskUsd / mReq * 100).toFixed(1) + '%';
          const mRoiTp1 = (tp1Profit / mReq * 100).toFixed(1) + '%';
          const mRoiTp2 = ((tp1Profit + tp2Profit) / mReq * 100).toFixed(1) + '%';
          const isActive = (lev === leverage);
          const isLevSafe = mLiq ? (isLong ? sl > mLiq : sl < mLiq) : true;

          return `
            <tr class="${isActive ? 'active-lev-row' : ''}">
              <td><strong>${lev}x ${lev === 1 ? (isLong ? 'Spot' : 'Hedge') : 'Isolated'}</strong> ${isActive ? '👉' : ''}</td>
              <td><strong style="color: #60a5fa;">$${formatShortPrice(mReq)}</strong></td>
              <td>$${formatShortPrice(notional)}</td>
              <td>-$${riskUsd.toFixed(2)} (${mRiskPct})</td>
              <td><strong style="color: ${mLiq ? '#f87171' : '#34d399'};">${mLiq ? '$' + formatShortPrice(mLiq) : '—'}</strong></td>
              <td><span class="${isLevSafe ? 'liq-safe-pill' : 'liq-danger-pill'}">${mDist}</span></td>
              <td><strong style="color: #34d399;">+${mRoiTp1}</strong></td>
              <td><strong style="color: #34d399;">+${mRoiTp2}</strong></td>
            </tr>
          `;
        }).join('');
      }

      const dca1 = document.getElementById('pageDcaStep1');
      if (dca1) dca1.textContent = `Пазарен вход на $${entry.toFixed(2)} (${(units * 0.5).toFixed(2)} бр. = $${(notional * 0.5).toFixed(2)})`;

      const dca2 = document.getElementById('pageDcaStep2');
      if (dca2) dca2.textContent = `Лимитна поръчка на S1 подкрепа (${(units * 0.5).toFixed(2)} бр. = $${(notional * 0.5).toFixed(2)})`;

      // Compound growth calculations
      const monthlyReturnPct = 0.04;
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

  if (!pageCalcEventsBound) {
    pageCalcEventsBound = true;

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

    document.querySelectorAll('#pageCalcDirectionGroup .dir-toggle-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('#pageCalcDirectionGroup .dir-toggle-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        currentCalcDirection = e.target.dataset.dir;

        // Auto adjust SL/TP defaults if they were on opposite side
        const entry = parseFloat(entryInput ? entryInput.value : 100) || 100;
        if (currentCalcDirection === 'SHORT') {
          if (slInput && parseFloat(slInput.value) < entry) slInput.value = (entry * 1.05).toFixed(2);
          if (tp1Input && parseFloat(tp1Input.value) > entry) tp1Input.value = (entry * 0.90).toFixed(2);
          if (tp2Input && parseFloat(tp2Input.value) > entry) tp2Input.value = (entry * 0.80).toFixed(2);
        } else {
          if (slInput && parseFloat(slInput.value) > entry) slInput.value = (entry * 0.95).toFixed(2);
          if (tp1Input && parseFloat(tp1Input.value) < entry) tp1Input.value = (entry * 1.10).toFixed(2);
          if (tp2Input && parseFloat(tp2Input.value) < entry) tp2Input.value = (entry * 1.20).toFixed(2);
        }
        recalc();
      });
    });

    document.querySelectorAll('#pageCalcLeverageGroup .lev-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('#pageCalcLeverageGroup .lev-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        currentCalcLeverage = parseInt(e.target.dataset.lev, 10);
        recalc();
      });
    });

    // Execution Buttons
    const execPaperBtn = document.getElementById('btnPageExecPaper');
    if (execPaperBtn) {
      execPaperBtn.addEventListener('click', () => {
        const ticker = (tickerInput ? tickerInput.value : 'NVDA').trim().toUpperCase();
        const entry = parseFloat(entryInput ? entryInput.value : 100) || 100;
        const sl = parseFloat(slInput ? slInput.value : 95) || 95;
        const tp1 = parseFloat(tp1Input ? tp1Input.value : 110) || 110;
        const tp2 = parseFloat(tp2Input ? tp2Input.value : 120) || 120;
        const tier = tierSelect ? tierSelect.value : 'A';
        const direction = currentCalcDirection;
        const leverage = currentCalcLeverage;
        const capital = parseFloat(capInput ? capInput.value : 10000) || 10000;
        const activeRiskBtn = document.querySelector('#pageRiskPresets .preset-btn.active');
        const riskPct = activeRiskBtn ? parseFloat(activeRiskBtn.dataset.risk) : 1.0;
        const tierMultiplier = { 'S': 1.0, 'A': 0.85, 'B': 0.6, 'C': 0.3 }[tier] || 0.85;
        const riskUsd = capital * (riskPct / 100.0) * tierMultiplier;
        const riskPerUnit = Math.abs(entry - sl);
        const units = riskPerUnit > 0 ? (riskUsd / riskPerUnit) : 1;
        const notional = units * entry;
        const margin = notional / leverage;
        const isLong = (direction === 'LONG');
        const liqPrice = leverage > 1 
          ? (isLong ? entry * (1.0 - 1.0/leverage + 0.005) : entry * (1.0 + 1.0/leverage - 0.005))
          : null;

        const newPos = {
          position_id: `paper_calc_${ticker}_${Date.now()}`,
          symbol: ticker,
          direction: direction,
          leverage: leverage,
          entry_price: entry,
          current_price: entry,
          units: units,
          position_size_usd: notional,
          margin_usd: margin,
          liquidation_price: liqPrice,
          current_value: notional,
          unrealized_pnl: 0.0,
          unrealized_pnl_pct: 0.0,
          stop_loss: sl,
          tp1: tp1,
          tp2: tp2,
          duration_days: 0,
          opened_at: new Date().toISOString(),
          tier: tier,
          asset_class: 'us_stocks',
          portfolio_type: 'PAPER',
          broker_exchange: `Calculator ${leverage}x Isolated`,
          notes: `Ръчно въведена позиция от Калкулатора (${leverage}x ${direction})`
        };

        if (!portfolioPaperData.positions) portfolioPaperData.positions = [];
        portfolioPaperData.positions.unshift(newPos);

        const curCash = (portfolioPaperData.summary && portfolioPaperData.summary.available_cash) || 10000;
        portfolioPaperData.summary.available_cash = Math.max(0, curCash - margin);
        localStorage.setItem('larsson_custom_paper_cash', portfolioPaperData.summary.available_cash.toString());

        try {
          const saved = JSON.parse(localStorage.getItem('larsson_custom_paper_positions') || '[]');
          saved.unshift(newPos);
          localStorage.setItem('larsson_custom_paper_positions', JSON.stringify(saved));
        } catch(err) {
          console.error(err);
        }

        switchTab('portfolio');
        switchPortfolioMode('PAPER');
        alert(`🧪 Позицията ${ticker} (${leverage}x ${direction}, Маржин депозит: $${margin.toFixed(2)}) бе записана в симулатора!`);
      });
    }

    const execRealBtn = document.getElementById('btnPageExecReal');
    if (execRealBtn) {
      execRealBtn.addEventListener('click', () => {
        const ticker = (tickerInput ? tickerInput.value : 'NVDA').trim().toUpperCase();
        const entry = parseFloat(entryInput ? entryInput.value : 100) || 100;
        const sl = parseFloat(slInput ? slInput.value : 95) || 95;
        const tp1 = parseFloat(tp1Input ? tp1Input.value : 110) || 110;
        const capital = parseFloat(capInput ? capInput.value : 10000) || 10000;
        const activeRiskBtn = document.querySelector('#pageRiskPresets .preset-btn.active');
        const riskPct = activeRiskBtn ? parseFloat(activeRiskBtn.dataset.risk) : 1.0;
        const tier = tierSelect ? tierSelect.value : 'A';
        const tierMultiplier = { 'S': 1.0, 'A': 0.85, 'B': 0.6, 'C': 0.3 }[tier] || 0.85;
        const riskUsd = capital * (riskPct / 100.0) * tierMultiplier;
        const riskPerUnit = Math.abs(entry - sl);
        const units = riskPerUnit > 0 ? (riskUsd / riskPerUnit) : 1;

        switchTab('portfolio');
        switchPortfolioMode('REAL');
        const modal = document.getElementById('addRealModal');
        if (modal) {
          modal.style.display = 'flex';
          const t = document.getElementById('realTicker');
          const e = document.getElementById('realEntryPrice');
          const u = document.getElementById('realUnits');
          const d = document.getElementById('realDirection');
          const l = document.getElementById('realLeverage');
          const s = document.getElementById('realSl');
          const p = document.getElementById('realTp1');
          if (t) t.value = ticker;
          if (e) e.value = entry;
          if (u) u.value = units < 1 ? units.toFixed(4) : units.toFixed(2);
          if (d) d.value = currentCalcDirection;
          if (l) l.value = currentCalcLeverage.toString();
          if (s) s.value = sl;
          if (p) p.value = tp1;
        }
      });
    }
  }

  recalc();
}

function quickFillCalculator(ticker, entry, sl, tp1, tp2, tier, direction, leverage) {
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

  if (direction) {
    currentCalcDirection = direction;
    document.querySelectorAll('#pageCalcDirectionGroup .dir-toggle-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.dir === direction);
    });
  }
  if (leverage) {
    currentCalcLeverage = leverage;
    document.querySelectorAll('#pageCalcLeverageGroup .lev-btn').forEach(b => {
      b.classList.toggle('active', parseInt(b.dataset.lev, 10) === leverage);
    });
  }

  initPageCalculator();
}

// =============================================================================
// SECTION VISIBILITY CONTROLLERS (HIDE / SHOW PROPOSALS & LIVE CHART)
// =============================================================================

let isProposalsCollapsed = localStorage.getItem('larsson_proposals_collapsed') === 'true';
let isChartCollapsed = localStorage.getItem('larsson_chart_collapsed') === 'true';
let sectionVisibilityEventsBound = false;

function initSectionVisibilityControllers() {
  applyProposalsVisibility(isProposalsCollapsed);
  applyChartVisibility(isChartCollapsed);

  if (sectionVisibilityEventsBound) return;
  sectionVisibilityEventsBound = true;

  // Proposals toggle buttons
  const btnToggleProp = document.getElementById('btnToggleProposals');
  if (btnToggleProp) {
    btnToggleProp.addEventListener('click', toggleProposalsVisibility);
  }
  const hdrToggleProp = document.getElementById('hdrToggleProposals');
  if (hdrToggleProp) {
    hdrToggleProp.addEventListener('click', toggleProposalsVisibility);
  }

  // Chart toggle buttons
  const btnToggleChart = document.getElementById('btnToggleLiveChart');
  if (btnToggleChart) {
    btnToggleChart.addEventListener('click', toggleChartVisibility);
  }
  const hdrToggleChart = document.getElementById('hdrToggleChart');
  if (hdrToggleChart) {
    hdrToggleChart.addEventListener('click', toggleChartVisibility);
  }
}

function toggleProposalsVisibility() {
  isProposalsCollapsed = !isProposalsCollapsed;
  localStorage.setItem('larsson_proposals_collapsed', isProposalsCollapsed ? 'true' : 'false');
  applyProposalsVisibility(isProposalsCollapsed);
}

function applyProposalsVisibility(collapsed) {
  const section = document.getElementById('proposalsBannerSection');
  const btnToggle = document.getElementById('btnToggleProposals');
  const btnTxt = document.getElementById('btnToggleProposalsTxt');
  const hdrBtn = document.getElementById('hdrToggleProposals');
  const hdrTxt = document.getElementById('hdrToggleProposalsTxt');
  if (!section) return;

  let resolved = {};
  try {
    resolved = JSON.parse(localStorage.getItem('larsson_resolved_proposals') || '{}');
  } catch(e) { resolved = {}; }
  const activeCount = (pendingProposals || []).filter(p => !resolved[p.proposal_id]).length;

  if (collapsed) {
    section.classList.add('is-collapsed');
    if (btnToggle) {
      btnToggle.classList.add('is-collapsed');
      btnToggle.setAttribute('aria-expanded', 'false');
      const icon = btnToggle.querySelector('.toggle-icon');
      if (icon) icon.textContent = '▼';
    }
    if (btnTxt) {
      btnTxt.textContent = activeCount > 0 ? `Покажи (${activeCount})` : 'Покажи';
    }
    if (hdrBtn) {
      hdrBtn.classList.add('is-hidden');
    }
    if (hdrTxt) {
      hdrTxt.textContent = '⚡ Сделки (скрити)';
    }
  } else {
    section.classList.remove('is-collapsed');
    if (btnToggle) {
      btnToggle.classList.remove('is-collapsed');
      btnToggle.setAttribute('aria-expanded', 'true');
      const icon = btnToggle.querySelector('.toggle-icon');
      if (icon) icon.textContent = '▲';
    }
    if (btnTxt) {
      btnTxt.textContent = 'Скрий';
    }
    if (hdrBtn) {
      hdrBtn.classList.remove('is-hidden');
    }
    if (hdrTxt) {
      hdrTxt.textContent = '⚡ Сделки';
    }
  }
}

function toggleChartVisibility() {
  isChartCollapsed = !isChartCollapsed;
  localStorage.setItem('larsson_chart_collapsed', isChartCollapsed ? 'true' : 'false');
  applyChartVisibility(isChartCollapsed);
}

function applyChartVisibility(collapsed) {
  const section = document.getElementById('liveChartSection');
  const btnToggle = document.getElementById('btnToggleLiveChart');
  const btnTxt = document.getElementById('btnToggleLiveChartTxt');
  const hdrBtn = document.getElementById('hdrToggleChart');
  const hdrTxt = document.getElementById('hdrToggleChartTxt');
  if (!section) return;

  if (collapsed) {
    section.classList.add('is-collapsed');
    if (btnToggle) {
      btnToggle.classList.add('is-collapsed');
      btnToggle.setAttribute('aria-expanded', 'false');
      const icon = btnToggle.querySelector('.toggle-icon');
      if (icon) icon.textContent = '▼';
    }
    if (btnTxt) {
      btnTxt.textContent = 'Покажи графиката';
    }
    if (hdrBtn) {
      hdrBtn.classList.add('is-hidden');
    }
    if (hdrTxt) {
      hdrTxt.textContent = '📈 Графика (скрита)';
    }
  } else {
    section.classList.remove('is-collapsed');
    if (btnToggle) {
      btnToggle.classList.remove('is-collapsed');
      btnToggle.setAttribute('aria-expanded', 'true');
      const icon = btnToggle.querySelector('.toggle-icon');
      if (icon) icon.textContent = '▲';
    }
    if (btnTxt) {
      btnTxt.textContent = 'Скрий графиката';
    }
    if (hdrBtn) {
      hdrBtn.classList.remove('is-hidden');
    }
    if (hdrTxt) {
      hdrTxt.textContent = '📈 Графика';
    }

    // Auto-refresh or resize chart upon expanding
    setTimeout(() => {
      const container = document.getElementById('liveChartCanvas');
      if (liveActiveChart && container && container.clientWidth) {
        liveActiveChart.applyOptions({ 
          width: container.clientWidth,
          height: container.clientHeight || 480
        });
      } else if (!liveActiveChart && liveTicker) {
        selectLiveAsset(liveTicker, liveTf, liveClass);
      }
    }, 60);
  }
}

// Immediate init of visibility on DOM load
document.addEventListener('DOMContentLoaded', () => {
  initSectionVisibilityControllers();
});

// Initialize
initSectionVisibilityControllers();
loadDashboardData();

function initSystemDiagnosticsListeners() {
  const closeBtn = document.getElementById('closeSystemStatusModalBtn');
  if (closeBtn) closeBtn.addEventListener('click', closeSystemStatusModal);

  const modal = document.getElementById('systemStatusModal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeSystemStatusModal();
    });
  }

  const btnScan = document.getElementById('btnDiagRunScan');
  if (btnScan) {
    btnScan.addEventListener('click', () => {
      closeSystemStatusModal();
      runNewTradeAnalysis();
    });
  }

  const btnReload = document.getElementById('btnDiagReload');
  if (btnReload) {
    btnReload.addEventListener('click', () => {
      loadDashboardData();
    });
  }

  const btnReset = document.getElementById('btnDiagResetFilters');
  if (btnReset) {
    btnReset.addEventListener('click', () => {
      resetAllFilters();
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const diagModal = document.getElementById('systemStatusModal');
      if (diagModal && diagModal.style.display !== 'none') {
        closeSystemStatusModal();
      }
    }
  });

  checkServerStatus();
  if (!systemStatusTimer) {
    systemStatusTimer = setInterval(checkServerStatus, 5000);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initSystemDiagnosticsListeners();
  initFundamentalSearchListeners();
});
initSystemDiagnosticsListeners();

// =============================================================================
// TAB 5: FUNDAMENTAL ANALYSIS & INSTITUTIONAL DCF HUB CONTROLLER
// =============================================================================

function initFundamentalSearchListeners() {
  const fundInput = document.getElementById('fundTickerInput');
  if (fundInput) {
    fundInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        handleFundSearchSubmit();
      }
    });
  }
}

function openFundamentalTab(ticker, returnContext) {
  if (returnContext) {
    fundReturnContext = returnContext;
  }
  if (ticker) {
    currentFundTicker = ticker.trim().toUpperCase();
  }

  // Switch tab navigation
  switchTab('fundamentals');

  // Sync search input
  const inputEl = document.getElementById('fundTickerInput');
  if (inputEl) {
    inputEl.value = currentFundTicker || '';
  }

  // Highlight matching quick pill
  document.querySelectorAll('.fund-pill').forEach(pill => {
    const pillTxt = pill.textContent.replace(/[₿Ξ◎🏆\s]/g, '').trim().toUpperCase();
    const curNorm = (currentFundTicker || '').replace('USDT', '').trim().toUpperCase();
    pill.classList.toggle('active', pillTxt === curNorm || pill.textContent.toUpperCase().includes(curNorm));
  });

  if (currentFundTicker) {
    renderFundamentalDossier(currentFundTicker);
  }
}

function handleFundSearchSubmit() {
  const inputEl = document.getElementById('fundTickerInput');
  if (!inputEl) return;
  const val = inputEl.value.trim();
  if (val) {
    openFundamentalTab(val);
  }
}

function getFundamentalProfile(ticker) {
  if (!ticker) return null;
  const symNorm = ticker.toUpperCase().trim();

  // 1. Direct match in fundamentalProfiles
  if (fundamentalProfiles[symNorm]) {
    return fundamentalProfiles[symNorm];
  }

  // 1b. Crypto aliases (e.g. BTC <-> BTCUSDT)
  if (fundamentalProfiles[symNorm + 'USDT']) {
    return fundamentalProfiles[symNorm + 'USDT'];
  }
  if (symNorm.endsWith('USDT') && fundamentalProfiles[symNorm.slice(0, -4)]) {
    return fundamentalProfiles[symNorm.slice(0, -4)];
  }

  // 2. Search in allSymbols
  const s = allSymbols.find(x => (x.ticker || '').toUpperCase() === symNorm) ||
            allSymbols.find(x => (x.symbol || '').toUpperCase() === symNorm) ||
            allSymbols.find(x => (x.ticker || '').toUpperCase().startsWith(symNorm));

  if (s && (s.fund_data || s.fundamental)) {
    const fd = s.fund_data || {};
    const f = s.fundamental || {};
    return {
      ticker: s.ticker,
      name: s.name || s.ticker,
      verdict: fd.action || fd.verdict || f.action || 'HOLD',
      target_price: fd.fair_value || f.fair_value,
      fair_value: fd.fair_value || f.fair_value,
      mos_pct: fd.mos_pct !== undefined ? fd.mos_pct : f.mos_pct,
      moat: fd.moat || f.moat || 'None',
      roic_pct: fd.roic_pct !== undefined ? fd.roic_pct : f.roic_pct,
      wacc_pct: fd.wacc_pct !== undefined ? fd.wacc_pct : f.wacc_pct,
      z_score: fd.z_score !== undefined ? fd.z_score : f.z_score,
      m_score: fd.m_score !== undefined ? fd.m_score : f.m_score,
      tata: fd.tata,
      upside_pct: fd.upside_pct !== undefined ? fd.upside_pct : f.upside_pct,
      thesis: fd.thesis || fd.thesis_bg || f.thesis_bg || f.thesis,
      sector: fd.sector || (s.asset_class === 'crypto' ? 'Крипто активи' : (s.asset_class === 'commodities' ? 'Суровини' : 'Акции')),
      industry: fd.industry || s.asset_class,
      model_type: fd.model_type || (s.asset_class === 'crypto' ? 'Макро ончейн себестойност' : 'DCF модел'),
      price: s.price,
      shares: fd.shares,
      mcap_b: fd.mcap_b,
      beta: fd.beta,
      revenue_b: fd.revenue_b,
      ebit_b: fd.ebit_b,
      nopat_b: fd.nopat_b,
      entry_price: fd.entry_price || (s.trade_suggestion && s.trade_suggestion.entry),
      action: fd.action || f.action,
      solvency_type: fd.solvency_type,
      production_cost: fd.production_cost,
      mvrv_ratio: fd.mvrv_ratio
    };
  }

  // 3. Fallback to basic symbol if present
  if (s) {
    return {
      ticker: s.ticker,
      name: s.name || s.ticker,
      verdict: 'SPECULATIVE_NA',
      target_price: s.price,
      fair_value: s.price,
      mos_pct: 0,
      moat: 'None',
      price: s.price,
      sector: s.asset_class === 'crypto' ? 'Крипто активи' : 'Финансови пазари',
      industry: s.asset_class,
      model_type: 'Технически модел на Larsson',
      thesis: 'Липсва пълен фундаментален модел за актива. Анализът се базира на технически индикатори и тренд на Larsson.'
    };
  }

  return null;
}

function renderFundamentalDossier(ticker) {
  const container = document.getElementById('fundDossierLayout');
  if (!container) return;

  const prof = getFundamentalProfile(ticker);
  const symItem = allSymbols.find(x => (x.ticker || '').toUpperCase() === (ticker || '').toUpperCase()) ||
                  allSymbols.find(x => (x.ticker || '').toUpperCase().startsWith((ticker || '').toUpperCase()));

  if (!prof) {
    container.innerHTML = `
      <div class="fund-loading-placeholder">
        <div class="fund-empty-icon">⚠️</div>
        <h3>Няма намерен фундаментален модел за "${escapeHtml(ticker)}"</h3>
        <p>Моля, въведете валиден тикер (напр. NVDA, MSTR, NAKA, AAPL, BTC, ETH, GC=F) или изберете от бързите бутони горе.</p>
        <button type="button" class="btn btn-fund-load" onclick="openFundamentalTab('NVDA')" style="margin-top: 14px; cursor: pointer;">
          Зареди NVDA (Примерен анализ)
        </button>
      </div>
    `;
    return;
  }

  const price = (symItem && symItem.price) ? symItem.price : (prof.price || 0);
  const fairValue = prof.fair_value || prof.target_price || price;

  // Calculate MoS & Upside dynamically if price available
  let mosPct = prof.mos_pct;
  let upsidePct = prof.upside_pct;
  if (price > 0 && fairValue > 0) {
    mosPct = Math.round(((fairValue - price) / fairValue) * 100);
    upsidePct = Math.round(((fairValue - price) / price) * 100);
  }

  // Base values for DCF Simulator
  const baseWacc = prof.wacc_pct || 9.5;
  const baseG = 2.5;
  const baseFcfGrowth = 0.0;
  currentSimBase = {
    ticker: prof.ticker,
    price: price,
    baseFairValue: fairValue,
    baseWacc: baseWacc,
    baseG: baseG,
    baseFcfGrowth: baseFcfGrowth
  };

  // Verdict style
  const isStrongBuy = (prof.verdict || '').includes('STRONG BUY') || (prof.action === 'STRONG_BUY');
  const isBuy = (prof.verdict || '').includes('BUY') || (prof.action === 'BUY');
  const isHold = (prof.verdict || '').includes('HOLD') || (prof.action === 'HOLD');
  const isReduce = (prof.verdict || '').includes('REDUCE') || (prof.verdict || '').includes('AVOID');

  let verdictBadge = 'badge-gold';
  let verdictText = prof.verdict || 'BUY';
  if (isStrongBuy) {
    verdictBadge = 'badge-gold';
    verdictText = '⭐ ALPHA STRONG BUY';
  } else if (isBuy) {
    verdictBadge = 'badge-gold';
    verdictText = '🟢 VALUE BUY';
  } else if (isHold) {
    verdictBadge = 'badge-neutral';
    verdictText = '⚪ HOLD / FAIR VALUE';
  } else if (isReduce) {
    verdictBadge = 'badge-blue';
    verdictText = '🔴 REDUCE / AVOID';
  }

  // MoS Styling
  let mosClass = 'accent';
  let mosLabel = 'Неопределен';
  if (mosPct !== null && mosPct !== undefined) {
    if (mosPct >= 20) {
      mosClass = 'bullish';
      mosLabel = `+${mosPct}% (Здрав институционален буфер)`;
    } else if (mosPct >= 0) {
      mosClass = 'accent';
      mosLabel = `+${mosPct}% (Справедлива цена)`;
    } else {
      mosClass = 'bearish';
      mosLabel = `${mosPct}% (Надценена)`;
    }
  }

  // Barometer track fill calculation
  let trackPct = 50;
  let trackClass = 'fill-fair';
  if (fairValue > 0) {
    const ratio = price / fairValue;
    if (ratio < 0.8) {
      trackPct = Math.min(100, Math.max(15, (1 - ratio) * 100 + 30));
      trackClass = 'fill-undervalued';
    } else if (ratio <= 1.1) {
      trackPct = 50;
      trackClass = 'fill-fair';
    } else {
      trackPct = Math.min(100, (ratio - 1) * 100 + 40);
      trackClass = 'fill-overvalued';
    }
  }

  // Moat & EVA
  const moat = prof.moat || 'None';
  let moatBadge = '<span class="fund-pillar-badge" style="background: rgba(148, 163, 184, 0.2); color: #94a3b8;">⚪ No Moat</span>';
  if (moat === 'Wide') {
    moatBadge = '<span class="fund-pillar-badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">💎 Wide Moat</span>';
  } else if (moat === 'Narrow') {
    moatBadge = '<span class="fund-pillar-badge" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa;">🏰 Narrow Moat</span>';
  }

  const roic = prof.roic_pct;
  const wacc = prof.wacc_pct || baseWacc;
  let evaSpreadHtml = '—';
  if (roic !== null && roic !== undefined && wacc !== null && wacc !== undefined) {
    const spread = (roic - wacc).toFixed(1);
    if (spread > 0) {
      evaSpreadHtml = `<span style="color: #34d399;">+${spread}% (Създава акционерна стойност)</span>`;
    } else {
      evaSpreadHtml = `<span style="color: #f87171;">${spread}% (Унищожава капитал)</span>`;
    }
  }

  // Altman Z-Score & Solvency
  const zScore = prof.z_score;
  let zBadge = '<span class="fund-pillar-badge" style="background: rgba(148, 163, 184, 0.2); color: #94a3b8;">N/A</span>';
  let zStatusText = 'Няма данни';
  if (zScore !== null && zScore !== undefined) {
    if (zScore >= 2.99) {
      zBadge = '<span class="fund-pillar-badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">🟢 Safe Zone</span>';
      zStatusText = 'Нулев кредитен риск / Отличен баланс';
    } else if (zScore >= 1.81) {
      zBadge = '<span class="fund-pillar-badge" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24;">🟡 Grey Zone</span>';
      zStatusText = 'Умерено внимание / Стабилна ликвидност';
    } else {
      zBadge = '<span class="fund-pillar-badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171;">🔴 Distress Zone</span>';
      zStatusText = 'Висок финансов риск / Спекулативен дълг';
    }
  }

  // Beneish M-Score & Forensic
  const mScore = prof.m_score;
  let mBadge = '<span class="fund-pillar-badge" style="background: rgba(148, 163, 184, 0.2); color: #94a3b8;">N/A</span>';
  let mStatusText = 'Няма данни за счетоводни начисления';
  if (mScore !== null && mScore !== undefined) {
    if (mScore <= -1.78) {
      mBadge = '<span class="fund-pillar-badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">🟢 Low Risk</span>';
      mStatusText = 'Чисти финансови отчети / Качествен FCF';
    } else {
      mBadge = '<span class="fund-pillar-badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171;">🔴 Manipulation Alert</span>';
      mStatusText = 'Риск от агресивно признаване на приходи';
    }
  }

  // Crypto / Commodities Specifics
  const isCrypto = (symItem && symItem.asset_class === 'crypto') || prof.ticker.includes('USDT') || prof.production_cost || prof.mvrv_ratio;
  let cryptoCardHtml = '';
  if (isCrypto) {
    const prodCost = prof.production_cost || (prof.ticker.startsWith('BTC') ? 62000 : null);
    const mvrv = prof.mvrv_ratio || (prof.ticker.startsWith('BTC') ? 1.95 : null);
    cryptoCardHtml = `
      <div class="fund-crypto-card">
        <div class="fund-pillar-header">
          <span class="fund-pillar-title">🪙 Ончейн &amp; Себестойностен Анализ (Digital Asset Valuation)</span>
          <span class="fund-pillar-badge" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24;">⚡ Proof-of-Work &amp; Network Value</span>
        </div>
        <div class="fund-pillars-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px;">
          <div class="fund-metric-row">
            <span class="fund-metric-label">Себестойност (Mining / Floor Cost):</span>
            <span class="fund-metric-val" style="color: #f59e0b;">${prodCost ? '$' + formatShortPrice(prodCost) : 'Пазарна себестойност'}</span>
          </div>
          <div class="fund-metric-row">
            <span class="fund-metric-label">MVRV Ratio:</span>
            <span class="fund-metric-val" style="color: #38bdf8;">${mvrv ? mvrv.toFixed(2) + ' (Консолидационна зона)' : 'Зрял мрежов ефект'}</span>
          </div>
          <div class="fund-metric-row">
            <span class="fund-metric-label">Институционален интерес:</span>
            <span class="fund-metric-val">Спот ETF притоци &amp; Трежъри акумулация</span>
          </div>
          <div class="fund-metric-row">
            <span class="fund-metric-label">Дългосрочен подкрепен под:</span>
            <span class="fund-metric-val" style="color: #34d399;">$${prodCost ? formatShortPrice(prodCost * 0.95) : formatShortPrice(price * 0.8)}</span>
          </div>
        </div>
      </div>
    `;
  }

  // Active Proposal Link (if any)
  const activeProposal = (pendingProposals || []).find(p => p.ticker === prof.ticker);
  let proposalActionsHtml = '';
  if (activeProposal) {
    const isLong = (activeProposal.direction || 'LONG') === 'LONG';
    const recLev = activeProposal.recommended_leverage || 1;
    proposalActionsHtml = `
      <div class="fund-proposal-actions">
        <span style="font-size: 0.85rem; font-weight: 700; color: #f59e0b;">⚡ Активно Предложение:</span>
        <button type="button" class="btn btn-approve-1x" onclick="approveProposal('${activeProposal.proposal_id}', 1); openFundamentalTab('${prof.ticker}');">
          ${isLong ? '🟢 Одобри Spot 1x' : '🟢 Одобри Hedge 1x'}
        </button>
        ${(recLev >= 2 || (activeProposal.max_leverage || 1) >= 2) ? `
          <button type="button" class="btn btn-approve-2x" onclick="approveProposal('${activeProposal.proposal_id}', 2); openFundamentalTab('${prof.ticker}');">
            ⚡ Long 2x
          </button>
        ` : ''}
        ${(recLev >= 3 || (activeProposal.max_leverage || 1) >= 3) ? `
          <button type="button" class="btn btn-approve-3x" onclick="approveProposal('${activeProposal.proposal_id}', 3); openFundamentalTab('${prof.ticker}');">
            🚀 Long 3x
          </button>
        ` : ''}
      </div>
    `;
  }

  // Render Full HTML layout
  container.innerHTML = `
    <!-- Header Card -->
    <div class="fund-header-card">
      <div class="fund-header-left">
        <div>
          <div style="display: flex; align-items: center; gap: 10px;">
            <span class="fund-header-ticker">${prof.ticker}</span>
            <span class="badge ${verdictBadge}">${verdictText}</span>
          </div>
          <div class="fund-header-name">${escapeHtml(prof.name || prof.ticker)}</div>
          <div class="fund-header-meta">
            <span class="fund-meta-chip">📁 Сектор: ${escapeHtml(prof.sector || 'Финансови пазари')}</span>
            <span class="fund-meta-chip">🏭 Индустрия: ${escapeHtml(prof.industry || 'Инфраструктура')}</span>
            <span class="fund-meta-chip">📐 Модел: ${escapeHtml(prof.model_type || 'Тристепенен DCF')}</span>
          </div>
        </div>
      </div>
      <div class="fund-header-right">
        ${moatBadge}
      </div>
    </div>

    <!-- Hero Valuation Card -->
    <div class="fund-hero-card">
      <div class="fund-hero-grid">
        <div class="fund-hero-stat">
          <span class="fund-hero-label">Текуща Пазарна Цена</span>
          <span class="fund-hero-value">$${formatShortPrice(price)}</span>
        </div>
        <div class="fund-hero-stat">
          <span class="fund-hero-label">DCF Справедлива Стойност (Base)</span>
          <span class="fund-hero-value" style="color: #60a5fa;">$${formatShortPrice(fairValue)}</span>
        </div>
        <div class="fund-hero-stat">
          <span class="fund-hero-label">Марж на Безопасност (Margin of Safety)</span>
          <span class="fund-hero-value ${mosClass}">${mosLabel}</span>
        </div>
        <div class="fund-hero-stat">
          <span class="fund-hero-label">Потенциал за Ръст (Upside)</span>
          <span class="fund-hero-value ${upsidePct >= 0 ? 'bullish' : 'bearish'}">${upsidePct !== null && upsidePct !== undefined ? (upsidePct >= 0 ? '+' : '') + upsidePct + '%' : '—'}</span>
        </div>
      </div>

      <!-- Barometer Track -->
      <div class="fund-barometer-bar-container">
        <div class="fund-barometer-labels">
          <span>🟢 Подценена зона (Discount)</span>
          <span>🟡 Справедлива цена ($${formatShortPrice(fairValue)})</span>
          <span>🔴 Надценена зона (Premium)</span>
        </div>
        <div class="fund-barometer-track">
          <div class="fund-barometer-fill ${trackClass}" style="width: ${trackPct}%;"></div>
        </div>
      </div>
    </div>

    <!-- 3-Pillars Institutional Grid -->
    <div class="fund-pillars-grid">
      <!-- Pillar 1: Economic Moat & EVA -->
      <div class="fund-pillar-card">
        <div class="fund-pillar-header">
          <span class="fund-pillar-title">💎 Стълб 1: Икономически Ров (Moat) &amp; EVA</span>
          ${moatBadge}
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">Възвръщаемост на Капитала (ROIC):</span>
          <span class="fund-metric-val" style="color: #38bdf8;">${roic !== null && roic !== undefined ? roic.toFixed(1) + '%' : '—'}</span>
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">Цена на Капитала (WACC):</span>
          <span class="fund-metric-val">${wacc !== null && wacc !== undefined ? wacc.toFixed(1) + '%' : '9.5%'}</span>
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">EVA Спред (ROIC - WACC):</span>
          <span class="fund-metric-val">${evaSpreadHtml}</span>
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">Конкурентен бариерен статус:</span>
          <span class="fund-metric-val">${moat === 'Wide' ? 'Високи превключващи разходи & Мрежов ефект' : (moat === 'Narrow' ? 'Умерено ценово предимство' : 'Ценова конкуренция')}</span>
        </div>
      </div>

      <!-- Pillar 2: Solvency & Distress (Altman Z-Score) -->
      <div class="fund-pillar-card">
        <div class="fund-pillar-header">
          <span class="fund-pillar-title">🛡️ Стълб 2: Платежоспособност (Altman Z-Score)</span>
          ${zBadge}
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">Z-Score Индекс:</span>
          <span class="fund-metric-val" style="color: #34d399; font-size: 1.15rem;">${zScore !== null && zScore !== undefined ? zScore.toFixed(2) : '—'}</span>
        </div>
        <div class="fund-zscore-thermometer" title="Altman Z-Score зони: Червено (<1.81), Жълто (1.81-2.99), Зелено (>2.99)">
          <div class="z-distress-zone"></div>
          <div class="z-grey-zone"></div>
          <div class="z-safe-zone"></div>
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">Статус на Ликвидност:</span>
          <span class="fund-metric-val">${zStatusText}</span>
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">Модел на оценка:</span>
          <span class="fund-metric-val">${escapeHtml(prof.solvency_type || 'Altman Z-Score Standard')}</span>
        </div>
      </div>

      <!-- Pillar 3: Forensic Red Flags (Beneish M-Score) -->
      <div class="fund-pillar-card">
        <div class="fund-pillar-header">
          <span class="fund-pillar-title">🔬 Стълб 3: Счетоводна Чистота (Beneish M)</span>
          ${mBadge}
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">Beneish M-Score (Праг -1.78):</span>
          <span class="fund-metric-val" style="color: #38bdf8;">${mScore !== null && mScore !== undefined ? mScore.toFixed(2) : '—'}</span>
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">Качество на печалбите:</span>
          <span class="fund-metric-val">${mStatusText}</span>
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">Начисления спрямо активи (TATA):</span>
          <span class="fund-metric-val">${prof.tata !== null && prof.tata !== undefined ? prof.tata.toFixed(3) : 'Норма'}</span>
        </div>
        <div class="fund-metric-row">
          <span class="fund-metric-label">Риск от ревизия на отчети:</span>
          <span class="fund-metric-val" style="color: #34d399;">Минимален</span>
        </div>
      </div>
    </div>

    <!-- Crypto / Commodities Specialized Card (if applicable) -->
    ${cryptoCardHtml}

    <!-- Financial Fundamentals & Multiples (if company) -->
    ${(!isCrypto && (prof.mcap_b || prof.revenue_b)) ? `
      <div class="fund-pillar-card">
        <div class="fund-pillar-header">
          <span class="fund-pillar-title">📊 Финансови Параметри &amp; Мащаб на Бизнеса</span>
          <span class="fund-pillar-badge" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa;">SEC Filings / LTM</span>
        </div>
        <div class="fund-pillars-grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
          <div class="fund-metric-row">
            <span class="fund-metric-label">Пазарна капитализация:</span>
            <span class="fund-metric-val">${prof.mcap_b ? '$' + prof.mcap_b.toFixed(1) + ' млрд.' : '—'}</span>
          </div>
          <div class="fund-metric-row">
            <span class="fund-metric-label">Приходи (LTM Revenue):</span>
            <span class="fund-metric-val">${prof.revenue_b ? '$' + prof.revenue_b.toFixed(2) + ' млрд.' : '—'}</span>
          </div>
          <div class="fund-metric-row">
            <span class="fund-metric-label">Оперативна печалба (EBIT):</span>
            <span class="fund-metric-val">${prof.ebit_b ? '$' + prof.ebit_b.toFixed(2) + ' млрд.' : '—'}</span>
          </div>
          <div class="fund-metric-row">
            <span class="fund-metric-label">Чист NOPAT:</span>
            <span class="fund-metric-val">${prof.nopat_b ? '$' + prof.nopat_b.toFixed(2) + ' млрд.' : '—'}</span>
          </div>
          <div class="fund-metric-row">
            <span class="fund-metric-label">Пазарен коефициент Beta:</span>
            <span class="fund-metric-val">${prof.beta ? prof.beta.toFixed(2) : '1.0'}</span>
          </div>
          <div class="fund-metric-row">
            <span class="fund-metric-label">Брой акции в обращение:</span>
            <span class="fund-metric-val">${prof.shares ? (prof.shares / 1e6).toFixed(1) + ' млн.' : '—'}</span>
          </div>
        </div>
      </div>
    ` : ''}

    <!-- Investment Committee Thesis Memo -->
    <div class="fund-thesis-card">
      <div class="fund-thesis-title">
        <span>📝</span> Меморандум на Инвестиционния Комитет (Investment Thesis)
      </div>
      <div class="fund-thesis-body">
        ${escapeHtml(prof.thesis || 'Анализът се базира на фундаменталното съотношение риск/доходност и стабилен икономически ров.')}
      </div>
    </div>

    <!-- Interactive DCF Sensitivity Simulator -->
    <div class="fund-simulator-card">
      <div class="fund-sim-header">
        <div class="fund-sim-title">
          <span>🧮</span> Интерактивен DCF Симулатор на Чувствителността (What-If Analysis)
        </div>
        <button type="button" class="btn btn-secondary" onclick="resetDcfSimulator('${prof.ticker}')" style="font-size: 0.75rem; padding: 4px 10px; cursor: pointer;">
          ↺ Върни базови стойности
        </button>
      </div>
      <p style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">
        Променете цената на капитала (WACC), дългосрочния терминален растеж ($g$) или паричните потоци, за да видите динамичната оценка:
      </p>
      <div class="fund-sim-sliders-grid">
        <div class="fund-sim-control">
          <div class="fund-sim-control-header">
            <span>Цена на капитала (WACC %):</span>
            <span class="fund-sim-control-val" id="valSimWacc">${baseWacc.toFixed(1)}%</span>
          </div>
          <input type="range" class="fund-sim-slider" id="sliderSimWacc" min="6.0" max="18.0" step="0.1" value="${baseWacc.toFixed(1)}" oninput="updateDcfSimulator('${prof.ticker}')">
        </div>
        <div class="fund-sim-control">
          <div class="fund-sim-control-header">
            <span>Терминален растеж g (%):</span>
            <span class="fund-sim-control-val" id="valSimG">${baseG.toFixed(1)}%</span>
          </div>
          <input type="range" class="fund-sim-slider" id="sliderSimG" min="1.0" max="5.0" step="0.1" value="${baseG.toFixed(1)}" oninput="updateDcfSimulator('${prof.ticker}')">
        </div>
        <div class="fund-sim-control">
          <div class="fund-sim-control-header">
            <span>Корекция на свободен FCF (%):</span>
            <span class="fund-sim-control-val" id="valSimFcf">0%</span>
          </div>
          <input type="range" class="fund-sim-slider" id="sliderSimFcf" min="-50" max="50" step="5" value="0" oninput="updateDcfSimulator('${prof.ticker}')">
        </div>
      </div>

      <div class="fund-sim-results-strip">
        <div class="fund-sim-res-item">
          <span class="fund-sim-res-lbl">Симулирана Справедлива Цена</span>
          <span class="fund-sim-res-val" id="simResultFairValue" style="color: #60a5fa;">$${formatShortPrice(fairValue)}</span>
        </div>
        <div class="fund-sim-res-item">
          <span class="fund-sim-res-lbl">Симулиран Марж (MoS)</span>
          <span class="fund-sim-res-val ${mosClass}" id="simResultMos">${mosPct !== null ? (mosPct >= 0 ? '+' : '') + mosPct + '%' : '—'}</span>
        </div>
        <div class="fund-sim-res-item">
          <span class="fund-sim-res-lbl">Симулиран Потенциал (Upside)</span>
          <span class="fund-sim-res-val ${upsidePct >= 0 ? 'bullish' : 'bearish'}" id="simResultUpside">${upsidePct !== null ? (upsidePct >= 0 ? '+' : '') + upsidePct + '%' : '—'}</span>
        </div>
      </div>
    </div>

    <!-- Action Bar -->
    <div class="fund-action-bar">
      ${proposalActionsHtml}
      <div class="fund-external-actions">
        <button type="button" class="btn btn-primary-action" onclick="openChartModal('${prof.ticker}')">
          📊 Отвори Графика &amp; Нива
        </button>
        <button type="button" class="btn btn-secondary-action" onclick="openCalculatorForTicker('${prof.ticker}')">
          🧮 Отвори в Калкулатора
        </button>
      </div>
    </div>
  `;
}

function updateDcfSimulator(ticker) {
  if (!currentSimBase) return;
  const sliderWacc = document.getElementById('sliderSimWacc');
  const sliderG = document.getElementById('sliderSimG');
  const sliderFcf = document.getElementById('sliderSimFcf');

  const valWaccEl = document.getElementById('valSimWacc');
  const valGEl = document.getElementById('valSimG');
  const valFcfEl = document.getElementById('valSimFcf');

  const resFvEl = document.getElementById('simResultFairValue');
  const resMosEl = document.getElementById('simResultMos');
  const resUpsideEl = document.getElementById('simResultUpside');

  if (!sliderWacc || !sliderG || !sliderFcf) return;

  const newWacc = parseFloat(sliderWacc.value);
  const newG = parseFloat(sliderG.value);
  const newFcf = parseFloat(sliderFcf.value);

  if (valWaccEl) valWaccEl.textContent = newWacc.toFixed(1) + '%';
  if (valGEl) valGEl.textContent = newG.toFixed(1) + '%';
  if (valFcfEl) valFcfEl.textContent = (newFcf >= 0 ? '+' : '') + newFcf + '%';

  // Prevent divide by zero or negative denominator
  const denom = Math.max(0.01, (newWacc - newG) / 100);
  const baseDenom = Math.max(0.01, (currentSimBase.baseWacc - currentSimBase.baseG) / 100);
  const fcfMult = 1.0 + (newFcf / 100);

  const multiplier = (baseDenom / denom) * fcfMult;
  const simFairValue = Math.max(0.01, currentSimBase.baseFairValue * multiplier);

  const price = currentSimBase.price || 0;
  let simMos = 0;
  let simUpside = 0;
  if (price > 0 && simFairValue > 0) {
    simMos = Math.round(((simFairValue - price) / simFairValue) * 100);
    simUpside = Math.round(((simFairValue - price) / price) * 100);
  }

  if (resFvEl) resFvEl.textContent = '$' + formatShortPrice(simFairValue);
  if (resMosEl) {
    resMosEl.textContent = (simMos >= 0 ? '+' : '') + simMos + '%';
    resMosEl.className = 'fund-sim-res-val ' + (simMos >= 20 ? 'bullish' : (simMos >= 0 ? 'accent' : 'bearish'));
  }
  if (resUpsideEl) {
    resUpsideEl.textContent = (simUpside >= 0 ? '+' : '') + simUpside + '%';
    resUpsideEl.className = 'fund-sim-res-val ' + (simUpside >= 0 ? 'bullish' : 'bearish');
  }
}

function resetDcfSimulator(ticker) {
  if (!currentSimBase) return;
  const sliderWacc = document.getElementById('sliderSimWacc');
  const sliderG = document.getElementById('sliderSimG');
  const sliderFcf = document.getElementById('sliderSimFcf');

  if (sliderWacc) sliderWacc.value = currentSimBase.baseWacc.toFixed(1);
  if (sliderG) sliderG.value = currentSimBase.baseG.toFixed(1);
  if (sliderFcf) sliderFcf.value = 0;

  updateDcfSimulator(ticker);
}

function openCalculatorForTicker(ticker) {
  switchTab('calculator');
  const s = allSymbols.find(x => x.ticker === ticker);
  const tickerInput = document.getElementById('pageCalcTicker');
  const entryInput = document.getElementById('pageCalcEntry');
  if (tickerInput) tickerInput.value = ticker;
  if (entryInput && s && s.price) entryInput.value = s.price;
  if (typeof initPageCalculator === 'function') initPageCalculator();
}


