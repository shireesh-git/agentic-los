/* CAM Intelligence Platform — Borrower overview: the credit decision, the credit journey, key credit risks
   and the decision trail. A presentation layer over the composed CAM (GET /api/cases/{id}/final-cam: headline,
   journey, decision_trail) and the already-loaded observations / investigations / challenges. No figures are
   computed here; values are only formatted for display.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camOverview() {
  // Credit journey stage → the workspace tab that holds its detail.
  const STAGE_TABS = {
    credit_assessment: 'risk', risk_identification: 'observations', due_diligence: 'investigations',
    credit_challenge: 'challenges', repayment: 'repayment', resilience: 'stress', reassessment: 'reassessment',
    decision: 'reassessment', cam: 'cam',
  };
  const SEV_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 };

  return {
    ovHeadline() { return this.fc().headline || {}; },

    ovJourney() { return this.fc().journey || []; },

    ovTrail() { return this.fc().decision_trail || { steps: [] }; },

    ovStageTab(stage) { return STAGE_TABS[stage.id] || 'overview'; },

    ovStageIcon(status) { return { complete: '✓', attention: '!', unavailable: '–' }[status] || '–'; },

    ovStageTitle(stage) {
      return stage.label + ': ' + ({ complete: 'complete', attention: 'complete, needs attention',
                                     unavailable: 'not available' }[stage.status] || '') + ' — ' + stage.summary;
    },

    ovOpenStage(stage) {
      if (stage.status !== 'unavailable') this.setWorkspaceTab(this.ovStageTab(stage));
    },

    /* The most material risks: critical/high first, at most five. */
    ovKeyRisks() {
      return [...this.obsList()].sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)).slice(0, 5);
    },

    /* Supporting figures for a risk: its metrics for the latest period it reports (deterministic values). */
    ovRiskMetrics(o) {
      const metrics = o.metrics || [];
      const latest = metrics.map(m => m.period || '').sort().pop();
      return metrics.filter(m => (m.period || '') === latest).slice(0, 3)
        .map(m => String(m.label || m.metric).replace(/_/g, ' ') + ' ' + this.ovValue(m.value, m.unit) + (m.period ? ' (' + m.period + ')' : ''));
    },

    ovValue(v, unit) {
      if (v === null || v === undefined) return '--';
      if (unit === 'fraction') return (Number(v) * 100).toFixed(1) + '%';
      if (unit === 'days') return Number(v).toFixed(1) + ' days';
      return this.rpyValue(v, unit);
    },

    /* Due-diligence status for a risk: the investigation(s) opened from it. */
    ovRiskDiligence(o) {
      const tasks = this.invList().filter(t => t.observation_id === o.observation_id
        || (t.related_observation_ids || []).includes(o.observation_id));
      if (!tasks.length) return { label: 'No due diligence required', cls: 'badge-grey' };
      const open = tasks.filter(t => t.status === 'OPEN' || t.status === 'IN_PROGRESS');
      if (open.length) return { label: 'Due diligence ' + (open.some(t => t.status === 'IN_PROGRESS') ? 'in progress' : 'open'),
                                cls: 'badge-amber' };
      return { label: 'Due diligence ' + tasks.map(t => this.invStatusLabel(t.status).toLowerCase()).join(', '), cls: 'badge-green' };
    },

    ovDscr(scenario) {
      const v = this.ovHeadline().dscr_by_scenario?.[scenario];
      return v === null || v === undefined ? '--' : Number(v).toFixed(2) + 'x';
    },

    /* Whether the scenario breaches the DSCR policy minimum (from the resilience assessment's policy breaches). */
    ovDscrBreach(scenario) { return !!this.ovHeadline().dscr_breach_by_scenario?.[scenario]; },

    ovToggleWhy() { this.ovShowWhy = !this.ovShowWhy; },
  };
}
