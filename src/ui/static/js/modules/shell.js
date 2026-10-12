/* CAM Intelligence Platform — App-wide tools: borrower search, notifications, guided tour,
   sortable / exportable tables and term definitions (no page of their own).
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

const NOTIFICATIONS_KEY = 'cam.notifications';
const TOUR_SEEN_KEY = 'cam.tourSeen';
const MAX_NOTIFICATIONS = 30;

/* localStorage can be unavailable (private mode, blocked site data): never let that break the page. */
function readStore(key, fallback) {
  try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch { return fallback; }
}
function writeStore(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
}

/* Plain-language definitions shown as tooltips next to credit terms. */
const GLOSSARY = {
  dscr: 'Debt Service Coverage Ratio — cash available for debt service ÷ principal and interest due. Below 1.0x the borrower cannot meet repayments from operations.',
  icr: 'Interest Coverage Ratio — EBITDA (or EBIT) ÷ interest expense. How many times operating profit covers interest.',
  de: 'Debt / Equity — total borrowings ÷ net worth. Higher means more leverage.',
  cr: 'Current Ratio — current assets ÷ current liabilities. Short-term liquidity; below 1.0x is a warning.',
  tol_tnw: 'TOL / TNW — total outside liabilities ÷ tangible net worth. A banking measure of leverage.',
  debt_ebitda: 'Debt / EBITDA — years of operating profit needed to repay all debt.',
  ebitda_margin: 'EBITDA margin — operating profit before depreciation, interest and tax, as a share of revenue.',
  composite: 'Composite score (0–100) — weighted blend of the financial, conduct, governance and market scores. It sets the risk grade.',
  grade: 'Risk grade A (lowest risk) to E (highest), derived from the composite score.',
  ntb: 'New to Bank — a borrower with no existing relationship.',
  etb: 'Existing to Bank — a borrower with an existing relationship and account conduct history.',
  tat: 'Turnaround time — how long a submitted case has waited for a decision.',
  fsv: 'Forced Sale Value — what collateral would fetch in a distressed sale; security cover is measured on it.',
};

function camShell() {
  return {
    /* ─── Borrower search (top bar; press / to focus) ─────────────────── */
    searchQuery: '',
    searchOpen: false,
    searchIndex: 0,

    searchResults() {
      const query = this.searchQuery.trim().toLowerCase();
      if (!query) return [];
      return this.companies
        .filter(c => [c.company_name, c.entity_id, c.cin, c.pan, c.sector]
          .some(value => String(value || '').toLowerCase().includes(query)))
        .slice(0, 8);
    },

    moveSearch(delta) {
      const count = this.searchResults().length;
      if (count) this.searchIndex = (this.searchIndex + delta + count) % count;
    },

    openSearchResult(company) {
      if (!company) return;
      this.searchQuery = '';
      this.searchOpen = false;
      this.searchIndex = 0;
      if (this.caseMap[company.entity_id]) return this.openWorkspace(company.entity_id, 'overview');
      this.pipelineTarget = company.entity_id;
      this.navigate('pipeline');
      this.notify(this.displayCompanyName(company.company_name) + ' has not been analysed yet — run its CAM here', 'ok');
    },

    focusSearchShortcut(event) {
      const tag = document.activeElement?.tagName;
      if (event.key !== '/' || ['INPUT', 'TEXTAREA', 'SELECT'].includes(tag) || document.activeElement?.isContentEditable) return;
      event.preventDefault();
      this.$refs.globalSearch?.focus();
    },

    /* ─── Notifications (bell) ───────────────────────────────────────── */
    /* { id, at, text, tone: 'ok'|'error', entity_id, tab, read } — kept in this browser only. */
    notifications: readStore(NOTIFICATIONS_KEY, []),
    notificationsOpen: false,

    pushNotification(text, tone = 'ok', entityId = '', tab = 'overview') {
      const item = { id: Date.now() + '-' + Math.random().toString(36).slice(2, 7), at: new Date().toISOString(),
                     text, tone, entity_id: entityId, tab, read: false };
      this.notifications = [item, ...this.notifications].slice(0, MAX_NOTIFICATIONS);
      writeStore(NOTIFICATIONS_KEY, this.notifications);
    },

    companyLabel(entityId) {
      const company = this.companies.find(c => c.entity_id === entityId);
      return company ? this.displayCompanyName(company.company_name) : entityId;
    },

    unreadCount() {
      return this.notifications.filter(n => !n.read).length;
    },

    toggleNotifications() {
      this.notificationsOpen = !this.notificationsOpen;
    },

    markAllRead() {
      this.notifications = this.notifications.map(n => ({ ...n, read: true }));
      writeStore(NOTIFICATIONS_KEY, this.notifications);
    },

    openNotification(item) {
      this.notifications = this.notifications.map(n => (n.id === item.id ? { ...n, read: true } : n));
      writeStore(NOTIFICATIONS_KEY, this.notifications);
      this.notificationsOpen = false;
      if (item.entity_id) this.openWorkspace(item.entity_id, item.tab || 'overview');
    },

    clearNotifications() {
      this.notifications = [];
      writeStore(NOTIFICATIONS_KEY, []);
    },

    /* ─── Guided tour (first visit; Help button to replay) ───────────── */
    tourStep: -1,

    tourSteps() {
      return [
        { target: '[data-tour="summary"]', title: 'Summary',
          text: 'The portfolio at a glance for senior management: headline numbers, where the money sits by risk grade, status and sector, and the proposals that need attention. Click any number or bar to filter.' },
        { target: '[data-tour="cases"]', title: 'Cases',
          text: 'Every borrower with its latest grade, score and status. Open one to get its workspace — CAM, one-pager, risk checks, documents, AI analyst, decision and run history in one place.' },
        { target: '[data-tour="run"]', title: 'Run CAM',
          text: 'Run the credit analysis for a borrower and follow each step live, from data collection to the written CAM.' },
        { target: '[data-tour="approvals"]', title: 'Approvals',
          text: 'Cases waiting for a decision at your authority level, with how long each has waited.' },
        { target: '[data-tour="new"]', title: 'Create New CAM',
          text: 'Start a new case: pick the borrower, pull verified public data, add documents, and generate the CAM.' },
        { target: '[data-tour="search"]', title: 'Find a borrower',
          text: 'Jump to any borrower by name, ID, CIN or PAN. Press / from anywhere to start typing.' },
      ];
    },

    maybeStartTour() {
      if (!readStore(TOUR_SEEN_KEY, false)) this.startTour();
    },

    startTour() {
      this.notificationsOpen = false;
      this.showTourStep(0);
    },

    nextTourStep() {
      if (this.tourStep >= this.tourSteps().length - 1) return this.endTour();
      this.showTourStep(this.tourStep + 1);
    },

    endTour() {
      this.highlightTourTarget(null);
      this.tourStep = -1;
      writeStore(TOUR_SEEN_KEY, true);
    },

    currentTourStep() {
      return this.tourSteps()[this.tourStep] || null;
    },

    /* The card stays put (bottom centre); the step's element gets a highlight class, so the
       highlight moves with the page instead of being drawn at fixed coordinates. */
    showTourStep(index) {
      this.tourStep = index;
      const step = this.currentTourStep();
      const el = step && document.querySelector(step.target);
      this.highlightTourTarget(el && el.offsetParent !== null ? el : null);
    },

    highlightTourTarget(el) {
      document.querySelectorAll('.tour-target').forEach(node => node.classList.remove('tour-target'));
      if (!el) return;
      el.classList.add('tour-target');
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    },

    /* ─── Sortable tables ────────────────────────────────────────────── */
    /* tableSort[table] = { key, dir: 1 | -1 }; rows are sorted by sortRows(table, rows, accessors). */
    tableSort: {},

    toggleSort(table, key) {
      const current = this.tableSort[table];
      const dir = current?.key === key ? -current.dir : 1;
      this.tableSort = { ...this.tableSort, [table]: { key, dir } };
    },

    clearSort(table) {
      const next = { ...this.tableSort };
      delete next[table];
      this.tableSort = next;
    },

    sortIcon(table, key) {
      const current = this.tableSort[table];
      if (current?.key !== key) return '#i-sort';
      return current.dir === 1 ? '#i-sort-up' : '#i-sort-down';
    },

    ariaSort(table, key) {
      const current = this.tableSort[table];
      if (current?.key !== key) return 'none';
      return current.dir === 1 ? 'ascending' : 'descending';
    },

    /* accessors: { key: row => value }. Numbers sort numerically, text alphabetically, blanks last. */
    sortRows(table, rows, accessors) {
      const sort = this.tableSort[table];
      const get = sort && accessors[sort.key];
      if (!get) return rows;
      return rows.slice().sort((a, b) => {
        const x = get(a), y = get(b);
        const blankX = x === null || x === undefined || x === '', blankY = y === null || y === undefined || y === '';
        if (blankX || blankY) return blankX === blankY ? 0 : (blankX ? 1 : -1);
        if (typeof x === 'number' && typeof y === 'number') return (x - y) * sort.dir;
        return String(x).localeCompare(String(y), 'en-IN', { numeric: true }) * sort.dir;
      });
    },

    /* ─── Export to Excel (CSV) ──────────────────────────────────────── */
    /* columns: [{ label, value: row => value }]. Opens in Excel; a BOM keeps ₹ and names intact. */
    exportCsv(filename, columns, rows) {
      const cell = value => {
        const text = value === null || value === undefined ? '' : String(value);
        // Quote every cell; neutralise formula injection (=, +, -, @ at the start).
        return '"' + text.replace(/"/g, '""').replace(/^([=+\-@])/, "'$1") + '"';
      };
      const lines = [columns.map(c => cell(c.label)).join(',')]
        .concat(rows.map(row => columns.map(c => cell(c.value(row))).join(',')));
      this._download(filename, '﻿' + lines.join('\r\n'), 'text/csv;charset=utf-8');
      this.notify('Exported ' + rows.length + ' rows to ' + filename, 'ok');
    },

    /* ─── Term definitions ───────────────────────────────────────────── */
    term(key) {
      return GLOSSARY[key] || '';
    },

    /* Definition for a ratio label as it appears in the data (e.g. "DSCR", "Debt/Equity"). */
    termFor(label) {
      const text = String(label || '').toLowerCase().replace(/[\s_]+/g, '');
      if (text.includes('dscr')) return GLOSSARY.dscr;
      if (text.includes('interestcoverage') || text === 'icr') return GLOSSARY.icr;
      if (text.includes('tol') && text.includes('tnw')) return GLOSSARY.tol_tnw;
      if (text.includes('debt/ebitda') || text.includes('debttoebitda')) return GLOSSARY.debt_ebitda;
      if (text.includes('debt/equity') || text.includes('debttoequity') || text === 'd/e') return GLOSSARY.de;
      if (text.includes('currentratio')) return GLOSSARY.cr;
      if (text.includes('ebitdamargin')) return GLOSSARY.ebitda_margin;
      return '';
    },
  };
}
