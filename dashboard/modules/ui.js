/**
 * UI Utilities and Formatting Module for Larsson Scanner.
 * @module ui
 */

export const CLASS_LABELS = {
  crypto_stocks: 'Crypto Stock',
  ai_stocks: 'AI Stock',
  crypto: 'Crypto',
  us_stocks: 'US Stock',
  intl_stocks: 'Europe & Global',
  commodities: 'Commodity',
  indices: 'Index',
};

export function formatShortPrice(val) {
  if (val === null || val === undefined || isNaN(val)) return 'N/A';
  if (val >= 10000) {
    return (val / 1000).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'k';
  } else if (val >= 1000) {
    return val.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  } else if (val >= 1) {
    return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  } else {
    return val.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 });
  }
}

export function formatPrice(val) {
  if (val === null || val === undefined || isNaN(val)) return 'N/A';
  if (val >= 1000) {
    return '$' + val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  } else if (val >= 1) {
    return '$' + val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  } else {
    return '$' + val.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 });
  }
}

export function formatPercent(val) {
  if (val === null || val === undefined || isNaN(val)) return '0.0%';
  const prefix = val > 0 ? '+' : '';
  return `${prefix}${val.toFixed(2)}%`;
}

export function getTvInterval(tf) {
  if (!tf) return 'D';
  const upper = tf.toUpperCase();
  if (upper === '4H') return '240';
  if (upper === '1H') return '60';
  if (upper === '1W' || upper === 'W') return 'W';
  if (upper === '1M' || upper === 'M') return 'M';
  return 'D';
}

export function getTvSymbol(item, ticker, assetClass) {
  if (item && item.tv_symbol) return item.tv_symbol;
  if (assetClass === 'crypto' || (ticker && ticker.endsWith('USDT'))) {
    return `BINANCE:${ticker}`;
  }
  return ticker;
}

export const NATIVE_BINANCE_BTC_PAIRS = {
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

export function getTvRatioSymbol(item, ticker, assetClass) {
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

export function getTvRatioLink(item, ticker, assetClass, timeframe) {
  if (item && item.tv_ratio_url) return item.tv_ratio_url;
  const ratioSym = getTvRatioSymbol(item, ticker, assetClass);
  const tfCode = getTvInterval(timeframe || (item && item.timeframe) || '1D');
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(ratioSym)}&interval=${tfCode}`;
}

export function normalizeCyrillic(str) {
  if (!str) return '';
  const cyrToLat = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ж': 'zh', 'з': 'z',
    'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p',
    'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'sht', 'ъ': 'a', 'ь': 'y', 'ю': 'yu', 'я': 'ya'
  };
  return str.toLowerCase().split('').map(char => cyrToLat[char] || char).join('');
}
