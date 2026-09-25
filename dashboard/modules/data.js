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
   * Tries /api/state or data/state.json, falling back to data.json.
   */
  async loadState() {
    this.isLoading = true;
    try {
      // 1. Try dedicated split state endpoint/file
      let resp = await fetch('data/state.json?t=' + Date.now()).catch(() => null);
      if (!resp || !resp.ok) {
        resp = await fetch('/api/state').catch(() => null);
      }
      // 2. Fallback to monolithic data.json
      if (!resp || !resp.ok) {
        resp = await fetch('data.json?t=' + Date.now());
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
  async loadFundamentals() {
    if (this.fundamentals) return this.fundamentals;

    try {
      let resp = await fetch('data/fundamentals.json?t=' + Date.now()).catch(() => null);
      if (!resp || !resp.ok) {
        resp = await fetch('/api/fundamentals').catch(() => null);
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
    return {};
  }

  /**
   * Lazy-loads historical trade journals, performance attribution, and correlation.
   */
  async loadHistory() {
    if (this.history) return this.history;

    try {
      let resp = await fetch('data/history.json?t=' + Date.now()).catch(() => null);
      if (!resp || !resp.ok) {
        resp = await fetch('/api/history').catch(() => null);
      }
      if (resp && resp.ok) {
        const data = await resp.json();
        this.history = data;
        return this.history;
      }
    } catch (e) {
      console.warn('[DataLoader] Could not load split history:', e);
    }

    return {
      trade_log: [],
      performance_attribution: this.state?.performance_attribution || {},
      correlation: this.state?.correlation || {},
    };
  }
}

export const dataLoader = new DataLoader();
