/* CAM Intelligence Platform — Summary view: the executive (GM / Head of Bank) portfolio
   view built from GET /api/dashboard → portfolio (one row per borrower).
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

const SUMMARY_GRADES = ['A', 'B', 'C', 'D', 'E'];
const SUMMARY_STATUSES = ['draft', 'submitted', 'returned_for_rework', 'approved', 'rejected'];
const DAY_MS = 86400000;

function camSummary() {
  return {
    /* Active table filter: { type, value, label }. Tiles, chips and bars all set it. */
    summaryFilter: { type: 'all' },
    summaryLoadedAt: null,
    summaryPreview: null,   /* portfolio row shown in the side panel */

    async loadSummary() {
      this.dash = await this.api('dashboard');
      this.summaryLoadedAt = new Date();
    },

    /* ─── Row classification ─── */
    summaryRows() {
      return this.dash.portfolio || [];
    },

    hasCase(row) {
      return !!row.workflow_status;
    },

    isHighRisk(row) {
      return ['D', 'E'].includes(row.risk_grade) || row.recommendation === 'decline';
    },

    lastRunStatus(row) {
      return row.last_run?.status || '';
    },

    daysSince(timestamp) {
      const t = timestamp ? new Date(timestamp).getTime() : NaN;
      return Number.isNaN(t) ? null : Math.max(0, Math.floor((Date.now() - t) / DAY_MS));
    },

    ageLabel(timestamp) {
      const days = this.daysSince(timestamp);
      if (days === null) return '--';
      if (days === 0) return 'Today';
      return days === 1 ? '1 day ago' : days + ' days ago';
    },

    /* Submitted cases waiting longer than the decision TAT (isOverdue in approvals.js). */
    isRowOverdue(row) {
      return row.workflow_status === 'submitted' && this.isOverdue(row.workflow_updated_at);
    },

    overdueCount() {
      return this.summaryRows().filter(row => this.isRowOverdue(row)).length;
    },

    isThisMonth(timestamp) {
      const d = timestamp ? new Date(timestamp) : null;
      const now = new Date();
      return !!d && !Number.isNaN(d.getTime()) && d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
    },

    sumAmount(rows) {
      return rows.reduce((total, row) => total + Number(row.requested_amount_cr || 0), 0);
    },

    /* Filter predicates, shared by the tiles, the chips and the table. */
    summaryMatches(row, filter) {
      switch (filter.type) {
        case 'cases': return this.hasCase(row);
        case 'awaiting': return row.workflow_status === 'submitted';
        case 'overdue': return this.isRowOverdue(row);
        case 'approved': return row.workflow_status === 'approved';
        case 'high_risk': return this.hasCase(row) && this.isHighRisk(row);
        case 'returned': return row.workflow_status === 'returned_for_rework';
        case 'failed': return this.lastRunStatus(row) === 'failed';
        case 'grade': return this.hasCase(row) && (row.risk_grade || 'N/A') === filter.value;
        case 'status': return row.workflow_status === filter.value;
        case 'sector': return this.hasCase(row) && (row.sector || 'other') === filter.value;
        default: return true;
      }
    },

    rowsWhere(type) {
      return this.summaryRows().filter(row => this.summaryMatches(row, { type }));
    },

    /* ─── Headline tiles ─── */
    summaryKpis() {
      const cases = this.rowsWhere('cases');
      const awaiting = this.rowsWhere('awaiting');
      const approved = this.rowsWhere('approved');
      const highRisk = this.rowsWhere('high_risk');
      const oldest = Math.max(0, ...awaiting.map(row => this.daysSince(row.workflow_updated_at) || 0));
      const overdue = awaiting.filter(row => this.isRowOverdue(row)).length;
      const thisMonth = cases.filter(row => this.isThisMonth(row.run_at)).length;
      return [
        { type: 'cases', label: 'Proposals', figure: cases.length,
          sub: this.formatCurrencyCr(this.sumAmount(cases)) + ' requested · ' + thisMonth + ' analysed this month' },
        { type: 'awaiting', label: 'Awaiting decision', figure: awaiting.length,
          tone: overdue ? 'red' : (awaiting.length ? 'blue' : ''),
          sub: awaiting.length
            ? this.formatCurrencyCr(this.sumAmount(awaiting)) + ' · '
              + (overdue ? overdue + ' past ' + this.decisionTatDays + '-day TAT' : 'oldest ' + (oldest === 1 ? '1 day' : oldest + ' days'))
            : 'Nothing pending' },
        { type: 'approved', label: 'Approved', figure: approved.length, tone: 'green',
          sub: this.formatCurrencyCr(this.sumAmount(approved)) },
        { type: 'high_risk', label: 'High risk', figure: highRisk.length, tone: highRisk.length ? 'red' : '',
          sub: highRisk.length ? this.formatCurrencyCr(this.sumAmount(highRisk)) + ' · grade D–E or decline' : 'None flagged' },
        { type: null, label: 'Avg risk score', figure: this.weightedScore(cases), sub: 'Weighted by amount' },
      ];
    },

    weightedScore(rows) {
      const scored = rows.filter(row => Number(row.composite_score) > 0);
      if (!scored.length) return '--';
      const weight = row => Number(row.requested_amount_cr) || 1;
      const total = scored.reduce((sum, row) => sum + weight(row), 0);
      return (scored.reduce((sum, row) => sum + Number(row.composite_score) * weight(row), 0) / total).toFixed(1);
    },

    /* ─── Breakdown panels (bars sized by amount) ─── */
    barList(groups, type, labelFor, toneFor) {
      const max = Math.max(1, ...groups.map(g => g.amount));
      return groups.map(g => ({
        ...g,
        label: labelFor(g.key),
        tone: toneFor(g.key),
        pct: Math.round((g.amount / max) * 100),
        filter: { type, value: g.key, label: labelFor(g.key) },
      }));
    },

    groupBy(rows, keyFor) {
      const groups = {};
      for (const row of rows) {
        const key = keyFor(row);
        groups[key] = groups[key] || { key, count: 0, amount: 0 };
        groups[key].count += 1;
        groups[key].amount += Number(row.requested_amount_cr || 0);
      }
      return groups;
    },

    gradeBars() {
      const groups = this.groupBy(this.rowsWhere('cases'), row => row.risk_grade || 'N/A');
      const keys = [...SUMMARY_GRADES, ...Object.keys(groups).filter(k => !SUMMARY_GRADES.includes(k))];
      return this.barList(keys.map(k => groups[k] || { key: k, count: 0, amount: 0 }), 'grade',
        k => 'Grade ' + k, k => ({ A: 'green', B: 'blue', C: 'amber' })[k] || (k === 'N/A' ? 'grey' : 'red'));
    },

    statusBars() {
      const groups = this.groupBy(this.rowsWhere('cases'), row => row.workflow_status);
      return this.barList(SUMMARY_STATUSES.map(k => groups[k] || { key: k, count: 0, amount: 0 }), 'status',
        k => this.workflowLabel(k), k => this.workflowTone(k));
    },

    sectorBars() {
      const groups = Object.values(this.groupBy(this.rowsWhere('cases'), row => row.sector || 'other'))
        .sort((a, b) => b.amount - a.amount)
        .slice(0, 6);
      return this.barList(groups, 'sector', k => this.titleCase(k), () => 'accent');
    },

    /* ─── Attention table ─── */
    summaryChips() {
      return [
        { type: 'all', label: 'All' },
        { type: 'awaiting', label: 'Awaiting decision' },
        { type: 'overdue', label: 'Overdue' },
        { type: 'high_risk', label: 'High risk' },
        { type: 'returned', label: 'Returned' },
        { type: 'failed', label: 'Run failed' },
      ].map(chip => ({ ...chip, count: chip.type === 'all' ? this.summaryRows().length : this.rowsWhere(chip.type).length }));
    },

    setSummaryFilter(filter) {
      this.summaryFilter = filter.type === 'all' ? { type: 'all' } : filter;
    },

    isSummaryFilter(filter) {
      if (!filter.type) return false;
      const active = this.summaryFilter;
      return active.type === filter.type && (active.value || '') === (filter.value || '');
    },

    /* Chips name the common filters; a tile or bar filter (grade, sector, ...) shows as its own chip. */
    summaryExtraFilter() {
      const chipTypes = this.summaryChips().map(chip => chip.type);
      if (chipTypes.includes(this.summaryFilter.type)) return null;
      return this.summaryFilter.label
        || ({ cases: 'All proposals', approved: 'Approved' })[this.summaryFilter.type]
        || this.titleCase(this.summaryFilter.type);
    },

    /* Most urgent first: awaiting decision (oldest first), failed runs, returned, high risk, the rest. */
    summaryPriority(row) {
      if (row.workflow_status === 'submitted') return 0;
      if (this.lastRunStatus(row) === 'failed') return 1;
      if (row.workflow_status === 'returned_for_rework') return 2;
      if (this.hasCase(row) && this.isHighRisk(row)) return 3;
      if (row.workflow_status === 'draft') return 4;
      return 5;
    },

    summaryTableRows() {
      const time = row => new Date(row.workflow_updated_at || row.run_at || row.last_run?.started_at || 0).getTime() || 0;
      const rows = this.summaryRows()
        .filter(row => this.summaryMatches(row, this.summaryFilter))
        .sort((a, b) => {
          const byPriority = this.summaryPriority(a) - this.summaryPriority(b);
          if (byPriority) return byPriority;
          // Awaiting decision: oldest first; everything else: most recent first.
          return a.workflow_status === 'submitted' ? time(a) - time(b) : time(b) - time(a);
        });
      // A clicked column header overrides the urgency order.
      return this.sortRows('summary', rows, this.summarySortAccessors());
    },

    summarySortAccessors() {
      return {
        borrower: row => this.displayCompanyName(row.company_name),
        facility: row => row.facility_type || '',
        amount: row => Number(row.requested_amount_cr) || 0,
        grade: row => row.risk_grade || '',
        score: row => (Number(row.composite_score) > 0 ? Number(row.composite_score) : null),
        view: row => this.fmtRec(row.recommendation),
        status: row => this.workflowLabel(row.workflow_status || ''),
        authority: row => row.required_authority || '',
        updated: row => new Date(this.summaryUpdatedAt(row) || 0).getTime() || null,
      };
    },

    exportSummaryCsv() {
      this.exportCsv('proposals_' + new Date().toISOString().slice(0, 10) + '.csv', [
        { label: 'Borrower', value: row => this.displayCompanyName(row.company_name) },
        { label: 'Entity ID', value: row => row.entity_id },
        { label: 'Sector', value: row => this.titleCase(row.sector) },
        { label: 'Case type', value: row => row.case_type || '' },
        { label: 'Facility', value: row => this.titleCase(row.facility_type) },
        { label: 'Amount (Rs Cr)', value: row => row.requested_amount_cr ?? '' },
        { label: 'Risk grade', value: row => row.risk_grade || '' },
        { label: 'Score', value: row => row.composite_score ?? '' },
        { label: 'System view', value: row => this.fmtRec(row.recommendation) },
        { label: 'Status', value: row => this.workflowLabel(row.workflow_status || '') },
        { label: 'Overdue', value: row => (this.isRowOverdue(row) ? 'Yes' : '') },
        { label: 'Sanctioning authority', value: row => row.required_authority || '' },
        { label: 'Last run', value: row => row.last_run?.status || '' },
        { label: 'Updated', value: row => this.summaryUpdatedAt(row) || '' },
      ], this.summaryTableRows());
    },

    printSummary() {
      this.closeSummaryPreview();
      this.$nextTick(() => window.print());
    },

    summaryUpdatedAt(row) {
      return row.workflow_updated_at || row.run_at || row.last_run?.started_at;
    },

    /* A row opens a side panel preview; the panel links on to the workspace. */
    openSummaryRow(row) {
      this.summaryPreview = row;
    },

    closeSummaryPreview() {
      this.summaryPreview = null;
    },

    /* Open the previewed borrower: its workspace tab, or Run CAM when it has no case yet. */
    openFromPreview(tab = 'overview') {
      const row = this.summaryPreview;
      this.summaryPreview = null;
      if (!row) return;
      if (this.hasCase(row)) return this.openWorkspace(row.entity_id, tab);
      this.pipelineTarget = row.entity_id;
      this.navigate('pipeline');
    },

    /* top_exception is a message, or an exception code when the check has no message. */
    issueText(value) {
      return /^[A-Z0-9_]+$/.test(String(value || '')) ? this.exceptionLabel(value) : this.presentationText(value);
    },

    /* Review indicators for the preview, from the case list (GET /api/cases). */
    previewCase() {
      return this.caseMap[this.summaryPreview?.entity_id] || {};
    },

    /* ─── Labels and colours ─── */
    workflowLabel(status) {
      return ({
        draft: 'Draft',
        submitted: 'Awaiting decision',
        returned_for_rework: 'Returned',
        approved: 'Approved',
        rejected: 'Rejected',
      })[status] || this.titleCase(status || '');
    },

    workflowTone(status) {
      return ({ submitted: 'blue', returned_for_rework: 'amber', approved: 'green', rejected: 'red' })[status] || 'grey';
    },

    workflowStatusClass(status) {
      return 'badge-' + this.workflowTone(status);
    },

    /* ─── Shared with the Pipeline page ─── */
    avgExecutedScore() {
      const scores = this.executedCompanies()
        .map(c => Number(this.caseMap[c.entity_id]?.composite_score))
        .filter(v => !Number.isNaN(v) && v > 0);
      if (!scores.length) return '0.0';
      return (scores.reduce((sum, v) => sum + v, 0) / scores.length).toFixed(1);
    },

    recommendationCount(type) {
      return this.executedCompanies().filter(c => this.caseMap[c.entity_id]?.recommendation === type).length;
    },

    modeCount(mode) {
      return this.executedCompanies().filter(c => (this.caseMap[c.entity_id]?.narrative_mode || 'template') === mode).length;
    },
  };
}
