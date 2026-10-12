/* CAM Intelligence Platform — Reassessment tab.
   The Credit Reassessment Agent's view of the proposal after observations, investigations,
   challenges, repayment and stress testing (GET /api/cases/{id}/reassessment). Deterministic.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camReassessment() {
  return {
    async loadReassessment() {
      const eid = this.detail?.entity_id;
      if (!eid) return;
      const runId = this.reportRunId || '';
      try {
        const q = runId ? '?run_id=' + encodeURIComponent(runId) : '';
        this.reasData = await this.api('cases/' + eid + '/reassessment' + q, undefined, { quiet: true });
      } catch { this.reasData = null; }
    },

    reas() { return this.reasData?.reassessment || {}; },

    reasDecisionCls(d) {
      return { SUPPORTED: 'badge-green', SUPPORTED_WITH_CONDITIONS: 'badge-blue', REDUCED_MODIFIED: 'badge-amber',
               DEFERRED: 'badge-grey', NOT_SUPPORTED: 'badge-red' }[d] || 'badge-grey';
    },

    reasRiskStatusCls(s) { return { RESOLVED: 'badge-green', MITIGATED: 'badge-blue', UNRESOLVED: 'badge-red' }[s] || 'badge-grey'; },

    reasDimStatusCls(s) {
      const v = String(s || '');
      if (/WITHIN|SOUND|RESILIENT|ADEQUATE|STRONG|NONE/.test(v)) return 'badge-green';
      if (/WEAK|MODERATE|DOWNSIDE/.test(v)) return 'badge-amber';
      return 'badge-red';
    },

    reasDimLabel(key) {
      return { repayment_capacity: 'Repayment capacity', stress_resilience: 'Stress resilience', leverage: 'Leverage',
               liquidity: 'Liquidity', cash_flow: 'Cash flow', policy_exceptions: 'Policy exceptions' }[key] || key;
    },

    reasAmount(v) {
      if (v === null || v === undefined) return '--';
      return (v < 0 ? '-Rs. ' : 'Rs. ') + Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 2 }) + ' Cr';
    },

    reasOpenIssue(issue) {
      return this.setWorkspaceTab(issue.type === 'investigation' ? 'investigations' : 'challenges');
    },
  };
}
