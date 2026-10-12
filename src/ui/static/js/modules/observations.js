/* CAM Intelligence Platform — Credit observations tab and Overview card.
   Observations are detected deterministically by the backend (GET /api/cases/{id}/observations);
   the analyst sets a status, and can ask the LLM to word them (explanation only).
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camObservations() {
  const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
  const STATUSES = ['NEW', 'INVESTIGATION_REQUIRED', 'EXPLAINED', 'ACCEPTED', 'DISMISSED'];

  return {
    obsSeverities: SEVERITIES,
    obsStatuses: STATUSES,

    async loadObservations() {
      const eid = this.detail?.entity_id;
      if (!eid) return;
      const runId = this.reportRunId || '';
      try {
        const q = runId ? '?run_id=' + encodeURIComponent(runId) : '';
        this.obsData = await this.api('cases/' + eid + '/observations' + q, undefined, { quiet: true });
        this.obsFor = eid + '|' + runId;
      } catch { this.obsData = null; this.obsFor = null; }
    },

    obsList() { return this.obsData?.observations || []; },

    obsCount(severities) {
      const targets = Array.isArray(severities) ? severities : [severities];
      return this.obsList().filter(o => targets.includes(o.severity)).length;
    },

    obsFiltered() {
      return this.obsList().filter(o =>
        (!this.obsFilterSeverity || o.severity === this.obsFilterSeverity) &&
        (!this.obsFilterStatus || o.status === this.obsFilterStatus));
    },

    /* [{category, items, worst}] ordered by the most severe observation in each category. */
    obsGroups() {
      const groups = {};
      for (const o of this.obsFiltered()) (groups[o.category] ||= []).push(o);
      const rank = s => SEVERITIES.indexOf(s);
      return Object.entries(groups)
        .map(([category, items]) => ({ category, items, worst: items.reduce((w, o) => rank(o.severity) < rank(w) ? o.severity : w, 'INFO') }))
        .sort((a, b) => rank(a.worst) - rank(b.worst) || a.category.localeCompare(b.category));
    },

    obsSevCls(s) {
      return { CRITICAL: 'badge-red', HIGH: 'badge-amber', MEDIUM: 'badge-blue', LOW: 'badge-grey', INFO: 'badge-info' }[s] || 'badge-grey';
    },

    obsStatusLabel(s) {
      return { NEW: 'New', INVESTIGATION_REQUIRED: 'Investigation required', EXPLAINED: 'Explained',
               ACCEPTED: 'Accepted', DISMISSED: 'Dismissed' }[s] || s;
    },

    obsReadOnly() { return !this.obsData?.is_latest_run; },

    obsToggle(id) { this.obsExpanded = { ...this.obsExpanded, [id]: !this.obsExpanded[id] }; },

    /* A metric value in its unit: fraction → %, pct → %, x → 2 dp, days, Rs Cr, text as given. */
    obsValue(value, unit) {
      if (value === null || value === undefined || value === '') return '--';
      if (typeof value !== 'number') return String(value);
      switch (unit) {
        case 'fraction': return (value * 100).toFixed(1) + '%';
        case 'pct': return value.toFixed(1) + '%';
        case 'x': return value.toFixed(2) + 'x';
        case 'days': return value.toFixed(1) + ' days';
        case 'cr': return 'Rs. ' + value.toLocaleString('en-IN', { maximumFractionDigits: 2 }) + ' Cr';
        default: return String(value);
      }
    },

    obsChange(c) {
      if (c.change === null || c.change === undefined) return '--';
      const sign = c.change > 0 ? '+' : '';
      const unit = { pct: '%', pp: ' pp', bps: ' bps', x: 'x', days: ' days', score: '' }[c.change_unit] ?? '';
      return sign + (c.change_unit === 'bps' ? c.change : Number(c.change).toFixed(c.change_unit === 'x' ? 2 : 1)) + unit;
    },

    /* Unit of a comparison row's from / to values, from the metric name. */
    obsChangeUnit(c) {
      const m = c.metric || '';
      if (m.endsWith('_cr')) return 'cr';
      if (m.endsWith('_pct')) return 'pct';
      if (m.endsWith('_days')) return 'days';
      if (m === 'altman_z_score') return 'score';
      return 'x';
    },

    obsThresholds(o) {
      return Object.entries(o.trigger?.thresholds || {})
        .filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object')
        .map(([k, v]) => k.replace(/_/g, ' ') + ': ' + v).join(' · ');
    },

    async setObservationStatus(o, status) {
      if (this.obsReadOnly()) return;
      try {
        const r = await this.api('cases/' + this.detail.entity_id + '/observations/' + encodeURIComponent(o.observation_id), {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
        });
        Object.assign(o, r.observation);
        this.notify(o.title + ': ' + this.obsStatusLabel(status), 'ok');
        this.loadInvestigations();   /* tasks follow observation status */
      } catch { await this.loadObservations(); }
    },

    async saveObservationNote(o) {
      if (this.obsReadOnly()) return;
      const note = this.obsNoteDrafts[o.observation_id] ?? (o.review?.note || '');
      try {
        const r = await this.api('cases/' + this.detail.entity_id + '/observations/' + encodeURIComponent(o.observation_id), {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note }),
        });
        Object.assign(o, r.observation);
        this.notify('Note saved', 'ok');
      } catch {}
    },

    /* Ask the LLM to word observations (all, or one). Detection and severity are unchanged. */
    async explainObservations(ids = null) {
      if (this.obsReadOnly() || this.obsExplaining) return;
      this.obsExplaining = ids ? ids[0] : 'all';
      try {
        const r = await this.api('cases/' + this.detail.entity_id + '/observations/explain', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ observation_ids: ids }),
        });
        this.obsData = { ...this.obsData, observations: r.observations };
        const results = Object.values(r.results || {});
        const ok = results.filter(x => x.status === 'ok').length;
        const rejected = results.length - ok;
        this.notify('AI explanations: ' + ok + ' added' + (rejected ? ', ' + rejected + ' rejected (kept rule-based text)' : ''),
                    rejected && !ok ? 'error' : 'ok');
      } catch {} finally { this.obsExplaining = null; }
    },
  };
}
