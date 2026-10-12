/* CAM Intelligence Platform — Investigations tab.
   Tasks are opened by the backend Investigation Agent from credit observations
   (GET /api/cases/{id}/investigations); the analyst moves them through
   OPEN → IN_PROGRESS → RESOLVED / WAIVED and can ask the LLM to draft the borrower request.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camInvestigations() {
  const STATUSES = ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'WAIVED'];

  return {
    invStatuses: STATUSES,

    async loadInvestigations() {
      const eid = this.detail?.entity_id;
      if (!eid) return;
      const runId = this.reportRunId || '';
      try {
        const q = runId ? '?run_id=' + encodeURIComponent(runId) : '';
        this.invData = await this.api('cases/' + eid + '/investigations' + q, undefined, { quiet: true });
        this.invFor = eid + '|' + runId;
      } catch { this.invData = null; this.invFor = null; }
    },

    invList() { return this.invData?.investigations || []; },

    invOpenCount() { return this.invList().filter(t => t.status === 'OPEN' || t.status === 'IN_PROGRESS').length; },

    invFiltered() {
      const open = t => t.status === 'OPEN' || t.status === 'IN_PROGRESS';
      return this.invList().filter(t => this.invShowAll || open(t))
        .sort((a, b) => a.priority.localeCompare(b.priority));
    },

    invReadOnly() { return !this.invData?.is_latest_run; },

    invPriorityCls(p) { return { P1: 'badge-red', P2: 'badge-amber', P3: 'badge-blue' }[p] || 'badge-grey'; },

    invPriorityLabel(p) {
      return { P1: 'P1 · before credit committee', P2: 'P2 · before sanction', P3: 'P3 · pre-disbursement condition' }[p] || p;
    },

    invStatusLabel(s) {
      return { OPEN: 'Open', IN_PROGRESS: 'In progress', RESOLVED: 'Resolved', WAIVED: 'Waived' }[s] || s;
    },

    invStatusCls(s) {
      return { OPEN: 'badge-amber', IN_PROGRESS: 'badge-blue', RESOLVED: 'badge-green', WAIVED: 'badge-grey' }[s] || 'badge-grey';
    },

    invObservation(id) { return this.invData?.observations?.[id] || {}; },

    /* Open the Credit observations tab with the linked observation expanded. */
    async openLinkedObservation(id) {
      await this.setWorkspaceTab('observations');
      this.obsFilterSeverity = '';
      this.obsFilterStatus = '';
      this.obsExpanded = { ...this.obsExpanded, [id]: true };
      this.$nextTick(() => {
        const card = document.querySelector('[data-obs-id="' + id + '"]');
        if (!card) return;
        card.scrollIntoView({ block: 'start' });
        window.scrollBy(0, -130);   /* clear the sticky workspace header */
      });
    },

    invToggle(id) { this.invExpanded = { ...this.invExpanded, [id]: !this.invExpanded[id] }; },

    async patchInvestigation(t, body, message) {
      if (this.invReadOnly()) return;
      try {
        const r = await this.api('cases/' + this.detail.entity_id + '/investigations/' + encodeURIComponent(t.investigation_id), {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        Object.assign(t, r.investigation);
        this.notify(message, 'ok');
        this.loadChallenges();   /* challenges follow investigation status */
      } catch { await this.loadInvestigations(); }
    },

    setInvestigationStatus(t, status) {
      return this.patchInvestigation(t, { status }, t.title + ': ' + this.invStatusLabel(status));
    },

    saveInvestigationNote(t) {
      const note = this.invNoteDrafts[t.investigation_id] ?? (t.review?.note || '');
      return this.patchInvestigation(t, { note }, 'Note saved');
    },

    /* LLM drafts the borrower request (all open tasks, or one). The task itself is unchanged. */
    async phraseInvestigations(ids = null) {
      if (this.invReadOnly() || this.invPhrasing) return;
      this.invPhrasing = ids ? ids[0] : 'all';
      try {
        const r = await this.api('cases/' + this.detail.entity_id + '/investigations/phrase', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ investigation_ids: ids }),
        });
        this.invData = { ...this.invData, investigations: r.investigations };
        const results = Object.values(r.results || {});
        const ok = results.filter(x => x.status === 'ok').length;
        const rejected = results.length - ok;
        this.notify('Borrower requests drafted: ' + ok + (rejected ? ', ' + rejected + ' rejected' : ''),
                    rejected && !ok ? 'error' : 'ok');
      } catch {} finally { this.invPhrasing = null; }
    },
  };
}
