/* CAM Intelligence Platform — Settings: LLM provider, engines, benchmarks and rules.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camSettings() {
  return {
    /* ─── Config ───────────────────────────────────────────────────── */
    async loadConfig() {
      this.cfg = await this.api('config');
      const sectors = Object.keys(this.cfg.benchmarks?.sectors || {});
      if (sectors.length && !this.cfgSector) this.cfgSector = sectors[0];
      this.loadBenchmarkSector();
    },

    loadBenchmarkSector() {
      const s = this.cfg.benchmarks?.sectors?.[this.cfgSector];
      // deep clone so edits don't mutate original until save
      this.cfgSectorData = s ? JSON.parse(JSON.stringify(s)) : null;
    },

    async saveBenchmarks() {
      if (!this.cfgSectorData) return;
      this.cfg.benchmarks.sectors[this.cfgSector] = this.cfgSectorData;
      await this.api('config/benchmarks', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.cfg.benchmarks),
      });
      this.notify('Benchmarks saved for ' + this.cfgSector, 'ok');
    },

    async saveRules() {
      await this.api('config/rules', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.cfg.rules),
      });
      this.notify('Rules saved', 'ok');
    },

    /* ─── LLM ──────────────────────────────────────────────────────── */
    async loadLLM() {
      const r = await this.api('llm/providers');
      this.llmProviders = r.providers || [];
      this.llmActive = r.active_provider || 'mock';
      this.narrativeMode = r.narrative_mode || 'template';
      this.activeProvider = this.llmActive;
    },

    async setLLM() {
      await this.api('llm/active', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: this.llmActive, narrative_mode: this.narrativeMode }),
      });
      this.activeProvider = this.llmActive;
      this.notify('LLM set to ' + this.llmActive + ' / ' + this.narrativeMode, 'ok');
    },

    async testLLM() {
      this.llmTestResult = 'Testing…';
      const r = await this.api('llm/test', { method: 'POST' });
      this.llmTestResult = r.status === 'ok' ? 'Connected' : ('Error: ' + (r.message || 'unknown'));
    },

    /* ─── Engines ──────────────────────────────────────────────────── */
    async loadEngines() {
      const r = await this.api('engines');
      this.engines = r.engines || [];
    },

    async toggleEngine(name) {
      await this.api('engines/' + name + '/toggle', { method: 'PUT' });
      await this.loadEngines();
    },

    configFieldType(value) {
      if (Array.isArray(value)) return 'list';
      if (value && typeof value === 'object') return 'object';
      if (typeof value === 'boolean') return 'boolean';
      if (typeof value === 'number') return 'number';
      return 'text';
    },

    configFieldValue(value) {
      if (Array.isArray(value)) return value.join(', ');
      if (value == null) return '';
      return String(value);
    },

    applyConfigInput(container, key, rawValue) {
      if (!container || !(key in container)) return;
      const current = container[key];
      if (Array.isArray(current)) {
        const parts = String(rawValue || '')
          .split(',')
          .map(v => v.trim())
          .filter(Boolean);
        const numeric = current.every(v => typeof v === 'number');
        container[key] = numeric
          ? parts.map(v => Number(v)).filter(v => !Number.isNaN(v))
          : parts;
        return;
      }
      if (typeof current === 'number') {
        if (rawValue === '') {
          container[key] = '';
          return;
        }
        const parsed = Number(rawValue);
        if (!Number.isNaN(parsed)) container[key] = parsed;
        return;
      }
      container[key] = rawValue;
    },

    thresholdLabel(index) {
      return ['Lower Band', 'Mid Band', 'Upper Band'][index] || ('Band ' + (index + 1));
    },
  };
}
