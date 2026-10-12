/* CAM Intelligence Platform — Stress test tab.
   Deterministic base / downside / severe-downside results (GET /api/cases/{id}/stress-test).
   No recommendation is made here.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camStress() {
  return {
    async loadStress() {
      const eid = this.detail?.entity_id;
      if (!eid) return;
      const runId = this.reportRunId || '';
      try {
        const q = runId ? '?run_id=' + encodeURIComponent(runId) : '';
        this.stressData = await this.api('cases/' + eid + '/stress-test' + q, undefined, { quiet: true });
      } catch { this.stressData = null; }
    },

    stress() { return this.stressData?.stress_test || {}; },

    stressScenarios() { return this.stress().scenarios || []; },

    stressSevCls(s) { return this.obsSevCls(s); },

    /* The four coverage and leverage measures a credit committee reads first. */
    stressKeyMetrics() {
      const keys = ['dscr', 'interest_coverage_ratio', 'debt_to_ebitda', 'ocf_to_debt_pct'];
      return (this.stress().metrics || []).filter(m => keys.includes(m.metric));
    },

    /* Credit implication: the reassessment's stress-resilience status, worded by the composed CAM. */
    stressImplication() {
      const dim = this.reas().overall_credit_assessment?.dimensions?.stress_resilience || {};
      return { status: dim.status || '', detail: dim.detail || '',
               text: this.fc().headline?.resilience_status === dim.status ? this.fc().headline?.resilience_implication || '' : '' };
    },

    stressAssumptionRows() {
      return [
        ['revenue_change_pct', 'Revenue', v => (v > 0 ? '+' : '') + v + '%'],
        ['margin_change_bps', 'EBITDA margin', v => (v > 0 ? '+' : '') + v + ' bps'],
        ['debtor_days_change', 'Debtor days', v => (v > 0 ? '+' : '') + v + ' days'],
        ['inventory_days_change', 'Inventory days', v => (v > 0 ? '+' : '') + v + ' days'],
        ['rate_shock_bps', 'Interest rate', v => (v > 0 ? '+' : '') + v + ' bps'],
      ];
    },

    stressValue(v, unit) {
      if (v === null || v === undefined) return '--';
      if (unit === 'cr') return (v < 0 ? '-Rs. ' : 'Rs. ') + Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 2 }) + ' Cr';
      if (unit === 'pct') return Number(v).toFixed(1) + '%';
      if (unit === 'days') return Number(v).toFixed(1) + ' days';
      if (unit === 'x') return Number(v).toFixed(2) + 'x';
      return String(v);
    },

    stressPolicy(metric) {
      const c = (this.stress().policy_checks || []).find(p => p.metric === metric);
      if (!c || c.limit === null || c.limit === undefined) return '--';
      return (c.limit_type === 'min' ? '≥ ' : '≤ ') + c.limit;
    },

    stressBreached(s, metric) { return (s.policy_breaches || []).some(b => b.metric === metric); },

    stressNewBreach(s, metric) { return (s.new_breaches || []).includes(metric); },

    stressChange(s, metric, unit) {
      const d = s.change_vs_base?.[metric];
      if (s.scenario === 'base' || d === null || d === undefined || d === 0) return '';
      const sign = d > 0 ? '+' : '';
      if (unit === 'cr') return sign + d.toLocaleString('en-IN', { maximumFractionDigits: 2 });
      return sign + (unit === 'x' ? d.toFixed(2) : d.toFixed(1));
    },
  };
}
