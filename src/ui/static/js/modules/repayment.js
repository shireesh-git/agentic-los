/* CAM Intelligence Platform — Repayment & cash flow tab.
   Deterministic repayment assessment (GET /api/cases/{id}/repayment) with an optional
   AI explanation (POST …/repayment/explain). No forecasting or stress testing here.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camRepayment() {
  return {
    async loadRepayment() {
      const eid = this.detail?.entity_id;
      if (!eid) return;
      const runId = this.reportRunId || '';
      try {
        const q = runId ? '?run_id=' + encodeURIComponent(runId) : '';
        this.rpyData = await this.api('cases/' + eid + '/repayment' + q, undefined, { quiet: true });
      } catch { this.rpyData = null; }
    },

    rpy() { return this.rpyData?.assessment || {}; },

    rpyReadOnly() { return !this.rpyData?.is_latest_run; },

    rpyCapacityCls(level) {
      return { STRONG: 'badge-green', ADEQUATE: 'badge-blue', MODERATE: 'badge-amber', STRESSED: 'badge-red' }[level] || 'badge-grey';
    },

    rpyRiskCls(level) {
      return { LOW: 'badge-green', MODERATE: 'badge-amber', HIGH: 'badge-red', VERY_HIGH: 'badge-red' }[level] || 'badge-grey';
    },

    rpyAdequacyCls(level) {
      return { ADEQUATE: 'badge-green', PARTIAL: 'badge-amber', INADEQUATE: 'badge-red' }[level] || 'badge-grey';
    },

    rpyGradeCls(g) {
      return { strong: 'badge-green', adequate: 'badge-blue', weak: 'badge-amber', critical: 'badge-red' }[g] || 'badge-grey';
    },

    rpyValue(v, unit) {
      if (v === null || v === undefined) return '--';
      if (unit === 'cr') return (v < 0 ? '-Rs. ' : 'Rs. ') + Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 2 }) + ' Cr';
      if (unit === 'pct') return Number(v).toFixed(1) + '%';
      if (unit === 'x') return Number(v).toFixed(2) + 'x';
      return String(v);
    },

    /* Key financial indicators for the latest period, as computed by the repayment assessment. */
    rpyIndicators() {
      const wanted = ['ebitda_cr', 'operating_cash_flow_cr', 'total_debt_cr', 'debt_to_ebitda', 'interest_coverage_ratio',
                      'dscr', 'ocf_to_debt'];
      const metrics = this.rpy().key_metrics || [];
      return wanted.map(key => metrics.find(m => m.metric === key)).filter(Boolean)
        .map(m => ({ label: m.label, value: this.rpyValue(m.latest, m.unit), grade: m.grade, policy: this.rpyPolicy(m) }));
    },

    rpyPolicy(m) {
      if (m.policy === null || m.policy === undefined) return '--';
      return (m.metric === 'debt_to_ebitda' ? '≤ ' : '≥ ') + this.rpyValue(m.policy, m.unit);
    },

    rpySourceMetrics(src) {
      const labels = {
        operating_cash_flow_cr: ['Operating cash flow', 'cr'], ocf_to_ebitda_pct: ['OCF / EBITDA', 'pct'],
        ocf_to_interest: ['OCF / interest', 'x'], dscr: ['DSCR', 'x'], free_cash_flow_cr: ['Free cash flow', 'cr'],
        forced_sale_value_cr: ['Forced-sale value', 'cr'], fsv_cover: ['FSV cover', 'x'],
        hard_security_fsv_cr: ['Hard security (FSV)', 'cr'], hard_security_cover: ['Hard security cover', 'x'],
        facility_amount_cr: ['Facility', 'cr'],
      };
      return Object.entries(src?.metrics || {}).filter(([k]) => labels[k])
        .map(([k, v]) => ({ label: labels[k][0], value: this.rpyValue(v, labels[k][1]) }));
    },

    async explainRepayment() {
      if (this.rpyReadOnly() || this.rpyExplaining) return;
      this.rpyExplaining = true;
      try {
        const r = await this.api('cases/' + this.detail.entity_id + '/repayment/explain', { method: 'POST' });
        this.rpyData = { ...this.rpyData, assessment: r.assessment };
        this.notify(r.status === 'ok' ? 'AI explanation added' : 'AI explanation rejected (kept rule-based assessment)',
                    r.status === 'ok' ? 'ok' : 'error');
      } catch {} finally { this.rpyExplaining = false; }
    },
  };
}
