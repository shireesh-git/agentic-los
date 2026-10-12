/* CAM Intelligence Platform — Banker CAM (M7): the 12-section final CAM composed from the
   structured outputs (GET /api/cases/{id}/final-cam). The 21-section CAM stays as the analyst view.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camFinalCam() {
  const PROV = {
    source: ['S', 'Borrower / source data'], external: ['Ext', 'External verified data'],
    calculated: ['C', 'Deterministic calculation'],
    derived: ['R', 'Rule-based analysis'], synthetic_demo: ['Demo', 'Synthetic demo data (not verified)'],
    template: ['T', 'Reference / template text'], unavailable: ['N/A', 'Not available'], ai: ['AI', 'AI interpretation'],
  };
  // Workspace tabs that hold the detail behind each banker section.
  const DETAIL_TABS = {
    executive_summary: [['reassessment', 'Credit reassessment']],
    key_risks: [['observations', 'Risk identification'], ['investigations', 'Due diligence'], ['challenges', 'Credit challenge']],
    compliance_intelligence: [['investigations', 'Due diligence'], ['risk', 'Policy & checks']],
    financials_repayment: [['repayment', 'Repayment assessment']],
    projections_stress: [['stress', 'Resilience assessment']],
    facility_structure: [['reassessment', 'Credit reassessment']],
    final_recommendation: [['reassessment', 'Credit reassessment'], ['decision', 'Approval']],
  };

  return {
    async setCamView(view) {
      this.camView = view;
      if (view === 'banker') await this.loadFinalCam();
      else if (!this.camSections.length && !this.camHtml) await this.loadCAMReport();
    },

    async loadFinalCam() {
      if (!this.reportEntity) return;
      try {
        this.finalCamData = await this.api('cases/' + this.reportEntity + '/final-cam' + this.runQuery(), undefined, { quiet: true });
        if (this.fcActive >= this.fcSections().length) this.fcActive = 0;
      } catch { this.finalCamData = null; }
    },

    fc() { return this.finalCamData?.final_cam || {}; },

    fcSections() { return this.fc().sections || []; },

    fcSection() { return this.fcSections()[this.fcActive] || null; },

    /* The section's sub-headed blocks (older stored CAMs without blocks show as one block). */
    fcBlocks() {
      const s = this.fcSection();
      if (!s) return [];
      return s.blocks || [{ heading: null, statements: s.statements || [], facts: s.facts || [], tables: s.tables || [] }];
    },

    /* Synthetic demo data, gaps and AI text are always marked; the other basis tags show on request. */
    fcAlwaysTag(cls) { return ['synthetic_demo', 'unavailable', 'ai'].includes(cls); },

    fcReadOnly() { return !this.finalCamData?.is_latest_run; },

    provTag(cls) { return (PROV[cls] || [cls, cls])[0]; },

    provLabel(cls) { return (PROV[cls] || [cls, cls])[1]; },

    provLegend() { return Object.entries(PROV).map(([cls, [tag, label]]) => ({ cls, tag, label })); },

    fcDetailTabs(sectionId) { return DETAIL_TABS[sectionId] || []; },

    fcToggleDrill(i) { this.fcDrillOpen = { ...this.fcDrillOpen, [i]: !this.fcDrillOpen[i] }; },

    async interpretFinalCam(sectionIds = null) {
      if (this.fcReadOnly() || this.fcInterpreting) return;
      this.fcInterpreting = sectionIds ? sectionIds[0] : 'all';
      try {
        const r = await this.api('cases/' + this.reportEntity + '/final-cam/interpret', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ section_ids: sectionIds }),
        });
        this.finalCamData = { ...this.finalCamData, final_cam: r.final_cam };
        const results = Object.values(r.results || {});
        const ok = results.filter(x => x.status === 'ok').length;
        this.notify('AI interpretation: ' + ok + ' added' + (results.length - ok ? ', ' + (results.length - ok) + ' rejected' : ''),
                    ok ? 'ok' : 'error');
      } catch {} finally { this.fcInterpreting = null; }
    },

    openFinalCamNewTab() {
      if (this.reportEntity) window.open('/api/cases/' + this.reportEntity + '/final-cam-html' + this.runQuery(), '_blank');
    },
  };
}
