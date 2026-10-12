/* CAM Intelligence Platform — Credit challenges tab.
   The backend Credit Challenge Agent questions the proposed facility
   (GET /api/cases/{id}/challenges); the analyst records the RM's response and
   whether each challenge is ADDRESSED, ACCEPTED or OVERRIDDEN. No decision is made here.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camChallenges() {
  const STATUSES = ['OPEN', 'ADDRESSED', 'ACCEPTED', 'OVERRIDDEN'];

  return {
    chlStatuses: STATUSES,

    async loadChallenges() {
      const eid = this.detail?.entity_id;
      if (!eid) return;
      const runId = this.reportRunId || '';
      try {
        const q = runId ? '?run_id=' + encodeURIComponent(runId) : '';
        this.chlData = await this.api('cases/' + eid + '/challenges' + q, undefined, { quiet: true });
      } catch { this.chlData = null; }
    },

    chlList() { return this.chlData?.challenges || []; },

    chlOpenCount() { return this.chlList().filter(c => c.status === 'OPEN').length; },

    chlFiltered() { return this.chlList().filter(c => this.chlShowAll || c.status === 'OPEN'); },

    chlReadOnly() { return !this.chlData?.is_latest_run; },

    chlStatusLabel(s) {
      return { OPEN: 'Open', ADDRESSED: 'Addressed', ACCEPTED: 'Risk accepted', OVERRIDDEN: 'Overridden' }[s] || s;
    },

    chlLink(id) { return this.chlData?.links?.[id] || {}; },

    chlValue(m) {
      const v = m.value;
      if (v === null || v === undefined) return '--';
      if (typeof v !== 'number') return String(v);
      if (m.unit === 'cr') return (v < 0 ? '-Rs. ' : 'Rs. ') + Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 2 }) + ' Cr';
      if (m.unit === 'pct') return v.toFixed(1) + '%';
      if (m.unit === 'days') return v.toFixed(1) + ' days';
      if (m.unit === 'x') return v.toFixed(2) + 'x';
      return String(v);
    },

    chlToggle(id) { this.chlExpanded = { ...this.chlExpanded, [id]: !this.chlExpanded[id] }; },

    /* How the challenge shows in the credit reassessment (when loaded): the risks it bears on and their status,
       and for facility-amount challenges the reassessed amount. Read from the reassessment; nothing computed. */
    chlImpact(c) {
      const r = this.reasData?.reassessment;
      if (!r?.available) return [];
      const out = (r.risk_register || []).filter(x => (x.challenge_ids || []).includes(c.challenge_id))
        .map(x => ({ text: x.title + ': ' + String(x.status).toLowerCase(), cls: this.reasRiskStatusCls(x.status) }));
      const fr = r.facility_recommendation || {};
      if (['Facility amount', 'Working-capital requirement'].includes(c.category) && fr.recommended_cr !== undefined)
        out.unshift({ text: 'Reassessed amount ' + this.reasAmount(fr.recommended_cr) + ' against ' + this.reasAmount(fr.requested_cr)
                      + ' requested', cls: this.reasDecisionCls(r.decision) });
      return out;
    },

    async openChallengeLink(id) {
      if (id.startsWith('INV-')) return this.setWorkspaceTab('investigations');
      return this.openLinkedObservation(id);
    },

    async patchChallenge(c, body, message) {
      if (this.chlReadOnly()) return;
      try {
        const r = await this.api('cases/' + this.detail.entity_id + '/challenges/' + encodeURIComponent(c.challenge_id), {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        Object.assign(c, r.challenge);
        this.notify(message, 'ok');
      } catch { await this.loadChallenges(); }
    },

    setChallengeStatus(c, status) { return this.patchChallenge(c, { status }, c.title + ': ' + this.chlStatusLabel(status)); },

    saveChallengeResponse(c) {
      const response = this.chlResponseDrafts[c.challenge_id] ?? (c.review?.response || '');
      return this.patchChallenge(c, { response }, 'Response saved');
    },

    /* LLM rewords challenges in committee language. Figures, severity and required response are unchanged. */
    async wordChallenges(ids = null) {
      if (this.chlReadOnly() || this.chlWording) return;
      this.chlWording = ids ? ids[0] : 'all';
      try {
        const r = await this.api('cases/' + this.detail.entity_id + '/challenges/word', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ challenge_ids: ids }),
        });
        this.chlData = { ...this.chlData, challenges: r.challenges };
        const results = Object.values(r.results || {});
        const ok = results.filter(x => x.status === 'ok').length;
        const rejected = results.length - ok;
        this.notify('AI wording: ' + ok + ' added' + (rejected ? ', ' + rejected + ' rejected (kept rule-based text)' : ''),
                    rejected && !ok ? 'error' : 'ok');
      } catch {} finally { this.chlWording = null; }
    },
  };
}
