/* CAM Intelligence Platform — Cases list and case detail: summary tabs, extraction, ETB, risk checks,
   run history, downloads.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camCaseDetail() {
  return {
    /* ─── Cases list ───────────────────────────────────────────────── */
    /* Every borrower: analysed ones first (most recent run first), then the rest by name. */
    caseListRows() {
      const query = this.casesQuery.trim().toLowerCase();
      const matches = c => !query || [c.company_name, c.entity_id, c.sector]
        .some(value => String(value || '').toLowerCase().includes(query));
      const runAt = c => this.caseMap[c.entity_id]?.run_at || '';
      const rows = this.companies.filter(matches).sort((a, b) =>
        runAt(b).localeCompare(runAt(a)) || (a.company_name || '').localeCompare(b.company_name || ''));
      return this.sortRows('cases', rows, this.caseSortAccessors());
    },

    caseSortAccessors() {
      const kase = c => this.caseMap[c.entity_id] || {};
      return {
        borrower: c => this.displayCompanyName(c.company_name),
        type: c => c.case_type || '',
        amount: c => Number(c.requested_amount_cr) || 0,
        grade: c => kase(c).risk_grade || '',
        score: c => (Number(kase(c).composite_score) > 0 ? Number(kase(c).composite_score) : null),
        view: c => this.fmtRec(kase(c).recommendation),
        status: c => this.workflowLabel(this.portfolioRow(c.entity_id)?.workflow_status || ''),
        run: c => new Date(kase(c).run_at || 0).getTime() || null,
      };
    },

    exportCasesCsv() {
      const kase = c => this.caseMap[c.entity_id] || {};
      this.exportCsv('cases_' + new Date().toISOString().slice(0, 10) + '.csv', [
        { label: 'Borrower', value: c => this.displayCompanyName(c.company_name) },
        { label: 'Entity ID', value: c => c.entity_id },
        { label: 'Sector', value: c => this.titleCase(c.sector) },
        { label: 'Case type', value: c => c.case_type || '' },
        { label: 'Amount (Rs Cr)', value: c => c.requested_amount_cr ?? '' },
        { label: 'Risk grade', value: c => kase(c).risk_grade || '' },
        { label: 'Score', value: c => kase(c).composite_score ?? '' },
        { label: 'System view', value: c => this.fmtRec(kase(c).recommendation) },
        { label: 'Status', value: c => this.workflowLabel(this.portfolioRow(c.entity_id)?.workflow_status || '') || 'Not run' },
        { label: 'Last run', value: c => kase(c).run_at || '' },
      ], this.caseListRows());
    },

    /* Workflow status and latest run attempt, from the Summary payload (GET /api/dashboard). */
    portfolioRow(entityId) {
      return (this.dash.portfolio || []).find(row => row.entity_id === entityId) || null;
    },

    runCaseFromList(entityId) {
      this.pipelineTarget = entityId;
      this.navigate('pipeline');
      this.runPipelineSSE();
    },

    /* ─── Borrower workspace (#case/{id}/{tab}) ─────────────────────── */
    /* One place per borrower: the case (detail), its CAM and reports (reportEntity),
       its documents (docEntity) — all set to the same borrower here. */
    /* Tabs follow the credit process; ids are unchanged so existing links (#case/{id}/{tab}) keep working. */
    workspaceTabs() {
      return [
        { id: 'overview', label: 'Overview', group: '' },
        { id: 'observations', label: 'Risk Identification', group: 'Credit Assessment', count: this.obsCount(['CRITICAL', 'HIGH']) },
        { id: 'risk', label: 'Policy & Checks', group: 'Credit Assessment', count: (this.detail?.exceptions || []).length },
        { id: 'view360', label: 'Borrower 360°', group: 'Credit Assessment' },
        { id: 'investigations', label: 'Investigations', group: 'Due Diligence', count: this.invOpenCount() },
        { id: 'challenges', label: 'Credit Challenge', group: 'Due Diligence', count: this.chlOpenCount() },
        { id: 'repayment', label: 'Repayment', group: 'Repayment & Resilience' },
        { id: 'stress', label: 'Resilience', group: 'Repayment & Resilience' },
        { id: 'reassessment', label: 'Recommendation', group: 'Credit Decision' },
        { id: 'decision', label: 'Approval', group: 'Credit Decision' },
        { id: 'cam', label: 'CAM', group: 'CAM' },
        { id: 'memo', label: 'One-pager', group: 'CAM' },
        { id: 'documents', label: 'Documents', group: 'Workspace' },
        { id: 'chat', label: 'Ask AI', group: 'Workspace' },
        { id: 'runs', label: 'Runs', group: 'Workspace', count: this.reportRuns.length > 1 ? this.reportRuns.length : 0 },
      ];
    },

    /* The tabs as consecutive groups, for the grouped tab bar. */
    workspaceTabGroups() {
      const groups = [];
      for (const t of this.workspaceTabs()) {
        const last = groups[groups.length - 1];
        if (last && last.label === t.group) last.tabs.push(t);
        else groups.push({ label: t.group, tabs: [t] });
      }
      return groups;
    },

    viewCase(eid) {
      return this.openWorkspace(eid, 'overview');
    },

    /* runId opens an earlier run's CAM read-only ('' = latest run). */
    async openWorkspace(eid, tab = 'overview', runId = '') {
      if (!eid) return;
      this.loading = true;
      try {
        const detail = await this.api('cases/' + eid);
        if (this.detail?.entity_id !== eid) {
          this.detailExtraction = null;
          this.detailETB = null;
          this.detailFraud = null;
          this.detailPep = null;
          this.detailRuns = [];
          this._docLoadedFor = null;
          this.obsData = null;
          this.obsFor = null;
          this.obsExpanded = {};
          this.obsNoteDrafts = {};
          this.invData = null;
          this.invFor = null;
          this.invExpanded = {};
          this.invNoteDrafts = {};
          this.chlData = null;
          this.chlExpanded = {};
          this.chlResponseDrafts = {};
          this.rpyData = null;
          this.stressData = null;
          this.reasData = null;
          this.finalCamData = null;
          this.fcActive = 0;
          this.fcDrillOpen = {};
          this.ovShowWhy = false;
        }
        this.detail = detail;
        if (this.page !== 'detail') window.scrollTo({ top: 0 });
        this.page = 'detail';
        this.docEntity = eid;
        if (this.reportEntity !== eid) {
          this.reportEntity = eid;
          await this.onReportEntityChange();   // resets CAM/memo/360/chat/approval, loads runs
        } else {
          await this.loadReportRuns();
        }
        const latest = this.reportRuns.find(run => run.is_current);
        const wanted = runId && runId !== latest?.case_run_id ? runId : '';
        if (wanted !== this.reportRunId) {
          this.reportRunId = wanted;
          this.camSections = [];
          this.camHtml = '';
          this.memoHtml = '';
        }
        this.camEditMode = false;
        if (!(this.dash.portfolio || []).length) this.loadSummary();  // header status / authority
        this.loadWorkspaceExtras(eid);
        await this.setWorkspaceTab(tab);
      } catch {
        // No CAM has been run for this borrower yet (e.g. opened from an LOS application at Prospect
        // Sourcing): say so on the page and offer to run it, instead of leaving the previous page up.
        const company = (this.companies || []).find(c => c.entity_id === eid);
        this.noCase = { entity_id: eid, name: company?.company_name || company?.name || eid };
        window.scrollTo({ top: 0 });
        this.page = 'nocase';
      } finally { this.loading = false; }
    },

    /* Extracted figures and (ETB) account conduct, for the Documents tab; not awaited. */
    async loadWorkspaceExtras(eid) {
      this.loadObservations();   /* Overview card + tab count */
      this.loadInvestigations(); /* tab count */
      this.loadChallenges();     /* tab count */
      try { this.detailExtraction = await this.api('companies/' + eid + '/extraction', undefined, { quiet: true }); } catch {}
      if (this.isEtbCase()) {
        try { this.detailETB = await this.api('companies/' + eid + '/etb-analytics', undefined, { quiet: true }); } catch {}
      }
    },

    /* Show a tab and load its data the first time it is opened for this borrower. */
    async setWorkspaceTab(tab) {
      const eid = this.detail?.entity_id;
      if (!eid) return;
      if (!this.workspaceTabs().some(t => t.id === tab)) tab = 'overview';
      if (tab !== this.wtab) window.scrollTo({ top: 0 });  // a tab opens at its top
      this.wtab = tab;
      const hash = 'case/' + eid + (tab === 'overview' ? '' : '/' + tab);
      if (location.hash.slice(1) !== hash) location.hash = hash;
      /* The overview reads the composed CAM's headline, journey and decision trail (deterministic, re-synced). */
      if (tab === 'overview') await this.loadFinalCam();
      if (tab === 'cam') {
        if (this.camView === 'banker') await this.loadFinalCam();
        else if (!this.camSections.length && !this.camHtml) await this.loadCAMReport();
      }
      if (tab === 'memo' && !this.memoHtml) await this.loadOnePager();
      if (tab === 'view360' && this.view360Data?.entity_id !== eid) await this.load360();
      if (tab === 'risk' && !this.detailPep) await this.loadRiskChecks();
      if (tab === 'observations' && this.obsFor !== eid + '|' + (this.reportRunId || '')) await this.loadObservations();
      if (tab === 'investigations') await this.loadInvestigations();   /* always: observation changes re-plan tasks */
      if (tab === 'challenges') {                                      /* always: follows investigation status */
        await this.loadChallenges();
        this.loadReassessment();   /* impact of each challenge on the reassessment; not awaited */
      }
      if (tab === 'repayment') await this.loadRepayment();
      if (tab === 'stress') {                                          /* + the credit implication */
        await Promise.all([this.loadStress(), this.loadReassessment()]);
        if (!this.finalCamData) this.loadFinalCam();
      }
      if (tab === 'reassessment') {                                    /* always: follows analyst statuses */
        await this.loadReassessment();
        if (!this.finalCamData) this.loadFinalCam();   /* decision trail; not awaited */
      }
      if (tab === 'documents' && this._docLoadedFor !== eid) {
        this._docLoadedFor = eid;
        await this.loadDocumentWorkspace();
      }
      if (tab === 'chat') await this.loadChatHistory();
      if (tab === 'decision') await this.loadApproval();
      if (tab === 'runs') await this.loadRunHistory();
    },

    policyCounts() {
      const rules = this.detail?.tier1_decisions || [];
      return { total: rules.length, fail: rules.filter(rule => rule.result === 'fail').length,
               notVerified: rules.filter(rule => rule.result === 'not_verified').length };
    },

    isEtbCase() {
      return String(this.detail?.case_type || '').toUpperCase() === 'ETB';
    },

    workspaceSubtitle() {
      const d = this.detail || {};
      return [d.entity_id, this.titleCase(d.sector), this.caseTypeLabel(d.case_type), this.titleCase(d.facility_type)]
        .filter(value => value && value !== '--').join(' · ');
    },

    /* Workflow status and sanctioning authority for the header (Summary payload). */
    workspaceRow() {
      return this.portfolioRow(this.detail?.entity_id);
    },

    /* ─── Case Detail: Risk checks & run history ───────────────────── */
    async loadRiskChecks() {
      const eid = this.detail?.entity_id;
      if (!eid) return;
      // A stored fraud scan is optional (404 until the first run); PEP screening is computed on request.
      try { this.detailFraud = await this.api('companies/' + eid + '/fraud-analysis', undefined, { quiet: true }); }
      catch { this.detailFraud = null; }
      try { this.detailPep = await this.api('companies/' + eid + '/pep-screening'); }
      catch { this.detailPep = null; }
    },

    async runFraudForDetail() {
      const eid = this.detail?.entity_id;
      if (!eid) return;
      this.loading = true;
      try {
        this.detailFraud = await this.api('companies/' + eid + '/fraud-analysis', { method: 'POST' });
        this.notify('Fraud scan: ' + (this.detailFraud?.risk_grade || 'N/A'), 'ok');
      } catch {} finally { this.loading = false; }
    },

    async loadRunHistory() {
      const eid = this.detail?.entity_id;
      if (!eid) return;
      try { this.detailRuns = (await this.api('cases/' + eid + '/runs')).runs || []; }
      catch { this.detailRuns = []; }
    },

    runDuration(run) {
      if (run.status === 'running') return 'running…';
      const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
      return Number.isNaN(ms) || ms < 0 ? '--' : this.formatDuration(ms);
    },

    runStatusClass(status) {
      return ({ completed: 'badge-green', failed: 'badge-red', running: 'badge-amber' })[status] || 'badge-grey';
    },

    /* A completed run's own CAM PDF or one-pager (with that run's edits and comments). */
    runReportUrl(run, kind) {
      return '/api/cases/' + this.detail?.entity_id + '/' + kind + '?run_id=' + encodeURIComponent(run.case_run_id);
    },

    /* ─── Case Detail: Extraction & ETB ────────────────────────────── */
    async runExtractionForDetail() {
      if (!this.detail?.entity_id) return;
      this.loading = true;
      try {
        await this.api('companies/' + this.detail.entity_id + '/extract', { method: 'POST' });
        this.detailExtraction = await this.api('companies/' + this.detail.entity_id + '/extraction');
        this.notify('Extraction complete', 'ok');
      } catch {} finally { this.loading = false; }
    },

    async runETBForDetail() {
      if (!this.detail?.entity_id) return;
      this.loading = true;
      try {
        // Ensure extraction is done first
        if (!this.detailExtraction) {
          await this.api('companies/' + this.detail.entity_id + '/extract', { method: 'POST' });
          this.detailExtraction = await this.api('companies/' + this.detail.entity_id + '/extraction');
        }
        await this.api('companies/' + this.detail.entity_id + '/etb-analytics', { method: 'POST' });
        this.detailETB = await this.api('companies/' + this.detail.entity_id + '/etb-analytics');
        this.notify('ETB analysis complete', 'ok');
      } catch {} finally { this.loading = false; }
    },

    /* ─── Downloads ────────────────────────────────────────────────── */
    downloadJSON() {
      if (!this.detail?.fact_pack) return;
      this._download(this.detail.entity_id + '_factpack.json',
                     JSON.stringify(this.detail.fact_pack, null, 2), 'application/json');
    },

    _download(name, content, mime) {
      const blob = new Blob([content], { type: mime });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
    },
  };
}
