/* Corporate LOS — single Alpine component for the LOS front end (/los).
   A presentation layer over /api/los: the workflow, permissions and audit live on the server.
   Demo sign-in (no passwords); the session token is kept in sessionStorage for this tab. */

function losApp() {
  const TOKEN_KEY = 'los.session';
  const STATUS = {
    DRAFT: ['Draft', 'badge-grey'], IN_PROGRESS: ['In progress', 'badge-blue'], UNDER_REVIEW: ['Under review', 'badge-amber'],
    RETURNED: ['Returned', 'badge-red'],
    APPROVED: ['Exit (approved)', 'badge-green'], REJECTED: ['Rejected', 'badge-red'],
  };
  const ACTIONS = {
    submit: ['Submit', 'btn-primary', 'Submitted'], approve: ['Approve', 'btn-primary', 'Approved'],
    return: ['Return', 'btn-outline', 'Returned'], reject: ['Reject', 'btn-danger', 'Rejected'],
    allocate: ['Allocate', 'btn-primary', 'Allocated'], sanction: ['Sanction', 'btn-primary', 'Sanctioned'],
    withdraw: ['Application Withdrawn', 'btn-danger', 'Withdrawn'], drop: ['Drop / Terminate', 'btn-danger', 'Dropped'],
    propose_modification: ['Modification Proposed', 'btn-outline', 'Modification proposed'],
    recommend_modification: ['Recommend for Modification', 'btn-outline', 'Modification recommended'],
    create: ['', '', 'Created'], reassign: ['', '', 'Reassigned'], escalate: ['', '', 'Escalated'],
    assessment_started: ['', '', 'Credit assessment started'], assessment: ['', '', 'Credit assessment completed'],
    assessment_failed: ['', '', 'Credit assessment failed'], field_review: ['', '', 'Assessment fields reviewed'],
    committee_brief: ['', '', 'Committee brief generated (AI)'], document_upload: ['', '', 'Document uploaded'],
    document_prefill: ['', '', 'Document prefill run'], prefill_apply: ['', '', 'Prefilled values accepted'],
    ip_note: ['', '', 'IP Note generated'], conditions_update: ['', '', 'Conditions updated'],
    checklist_update: ['', '', 'Disbursement checklist updated'], tranche_request: ['', '', 'Tranche recorded'],
    consent_recorded: ['', '', 'Sanction consent recorded'],
    dd_trigger: ['', '', 'Due-diligence check run'], dd_record: ['', '', 'Due-diligence check recorded'],
    dd_comment: ['', '', 'Due-diligence comment added'], dd_exception: ['', '', 'Due-diligence exception approved'],
    copilot_action: ['', '', 'Copilot task run'], copilot_ask: ['', '', 'Copilot question'],
    letter_issued: ['', '', 'Document issued'],
  };

  const PROV = {
    source: ['S', 'Borrower / source data'], external: ['Ext', 'External verified data'],
    calculated: ['C', 'Deterministic calculation'], derived: ['R', 'Rule-based analysis'],
    synthetic_demo: ['Demo', 'Synthetic demo value (not bank evidence)'], template: ['T', 'Standard / template value'],
    unavailable: ['N/A', 'Not available from submitted information'], ai: ['AI', 'AI interpretation'],
  };
  const RISK_MAKER_STEPS = ['ip_risk_maker', 'ap_risk_maker'];

  function storage(fn) { try { return fn(window.sessionStorage); } catch { return null; } }

  return {
    directory: { groups: [], roles: {}, users: [] },
    session: null,
    signinGroup: null, signinUser: '', signinRole: '',
    page: 'dashboard', lastList: 'dashboard',
    dash: {}, apps: [], query: '', stageFilter: '', statusFilter: '',
    statusFilters: [{ id: '', label: 'All' }, { id: 'DRAFT', label: 'Draft' }, { id: 'IN_PROGRESS', label: 'In progress' },
                    { id: 'UNDER_REVIEW', label: 'Under review' }, { id: 'RETURNED', label: 'Returned' },
                    { id: 'APPROVED', label: 'Exit (approved)' }, { id: 'REJECTED', label: 'Rejected' }],
    current: null, openStages: {}, panel: '', appTab: 'details',
    comment: '', allocateTo: '', reassignTo: '', escalateNote: '', sigChanges: '', reworkTo: '', busy: false,
    borrowers: [], identity: null, customerIdSel: '', newApp: { entity_id: '', priority: 'Normal', facilities: [], related_parties: [],
                     prospect: { project_type: '', funding_type: '', brief_description: '', detailed_discussion: '',
                                 initial_remarks: '' },
                     decision: { decision: '', mandatory_remarks: '', conditional_remarks: '' } },
    dd: null, ddEdit: '', ddResult: 'clear', ddRemarks: '', ddEv: '', ddEvName: '', ddEvNote: '', udinOpen: false, udinRows: [], udinRow: { document: '', udin_code: '', status: 'verified' }, invResolving: '', invResolution: '', subTrancheReason: '',
    consent: { acknowledged_by: '', consent_date: '', remarks: '' }, consentFacilities: [],
    auditEvents: [],
    rm: null, rmTab: 'customer', _rmTimer: null, rmEdit: '', rmEditValue: '', rmEditReason: '',
    pack: null, briefing: false, sanctionAmount: null, RISK_MAKER: RISK_MAKER_STEPS,
    src: null, prefilling: false, uploadCategory: 'request', srcSel: {}, srcEdit: '', srcEditValue: '', srcEditReason: '',
    ipn: null, noting: false, noteWithAi: true,
    letters: null, mis: null,
    copilot: null, copilotBusy: '', draft: null, question: '', asking: false, digest: null,
    ps: null, psTab: 'conditions', condEdit: '', condForm: {}, trancheForm: { amount_cr: null, value_date: '', purpose: '' },
    gov: { tab: 'facilities', party: {}, partyEv: null, entity: { entity_incorporated: false, latest_material_information_date: '' },
           security: {}, project: {}, projectChange: {}, esms: {}, ewp: {},
           rating: { kind: 'internal' }, cma: { subject: 'borrower', period: 'FY2025', rows: {} },
           cmaReview: false, cmaRemarks: '', conduct: {}, exposure: { exception: {} }, banking: {},
           pricing: { facility_id: '' }, fee: {}, schedule: {}, limit: {}, account: {}, secRef: {},
           beneficiary: {}, disFee: {}, repayment: {}, interest: {}, arrearsRow: {}, arrearsExists: false,
           memoReview: false, memoRemarks: '', docReview: '', docStatus: 'reviewed', docRemarks: '',
           mcDecision: 'accept', mcRemarks: '', outKind: '' },
    govDocs: null, govRules: null, govSnap: null, integrations: null,
    toast: '', toastType: '', _toastTimer: null,

    async init() {
      this.directory = await this.api('directory', {}, { auth: false });
      const token = storage(s => s.getItem(TOKEN_KEY));
      if (token) {
        try { this.session = await this.api('session'); } catch { storage(s => s.removeItem(TOKEN_KEY)); }
      }
      window.addEventListener('hashchange', () => this.onHash());
      if (this.session) await this.onHash();
    },

    /* ─── API ─────────────────────────────────────────────────────── */
    async api(path, opts = {}, { auth = true, quiet = false } = {}) {
      const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
      const token = storage(s => s.getItem(TOKEN_KEY));
      if (auth && token) headers['X-LOS-Session'] = token;
      const r = await fetch('/api/los/' + path, { ...opts, headers });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        if (r.status === 403 && /Not signed in/.test(e.detail || '')) { this.session = null; storage(s => s.removeItem(TOKEN_KEY)); }
        if (!quiet) this.notify(e.detail || r.statusText, 'error');
        throw new Error(e.detail || r.statusText);
      }
      return r.json();
    },
    post(path, body) { return this.api(path, { method: 'POST', body: JSON.stringify(body || {}) }); },

    notify(msg, type) {
      this.toast = msg; this.toastType = type === 'error' ? 'toast-err' : 'toast-ok';
      clearTimeout(this._toastTimer); this._toastTimer = setTimeout(() => (this.toast = ''), 3500);
    },

    /* ─── Sign-in ─────────────────────────────────────────────────── */
    pickGroup(g) { this.signinGroup = g; this.signinUser = ''; this.signinRole = ''; },
    groupUsers() {
      const roles = this.signinGroup?.roles || [];
      return this.directory.users.filter(u => u.roles.some(r => roles.includes(r)));
    },
    groupRolesOf(userId) {
      const u = this.directory.users.find(x => x.id === userId);
      return u ? u.roles.filter(r => (this.signinGroup?.roles || []).includes(r)) : [];
    },
    async signIn() {
      const s = await this.post('session', { user_id: this.signinUser, role: this.signinRole });
      storage(st => st.setItem(TOKEN_KEY, s.token));
      this.session = s; this.signinGroup = null;
      this.notify('Signed in as ' + s.user.name + ' · ' + s.role_name, 'ok');
      location.hash = 'dashboard';
      await this.onHash();
    },
    async switchRole(role) {
      this.session = await this.post('session/role', { role });
      this.notify('Acting as ' + this.session.role_name, 'ok');
      await this.refresh();
    },
    async signOut() {
      try { await this.api('session', { method: 'DELETE' }, { quiet: true }); } catch {}
      storage(s => s.removeItem(TOKEN_KEY));
      this.session = null; this.current = null; this.apps = []; this.dash = {};
    },

    /* ─── Routing ─────────────────────────────────────────────────── */
    go(hash) { if (location.hash.slice(1) === hash) this.onHash(); else location.hash = hash; },
    async onHash() {
      if (!this.session) return;
      const h = location.hash.slice(1) || 'dashboard';
      const [page, id] = h.split('/');
      this.page = page; this.panel = '';
      window.scrollTo({ top: 0 });
      if (page === 'dashboard' || page === 'queue') { this.lastList = page; await this.refresh(); }
      else if (page === 'app' && id) await this.loadApp(id);
      else if (page === 'new') await this.loadBorrowers();
      else if (page === 'audit') this.auditEvents = (await this.api('audit')).events;
      else if (page === 'mis') await this.loadMis();
      else await this.loadDash();
    },
    async refresh() {
      await this.loadDash();
      if (this.page === 'app' && this.current) await this.loadApp(this.current.application_id);
      else await this.loadApps();
    },
    async loadDash() {
      this.dash = await this.api('dashboard');
      try { this.digest = this.session ? await this.api('copilot/digest', {}, { quiet: true }) : null; } catch { this.digest = null; }
    },
    async loadApps() {
      const q = new URLSearchParams({ status: this.page === 'queue' ? '' : this.statusFilter,
                                      stage: this.page === 'queue' ? '' : this.stageFilter,
                                      mine: this.page === 'queue', q: this.query });
      this.apps = (await this.api('applications?' + q)).applications;
    },
    async loadApp(id) {
      const app = await this.api('applications/' + encodeURIComponent(id));
      if (this.current?.application_id !== app.application_id) {
        this.comment = ''; this.allocateTo = ''; this.reassignTo = ''; this.escalateNote = ''; this.appTab = 'details';
        this.openStages = Object.fromEntries((app.rail || []).map(s => [s.id, s.state !== 'pending']));
      }
      const changed = this.current?.application_id !== app.application_id;
      this.current = app;
      this.loadDash();
      if (changed) { this.rm = null; this.rmTab = 'customer'; this.rmEdit = ''; this.pack = null; this.src = null;
                     this.ipn = null; this.srcSel = {}; this.srcEdit = ''; this.ps = null; this.condEdit = '';
                     this.copilot = null; this.draft = null; this.question = ''; this.letters = null;
                     this.dd = null; this.ddEdit = ''; this.sigChanges = '';
                     this.trancheForm = { amount_cr: null, value_date: '', purpose: '' };
                     this.psTab = { DIS: 'disburse', POS: 'conditions', AP: 'compare' }[app.stage_id] || 'conditions';
                     this.consent = { acknowledged_by: '', consent_date: '', remarks: '' };
                     this.consentFacilities = (app.facilities || []).map(f => ({ facility_id: f.facility_id,
                        execution_status: ((app.consent || {}).facilities || []).find(x => x.facility_id === f.facility_id)
                          ?.execution_status || '', agreement_date: ((app.consent || {}).facilities || [])
                          .find(x => x.facility_id === f.facility_id)?.agreement_date || '' })); }
      await Promise.all([this.loadAssessment(), this.loadPack(), this.loadSourcing(), this.loadNote(), this.loadPost(),
                         this.loadCopilot(), this.loadLetters(), this.loadDD()]);
    },

    /* ─── Credit assessment (Risk Maker workspace) ────────────────── */
    rmVisible() {
      const c = this.current;
      return !!c && (RISK_MAKER_STEPS.includes(c.step?.id) || !!c.credit_assessment || !!this.rm?.view?.available);
    },
    async loadAssessment() {
      if (!this.current) return;
      const id = this.current.application_id;
      try {
        const rm = await this.api('applications/' + encodeURIComponent(id) + '/assessment', {}, { quiet: true });
        if (this.current?.application_id !== id) return;
        this.rm = rm;
        clearTimeout(this._rmTimer);
        if (rm.job?.state === 'running') this._rmTimer = setTimeout(() => this.loadAssessment(), 2000);
        else if (rm.job?.state === 'done' && !this.current.credit_assessment) {
          this.current = await this.api('applications/' + encodeURIComponent(id));  // pick up the audit event
        }
      } catch { this.rm = null; }
    },
    async runAssessment() {
      try {
        this.rm = await this.post('applications/' + this.current.application_id + '/assessment');
        this.notify('Credit assessment started — the agents are running', 'ok');
        this._rmTimer = setTimeout(() => this.loadAssessment(), 1500);
      } catch {}
    },
    /* Analyst review of assessment fields */
    overridden(f) { return f.review?.status === 'overridden' && !f.review?.stale; },
    fieldValue(f) { return this.overridden(f) ? f.review.value : f.value; },
    fieldTagTitle(f) {
      return this.overridden(f) ? 'Analyst override — was: ' + f.review.original
                                : this.provLabel(f.provenance) + (f.source ? ' — ' + f.source : '');
    },
    fieldCls(f) {
      return { 'los-rm-na': f.provenance === 'unavailable' && !this.overridden(f),
               'los-rm-confirmed': f.review?.status === 'confirmed' && !f.review?.stale,
               'los-rm-overridden': this.overridden(f), 'los-rm-stale': !!f.review?.stale };
    },
    reviewLine(f) {
      const r = f.review;
      if (!r) return '';
      if (r.stale) return 'Stale: the value changed after ' + (r.by_name || 'the analyst') + ' reviewed it (was ' + r.original + ')';
      if (r.status === 'confirmed') return '✓ Confirmed by ' + (r.by_name || r.by);
      return 'Overridden by ' + (r.by_name || r.by) + ' (was ' + r.original + '). Reason: ' + r.reason;
    },
    reviewSummaryText() {
      const s = this.rm?.review_summary || {};
      return (s.confirmed || 0) + ' confirmed · ' + (s.overridden || 0) + ' overridden · ' + (s.stale || 0) + ' stale · '
             + (s.pending || 0) + ' pending of ' + (s.fields || 0) + ' fields';
    },
    startOverride(f) {
      this.rmEdit = f.id;
      this.rmEditValue = this.overridden(f) ? f.review.value : '';
      this.rmEditReason = f.review?.reason || '';
    },
    async submitReviews(reviews, message) {
      this.busy = true;
      try {
        this.rm = await this.post('applications/' + this.current.application_id + '/field-reviews', { reviews });
        this.rmEdit = '';
        if (message) this.notify(message, 'ok');
        this.current = await this.api('applications/' + encodeURIComponent(this.current.application_id));
      } catch {} finally { this.busy = false; }
    },
    reviewField(f, status) { return this.submitReviews([{ field_id: f.id, status }], status === 'clear' ? 'Review cleared' : null); },
    saveOverride(f) {
      return this.submitReviews([{ field_id: f.id, status: 'overridden', value: this.rmEditValue, reason: this.rmEditReason }],
                                'Override saved: ' + f.label);
    },
    confirmTab(t) {
      const ids = t.sections.flatMap(s => s.fields || []).filter(f => !f.review || f.review.stale).map(f => f.id);
      if (ids.length) {
        return this.submitReviews(ids.map(id => ({ field_id: id, status: 'confirmed' })),
                                  ids.length + ' field(s) confirmed in ' + t.title);
      }
    },
    /* Review & committee pack */
    async loadPack() {
      if (!this.current) return;
      const id = this.current.application_id;
      try {
        const pack = await this.api('applications/' + encodeURIComponent(id) + '/committee-pack', {}, { quiet: true });
        if (this.current?.application_id !== id) return;
        this.pack = pack;
        if (this.current.actions?.includes('sanction')) this.sanctionAmount = pack.recommended_sanction_cr ?? this.current.amount_cr;
      } catch { this.pack = null; }
    },
    async generateBrief() {
      this.briefing = true;
      try {
        this.pack = await this.post('applications/' + this.current.application_id + '/committee-brief');
        const failed = Object.values(this.pack.brief_results || {}).filter(r => r.status !== 'ok').length;
        this.notify(failed ? 'Committee brief: ' + failed + ' section(s) rejected by the figure check' : 'Committee brief written (AI)',
                    failed ? 'error' : 'ok');
        this.current = await this.api('applications/' + encodeURIComponent(this.current.application_id));
      } catch {} finally { this.briefing = false; }
    },
    /* ─── Prospect sourcing: documents and prefill ────────────────── */
    appPath(suffix) { return 'applications/' + encodeURIComponent(this.current.application_id) + '/' + suffix; },
    async loadSourcing() {
      if (!this.current) return;
      const id = this.current.application_id;
      try {
        const src = await this.api(this.appPath('sourcing'), {}, { quiet: true });
        if (this.current?.application_id === id) this.src = src;
      } catch { this.src = null; }
    },
    srcHeadline() {
      const p = this.src?.prefill;
      if (!p) return (this.src?.documents || []).length ? 'Read the documents on file and propose the sourcing details with their source page.'
        : 'No documents on file — upload the request note, KYC, financials, rating and valuation report.';
      return 'Prefill run ' + this.fmtDateTime(p.generated_at) + ' over ' + p.documents.length + ' document(s) · '
        + (this.src.accepted_count || 0) + ' value(s) accepted';
    },
    docFields(doc) { return (this.src?.prefill?.documents || []).find(d => d.document === doc)?.fields_found || 0; },
    srcGroups() { return [...new Set((this.src?.prefill?.fields || []).map(f => f.group))]; },
    srcFields(g) { return (this.src?.prefill?.fields || []).filter(f => f.group === g); },
    srcSelected() { return Object.keys(this.srcSel).filter(k => this.srcSel[k]); },
    async refreshCurrent() {
      this.current = await this.api('applications/' + encodeURIComponent(this.current.application_id));
      this.loadCopilot();
    },

    /* ─── Governance workspaces (clientspec GAP-P0/P1/P2) ────────── */
    govTabs() {
      const st = this.current?.stage_id || 'PS';
      const tabs = [];
      if (['PS', 'IP', 'AP', 'POS', 'DIS'].includes(st)) tabs.push(['facilities', 'Facilities & limits']);
      tabs.push(['parties', 'Parties & identity']);
      if (['PS', 'IP', 'AP', 'POS'].includes(st)) tabs.push(['securities', 'Securities']);
      if (['PS', 'IP', 'AP'].includes(st)) { tabs.push(['projects', 'Projects & ESMS']); tabs.push(['ewp', 'External parties']); }
      if (['IP', 'AP', 'POS', 'DIS'].includes(st)) tabs.push(['ratings', 'Ratings & RAROC']);
      if (['IP', 'AP', 'POS'].includes(st)) tabs.push(['cma', 'CMA']);
      if (['AP', 'POS', 'DIS'].includes(st)) { tabs.push(['proposal', 'Proposal & exposure']); tabs.push(['pricing', 'Pricing & fees']); }
      tabs.push(['documents', 'Documents']);
      if (st === 'DIS') tabs.push(['disops', 'Disbursement ops']);
      tabs.push(['rules', 'Mandatory rules']);
      if ((this.current?.snapshots || []).length) tabs.push(['approvals', 'Approval package']);
      return tabs;
    },
    async openGov(tab) {
      this.gov.tab = tab;
      const id = encodeURIComponent(this.current.application_id);
      try {
        if (tab === 'documents') this.govDocs = await this.api('applications/' + id + '/documents');
        if (tab === 'rules') this.govRules = await this.api('applications/' + id + '/rules');
        if (tab === 'approvals') this.govSnap = await this.api('applications/' + id + '/snapshot');
      } catch { /* read-only context */ }
      if (tab === 'projects' && this.current?.esms_checklist) {
        const es = this.current.esms || {};
        const byId = Object.fromEntries((es.checklist || []).map(c => [c.id, c]));
        this.gov.esms = { screening_date: es.screening_date || '', category: es.category || '', esdd: es.esdd || '',
                          checklist: Object.fromEntries(this.current.esms_checklist.map(([id]) => [id, byId[id]?.answer || ''])),
                          remarks: Object.fromEntries(this.current.esms_checklist.map(([id]) => [id, byId[id]?.remarks || ''])) };
      }
      if (tab === 'cma' && !Object.keys(this.gov.cma.rows).length) this.gov.cma.rows = {};
      if (tab === 'cma' && !this.gov.cma.subject) this.gov.cma.subject = 'borrower';
    },
    async govSave(path, payload, label) {
      try {
        // Governance endpoints share WorkspacePayload on the server. Keep the
        // envelope here so every workspace sends the same, explicit contract.
        await this.post('applications/' + encodeURIComponent(this.current.application_id) + '/' + path, { payload });
        this.toast(label || 'Saved');
        await this.refreshCurrent();
        this.openGov(this.gov.tab);
        return true;
      } catch (e) {
        this.toast(e.message, 'error');
        return false;
      }
    },
    async saveParty() {
      const saved = await this.govSave('parties', this.gov.party, this.gov.party.party_id ? 'Party updated' : 'Party saved');
      if (saved) this.gov.party = {};
      return saved;
    },
    editParty(p) {
      const keys = ['party_id', 'name', 'role', 'party_type', 'pan', 'cin', 'ownership_pct',
                    'relationship', 'sourced_address', 'key_person_role', 'party_status'];
      this.gov.party = Object.fromEntries(keys.map(k => [k, p[k] ?? '']));
      this.gov.partyEv = null;
    },
    saveEntity() {
      const payload = { entity_incorporated: this.gov.entity.entity_incorporated,
                        latest_material_information_date: this.gov.entity.latest_material_information_date || '' };
      return this.govSave('entity', payload, 'Entity flags saved');
    },
    openPartyEvidence(p) {
      const v = p.verification || {};
      this.gov.partyEv = {
        party_id: p.party_id, party_name: p.name,
        kyc_status: v.kyc?.status || '', kyc_remarks: v.kyc?.remarks || '', kyc_evidence: (v.kyc?.evidence || []).join(', '),
        cibil_status: v.bureau?.cibil?.status || '', cibil_remarks: v.bureau?.cibil?.remarks || '',
        crif_status: v.bureau?.crif?.status || '', crif_remarks: v.bureau?.crif?.remarks || '',
        screening_status: v.name_screening?.status || '', screening_hits: v.name_screening?.hits ?? '', screening_remarks: v.name_screening?.remarks || '',
        rating_ref: v.rating_ref || '', financial_ref: v.financial_ref || '', document_ids: (v.document_ids || []).join(', '),
        exception_reason: '',
      };
    },
    savePartyEvidence() {
      const g = this.gov.partyEv || {};
      const payload = {
        kyc_status: g.kyc_status || undefined, kyc_remarks: g.kyc_remarks, kyc_evidence: g.kyc_evidence ? g.kyc_evidence.split(',').map(s => s.trim()).filter(Boolean) : undefined,
        cibil_status: g.cibil_status || undefined, cibil_remarks: g.cibil_remarks,
        crif_status: g.crif_status || undefined, crif_remarks: g.crif_remarks,
        screening_status: g.screening_status || undefined, screening_hits: g.screening_hits ?? undefined, screening_remarks: g.screening_remarks,
        rating_ref: g.rating_ref, financial_ref: g.financial_ref, document_ids: g.document_ids ? g.document_ids.split(',').map(s => s.trim()).filter(Boolean) : undefined,
        exception_reason: g.exception_reason || undefined,
      };
      const clean = Object.fromEntries(Object.entries(payload).filter(([, v]) => v !== undefined));
      if (!Object.keys(clean).length) { this.toast('Nothing to update', 'error'); return; }
      return this.govSave('parties/' + g.party_id + '/evidence', clean, 'Party evidence saved');
    },
    saveFacility(fid) {
      const f = (this.current.facilities || []).find(x => x.facility_id === fid);
      const p = f?.pricing || {}, r = f?.repayment || {}, o = f?.ops || {};
      const payload = { benchmark: this.gov.pricing.benchmark ?? p.benchmark, spread: this.gov.pricing.spread ?? p.spread,
        interest_rate: this.gov.pricing.interest_rate ?? p.interest_rate, other_banks_comparison: this.gov.pricing.other_banks_comparison ?? p.other_banks_comparison,
        justification: this.gov.pricing.justification ?? p.justification,
        tenor_months: this.gov.pricing.tenor_months ?? f?.tenor_months,
        repayment_type: this.gov.pricing.repayment_type ?? r.repayment_type, repayment_frequency: this.gov.pricing.repayment_frequency ?? r.repayment_frequency,
        moratorium_months: this.gov.pricing.moratorium_months ?? r.moratorium_months, next_review_date: this.gov.pricing.next_review_date ?? f?.next_review_date,
        total_limit_id: this.gov.pricing.total_limit_id ?? o.total_limit_id, fund_limit_id: this.gov.pricing.fund_limit_id ?? o.fund_limit_id };
      const clean = {};
      for (const [k, v] of Object.entries(payload)) if (v !== null && v !== '' && v !== undefined) clean[k] = v;
      this.gov.pricing = {};
      return this.govSave('facilities/' + fid, clean, 'Facility updated');
    },
    saveSecurity() { return this.govSave('securities', this.gov.security, 'Security saved'); },
    saveProject() { return this.govSave('projects', this.gov.project, 'Project saved'); },
    changeProject() { const c = this.gov.projectChange; return this.govSave('projects/' + c.project_id + '/change', c, 'Change recorded'); },
    saveEsms() { const g = this.gov.esms;
      const checklist = Object.entries(g.checklist || {}).filter(([, v]) => v).map(([id, answer]) => ({ id, answer, remarks: g.remarks?.[id] || '' }));
      this.govSave('esms', { screening_date: g.screening_date, category: g.category, esdd: g.esdd, checklist }, 'ESMS saved'); },
    saveEwp() { return this.govSave('ewps', this.gov.ewp, 'External party saved'); },
    recordRating() { const r = this.gov.rating; const payload = {};
      for (const k of ['subject', 'rating', 'rating_type', 'grade', 'score', 'date', 'rationale', 'trigger', 'review_date', 'downgrade_notches', 'revised_rating', 'comments']) if (r[k] !== '' && r[k] != null) payload[k] = r[k];
      this.gov.rating = { kind: 'internal' };
      return this.govSave('ratings?kind=' + encodeURIComponent(r.kind), payload, 'Rating recorded'); },
    computeRaroc(fid) { return this.govSave('raroc', { facility_id: fid }, 'RAROC computed (demo model)'); },
    saveCma() { const c = this.gov.cma; const rows = {};
      for (const [k, v] of Object.entries(c.rows)) if (v !== '' && v != null) rows[k] = Number(v);
      if (!Object.keys(rows).length) { this.toast('Enter at least one value', 'error'); return; }
      this.gov.cma.rows = {};
      return this.govSave('cma', { subject: c.subject, rows: { [c.period]: rows }, value_class: 'audited' }, 'CMA recorded'); },
    reviewCma() { return this.govSave('cma/review', { approve: this.gov.cmaReview, remarks: this.gov.cmaRemarks }, 'CMA reviewed'); },
    saveConduct() { const row = this.gov.conduct; this.gov.conduct = {};
      return this.govSave('proposal', { section: 'conduct', data: { rows: [row] } }, 'Conduct recorded'); },
    saveExposure() { const e = this.gov.exposure;
      const data = { sanctioned_cr: e.sanctioned_cr ?? null, outstanding_cr: e.outstanding_cr ?? null,
                     norms: { lef: e.lef ?? null, epm: e.epm ?? null }, breach_alert: e.breach_alert || null };
      if (e.exception_justification) data.exception = { description: 'Exposure norm exception', justification: e.exception_justification };
      this.gov.exposure = {};
      return this.govSave('proposal', { section: 'exposure', data }, 'Exposure recorded'); },
    saveBanking() { return this.govSave('proposal', { section: 'banking', data: { ...this.gov.banking } }, 'Banking arrangement saved'); },
    savePricingRow() { const p = this.gov.pricing; this.gov.pricing = { facility_id: '' };
      const payload = { facility_id: p.facility_id };
      for (const k of ['proposed_benchmark', 'proposed_spread_bps', 'proposed_rate', 'other_banks_comparison', 'justification']) if (p[k] !== '' && p[k] != null) payload[k] = p[k];
      return this.govSave('pricing', payload, 'Pricing recorded'); },
    saveFee() { return this.govSave('pricing/fees', this.gov.fee, 'Fee recorded'); },
    saveSchedule() { return this.govSave('pricing/schedule', this.gov.schedule, 'Tentative schedule recorded'); },
    reviewDoc() { const id = this.gov.docReview; this.gov.docReview = '';
      return this.govSave('documents/' + id + '/review', { status: this.gov.docStatus, remarks: this.gov.docRemarks }, 'Document reviewed'); },
    saveDisopsSection(section, data, label) { return this.govSave('disops', { section, data }, label); },
    saveLimit() { return this.saveDisopsSection('limits', { rows: [this.gov.limit] }, 'Limit recorded'); },
    saveAccount() { return this.saveDisopsSection('loan_accounts', { rows: [this.gov.account] }, 'Loan account recorded'); },
    saveSecRef() { return this.saveDisopsSection('security_refs', { rows: [this.gov.secRef] }, 'Security reference recorded'); },
    saveBeneficiary() { return this.saveDisopsSection('beneficiaries', { rows: [this.gov.beneficiary] }, 'Beneficiary recorded'); },
    saveDisFee() { return this.saveDisopsSection('fees', { rows: [this.gov.disFee] }, 'Fee recorded'); },
    saveRepayment() { return this.saveDisopsSection('repayment_final', { ...this.gov.repayment }, 'Repayment final recorded'); },
    saveInterest() { return this.saveDisopsSection('interest_terms', { ...this.gov.interest }, 'Interest terms recorded'); },
    saveArrears() { return this.saveDisopsSection('arrears', { exists: this.gov.arrearsExists, rows: this.gov.arrearsExists ? [this.gov.arrearsRow] : [] }, 'Arrears recorded'); },
    setSop(item) { item._saving = true;
      this.govSave('disops', { section: 'sop', data: { items: [{ id: item.id, status: item.status, remarks: item.remarks || item.detail }] } }).finally(() => { item._saving = false; }); },
    genMemo() { return this.govSave('disops/memo', {}, 'Disbursement memo generated'); },
    reviewMemo() { return this.govSave('disops/memo/review', { approve: this.gov.memoReview, remarks: this.gov.memoRemarks }, 'Memo reviewed'); },
    toggleReviewItem(kind) {
      const key = kind === 'checker' ? 'checker_review' : 'final_review';
      const items = this.current[key]; if (!items) return;
      const next = items.map(i => ({ id: i.id, done: !i.done }));
      this.govSave('disops/review', { stage: kind, items: next }, 'Review updated');
    },
    saveMc() { return this.govSave('material-changes/review', { decision: this.gov.mcDecision, remarks: this.gov.mcRemarks }, 'Material change reviewed'); },
    downloadOutput(kind) { window.open('/api/los/applications/' + encodeURIComponent(this.current.application_id) + '/outputs/' + kind + '.html', '_blank'); },
    async loadIntegrations() { if (!this.integrations) { try { this.integrations = await this.api('integrations', {}, { quiet: true }); } catch { this.integrations = null; } } },

    /* ─── Term sheet & sanction letter ───────────────────────────── */
    async loadLetters() {
      if (!this.current) return;
      const id = this.current.application_id;
      try {
        const l = await this.api(this.appPath('letters'), {}, { quiet: true });
        if (this.current?.application_id === id) this.letters = l;
      } catch { this.letters = null; }
    },
    async issueLetter(kind) {
      this.busy = true;
      try {
        this.letters = await this.post(this.appPath('letters/' + kind));
        this.notify('Issued: ' + this.letters.letters.find(l => l.kind === kind).versions[0].reference, 'ok');
        await this.refreshCurrent();
      } catch {} finally { this.busy = false; }
    },
    async openHtml(path) {
      const win = window.open('', '_blank');
      try {
        const token = storage(s => s.getItem(TOKEN_KEY));
        const r = await fetch('/api/los/' + path, { headers: token ? { 'X-LOS-Session': token } : {} });
        if (!r.ok) throw new Error(r.statusText);
        const url = URL.createObjectURL(new Blob([await r.text()], { type: 'text/html' }));
        if (win) win.location = url; else window.location = url;
      } catch (e) { if (win) win.close(); this.notify('Could not open the document: ' + e.message, 'error'); }
    },
    openLetter(kind, version) { return this.openHtml(this.appPath('letters/' + kind + '.html') + (version ? '?version=' + version : '')); },

    /* ─── Management MIS ──────────────────────────────────────────── */
    async loadMis() { try { this.mis = await this.api('mis'); } catch { this.mis = null; } },
    misPct(v, all) { const max = Math.max(1e-9, ...all.map(Number)); return Math.max(2, Math.round((Number(v) / max) * 100)); },
    misCards() {
      const h = this.mis?.headline || {};
      const pct = v => v === null || v === undefined ? '—' : v + '%';
      return [
        { label: 'Active pipeline', value: h.active ?? '—', sub: this.fmtCr(h.pipeline_cr) + ' proposed' },
        { label: 'Average time per step', value: (h.avg_step_days ?? '—') + 'd', sub: 'completed step visits' },
        { label: 'SLA compliance', value: pct(h.sla_compliance_pct), sub: 'completed step visits',
          cls: h.sla_compliance_pct !== null && h.sla_compliance_pct < 80 ? 'los-kpi-bad' : '' },
        { label: 'Live SLA breaches', value: h.live_breaches ?? '—', sub: 'waiting past SLA', cls: h.live_breaches ? 'los-kpi-bad' : '' },
        { label: 'First-time right', value: pct(h.first_time_right_pct), sub: 'decided without a return' },
        { label: 'Final sanctions', value: h.final_sanctions ?? '—', sub: this.fmtCr(h.sanctioned_cr) + ' sanctioned' },
        { label: 'Sanctioned / requested', value: pct(h.sanction_to_request_pct), sub: 'final sanctions' },
        { label: 'Tranches approved', value: this.fmtCr(h.disbursed_cr), sub: 'approved for release (exit)' },
      ];
    },

    /* ─── Copilot ─────────────────────────────────────────────────── */
    async loadCopilot() {
      if (!this.current) return;
      const id = this.current.application_id;
      try {
        const c = await this.api(this.appPath('copilot'), {}, { quiet: true });
        if (this.current?.application_id === id) this.copilot = c;
      } catch { this.copilot = null; }
    },
    async copilotRun(tool) {
      this.copilotBusy = tool;
      try {
        const out = await this.post(this.appPath('copilot/run'), { tool });  // the app reload below refreshes every panel
        this.notify('Copilot: ' + out.message, 'ok');
        await this.loadApp(this.current.application_id);
      } catch {} finally { this.copilotBusy = ''; }
    },
    async copilotDraft(kind) {
      this.copilotBusy = 'draft';
      try { this.draft = await this.post(this.appPath('copilot/draft'), { kind }); } catch {} finally { this.copilotBusy = ''; }
    },
    async copyDraft() {
      try { await navigator.clipboard.writeText(this.draft.text); this.notify('Draft copied', 'ok'); }
      catch { this.notify('Copy failed — select the text and copy it', 'error'); }
    },
    async copilotAsk() {
      const q = this.question.trim();
      if (!q) return;
      this.asking = true;
      try {
        await this.post(this.appPath('copilot/ask'), { question: q });
        this.question = '';
        await this.loadCopilot();
        this.current = await this.api('applications/' + encodeURIComponent(this.current.application_id));
      } catch {} finally { this.asking = false; }
    },
    async runPrefill() {
      this.prefilling = true;
      try {
        this.src = await this.post(this.appPath('prefill'));
        const s = this.src.prefill.summary;
        this.notify('Read ' + this.src.prefill.documents.length + ' documents: ' + s.found + ' of ' + s.total + ' fields found', 'ok');
        this.srcSel = Object.fromEntries(this.src.prefill.fields.filter(f => f.band === 'high').map(f => [f.id, true]));
        await this.refreshCurrent();
      } catch {} finally { this.prefilling = false; }
    },
    async applySrc(items, message) {
      this.busy = true;
      try {
        this.src = await this.post(this.appPath('prefill/apply'), { items });
        this.notify(message, 'ok');
        this.srcSel = {}; this.srcEdit = '';
        await this.refreshCurrent();
      } catch {} finally { this.busy = false; }
    },
    acceptHigh() {
      const ids = (this.src?.prefill?.fields || []).filter(f => f.band === 'high' && !f.accepted).map(f => f.id);
      if (!ids.length) return this.notify('All high-confidence values are already accepted', 'ok');
      return this.applySrc(ids.map(field_id => ({ field_id })), ids.length + ' high-confidence value(s) accepted');
    },
    acceptSelected() {
      const ids = this.srcSelected();
      return this.applySrc(ids.map(field_id => ({ field_id })), ids.length + ' value(s) accepted');
    },
    startSrcEdit(f) { this.srcEdit = f.id; this.srcEditValue = f.accepted ? f.accepted.display : (f.display || ''); this.srcEditReason = ''; },
    saveSrcEdit(f) {
      return this.applySrc([{ field_id: f.id, value: String(this.srcEditValue ?? ''), reason: this.srcEditReason }], f.label + ' saved');
    },
    clearSrc(f) { return this.applySrc([{ field_id: f.id, status: 'clear' }], f.label + ' cleared'); },
    async uploadDoc() {
      const file = this.$refs.srcFile?.files?.[0];
      if (!file) return this.notify('Choose a PDF to upload', 'error');
      const form = new FormData();
      form.append('file', file); form.append('category', this.uploadCategory);
      const token = storage(s => s.getItem(TOKEN_KEY));
      this.busy = true;
      try {
        const r = await fetch('/api/los/' + this.appPath('documents'), { method: 'POST', body: form,
                                                                       headers: token ? { 'X-LOS-Session': token } : {} });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.detail || r.statusText);
        this.src = body; this.$refs.srcFile.value = '';
        this.notify('Uploaded ' + file.name + ' — re-run the prefill to read it', 'ok');
        await this.refreshCurrent();
      } catch (e) { this.notify(e.message, 'error'); } finally { this.busy = false; }
    },

    /* ─── Post sanction & disbursement ────────────────────────────── */
    async loadPost() {
      if (!this.current) return;
      const id = this.current.application_id;
      try {
        const ps = await this.api(this.appPath('post-sanction'), {}, { quiet: true });
        if (this.current?.application_id === id) this.ps = ps;
      } catch { this.ps = null; }
    },
    async loadDD() {
      if (!this.current) return;
      const id = this.current.application_id;
      try {
        const d = await this.api(this.appPath('due-diligence'), {}, { quiet: true });
        if (this.current?.application_id === id) this.dd = d;
      } catch { this.dd = null; }
    },
    async ddRunAll() {
      this.busy = true;
      try { this.dd = await this.post(this.appPath('due-diligence/run')); this.notify('Due-diligence API checks run', 'ok'); await this.refreshCurrent(); }
      catch {} finally { this.busy = false; }
    },
    async ddTrigger(id) {
      this.busy = true;
      try { this.dd = await this.post(this.appPath('due-diligence/trigger'), { check_id: id }); this.notify('Check re-run — the earlier result is kept in its history', 'ok'); await this.refreshCurrent(); }
      catch {} finally { this.busy = false; }
    },
    startDdRecord(c) { this.ddEdit = c.id; this.ddResult = 'clear'; this.ddRemarks = ''; },
    async ddSaveRecord() {
      const c = (this.dd?.checks || []).find(x => x.id === this.ddEdit);
      this.busy = true;
      try {
        this.dd = await this.post(this.appPath('due-diligence/record'), { check_id: this.ddEdit, result: this.ddResult, remarks: this.ddRemarks });
        this.notify('Check recorded: ' + (c ? c.name : this.ddEdit), 'ok'); this.ddEdit = '';
        await this.refreshCurrent();
      } catch {} finally { this.busy = false; }
    },
    async ddException() {
      const reason = (this.ddRemarks || '').trim();
      if (!reason) return this.notify('Enter the exception reason first', 'error');
      this.busy = true;
      try {
        this.dd = await this.post(this.appPath('due-diligence/exception'), { check_id: this.ddEdit, remarks: reason });
        this.notify('Compliance VP exception approved', 'ok'); this.ddEdit = '';
        await this.refreshCurrent();
      } catch {} finally { this.busy = false; }
    },
    async ddAddEvidence(checkId) {
      if (!this.ddEvName.trim()) return this.notify('Enter the evidence reference', 'error');
      this.busy = true;
      try {
        this.dd = await this.post(this.appPath('due-diligence/evidence'), { check_id: checkId, name: this.ddEvName.trim(), note: this.ddEvNote.trim() });
        this.notify('Evidence attached', 'ok'); this.ddEv = ''; this.ddEvName = ''; this.ddEvNote = '';
        await this.refreshCurrent();
      } catch (e) { this.notify(e.message, 'error'); } finally { this.busy = false; }
    },
    openUdin(c) {
      this.udinRows = (c.grid || []).map(r => ({ document: r.document, udin_code: r.udin_code, status: r.status }));
      this.udinRow = { document: '', udin_code: '', status: 'verified' };
      this.udinOpen = true;
    },
    udinAddRow() {
      if (!this.udinRow.document.trim() || !this.udinRow.udin_code.trim()) return;
      this.udinRows.push({ ...this.udinRow, document: this.udinRow.document.trim(), udin_code: this.udinRow.udin_code.trim() });
      this.udinRow = { document: '', udin_code: '', status: 'verified' };
    },
    async udinSave() {
      this.busy = true;
      try {
        this.dd = await this.post(this.appPath('due-diligence/grid'), { check_id: 'udin', rows: this.udinRows });
        this.notify('UDIN grid saved', 'ok'); this.udinOpen = false; this.udinRows = [];
        await this.refreshCurrent();
      } catch (e) { this.notify(e.message, 'error'); } finally { this.busy = false; }
    },
    async resolveInvalidation(id) {
      if (!this.invResolution.trim()) return this.notify('Enter the resolution note', 'error');
      this.busy = true;
      try {
        this.current = await this.post('applications/' + encodeURIComponent(this.current.application_id) + '/invalidations/' + id + '/resolve', { resolution: this.invResolution.trim() });
        this.notify('Invalidation resolved', 'ok'); this.invResolving = ''; this.invResolution = '';
      } catch (e) { this.notify(e.message, 'error'); } finally { this.busy = false; }
    },
    async requestSubsequentTranche() {
      if (!this.subTrancheReason.trim()) return this.notify('Enter the reason for the subsequent tranche', 'error');
      this.busy = true;
      try {
        this.current = await this.post(this.appPath('disbursement/subsequent-tranche'), { reason: this.subTrancheReason.trim() });
        this.notify('Subsequent tranche requested — re-opened at the Disbursement Maker', 'ok'); this.subTrancheReason = '';
        await this.refreshCurrent(); this.loadPost();
      } catch (e) { this.notify(e.message, 'error'); } finally { this.busy = false; }
    },
    async saveConsent() {
      const c = this.consent;
      if (!c.acknowledged_by.trim() || !c.consent_date) return this.notify('The acknowledgement and the consent date are required', 'error');
      this.busy = true;
      try {
        this.ps = await this.post(this.appPath('post-sanction/consent'), { acknowledged_by: c.acknowledged_by, consent_date: c.consent_date,
          remarks: c.remarks, facilities: this.consentFacilities.filter(f => f.execution_status) });
        this.notify('Sanction consent recorded', 'ok');
        await this.refreshCurrent();
        this.current = await this.api('applications/' + encodeURIComponent(this.current.application_id));
      } catch {} finally { this.busy = false; }
    },
    postHeadline() {
      const s = this.ps?.condition_summary || {}, d = this.ps?.disbursement || {};
      const parts = [];
      if (s.cp_total) parts.push(s.cp_open + ' CP open, ' + s.cs_open + ' CS open');
      parts.push((this.ps?.deviations || []).length + ' deviation(s)');
      if (d.sanctioned_cr) parts.push(this.fmtCr(d.disbursed_cr) + ' of ' + this.fmtCr(d.sanctioned_cr) + ' approved for release');
      return parts.join(' · ');
    },
    condCls(s) { return { satisfied: 'badge-green', waived: 'badge-amber', deferred: 'badge-amber', overdue: 'badge-red', open: 'badge-grey' }[s] || 'badge-grey'; },
    startCondition(c) {
      this.condEdit = c.id;
      this.condForm = { status: c.status === 'open' ? 'satisfied' : c.status, note: '', evidence: c.evidence || '', due: c.due || '' };
    },
    async postWrite(path, body, message) {
      this.busy = true;
      try {
        this.ps = await this.post(this.appPath(path), body);
        this.notify(message, 'ok');
        await this.refreshCurrent();
        return true;
      } catch { return false; } finally { this.busy = false; }
    },
    async saveCondition(c) {
      const ok = await this.postWrite('conditions', { updates: [{ id: c.id, ...this.condForm }] }, c.id + ' updated');
      if (ok) this.condEdit = '';
    },
    toggleCheck(i, done) { return this.postWrite('disbursement/checklist', { items: [{ id: i.id, done }] }, (done ? 'Confirmed: ' : 'Unchecked: ') + i.label); },
    saveTranche() { return this.postWrite('disbursement/tranche', this.trancheForm, 'Tranche recorded'); },
    covenantTest(id, result) {
      const remarks = prompt('Test remark (optional) — e.g. source of the covenant test', '') ?? '';
      return this.postWrite('covenants', { condition_id: id, action: 'test', result, remarks }, 'Covenant ' + id + ' tested: ' + result);
    },
    covenantCure(id) {
      const remarks = prompt('Cure remark (required) — evidence of the cure', '') ?? '';
      if (!remarks.trim()) return this.notify('A cure remark is required', 'error');
      return this.postWrite('covenants', { condition_id: id, action: 'cure', result: '', remarks }, 'Covenant ' + id + ' cured');
    },
    fmtCr(v) { return v === null || v === undefined ? '—' : '₹' + Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Cr'; },

    /* ─── IP Note ─────────────────────────────────────────────────── */
    async saveIpnAssign() {
      const payload = { lpfg_analyst: this.ipnAssign.lpfg_analyst, lpfg_senior_analyst: this.ipnAssign.lpfg_senior_analyst,
                        crac_recommendation: this.ipnAssign.crac_recommendation, crac_remarks: this.ipnAssign.crac_remarks };
      const clean = Object.fromEntries(Object.entries(payload).filter(([, v]) => (v || '').toString().trim() !== ''));
      if (!Object.keys(clean).length) { this.notify('Nothing to update', 'error'); return; }
      this.busy = true;
      try { this.ipn = await this.post(this.appPath('ip-note/assignments'), clean); this.notify('IP assignments saved', 'ok'); }
      catch (e) { this.notify(e.message, 'error'); } finally { this.busy = false; }
    },
    async loadNote() {
      if (!this.current) return;
      const id = this.current.application_id;
      try {
        const n = await this.api(this.appPath('ip-note'), {}, { quiet: true });
        if (this.current?.application_id === id) this.ipn = n;
      } catch { this.ipn = null; }
    },
    async generateNote() {
      this.noting = true;
      try {
        this.ipn = await this.post(this.appPath('ip-note'), { with_ai: this.noteWithAi });
        const ai = this.ipn.note.ai_status;
        this.notify('IP Note generated' + (this.noteWithAi && ai !== 'ok' ? ' (AI summary ' + ai.split(' ')[0] + ')' : ''), 'ok');
        await this.refreshCurrent();
      } catch {} finally { this.noting = false; }
    },
    openNote() { return this.openHtml(this.appPath('ip-note.html')); },

    sevCls(s) { return { CRITICAL: 'badge-red', HIGH: 'badge-red', MEDIUM: 'badge-amber', LOW: 'badge-blue' }[s] || 'badge-grey'; },
    provTag(cls) { return (PROV[cls] || [cls])[0]; },
    provLabel(cls) { return (PROV[cls] || [cls, cls])[1]; },
    decisionCls(d) {
      return { SUPPORTED: 'badge-green', SUPPORTED_WITH_CONDITIONS: 'badge-blue', REDUCED_MODIFIED: 'badge-amber',
               DEFERRED: 'badge-grey', NOT_SUPPORTED: 'badge-red' }[d] || 'badge-grey';
    },
    toggleStage(id) { this.openStages = { ...this.openStages, [id]: !this.openStages[id] }; },

    /* ─── Actions ─────────────────────────────────────────────────── */
    async act(action) {
      if (this.busy) return;
      this.busy = true;
      try {
        const before = this.current.step?.name;
        this.current = await this.post('applications/' + this.current.application_id + '/actions',
                                       { action, comment: this.comment, allocate_to: this.allocateTo || null,
                                         sanctioned_amount_cr: action === 'sanction' ? this.sanctionAmount : null,
                                         significant_changes: this.current?.step?.id === 'dis_vp_review' ? this.sigChanges : null,
                                         rework_to: action === 'return' ? (this.reworkTo || null) : null });
        this.loadPack();
        this.comment = ''; this.allocateTo = ''; this.sigChanges = ''; this.reworkTo = ''; this.draft = null;
        this.loadAssessment(); this.loadSourcing(); this.loadNote(); this.loadPost(); this.loadCopilot(); this.loadLetters();
        this.notify((ACTIONS[action]?.[2] || action) + ' at ' + before
                    + (this.current.step ? ' → ' + this.current.step.name : ''), 'ok');
        this.loadDash();
      } catch {} finally { this.busy = false; }
    },
    async reassign() {
      this.busy = true;
      try {
        this.current = await this.post('applications/' + this.current.application_id + '/reassign', { user_id: this.reassignTo });
        this.panel = ''; this.reassignTo = '';
        this.notify('Reassigned to ' + this.current.assignee_name, 'ok');
      } catch {} finally { this.busy = false; }
    },
    async escalate() {
      this.busy = true;
      try {
        this.current = await this.post('applications/' + this.current.application_id + '/escalate', { comment: this.escalateNote });
        this.panel = ''; this.escalateNote = '';
        this.notify('Escalated', 'ok');
      } catch {} finally { this.busy = false; }
    },
    async loadBorrowers() {
      if (!this.borrowers.length) this.borrowers = (await this.api('borrowers')).borrowers;
      this.newApp = { entity_id: '', priority: 'Normal', facilities: [this.blankFacility()], related_parties: [],
                      prospect: { project_type: '', funding_type: '', brief_description: '', detailed_discussion: '',
                                  initial_remarks: '' },
                      decision: { decision: '', mandatory_remarks: '', conditional_remarks: '' } };
      this.identity = null;
      this.customerIdSel = '';
    },
    async onBorrowerChange() {
      this.prefillFacility();
      this.identity = null;
      this.customerIdSel = '';
      if (!this.newApp.entity_id) return;
      try {
        this.identity = await this.api('borrowers/' + encodeURIComponent(this.newApp.entity_id) + '/identity');
      } catch { this.identity = null; }
    },
    blankFacility() {
      return { proposal_type: 'Fresh', facility_nature: 'fund_based', facility_type: 'working_capital',
               amount_cr: null, tenor_months: null, purpose: '', ad_hoc: false };
    },
    blankRelatedParty() {
      return { name: '', role: '', party_type: 'non_individual', ownership_pct: null, pan: '', cin: '',
               party_status: 'active', relationship: '', sourced_address: '', key_person_role: '' };
    },
    addFacility() { this.newApp.facilities.push(this.blankFacility()); },
    removeFacility(index) { if (this.newApp.facilities.length > 1) this.newApp.facilities.splice(index, 1); },
    addRelatedParty() { this.newApp.related_parties.push(this.blankRelatedParty()); },
    removeRelatedParty(index) { this.newApp.related_parties.splice(index, 1); },
    totalNewAmount() { return this.newApp.facilities.reduce((sum, f) => sum + (Number(f.amount_cr) || 0), 0); },
    canCreateApp() {
      const facilitiesOk = this.newApp.facilities.length && this.newApp.facilities.every(
        f => f.facility_type && f.facility_nature && Number(f.amount_cr) > 0);
      const partiesOk = this.newApp.related_parties.every(p => p.name && p.role && p.party_type &&
        (p.ownership_pct === null || p.ownership_pct === '' || (Number(p.ownership_pct) >= 0 && Number(p.ownership_pct) <= 100)));
      // UAT-P0-4: the sourcing decision and the remarks applicable to it are mandatory.
      const d = this.newApp.decision || {};
      const decisionOk = Boolean(d.decision) && Boolean((d.mandatory_remarks || '').trim()) &&
        (d.decision !== 'Defer' || Boolean((d.conditional_remarks || '').trim()));
      return Boolean(this.newApp.entity_id && facilitiesOk && partiesOk && decisionOk);
    },
    prefillFacility() {
      const b = this.borrowers.find(x => x.entity_id === this.newApp.entity_id);
      const f = this.newApp.facilities[0];
      if (b && f) this.newApp.facilities[0] = { ...f, facility_type: b.facility_type || f.facility_type,
                                                amount_cr: b.amount_cr || f.amount_cr };
    },
    async createApp() {
      this.busy = true;
      try {
        const app = await this.post('applications', { entity_id: this.newApp.entity_id, priority: this.newApp.priority,
          facilities: this.newApp.facilities, related_parties: this.newApp.related_parties,
          prospect_discussion: this.newApp.prospect, sourcing_decision: this.newApp.decision,
          customer_id_selection: this.customerIdSel || null });
        this.notify('Application ' + app.application_id + ' created as draft', 'ok');
        this.go('app/' + app.application_id);
      } catch {} finally { this.busy = false; }
    },
    async resetDemo() {
      this.busy = true;
      try {
        const r = await this.post('demo/reset');
        this.notify('Demo pipeline reset: ' + r.seeded + ' applications', 'ok');
        this.current = null; this.go('dashboard');
      } catch {} finally { this.busy = false; }
    },

    /* ─── Display helpers (formatting only) ───────────────────────── */
    roleName(r) { return this.directory.roles?.[r] || r; },
    userName(id) { return this.directory.users.find(u => u.id === id)?.name || id || '—'; },
    usersWithRole(role) { return this.directory.users.filter(u => u.roles.includes(role)); },
    initials(name) { return String(name || '').split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase(); },
    titleCase(v) {
      const s = String(v ?? '').replace(/_/g, ' ').trim();
      return s ? s.replace(/\b\w/g, c => c.toUpperCase()) : '—';
    },
    fmtAmount(v) { return v === null || v === undefined ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 }); },
    fmtDateTime(v) {
      if (!v) return '—';
      const d = new Date(v);
      return isNaN(d) ? v : d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    },
    statusLabel(s) { return STATUS[s]?.[0] || s || '—'; },
    statusCls(s) { return STATUS[s]?.[1] || 'badge-grey'; },
    kindLabel(k) { return { maker: 'maker step', checker: 'review step', vp_review: 'VP review step', allocation: 'allocation step', committee: 'committee decision' }[k] || k; },
    actionLabel(a) { return ACTIONS[a]?.[0] || a; },
    actionLabelFor(a) {
      if (a === 'return' && this.current?.step?.kind === 'vp_review') return 'Rework';
      if (a === 'approve' && this.current?.step?.id === 'pos_checker') return 'Recommend for Disbursement';
      return this.actionLabel(a);
    },
    actionCls(a) { return ACTIONS[a]?.[1] || 'btn-outline'; },
    actionPast(a) { return ACTIONS[a]?.[2] || a; },
    slaText(sla) {
      if (!sla) return '—';
      const d = sla.days_remaining;
      if (sla.breached) {
        const base = 'Breached ' + Math.abs(d).toFixed(1) + 'd (working days)';
        return sla.escalated ? base + ' · ESCALATED' : base;
      }
      return d.toFixed(1) + 'd left (working days)';
    },
    slaCls(sla) { return !sla ? '' : sla.escalated ? 'los-sla-bad' : sla.breached ? 'los-sla-bad' : sla.days_remaining < 1 ? 'los-sla-warn' : 'los-sla-ok'; },
    lastReturn() { return (this.current?.events || []).find(e => e.action === 'return'); },
    barHeight(n) {
      const max = Math.max(1, ...(this.dash.stages || []).map(s => s.count));
      return Math.max(4, Math.round((n / max) * 100));
    },
    kpiCards() {
      const k = this.dash.kpis || {};
      return [
        { label: 'Total pipeline', value: k.total ?? '—', sub: 'applications' },
        { label: 'Active', value: k.active ?? '—', sub: 'in progress across stages' },
        { label: 'SLA breach', value: k.sla_breached ?? '—', sub: 'need immediate action', cls: k.sla_breached ? 'los-kpi-bad' : '' },
        { label: 'SLA escalated', value: k.sla_escalated ?? 0, sub: 'breaches aged beyond threshold', cls: k.sla_escalated ? 'los-kpi-bad' : '' },
        { label: 'Sanctioned MTD', value: k.sanctioned_mtd ?? '—', sub: 'committee sanctions this month' },
        { label: 'Active exposure', value: '₹' + this.fmtAmount(k.exposure_cr) + ' Cr', sub: 'proposed amounts' },
        { label: 'Average TAT', value: (k.avg_tat_days ?? '—') + 'd', sub: 'active applications' },
        { label: 'Pending committee', value: k.pending_committee ?? '—', sub: 'IP + AP sanction' },
        { label: 'Exit (approved)', value: k.disbursed ?? '—', sub: 'workflow complete after final approval' },
        { label: 'DD blockers', value: k.dd_blocking ?? '—', sub: 'mandatory checks open', cls: k.dd_blocking ? 'los-kpi-bad' : '' },
        { label: 'Re-screening overdue', value: k.dd_rescreen_overdue ?? 0, sub: '90-day name-screening due', cls: k.dd_rescreen_overdue ? 'los-kpi-bad' : '' },
      ];
    },
  };
}
