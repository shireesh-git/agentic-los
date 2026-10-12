/* ═══════════════════════════════════════════════════════════════════════
   CAM Intelligence Platform — v2.0 (Alpine.js)
   ═══════════════════════════════════════════════════════════════════════ */

/* Company/case lists fetched within this window are reused when moving between pages. */
const NAV_CACHE_MS = 10000;

function camApp() {
  // Kept outside the reactive component: Alpine proxies component state, which breaks Promises.
  let companiesLoadedAt = 0;
  let companiesInflight = null;

  return {
    /* Page modules (src/ui/static/js/modules/*.js, loaded before this file). */
    ...camFormatters(),
    ...camShell(),
    ...camSummary(),
    ...camJourney(),
    ...camPipeline(),
    ...camCaseDetail(),
    ...camDocuments(),
    ...camReports(),
    ...camApprovals(),
    ...camObservations(),
    ...camInvestigations(),
    ...camChallenges(),
    ...camRepayment(),
    ...camStress(),
    ...camReassessment(),
    ...camFinalCam(),
    ...camOverview(),
    ...camSettings(),

    /* ─── Core State ───────────────────────────────────────────────── */
    page: 'summary',
    loading: false,

    /* Toast */
    toast: '',
    toastType: '',
    _toastTimer: null,

    /* Summary (GET /api/dashboard) */
    dash: {},

    /* Companies & Cases */
    companies: [],
    caseMap: {},
    casesQuery: '',

    /* Borrower workspace (#case/{id}/{tab}) */
    detail: null,
    wtab: 'overview',
    _docLoadedFor: null,   /* borrower whose Documents tab data is loaded */
    detailExtraction: null,
    detailETB: null,
    detailFraud: null,
    detailPep: null,
    detailRuns: [],
    /* Credit observations tab (modules/observations.js) */
    obsData: null,
    obsFor: null,          /* 'entity|runId' the loaded observations belong to */
    obsFilterSeverity: '',
    obsFilterStatus: '',
    obsExpanded: {},
    obsNoteDrafts: {},
    obsExplaining: null,
    /* Investigations tab (modules/investigations.js) */
    invData: null,
    invFor: null,
    invShowAll: false,
    invExpanded: {},
    invNoteDrafts: {},
    invPhrasing: null,
    /* Credit challenges tab (modules/challenges.js) */
    chlData: null,
    chlShowAll: false,
    chlExpanded: {},
    chlResponseDrafts: {},
    chlWording: null,
    /* Repayment & cash flow tab (modules/repayment.js) */
    rpyData: null,
    rpyExplaining: false,
    rpyShowReasoning: false,
    /* Stress test tab (modules/stress.js) */
    stressData: null,
    /* Reassessment tab (modules/reassessment.js) */
    reasData: null,
    /* Banker CAM (modules/finalcam.js): 'banker' = 12-section final CAM, 'analyst' = 21-section CAM */
    camView: 'banker',
    finalCamData: null,
    fcActive: 0,
    fcDrillOpen: {},
    fcInterpreting: null,
    fcShowBasis: false,   /* show every basis tag (Demo, N/A and AI are always shown) */
    /* Overview (modules/overview.js) */
    ovShowWhy: false,

    /* Companies with a downloadable document pack (GET /companies/supported-downloads) */
    supportedDownloadIds: [],

    /* Approval workflow */
    approvalStatus: null,
    approvalLevels: [],
    approvalMakerRoles: [],
    approvalRole: '',
    approvalUserId: '',
    approvalComments: '',
    approvalConditions: '',
    approvalQueue: [],
    decisionTatDays: 3,   /* overdue threshold, from config/approval.yaml */

    /* Config / Settings */
    cfg: {},
    cfgSector: '',
    cfgSectorData: null,
    settingsTab: 'llm',
    probeStatus: null,
    reportProbe: null,

    /* LLM */
    llmProviders: [],
    llmActive: 'mock',
    narrativeMode: 'template',
    activeProvider: 'mock',
    llmTestResult: '',

    /* Engines */
    engines: [],

    /* Pipeline */
    agents: [],
    pipelineTarget: '',
    pipelineRunning: false,
    pipelineError: false,
    agentEvents: [],
    agentProgress: '',
    agentPct: 0,
    pipelineDoneResult: null,
    camBuildSections: [],

    /* Smart Onboard */
    enumVals: {},
    onboardMode: 'smart',
    onboardPick: '',            /* entity_id from the borrower dropdown, or '__other__' */
    onboardId: '',
    onboardFacility: 'working_capital',
    onboardAmount: null,
    onboardPurpose: '',
    onboardCaseType: 'NTB',
    onboardCrilcAvailable: false,
    journeyStage: 'select',
    etbLookupResult: null,
    etbLookupError: '',
    onboardResult: null,
    resolvePreview: null,

    /* Reports */
    reportEntity: '',
    reportRunId: '',     /* '' = latest run; otherwise an earlier run shown read-only */
    reportRuns: [],      /* completed runs of reportEntity, newest first */
    reportLoading: false,
    camHtml: '',
    camSections: [],
    camActiveSection: 0,
    camComments: {},
    camCommentDrafts: {},
    camCommentSaving: false,
    camEditMode: false,
    camSectionEdits: {},
    camEditSaving: false,
    memoHtml: '',
    view360Data: null,
    v360tab: 'overview',
    chatMessages: [],
    chatInput: '',
    chatLoading: false,

    /* Documents Workspace */
    docEntity: '',
    docLoading: false,
    docUploading: false,
    docExtracting: false,
    docData: null,
    docGaps: null,
    docExtraction: null,
    docProbe: null,
    docOpsHistory: [],
    docUploadCategory: 'financials',

    /* Manual Add Company */
    newCo: {
      entity_id: '', company_name: '', cin: '', pan: '',
      sector: '', borrower_type: 'unlisted', date_of_incorporation: '',
      credit_rating: '', rating_agency: '', employee_count: null,
      case_type: 'NTB', facility_type: 'working_capital',
      amount_requested_cr: null, purpose: '', tenor_months: null,
      existing_limit_cr: null,
      line_items: {
        revenue: null, ebitda: null, pat: null, total_debt: null,
        net_worth: null, total_assets: null, current_assets: null,
        current_liabilities: null, cash_and_equivalents: null,
        interest_expense: null, depreciation: null, tax_expense: null,
        inventory: null, trade_receivables: null, trade_payables: null,
      },
      collateral_type: '', collateral_desc: '',
      collateral_market_value: null, collateral_fsv: null,
    },

    /* ─── Core: start-up, navigation, API helper, shared company/case data ─── */
    /* Alpine calls init() itself — the page must not also use x-init="init()". */
    async init() {
      // One page app: the browser's own scroll restoration lands reloads mid-page.
      if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
      window.addEventListener('hashchange', () => this.onHash());
      window.addEventListener('keydown', event => this.focusSearchShortcut(event));
      // Reference data used across pages, loaded once; the current page loads its own data.
      await Promise.all([
        this.onHash(),
        this.loadConfig(),
        this.loadLLM(),
        this.loadEngines(),
        this.loadAgents(),
        this.loadEnums(),
        this.loadProbeStatus(),
        this.loadSupportedDownloads(),
        this.loadApprovalMatrix(),
        this.page === 'summary' ? null : this.loadSummary().catch(() => {}),  // nav overdue badge
      ]);
      this.maybeStartTour();  // first visit only
    },

    /* The URL hash is the single trigger for page loads (navigate() only changes it). */
    onHash() {
      let h = location.hash.slice(1) || 'summary';
      if (h === 'dashboard') h = 'summary';  // old bookmarks
      // Final CAM and Documents are tabs of the borrower workspace now.
      if (h === 'reports' || h === 'documents') {
        const eid = h === 'reports' ? this.reportEntity : this.docEntity;
        h = eid ? 'case/' + eid + (h === 'reports' ? '/cam' : '/documents') : 'cases';
        history.replaceState(null, '', '#' + h);
      }
      if (h.startsWith('case/')) {
        const [, eid, tab = 'overview'] = h.split('/');
        // Same borrower already open (a tab click set this hash): just show the tab.
        if (this.page === 'detail' && this.detail?.entity_id === eid) {
          return tab === this.wtab ? Promise.resolve() : this.setWorkspaceTab(tab);
        }
        return Promise.all([this.loadCompanies({ maxAgeMs: NAV_CACHE_MS }), this.openWorkspace(eid, tab)]);
      }
      if (this.page !== h) window.scrollTo({ top: 0 });
      this.page = h;
      return this.loadPage(h);
    },

    navigate(p) {
      if (this.page !== p) window.scrollTo({ top: 0 });  // a new page opens at its top
      this.page = p;
      if (location.hash.slice(1) !== p) location.hash = p;  // fires hashchange → onHash → loadPage
      else this.loadPage(p);                                 // same page clicked again: refresh it
    },

    /* Data each page needs. Company/case lists younger than NAV_CACHE_MS are reused,
       so moving between pages does not refetch them; actions that change data
       (runs, uploads, onboarding) call loadCompanies()/loadCases() directly for fresh data. */
    async loadPage(p) {
      const shared = () => this.loadCompanies({ maxAgeMs: NAV_CACHE_MS });
      if (p === 'summary') await Promise.all([this.loadSummary(), shared()]);
      if (p === 'cases') await Promise.all([shared(), this.loadSummary()]);
      if (p === 'pipeline') await shared();
      if (p === 'onboard') await Promise.all([shared(), this.loadEnums(), this.loadProbeStatus()]);
      if (p === 'approvals') await this.loadApprovalQueue();
      if (p === 'settings') await Promise.all([this.loadConfig(), this.loadLLM(), this.loadEngines()]);
    },

    notify(msg, type) {
      this.toast = msg;
      this.toastType = type === 'error' ? 'toast-err' : 'toast-ok';
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => this.toast = '', 3500);
    },

    /* ─── API Helpers ──────────────────────────────────────────────── */
    /* quiet: for optional lookups whose 404 just means "not run yet" — no error toast. */
    async api(path, opts, { quiet = false } = {}) {
      try {
        const r = await fetch('/api/' + path, opts);
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          throw new Error(e.detail || r.statusText);
        }
        return await r.json();
      } catch (e) {
        if (!quiet) this.notify(e.message, 'error');
        throw e;
      }
    },

    jsonBody(method, body) {
      return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    },

    async loadProbeStatus() {
      try {
        this.probeStatus = await this.api('probe/status');
      } catch {
        this.probeStatus = null;
      }
    },

    /* ─── Companies / Cases ────────────────────────────────────────── */
    /* maxAgeMs (navigation only): skip if loaded that recently, or join a load already
       under way. Without it — after runs, uploads, onboarding — always fetch fresh. */
    async loadCompanies({ maxAgeMs = 0 } = {}) {
      if (maxAgeMs) {
        if (Date.now() - companiesLoadedAt < maxAgeMs) return;
        if (companiesInflight) return companiesInflight;
      }
      const load = this._fetchCompanies();
      companiesInflight = load;
      try {
        await load;
        companiesLoadedAt = Date.now();
      } finally {
        if (companiesInflight === load) companiesInflight = null;
      }
    },

    async _fetchCompanies() {
      const r = await this.api('companies');
      this.companies = r.companies || [];
      if (this.companies.length && !this.pipelineTarget) {
        this.pipelineTarget = this.companies[0].entity_id;
      }
      if (this.companies.length && !this.docEntity) {
        this.docEntity = this.companies[0].entity_id;
      }
      if (this.companies.length && !this.reportEntity) {
        this.reportEntity = this.companies[0].entity_id;
      }
      await this.loadCases();
      const executed = this.companies.filter(c => this.caseMap[c.entity_id]);
      if ((!this.reportEntity || !this.caseMap[this.reportEntity]) && executed.length) {
        this.reportEntity = executed[0].entity_id;
      }
    },

    async loadCases() {
      const r = await this.api('cases');
      const map = {};
      for (const c of (r.cases || [])) map[c.entity_id] = c;
      this.caseMap = map;
      // Update has_result on companies
      for (const c of this.companies) c.has_result = !!map[c.entity_id];
    },

    /* ─── Executed-case helpers (used across pages) ─── */
    executedCompanies() {
      return this.companies.filter(c => !!this.caseMap[c.entity_id]);
    },

    hasExecutedCases() {
      return this.executedCompanies().length > 0;
    },

    selectedCompany(entityId) {
      const target = entityId || this.pipelineTarget || this.docEntity || this.reportEntity;
      return this.companies.find(c => c.entity_id === target) || null;
    },

    async loadEnums() {
      try { this.enumVals = await this.api('enums'); } catch {}
    },
  };
}
