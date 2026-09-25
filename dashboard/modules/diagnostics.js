/**
 * Diagnostics & System Health Module for Larsson Scanner.
 * @module diagnostics
 */

export class SystemDiagnostics {
  constructor() {
    this.serverHealth = {
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
    this.timer = null;
  }

  async pollStatus() {
    try {
      const resp = await fetch('/api/status', { cache: 'no-store' });
      if (!resp.ok) throw new Error('Status endpoint returned ' + resp.status);
      const data = await resp.json();

      this.serverHealth = {
        isOnline: true,
        isScanning: data.is_scanning || false,
        scanDurationSec: data.scan_duration_sec || 0,
        symbolsInDb: data.symbols_in_db || 0,
        dbHealthy: data.db_healthy !== false,
        dataJsonExists: data.data_json_exists !== false,
        dataJsonSize: data.data_json_size || 0,
        dataJsonMtime: data.data_json_mtime || null,
        uptimeSec: data.uptime_sec || 0,
        lastPollTime: new Date(),
      };
      this.updatePillUI();
      return this.serverHealth;
    } catch (e) {
      this.serverHealth.isOnline = false;
      this.updatePillUI();
      return this.serverHealth;
    }
  }

  updatePillUI() {
    const dot = document.getElementById('systemStatusDot');
    const text = document.getElementById('systemStatusText');
    if (!dot || !text) return;

    if (!this.serverHealth.isOnline) {
      dot.className = 'status-indicator-dot offline';
      text.textContent = 'Офлайн (Static)';
      return;
    }

    if (this.serverHealth.isScanning) {
      dot.className = 'status-indicator-dot scanning';
      text.textContent = `Сканиране (${this.serverHealth.scanDurationSec}s)...`;
    } else {
      dot.className = 'status-indicator-dot online';
      text.textContent = 'Системата работи (Live)';
    }
  }

  startPolling(intervalMs = 5000) {
    this.pollStatus();
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(() => this.pollStatus(), intervalMs);
  }

  stopPolling() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}

export const diagnostics = new SystemDiagnostics();
