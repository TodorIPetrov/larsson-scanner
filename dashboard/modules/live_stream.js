/**
 * Live Market Stream & Real-Time Tick Engine for Larsson Scanner.
 * Connects directly to Binance WebSocket from the browser (wss://stream.binance.com:9443)
 * for sub-second crypto prices, dynamically updates the Larsson SMMA ribbon,
 * and polls background live quotes for traditional assets without page reloads.
 * @module live_stream
 */

export class LiveMarketStream {
  constructor(options = {}) {
    this.ws = null;
    this.reconnectTimer = null;
    this.pollTimer = null;
    this.isConnected = false;
    this.tickCount = 0;
    this.lastTickTime = null;
    this.onPriceUpdate = options.onPriceUpdate || null;
    this.pollIntervalMs = options.pollIntervalMs || 30000; // 30s for non-crypto assets
  }

  /**
   * Initializes the browser-side WebSocket and starts live streaming.
   * @param {Array} symbolsList - List of current symbols tracked by dashboard
   */
  init(symbolsList = []) {
    this.symbols = symbolsList;
    this.connectBinanceWs();
    this.startBackgroundPoller();
  }

  connectBinanceWs() {
    if (this.ws) {
      try {
        this.ws.close();
      } catch (e) {}
    }

    // Connect to Binance Combined MiniTicker Stream for 24/7 sub-second price updates
    const wsUrl = 'wss://stream.binance.com:9443/ws/!miniTicker@arr';
    try {
      this.ws = new WebSocket(wsUrl);
    } catch (err) {
      console.warn('[LiveMarketStream] WebSocket instantiation failed:', err);
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.isConnected = true;
      console.info('[LiveMarketStream] ⚡ Connected to Binance Live WebSocket stream');
      this.updateLiveIndicator(true);
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (Array.isArray(data)) {
          this.handleMiniTickerBatch(data);
        }
      } catch (err) {
        console.debug('[LiveMarketStream] Message parse error:', err);
      }
    };

    this.ws.onerror = (err) => {
      console.warn('[LiveMarketStream] WebSocket error:', err);
      this.updateLiveIndicator(false);
    };

    this.ws.onclose = () => {
      this.isConnected = false;
      this.updateLiveIndicator(false);
      this.scheduleReconnect();
    };
  }

  scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      console.info('[LiveMarketStream] Attempting WebSocket reconnect...');
      this.connectBinanceWs();
    }, 5000);
  }

  handleMiniTickerBatch(tickers) {
    if (!Array.isArray(tickers)) return;
    let anyUpdated = false;

    // Fast mapping lookup
    const tickerMap = new Map();
    for (let i = 0; i < tickers.length; i++) {
      tickerMap.set(tickers[i].s, tickers[i]);
    }

    if (!window.allSymbols) return;

    for (let i = 0; i < window.allSymbols.length; i++) {
      const item = window.allSymbols[i];
      if (item.asset_class !== 'crypto') continue;

      const sym = item.ticker;
      if (tickerMap.has(sym)) {
        const tick = tickerMap.get(sym);
        const newPrice = parseFloat(tick.c);
        const high24h = parseFloat(tick.h);
        const low24h = parseFloat(tick.l);

        if (newPrice && newPrice > 0 && Math.abs(newPrice - (item.price || 0)) > 1e-6) {
          const oldPrice = item.price;
          item.price = newPrice;
          item.price_direction = newPrice > oldPrice ? 'up' : 'down';
          this.tickCount++;
          this.lastTickTime = new Date();
          anyUpdated = true;

          // Dynamically compute live ribbon & Mark-to-market MoS %
          this.recalculateLiveRibbonAndMetrics(item, newPrice, high24h, low24h);
        }
      }
    }

    if (anyUpdated && typeof this.onPriceUpdate === 'function') {
      this.onPriceUpdate();
    }
  }

  /**
   * Recalculates intraday SMMA ribbon approximation and live fundamental discount.
   */
  recalculateLiveRibbonAndMetrics(item, price, high, low) {
    // 1. Live SMMA approximation using recurrence formula
    // hl2_live = (High + Low) / 2
    const hl2 = high && low ? (high + low) / 2.0 : price;
    if (item.v1 && item.v2) {
      // Recurrent step on 15 and 29 periods
      const v1_live = (item.v1 * 14.0 + hl2) / 15.0;
      const v2_live = (item.v2 * 28.0 + hl2) / 29.0;
      item.v1_live = v1_live;
      item.v2_live = v2_live;
      if (v2_live > 0) {
        item.spread_pct = parseFloat((((v1_live - v2_live) / v2_live) * 100.0).toFixed(2));
      }
    }

    // 2. Mark-to-Market MoS% and Upside%
    if (item.fundamental && item.fundamental.fair_value && item.fundamental.fair_value > 0) {
      const fv = item.fundamental.fair_value;
      item.fundamental.mos_pct = parseFloat((((fv - price) / fv) * 100.0).toFixed(1));
      item.fundamental.upside_pct = parseFloat((((fv - price) / price) * 100.0).toFixed(1));
    }
  }

  /**
   * Background polling for non-crypto assets or GitHub Pages deployment state check.
   */
  startBackgroundPoller() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(async () => {
      try {
        // Try local or cloud API first if available
        let apiQuotes = null;
        try {
          const res = await fetch('/api/live-quotes', { cache: 'no-store' });
          if (res.ok) {
            const data = await res.json();
            if (data.success && data.quotes) {
              apiQuotes = data.quotes;
            }
          }
        } catch (e) {}

        if (apiQuotes && window.allSymbols) {
          const qMap = new Map();
          apiQuotes.forEach(q => qMap.set(q.ticker, q));

          let updated = false;
          window.allSymbols.forEach(item => {
            if (qMap.has(item.ticker)) {
              const q = qMap.get(item.ticker);
              if (q.price && Math.abs(q.price - (item.price || 0)) > 1e-4) {
                item.price = q.price;
                item.state = q.state;
                item.spread_pct = q.spread_pct;
                updated = true;
              }
            }
          });
          if (updated && typeof this.onPriceUpdate === 'function') {
            this.onPriceUpdate();
          }
        }
      } catch (err) {
        console.debug('[LiveMarketStream] Poll error:', err);
      }
    }, this.pollIntervalMs);
  }

  updateLiveIndicator(isWsOnline) {
    const badge = document.getElementById('systemStatusText');
    if (!badge) return;
    if (isWsOnline) {
      badge.innerHTML = `🟢 НА ЖИВО • Binance WS (${this.tickCount > 0 ? this.tickCount + ' тика' : 'Активен'})`;
    }
  }

  destroy() {
    if (this.ws) {
      try {
        this.ws.close();
      } catch (e) {}
    }
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.pollTimer) clearInterval(this.pollTimer);
  }
}
