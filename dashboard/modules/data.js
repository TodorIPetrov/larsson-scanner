/**
 * Data Loader & State Management Module for Larsson Scanner.
 * Supports split payloads (state.json, fundamentals.json, history.json)
 * with transparent fallback to monolithic data.json.
 * @module data
 */

export class DataLoader {
  constructor() {
    this.state = null;
    this.fundamentals = null;
    this.history = null;
    this.isLoading = false;
    this.lastUpdated = null;
  }

  /**
   * Loads the primary state data (fast initial payload).
   * Tries data/state.json or /api/state, falling back to data.json.
   */
  async loadState() {
    this.isLoading = true;
    try {
      // 1. Try dedicated split state endpoint/file (bypass HTTP cache)
      let resp = await fetch('data/state.json?t=' + Date.now(), { cache: 'no-store' }).catch(() => null);
      if (!resp || !resp.ok) {
        resp = await fetch('/api/state?t=' + Date.now(), { cache: 'no-store' }).catch(() => null);
      }
      // 2. Fallback to monolithic data.json
      if (!resp || !resp.ok) {
        resp = await fetch('data.json?t=' + Date.now(), { cache: 'no-store' });
      }

      if (!resp.ok) {
        throw new Error(`HTTP error ${resp.status}`);
      }

      const data = await resp.json();
      this.state = data;
      this.lastUpdated = data.generated_at ? new Date(data.generated_at) : new Date();
      return data;
    } finally {
      this.isLoading = false;
    }
  }

  /**
   * Lazy-loads fundamental profiles (DCF memos, moat ratings).
   */
  async loadFundamentals(force = false) {
    if (!force && this.fundamentals) return this.fundamentals;

    try {
      let resp = await fetch('data/fundamentals.json?t=' + Date.now(), { cache: 'no-store' }).catch(() => null);
      if (!resp || !resp.ok) {
        resp = await fetch('/api/fundamentals?t=' + Date.now(), { cache: 'no-store' }).catch(() => null);
      }
      if (resp && resp.ok) {
        const data = await resp.json();
        this.fundamentals = data.fundamental_profiles || data;
        return this.fundamentals;
      }
    } catch (e) {
      console.warn('[DataLoader] Could not load split fundamentals, falling back to state:', e);
    }

    // Fallback: check if profiles are present in main state
    if (this.state && this.state.fundamental_profiles) {
      this.fundamentals = this.state.fundamental_profiles;
      return this.fundamentals;
    }
    return this.fundamentals || {};
  }

  /**
   * Lazy-loads historical trade journals, performance attribution, and correlation.
   */
  async loadHistory(force = false) {
    if (!force && this.history) return this.history;

    try {
      let resp = await fetch('data/history.json?t=' + Date.now(), { cache: 'no-store' }).catch(() => null);
      if (!resp || !resp.ok) {
        resp = await fetch('/api/history?t=' + Date.now(), { cache: 'no-store' }).catch(() => null);
      }
      if (resp && resp.ok) {
        const data = await resp.json();
        this.history = data;
        return this.history;
      }
    } catch (e) {
      console.warn('[DataLoader] Could not load split history:', e);
    }

    return this.history || {
      trade_log: [],
      performance_attribution: this.state?.performance_attribution || {},
      correlation: this.state?.correlation || {},
    };
  }
}

export const dataLoader = new DataLoader();
