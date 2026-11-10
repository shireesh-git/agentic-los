// Corporate Credit Origination — front end (Alpine.js) for the agentic LOS (API: /api/flow).
// Strings use typographic quotes (’): a straight apostrophe inside a single-quoted JS string breaks the page.

const ICONS = {
  pipeline: '<path d="M3 4h18M3 12h18M3 20h18"/><circle cx="7" cy="4" r="1.6"/><circle cx="14" cy="12" r="1.6"/><circle cx="10" cy="20" r="1.6"/>',
  queue: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h10M7 17h6"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 8 3 8H3s3-1 3-8"/><path d="M10 21h4"/>',
  logout: '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5M4 20h16"/>',
  doc: '<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6M9 13h7M9 17h7"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  alert: '<path d="M12 3 2 21h20z"/><path d="M12 10v5M12 18h.01"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.9-3.5M4 4v4h4M4 13a8 8 0 0 0 14.9 3.5M20 20v-4h-4"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  back: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  dot: '<circle cx="12" cy="12" r="4"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>',
  more: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>',
  reset: '<path d="M4 12a8 8 0 1 0 3-6.2M4 4v4h4"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
};
function icon(name, size) {
  const s = size || 16;
  return '<svg class="ic" width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || '') + '</svg>';
}

function flowApp() {
  return {
    icon,
    dir: { users: [], stages: [], product_name: 'Corporate Credit Origination', environment: '' },
    session: null,
    page: 'pipeline',            // pipeline | case | analytics
    queueTab: 'mine',
    q: { mine: [], all: [], kpis: null },
    filter: { stage: '', sla: '', text: '', archived: false },
    qf: { text: '', to: '' },
    qa: {},
    search: '',
    borrowers: [],
    nc: { open: false, mode: 'borrower', entity_id: '', search: '', product: 'working_capital', amount_cr: '',
          tenor_months: 12, purpose: '', name: '', cin: '', pan: '', sector: 'manufacturing' },
    c: null,
    tab: 'overview',
    loading: false,
    searchOpen: false,
    listScroll: 0,
    timeline: [],
    showTimeline: false,
    report: null,
    bt: null,
    btPoll: null,
    busy: false,
    msg: '',
    chatOpen: false,
    chatText: '',
    chatBusy: false,
    expandedMsg: {},
    edit: null,
    evidence: null,
    dlg: { open: false, title: '', text: '', value: '', required: false, ok: 'OK', resolve: null, input: true },
    toast: null,
    poll: null,
    srcPoll: null,
    srcView: null,
    fsRows: [['revenue_operating', 'Revenue from operations'], ['other_income', 'Other income'], ['ebitda', 'EBITDA (incl. other income)'],
             ['finance_cost', 'Finance cost'], ['depreciation', 'Depreciation'], ['pbt', 'Profit before tax'], ['pat', 'Profit after tax'],
             ['total_assets', 'Total assets'], ['total_equity', 'Net worth'], ['total_debt', 'Borrowings'], ['current_assets', 'Current assets'],
             ['current_liabilities', 'Current liabilities'], ['inventory', 'Inventories'], ['trade_receivables', 'Trade receivables'],
             ['trade_payables', 'Trade payables'], ['ocf', 'Cash from operations'], ['capex', 'Capital expenditure']],
    expanded: {},
    menuOpen: false,
    bellOpen: false,
    cursor: { missing: -1, skipped: -1 },
    sectors: ['manufacturing', 'infrastructure', 'pharma', 'logistics', 'it_services', 'real_estate', 'nbfc',
              'trading', 'hospitality', 'healthcare', 'energy'],

    async init() {
      this.dir = await this.get('/api/flow/directory');
      document.title = this.dir.product_name;
      try {
        const saved = JSON.parse(localStorage.getItem('flow.session') || 'null');
        if (saved && saved.token) { this.session = saved; await this.loadQueue(); }
      } catch (e) { this.session = null; }
      if (this.session) await this.route();
      window.addEventListener('hashchange', () => this.route());
    },

    async route() {
      if (!this.session) return;
      this.searchOpen = false; this.bellOpen = false; this.menuOpen = false;
      const m = location.hash.match(/^#case\/(.+)$/);
      if (m) { if (!this.c || this.c.case_id !== m[1] || this.page !== 'case') await this.open(m[1]); }
      else if (location.hash === '#analytics') await this.openReport();
      else if (location.hash === '#backtest' && this.dir.features?.backtest) await this.openBacktest();
      else { this.page = 'pipeline'; this.c = null; this.stopPoll(); await this.loadQueue(); }
    },

    // ── http ───────────────────────────────────────────────────────────────
    headers() { return this.session ? { 'X-Flow-Session': this.session.token } : {}; },
    async req(method, url, body, isForm) {
      const opts = { method, headers: this.headers() };
      if (body !== undefined) {
        if (isForm) opts.body = body;
        else { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
      }
      const r = await fetch(url, opts);
      const data = await r.json().catch(() => ({}));
      if (r.status === 403 && /Sign in/.test(data.detail || '')) { this.signOut(); }
      if (!r.ok) { const e = new Error(data.detail || ('Request failed (' + r.status + ')')); this.notify(e.message, 'error'); throw e; }
      return data;
    },
    get(url) { return this.req('GET', url); },
    post(url, body) { return this.req('POST', url, body === undefined ? {} : body); },
    put(url, body) { return this.req('PUT', url, body); },
    cp(path) { return '/api/flow/cases/' + this.c.case_id + path; },
    link(path) { return this.cp(path) + (path.includes('?') ? '&' : '?') + 'session=' + encodeURIComponent(this.session.token); },
    notify(text, kind) {
      this.toast = { text, kind: kind || 'ok' };
      clearTimeout(this._t); this._t = setTimeout(() => { this.toast = null; }, kind === 'error' ? 7000 : 3500);
    },

    // ── sign-in ────────────────────────────────────────────────────────────
    async signIn(u) {
      this.session = await this.post('/api/flow/session', { user_id: u.id });
      try { localStorage.setItem('flow.session', JSON.stringify(this.session)); } catch (e) {}
      await this.loadQueue();
      await this.route();
    },
    signOut() {
      this.session = null; this.c = null; this.stopPoll(); this.menuOpen = false;
      try { localStorage.removeItem('flow.session'); } catch (e) {}
    },
    role() { return this.session ? this.session.user.role : ''; },
    myStage() { return this.session ? this.session.user.stage : ''; },
    initials(name) { return (name || '').split(' ').map(w => w[0]).join('').slice(0, 2); },

    // ── formatting ─────────────────────────────────────────────────────────
    cr(v) {
      if (v === null || v === undefined || v === '' || isNaN(Number(v))) return '—';
      const n = Number(v);
      const d = Math.abs(n) >= 1000 || Number.isInteger(n) ? 0 : 2;
      return '₹' + n.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: d }) + ' Cr';
    },
    fmt(type, v) {
      if (v === null || v === undefined || v === '') return '—';
      if (type === 'amount') return this.cr(v);
      if (type === 'ratio' && !isNaN(Number(v))) return Number(v).toFixed(2) + 'x';
      return String(v);
    },
    product(p) { return { working_capital: 'Working Capital', term_loan: 'Term Loan', project_finance: 'Project Finance' }[p] || String(p || '').replace('_', ' '); },
    dur(s) {
      if (s === null || s === undefined) return '—';
      if (s < 60) return Math.round(s) + 's';
      if (s < 3600) return Math.floor(s / 60) + 'm ' + String(Math.round(s % 60)).padStart(2, '0') + 's';
      if (s < 86400) return Math.floor(s / 3600) + 'h ' + String(Math.floor((s % 3600) / 60)).padStart(2, '0') + 'm';
      return Math.floor(s / 86400) + 'd ' + Math.floor((s % 86400) / 3600) + 'h';
    },
    hours(h) { return this.dur((h || 0) * 3600); },
    eta(s) {
      if (s === null || s === undefined) return 'Estimating time remaining';
      return s < 60 ? 'About ' + Math.max(5, Math.round(s / 5) * 5) + 's remaining' : 'About ' + Math.round(s / 60) + ' min remaining';
    },
    date(s) { return s ? String(s).replace('T', ' ').slice(0, 16) : '—'; },
    grade(r) {
      const g = String(r || '').split(' ')[0].toUpperCase();
      if (!g) return '';
      return /^(AAA|AA|A)/.test(g) ? 'g-high' : /^(BBB|BB)/.test(g) ? 'g-mid' : 'g-low';
    },
    slaLabel(s) { return { ok: 'Within SLA', amber: 'Approaching SLA', breach: 'SLA breached', closed: 'Closed' }[s] || s; },

    // ── pipeline ───────────────────────────────────────────────────────────
    async loadQueue() {
      this.q = await this.get('/api/flow/queue');
      if (this.role() === 'rm' && !this.borrowers.length) this.borrowers = await this.get('/api/flow/borrowers');
    },
    goPipeline() {
      location.hash = ''; this.page = 'pipeline'; this.c = null; this.stopPoll();
      this.loadQueue().then(() => this.$nextTick(() => window.scrollTo({ top: this.listScroll || 0 })));
    },
    searchHits() {
      const t = this.search.trim().toLowerCase();
      if (t.length < 2) return [];
      return (this.q.all || []).filter(r => (r.borrower_name + ' ' + (r.cin || '') + ' ' + r.case_id).toLowerCase().includes(t)).slice(0, 7);
    },
    closedAt(r) {
      const st = r.stage_short || r.stage_label || '';
      return { disbursed: 'Disbursed', rejected: 'Declined at ' + st, withdrawn: 'Withdrawn at ' + st }[r.status] || st;
    },
    shortDate(s) {
      if (!s) return '';
      const d = new Date(s); if (isNaN(d)) return String(s).slice(0, 10);
      return d.getDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()];
    },
    rows() {
      const src = this.queueTab === 'mine' ? this.q.mine : this.q.all;
      const t = (this.filter.text || this.search || '').toLowerCase();
      return (src || []).filter(r => (!this.filter.stage || r.stage === this.filter.stage)
        && (!this.filter.sla || r.sla_state === this.filter.sla)
        && (this.filter.archived || !r.archived)
        && (!t || (r.borrower_name + ' ' + (r.cin || '') + ' ' + r.case_id).toLowerCase().includes(t)));
    },
    stageMax() { return Math.max(1, ...((this.q.kpis && this.q.kpis.by_stage) || []).map(s => s.exposure_cr)); },
    filteredBorrowers() {
      const q = this.nc.search.toLowerCase();
      return this.borrowers.filter(b => !q || (b.company_name + ' ' + b.entity_id + ' ' + (b.cin || '')).toLowerCase().includes(q)).slice(0, 40);
    },
    pickBorrower(b) {
      this.nc.entity_id = b.entity_id;
      this.nc.product = b.facility.product || 'working_capital';
      this.nc.amount_cr = b.facility.amount_cr || '';
      this.nc.tenor_months = b.facility.tenor_months || 12;
      this.nc.purpose = b.facility.purpose || '';
    },
    async createCase() {
      const facility = { product: this.nc.product, amount_cr: Number(this.nc.amount_cr), tenor_months: Number(this.nc.tenor_months), purpose: this.nc.purpose };
      const body = this.nc.mode === 'borrower' ? { entity_id: this.nc.entity_id, facility }
        : { prospect: { company_name: this.nc.name, cin: this.nc.cin, pan: this.nc.pan, sector: this.nc.sector }, facility };
      this.busy = true;
      try {
        const v = await this.post('/api/flow/cases', body);
        this.nc.open = false; this.borrowers = [];
        this.setCase(v); location.hash = 'case/' + v.case_id;
      } finally { this.busy = false; }
    },
    // ── one proposal's lifecycle (the borrower's other proposals are never touched) ──
    async withdrawCase() {
      this.menuOpen = false;
      const why = await this.ask('Withdraw ' + this.c.case_id + '?', 'The proposal is closed and kept for the record; the borrower can then have a new proposal. Other proposals of ' + this.c.borrower_name + ' are not affected.', 'Reason (mandatory), e.g. borrower no longer needs the facility', true, 'Withdraw');
      if (why === null) return;
      this.busy = true;
      try { this.setCase(await this.post(this.cp('/withdraw'), { text: why })); this.borrowers = []; this.notify('Proposal withdrawn', 'ok'); }
      finally { this.busy = false; }
    },
    async archiveCase(flag) {
      this.menuOpen = false;
      this.setCase(await this.post(this.cp('/archive'), { archived: flag }));
      this.notify(flag ? 'Archived — hidden from the pipeline (tick “Show archived” to see it)' : 'Restored to the pipeline', 'ok');
    },
    async deleteCase() {
      this.menuOpen = false;
      const ok = await this.confirm('Delete ' + this.c.case_id + '?', 'This proposal and its audit trail are removed permanently (demo housekeeping). Other proposals of ' + this.c.borrower_name + ' stay. This cannot be undone.', 'Delete');
      if (!ok) return;
      await this.req('DELETE', this.cp(''));
      this.notify(this.c.case_id + ' deleted', 'ok');
      this.borrowers = [];
      this.goPipeline();
    },

    // ── clarifications inside the stage ───────────────────────────────────
    openQueries() { return ((this.c && this.c.queries) || []).filter(q => q.status === 'open'); },
    myQueries() { const r = this.role(); return this.openQueries().filter(q => q.to_role === r); },
    async raiseQuery() {
      if (!this.qf.text.trim()) { this.notify('Type the question', 'error'); return; }
      this.busy = true;
      try {
        this.setCase(await this.post(this.cp('/queries'), { question: this.qf.text, to_stage: this.qf.to || null }));
        this.qf = { text: '', to: '' };
        this.notify('Clarification sent — the proposal stays with you and its SLA clock pauses', 'ok');
      } finally { this.busy = false; }
    },
    async answerQuery(q) {
      const text = (this.qa[q.id] || '').trim();
      if (!text) { this.notify('Type the answer', 'error'); return; }
      this.busy = true;
      try { this.setCase(await this.post(this.cp('/queries/' + q.id + '/answer'), { text })); delete this.qa[q.id]; this.notify('Answer sent to ' + q.from_name, 'ok'); this.loadQueue(); }
      finally { this.busy = false; }
    },
    async withdrawQuery(q) {
      this.setCase(await this.post(this.cp('/queries/' + q.id + '/withdraw'), {}));
      this.notify('Clarification withdrawn', 'ok');
    },

    // ── a proposal ─────────────────────────────────────────────────────────
    async open(caseId) {
      if (this.page === 'pipeline') this.listScroll = window.scrollY;
      if (!this.c || this.c.case_id !== caseId) { this.c = null; this.page = 'case'; }
      this.busy = true; this.loading = true;
      window.scrollTo({ top: 0 });
      try { this.setCase(await this.get('/api/flow/cases/' + caseId)); this.page = 'case'; }
      catch (e) { this.goPipeline(); }
      finally { this.busy = false; this.loading = false; }
    },
    setCase(v) {
      const first = !this.c || this.c.case_id !== v.case_id;
      this.c = v; this.page = 'case';
      if (first) {
        this.showTimeline = false; this.timeline = []; this.edit = null; this.cursor = { missing: -1, skipped: -1 }; this.expandedMsg = {};
        this.tab = this.defaultTab(v); window.scrollTo({ top: 0 });
      }
      if (v.cam && v.cam.state === 'running') this.startPoll(); else this.stopPoll();
      if (this.acquiring()) this.startSrcPoll(); else this.stopSrcPoll();
      this.$nextTick(() => this.scrollChat());
    },

    // ── proposal tabs (U1) and what needs the signed-in officer (U15) ─────────
    tabs() {
      const c = this.c; if (!c) return [];
      const t = [{ id: 'overview', label: 'Overview', n: this.todo().filter(x => x.tone !== 'info').length },
                 { id: 'data', label: 'Credit data', n: c.editable ? (c.counts.missing || 0) : 0 },
                 { id: 'risk', label: 'Risk & decision', n: this.riskOpen() },
                 { id: 'docs', label: 'Documents & CAM', n: c.can_sources ? ((c.acquisition && c.acquisition.counts.needed) || 0) : 0 }];
      if (c.sanction) t.push({ id: 'post', label: 'Post-sanction', n: c.can_conditions && c.status === 'open' ? this.cpCount() - this.cpMet() : 0 });
      t.push({ id: 'activity', label: 'Activity', n: 0 });
      return t;
    },
    riskOpen() {
      const c = this.c; if (!c || !c.is_mine) return 0;
      return (c.sanction ? 0 : this.openChallenges().length) + this.devTodo().length + (c.stage === 'sanction' ? (c.pending_changes || 0) : 0);
    },
    riskAny() {
      const c = this.c;
      return (c.risk && (c.risk.limit || c.risk.notes) && c.cam.state === 'ready') || ((c.against || []).length && c.cam.state === 'ready' && !c.sanction) || ((c.register || []).length && c.cam.state === 'ready')
        || (c.changes || []).some(x => x.status !== 'superseded');
    },
    defaultTab(v) {
      if (v.status === 'open' && v.is_mine && ['cad', 'disbursement'].includes(v.stage)) return 'post';
      if (v.status === 'open' && v.can_cam && v.cam.state !== 'ready') return 'docs';
      return 'overview';
    },
    showTab(t) {
      this.tab = t;
      if (t === 'activity') this.loadTimeline();
      const head = document.querySelector('.head-card');
      if (head) { const top = head.getBoundingClientRect().bottom + window.scrollY - 58; if (window.scrollY > top) window.scrollTo({ top }); }
    },
    tabOf(id) {
      return { 'sec-checks': 'overview', 'sec-queries': 'overview', 'sec-todo': 'overview', 'sec-src': 'docs', 'sec-cam': 'docs',
               'sec-ovr': 'risk', 'sec-dev': 'risk', 'sec-chal': 'risk', 'sec-limit': 'risk', 'sec-notes': 'risk', 'sec-cp': 'post' }[id] || this.tab;
    },
    reveal(id) { this.tab = this.tabOf(id); this.$nextTick(() => this.flash(document.getElementById(id))); },
    todo() {
      const c = this.c; const out = [];
      if (!c || c.status !== 'open') return out;
      const add = (tone, text, label, act) => out.push({ tone, text, label, act });
      this.myQueries().forEach(q => add('warn', q.from_name + ' (' + q.stage_label + ') asks: “' + q.question + '”', 'Answer', () => this.reveal('sec-queries')));
      if (!c.is_mine) return out;
      if (c.ask) add('warn', 'Credit Copilot is waiting for your answer', 'Open Copilot', () => { this.chatOpen = true; this.$nextTick(() => this.scrollChat()); });
      if (c.can_cam && c.cam.state === 'none')
        add('warn', c.can_generate ? 'Generate the CAM, or ingest the bank’s CAM' : (c.generate_blocker || 'Complete the data sources first'), 'Go', () => this.reveal(c.can_generate ? 'sec-cam' : 'sec-src'));
      if (c.cam.state === 'running') add('info', 'The CAM is being generated · ' + ((c.progress && c.progress.percent) || 0) + '%', 'View progress', () => this.reveal('sec-cam'));
      if (c.cam.state === 'failed' && (c.can_cam || c.can_rerun)) add('bad', 'CAM generation stopped — resume it', 'Go', () => this.reveal('sec-cam'));
      if (c.cam.stale && c.can_rerun) add('warn', 'The CAM is out of date: ' + (c.cam.stale_reason || 'figures changed'), 'Re-run', () => this.reveal('sec-cam'));
      if (c.editable && c.counts.missing) add('bad', c.counts.missing + ' credit data field(s) pending', 'Go to field', () => this.goTo('missing'));
      if (c.checks && c.checks.open && c.checks.can_note) add('warn', c.checks.open + ' mandatory check(s) open', 'Review', () => this.reveal('sec-checks'));
      const oc = c.sanction ? [] : this.openChallenges();
      if (oc.length && ['credit_risk', 'sanction'].includes(c.stage)) add('warn', oc.length + ' key risk challenge(s) to answer', 'Answer', () => this.reveal('sec-chal'));
      const dv = this.devTodo().length;
      if (dv) add('warn', dv + ' deviation(s) ' + (c.stage === 'sanction' ? 'awaiting your approval' : 'need a mitigant'), 'Review', () => this.reveal('sec-dev'));
      if (c.stage === 'sanction' && c.pending_changes) add('warn', c.pending_changes + ' underwriting override(s) need your concurrence', 'Review', () => this.reveal('sec-ovr'));
      if (c.stage === 'cad' && c.sanction && this.cpCount() > this.cpMet()) add('warn', (this.cpCount() - this.cpMet()) + ' condition(s) precedent outstanding', 'Go', () => this.reveal('sec-cp'));
      this.openQueries().filter(q => q.stage === c.stage).forEach(q => add('info', 'Waiting for ' + q.to_name + ' to answer ' + q.id + ' · SLA clock paused', 'View', () => this.reveal('sec-queries')));
      return out;
    },
    groupSummary(g) {
      const n = k => g.points.filter(p => p.status === 'filled' && ((p.source || {}).kind === 'person') === k).length;
      const a = n(false), b = n(true);
      return [a ? a + ' by agents' : '', b ? b + ' by people' : ''].filter(Boolean).join(' · ');
    },

    // ── data sources (acquisition agents) ─────────────────────────────────
    acquiring() {
      const a = this.c && this.c.acquisition;
      return !!a && (a.state === 'running' || a.groups.some(g => g.sources.some(s => s.status === 'reading')));
    },
    startSrcPoll() {
      if (this.srcPoll) return;
      this.srcPoll = setInterval(async () => {
        if (!this.c || this.page !== 'case') return this.stopSrcPoll();
        try {
          const v = await this.get('/api/flow/cases/' + this.c.case_id);
          const was = this.acquiring();
          this.c = v;
          if (!this.acquiring()) { this.stopSrcPoll(); if (was) this.notify('Data sources updated', 'ok'); this.$nextTick(() => this.scrollChat()); }
        } catch (e) { this.stopSrcPoll(); }
      }, 1500);
    },
    stopSrcPoll() { if (this.srcPoll) { clearInterval(this.srcPoll); this.srcPoll = null; } },
    srcTag() {
      const a = this.c && this.c.acquisition;
      if (!a) return { text: '', cls: '' };
      if (this.acquiring()) return { text: 'Agents working', cls: 'tg-blue' };
      if (a.state === 'failed') return { text: 'Stopped', cls: 'tg-red' };
      if (a.counts.needed) return { text: a.counts.needed + ' required pending', cls: 'tg-amber' };
      return { text: 'Complete', cls: 'tg-green' };
    },
    srcStatus(s) {
      return ({ fetched: { text: 'Fetched via API', cls: 'tg-green' }, read: { text: 'Read from document', cls: 'tg-green' },
        awaiting_upload: { text: 'Awaiting document', cls: s.requirement === 'required' ? 'tg-amber' : 'tg-grey' },
        reading: { text: 'Reading…', cls: 'tg-blue' }, rejected: { text: 'Rejected', cls: 'tg-red' },
        failed: { text: s.mode === 'api' ? 'API unavailable' : 'Failed', cls: 'tg-red' }, match: { text: 'Potential match', cls: 'tg-red' },
        not_found: { text: 'Not found', cls: 'tg-amber' }, pending: { text: 'Pending', cls: 'tg-grey' } })[s.status] || { text: s.status, cls: 'tg-grey' };
    },
    async uploadSource(sid, ev) {
      const files = Array.from(ev.target.files || []); ev.target.value = '';
      if (!files.length) return;
      this.busy = true;
      try {
        for (const f of files) {
          const fd = new FormData(); fd.append('file', f);
          this.setCase(await this.req('POST', this.cp('/sources/' + sid + '/document'), fd, true));
        }
        this.notify(files.length + ' document(s) received — the agent is reading', 'ok');
      } finally { this.busy = false; }
    },
    async refreshSources() { this.setCase(await this.post(this.cp('/sources/refresh'))); },
    async openSource(s) { this.srcView = await this.get(this.cp('/sources/' + s.id)); },
    fmtNum(v) { return (v === null || v === undefined) ? '—' : Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); },
    async refresh() { if (this.c) this.setCase(await this.get('/api/flow/cases/' + this.c.case_id)); },
    startPoll() {
      if (this.poll) return;
      this.poll = setInterval(async () => {
        if (!this.c) return this.stopPoll();
        try {
          const p = await this.get(this.cp('/cam/progress'));
          this.c.progress = p.job; this.c.cam = Object.assign({}, this.c.cam, { state: p.cam.state });
          if (p.cam.state !== 'running') {
            this.stopPoll(); await this.refresh();
            this.notify(p.cam.state === 'ready' ? 'CAM ready' : 'CAM generation stopped', p.cam.state === 'ready' ? 'ok' : 'error');
          }
        } catch (e) { this.stopPoll(); }
      }, 1500);
    },
    stopPoll() { if (this.poll) { clearInterval(this.poll); this.poll = null; } },
    async generate() {
      this.busy = true;
      try { const p = await this.post(this.cp('/cam/generate')); this.c.cam = p.cam; this.c.progress = p.job; this.startPoll(); }
      finally { this.busy = false; }
    },
    async uploadCam(ev) {
      const f = ev.target.files[0]; ev.target.value = '';
      if (!f) return;
      const fd = new FormData(); fd.append('file', f);
      this.busy = true; this.msg = 'Ingesting ' + f.name + ' — the CAM intake agent is mapping sections, labels and figures';
      try { this.setCase(await this.req('POST', this.cp('/cam/upload'), fd, true)); this.notify('CAM ingested', 'ok'); }
      finally { this.busy = false; this.msg = ''; }
    },
    phase(id) { return ((this.c && this.c.progress && this.c.progress.phases) || []).find(p => p.id === id) || { items: [], status: 'waiting' }; },
    stepClass(s) { return { done: 'st-done', reused: 'st-reused', writing: 'st-run', running: 'st-run', failed: 'st-fail', not_applicable: 'st-na' }[s] || 'st-wait'; },

    // credit data fields
    tag(p) {
      if (p.status === 'missing') return { t: p.required ? 'Pending · mandatory' : 'Pending', c: 'tg-red' };
      if (p.status === 'skipped') return { t: 'Not provided', c: 'tg-amber' };
      if (p.flag) return { t: 'Verify', c: 'tg-amber' };
      const s = p.source || {};
      if (s.kind === 'person') return s.override ? { t: 'Overridden', c: 'tg-violet' } : { t: 'Provided', c: 'tg-blue' };
      return null;                                       // filled by an agent: the normal case, not marked
    },
    provenance(p) {
      const s = p.source || {};
      if (!s.kind) return '';
      if (s.kind === 'engine') return 'AI · CAM' + (s.section ? ' §' + String(s.section).split(' ')[0] : '');
      if (s.kind === 'upload') return 'Bank CAM' + (s.page ? ' p.' + s.page : '');
      if (s.kind === 'record') return 'Borrower master';
      const r = { rm: 'RM', credit_risk: 'Underwriting', sanctioning_authority: 'Sanction', cad: 'CAD' }[s.role] || '';
      return (s.label || '').split(' · ')[0] + (r ? ' · ' + r : '');
    },
    startEdit(p, value, reason, challenge) {
      this.edit = { id: p.id, label: p.label, type: p.type, value: value != null ? value : (p.value === null ? '' : p.value),
                    reason: reason || '', needsReason: this.c.stage === 'credit_risk', challenge: challenge || '' };
    },
    editField(id, value, reason, challenge) {
      // open a credit data field for editing and bring it into view
      const p = (this.c.groups || []).flatMap(g => g.points).find(x => x.id === id);
      this.tab = 'data';
      if (!p) { this.$nextTick(() => document.querySelector('.fields')?.scrollIntoView({ behavior: 'smooth' })); this.notify('Choose the figure to override, then state the rationale'); return; }
      this.startEdit(p, value, reason, challenge);
      this.$nextTick(() => { const el = document.querySelector('.fld[data-id="' + id + '"]'); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); } });
    },
    async saveEdit() {
      if (this.edit.needsReason && !this.edit.reason.trim()) { this.notify('State the rationale — the Sanctioning Authority sees it', 'error'); return; }
      this.busy = true;
      try { this.setCase(await this.put(this.cp('/datapoints/' + this.edit.id), { value: this.edit.value, reason: this.edit.reason, challenge: this.edit.challenge || '' })); this.edit = null; }
      finally { this.busy = false; }
    },
    async skip(p) { this.setCase(await this.post(this.cp('/datapoints/' + p.id + '/skip'))); },
    toggle(id) { this.expanded[id] = !this.expanded[id]; },
    goTo(status) {
      if (this.tab !== 'data') { this.tab = 'data'; return this.$nextTick(() => this.goTo(status)); }
      // jump to the next field with this status (pending / not provided), cycling
      const els = Array.from(document.querySelectorAll('.fld[data-status="' + status + '"]'));
      if (!els.length) { this.notify(status === 'missing' ? 'No pending fields' : 'No fields marked not provided'); return; }
      this.cursor[status] = (this.cursor[status] + 1) % els.length;
      const el = els[this.cursor[status]];
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
    },

    // overrides (Sanctioning Authority)
    async decide(ch, decision) {
      let comment = '';
      if (decision === 'dispute') {
        comment = await this.ask('Return with remarks', 'Underwriting sees your remarks when the proposal is returned.', 'Remarks', true, 'Return override');
        if (comment === null) return;
      }
      this.setCase(await this.post(this.cp('/changes/' + ch.id), { decision, comment }));
    },

    // actions
    approveAct() { return ((this.c && this.c.actions) || []).find(a => a.id === 'approve') || {}; },
    async act(a, prefill, challenge) {
      const just = a.id === 'approve' && (a.justify || []).length;
      const needs = a.id === 'reject' || a.id === 'send_back' || just;
      const text = just ? 'Proceeding despite ' + a.justify.join('; ') + '. State why and the mitigants — this is recorded as a deviation and shown to the next approver.'
        : needs ? 'Remarks are recorded in the audit trail and shown to the next officer.' : 'Optional remarks for the audit trail.';
      const comment = await this.ask(just ? a.label + ' — justification required' : a.label, text,
        just ? 'Justification and mitigants (mandatory)' : needs ? 'Remarks (mandatory)' : 'Remarks (optional)', needs, a.label, prefill);
      if (comment === null) return;
      this.busy = true;
      try { this.setCase(await this.post(this.cp('/action'), { action: a.id, comment, challenge: challenge || '' })); this.notify(a.label + ' — done', 'ok'); }
      finally { this.busy = false; }
    },

    // key risk challenges: suggested actions (also offered by Credit Copilot)
    structureAct() {
      const h = this.c && this.c.risk && this.c.risk.headroom;
      if (!h || h.fits || !h.max_amount_cr || h.max_amount_cr <= 0) return null;
      const tenor = h.source === 'capacity' && h.tenor_months !== h.current_tenor ? h.tenor_months : null;
      if (h.source === 'capacity' && tenor && h.max_amount_cr >= h.requested_cr) return { kind: 'reduce_amount', label: 'Extend tenor to ' + tenor + ' months', field: 'tenor_months', value: tenor, reason: h.text };
      return { kind: 'reduce_amount', label: 'Set limit to ' + this.cr(h.max_amount_cr) + (tenor ? ' over ' + tenor + ' months' : ''), field: 'recommended_cr', value: h.max_amount_cr, tenor, reason: h.text };
    },
    devTodo() {
      const r = (this.c && this.c.register) || [];
      if (['rm', 'credit_risk'].includes(this.c.stage)) return r.filter(d => d.deviable && ['open', 'rejected'].includes(d.status));
      if (this.c.stage === 'sanction') return r.filter(d => d.deviable && d.status === 'proposed');
      return [];
    },
    async devPropose(d) {
      const mitigant = await this.ask('Mitigant: ' + d.label, 'What offsets this breach — e.g. security, a covenant, a DSRA, equity infusion, pricing. ' + d.policy, 'Mitigant', true, 'Next', d.mitigant || '');
      if (mitigant === null) return;
      const justification = await this.ask('Justification: ' + d.label, 'Why the proposal can proceed with this deviation. The ' + d.authority + ' sees it.', 'Justification', true, 'Record', d.justification || '');
      if (justification === null) return;
      this.busy = true;
      try { this.setCase(await this.post(this.cp('/deviations/' + encodeURIComponent(d.id)), { action: 'propose', mitigant, justification })); this.notify('Mitigant recorded', 'ok'); }
      finally { this.busy = false; }
    },
    async devDecide(d, action) {
      let comment = '';
      if (action === 'reject') {
        comment = await this.ask('Reject deviation: ' + d.label, 'Underwriting sees your remarks when the proposal is returned.', 'Remarks', true, 'Reject');
        if (comment === null) return;
      }
      this.busy = true;
      try { this.setCase(await this.post(this.cp('/deviations/' + encodeURIComponent(d.id)), { action, comment })); }
      finally { this.busy = false; }
    },
    openChallenges() { return (this.c.against || []).filter(a => !(this.c.responses || {})[a.id]); },
    sevClass(s) { return { CRITICAL: 'tg-red', HIGH: 'tg-red', MEDIUM: 'tg-amber', LOW: 'tg-grey' }[s] || 'tg-grey'; },
    sevLabel(s) { s = String(s || ''); return s ? s.charAt(0) + s.slice(1).toLowerCase() + ' severity' : ''; },
    respText(r) {
      if (!r) return '';
      const how = { justify: 'Justification recorded', override: 'Figure overridden', send_back: 'Returned for documents', reject: 'Declined' }[r.kind] || r.kind;
      return how + ' by ' + r.by + (r.note ? ': “' + r.note + '”' : '');
    },
    allowed(x) {
      const has = id => (this.c.actions || []).some(a => a.id === id);
      return { reduce_amount: this.c.editable, override: this.c.editable, send_back: has('send_back'), reject: has('reject'),
               justify: this.c.is_mine && (this.c.against || []).length > 0, goto: true, approve: has('approve') && this.approveAct().enabled }[x.kind] || false;
    },
    async doAction(x, a) {
      const cid = a ? a.id : (x.challenge || '');
      if (x.kind === 'goto') return this.reveal(x.target);
      if (x.kind === 'reduce_amount' && x.tenor) {
        // a structure: limit and tenor together
        const ok = await this.confirm(x.label + '?', (x.reason || '') + ' Both figures are changed; the CAM is re-run for the new tenor.', 'Apply');
        if (!ok) return;
        const why = 'Structure within policy: ' + (x.reason || x.label);
        this.busy = true;
        try {
          await this.put(this.cp('/datapoints/recommended_cr'), { value: x.value, reason: why, challenge: cid });
          this.setCase(await this.put(this.cp('/datapoints/tenor_months'), { value: x.tenor, reason: why, challenge: cid }));
          this.notify('Structure applied', 'ok');
        } finally { this.busy = false; }
        return;
      }
      if (x.kind === 'reduce_amount') return this.editField(x.field || 'recommended_cr', x.value, x.reason || (a ? 'In answer to: ' + a.title : ''), cid);
      if (x.kind === 'override') return this.editField(x.field, null, a ? 'In answer to: ' + a.title : '', cid);
      if (x.kind === 'send_back' || x.kind === 'reject' || x.kind === 'approve') {
        const act = (this.c.actions || []).find(y => y.id === x.kind);
        if (act) return this.act(act, x.prefill || '', cid);
        return;
      }
      if (x.kind === 'justify') {
        if (!a) { this.notify('Choose the challenge to answer on screen'); this.reveal('sec-chal'); return; }
        const note = await this.ask('Justification: ' + a.title, 'Explain why the proposal can proceed despite this challenge, and the mitigants (security, covenant, pricing, condition). The next approver and the audit trail see it.', 'Justification and mitigants', true, 'Record');
        if (note === null) return;
        this.busy = true;
        try { this.setCase(await this.post(this.cp('/challenges/' + encodeURIComponent(a.id)), { kind: 'justify', note })); this.notify('Justification recorded', 'ok'); }
        finally { this.busy = false; }
      }
    },

    // CAD
    async uploadDoc(condId, ev) {
      const f = ev.target.files[0]; ev.target.value = '';
      if (!f) return;
      const fd = new FormData(); fd.append('file', f);
      this.busy = true;
      try { this.setCase(await this.req('POST', this.cp('/conditions/' + condId + '/document'), fd, true)); }
      finally { this.busy = false; }
    },
    async confirmCond(cond) {
      const note = await this.ask('Confirm: ' + cond.label, cond.documents.length ? 'Confirm you have verified the original.' : 'No document is uploaded — record why the condition is met.', 'Verification note', !cond.documents.length, 'Confirm');
      if (note === null) return;
      this.setCase(await this.post(this.cp('/conditions/' + cond.id + '/confirm'), { note }));
    },
    async reopenCond(cond) { this.setCase(await this.post(this.cp('/conditions/' + cond.id + '/confirm'), { reopen: true })); },
    async demoDocs() {
      this.busy = true;
      try {
        this.setCase(await this.post(this.cp('/demo-documents')));
        this.notify('Demo executed documents attached in Conditions Precedent', 'ok');
        this.reveal('sec-cp');
      }
      finally { this.busy = false; }
    },
    async saveDrawdown() {
      const d = this.c.drawdown;
      this.setCase(await this.put(this.cp('/drawdown'), { amount_cr: Number(d.amount_cr), account: d.account, value_date: d.value_date }));
      this.notify('Disbursement request saved', 'ok');
    },
    cps() { return (this.c.conditions || []).filter(x => x.when === 'precedent'); },
    css() { return (this.c.conditions || []).filter(x => x.when === 'subsequent'); },
    condTag(k) {
      return { verified: { t: 'Verified · agent', c: 'tg-green' }, confirmed: { t: 'Confirmed · ' + (k.confirmed_by || 'CAD'), c: 'tg-green' },
               auto: { t: 'Met · record', c: 'tg-green' }, review: { t: 'Verification required', c: 'tg-amber' },
               open: { t: 'Awaiting document', c: 'tg-grey' }, not_applicable: { t: 'Not applicable', c: 'tg-na' } }[k.status] || { t: k.status, c: 'tg-grey' };
    },
    cpMet() { return this.cps().filter(k => ['verified', 'confirmed', 'auto'].includes(k.status)).length; },
    cpCount() { return this.cps().filter(k => k.status !== 'not_applicable').length; },
    async loadTimeline() { this.showTimeline = true; this.timeline = await this.get(this.cp('/timeline')); },

    // ── E2 / E5 mandatory checks, E7 incomplete fields, E8 go-to links ─────
    async checkNote(k, kind) {
      const verified = kind === 'verified';
      const note = await this.ask(verified ? 'Record verification: ' + k.label : 'Proceed with justification: ' + k.label,
        verified ? 'Say what evidence you saw that clears this check (' + k.evidence + '), e.g. the report, its date and reference.'
                 : 'Say why the proposal can proceed without this check, and the mitigant. The Sanctioning Authority and the audit trail see it.',
        verified ? 'Evidence seen (mandatory)' : 'Justification and mitigant (mandatory)', true, 'Record');
      if (note === null) return;
      this.busy = true;
      try { this.setCase(await this.post(this.cp('/checks/' + encodeURIComponent(k.code)), { kind, note })); this.notify('Recorded', 'ok'); }
      finally { this.busy = false; }
    },
    incompleteSplit() {
      const n = s => (this.c.incomplete || []).filter(f => f.status === s).length;
      return [[n('pending'), 'pending'], [n('not_provided'), 'not provided'], [n('not_available'), 'not available']]
        .filter(([k]) => k).map(([k, t]) => k + ' ' + t).join(' · ');
    },
    flash(el) { if (!el) return; el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); },
    goToField(id) { this.tab = 'data'; this.$nextTick(() => this.flash(document.querySelector('.fld[data-id="' + id + '"]'))); },
    goToTarget(g) {
      if (!g) return;
      this.tab = g.row ? 'post' : this.tabOf(g.target);
      this.$nextTick(() => {
        const row = g.row ? document.querySelector('[data-cond="' + g.row + '"]') : null;
        this.flash(row || document.getElementById(g.target));
      });
    },
    md(t) {
      // Copilot text: escaped, with **bold** for the names of buttons and sections
      const esc = String(t || '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
      return esc.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    },

    // ── Credit Copilot ─────────────────────────────────────────────────────
    mineMsg(m) { return m.from === 'user' || m.stage === this.myStage(); },
    chatItems() {
      // the signed-in officer's messages in full; others' grouped by stage, one header per group (U10)
      const out = [];
      for (const m of (this.c && this.c.chat) || []) {
        if (this.mineMsg(m)) { if (!(this.c.ask && this.c.ask.msg === m.id)) out.push({ key: 'm' + m.id + m.from, m }); continue; }
        const last = out[out.length - 1];
        if (last && last.group && last.stage === m.stage) last.msgs.push(m);
        else out.push({ key: 'g' + m.id, group: true, stage: m.stage, msgs: [m] });
      }
      return out;
    },
    stageName(id) { const s = (this.c && this.c.chain || []).find(x => x.id === id); return s ? s.short : ''; },
    officerOf(id) { const s = (this.c && this.c.chain || []).find(x => x.id === id); return s ? s.who : ''; },
    async send(text) {
      const t = (text === undefined ? this.chatText : text).trim();
      if (!t) return;
      this.chatText = '';
      this.c.chat.push({ id: 'tmp' + Date.now(), from: 'user', name: this.session.user.name, stage: this.myStage(), text: t, quick: [] });
      this.$nextTick(() => this.scrollChat());
      this.chatBusy = true;
      try { this.setCase(await this.post(this.cp('/chat'), { message: t })); }
      finally { this.chatBusy = false; }
    },
    async chatUpload(ev) {
      if (!this.c.ask) return;
      if (this.c.ask.kind === 'source_doc') return this.uploadSource(this.c.ask.ref, ev);
      await this.uploadDoc(this.c.ask.ref, ev);
    },
    scrollChat() { const el = document.getElementById('chat-log'); if (el) el.scrollTop = el.scrollHeight; },

    // ── analytics ──────────────────────────────────────────────────────────
    an() { return (this.report && this.report.analytics) || {}; },
    pctOf(v, of) { return of ? Math.round(100 * (v || 0) / of) : 0; },
    maxOf(rows, k) { return Math.max(0, ...(rows || []).map(r => r[k] || 0)); },
    out() { return this.an().outcomes || {}; },
    qual() { return this.an().quality || {}; },
    actTotal() { return (this.an().activity || []).reduce((a, d) => a + d.events, 0); },
    // ── back-test (roadmap P1) ─────────────────────────────────────────────
    async openBacktest() {
      this.stopPoll(); this.page = 'backtest'; if (location.hash !== '#backtest') location.hash = 'backtest';
      this.bt = await this.get('/api/flow/backtest');
      if (this.bt.running) this.pollBacktest();
    },
    async runBacktest() {
      this.bt = await this.post('/api/flow/backtest/run');
      this.notify('Back-test started — the engine runs on each past proposal', 'ok');
      this.pollBacktest();
    },
    pollBacktest() {
      if (this.btPoll) return;
      this.btPoll = setInterval(async () => {
        if (this.page !== 'backtest') { clearInterval(this.btPoll); this.btPoll = null; return; }
        this.bt = await this.get('/api/flow/backtest');
        if (!this.bt.running) { clearInterval(this.btPoll); this.btPoll = null; this.notify('Back-test complete', 'ok'); }
      }, 1500);
    },
    async openReport() { this.stopPoll(); this.report = await this.get('/api/flow/report'); this.page = 'analytics'; if (location.hash !== '#analytics') location.hash = 'analytics'; },

    // ── dialogs ────────────────────────────────────────────────────────────
    ask(title, text, placeholder, required, ok, value) {
      return new Promise(resolve => { this.dlg = { open: true, input: true, title, text, placeholder, value: value || '', required, ok: ok || 'OK', resolve }; });
    },
    confirm(title, text, ok) {
      return new Promise(resolve => { this.dlg = { open: true, input: false, title, text, value: '', required: false, ok: ok || 'OK', resolve }; });
    },
    closeDlg(result) {
      const r = this.dlg.resolve; const v = this.dlg.value; const input = this.dlg.input;
      if (result && this.dlg.required && !v.trim()) { this.notify('Remarks are mandatory', 'error'); return; }
      this.dlg = { ...this.dlg, open: false, resolve: null };
      if (r) r(result ? (input ? v.trim() : true) : (input ? null : false));
    },
  };
}
