/* CAM Intelligence Platform — Display formatting, labels and the markdown renderer (no API calls).
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camFormatters() {
  return {
    companyInitials(name) {
      return (name || '')
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map(part => part[0])
        .join('')
        .toUpperCase() || '--';
    },

    humanizeText(value) {
      const raw = String(value || '').trim();
      if (!raw) return '';
      const tokenMap = {
        api: 'API',
        cam: 'CAM',
        cin: 'CIN',
        crilc: 'CRILC',
        epfo: 'EPFO',
        etb: 'ETB',
        gst: 'GST',
        it: 'IT',
        kyc: 'KYC',
        llm: 'LLM',
        mca: 'MCA',
        mcp: 'MCP',
        ntb: 'NTB',
        pan: 'PAN',
        pvt: 'Pvt',
        ltd: 'Ltd',
        limited: 'Limited',
        private: 'Private',
        public: 'Public',
        llp: 'LLP',
        llc: 'LLC',
        plc: 'PLC',
      };
      const lowerWords = new Set(['and', 'of', 'for', 'to', 'in', 'on', 'the']);
      return raw
        .replace(/_/g, ' ')
        .split(/\s+/)
        .map((token, index) => {
          const normalized = token.toLowerCase();
          if (normalized === 'the') return index === 0 ? 'The' : 'the';
          if (tokenMap[normalized]) return tokenMap[normalized];
          if (lowerWords.has(normalized) && index > 0) return normalized;
          if (!/[a-z]/.test(token) && /^[A-Z0-9&.-]{2,4}$/.test(token)) return token;
          return normalized.charAt(0).toUpperCase() + normalized.slice(1);
        })
        .join(' ');
    },

    displayCompanyName(value) {
      return this.humanizeText(value) || '--';
    },

    providerLabel(provider) {
      if (!provider) return 'Internal';
      if (provider === 'probe42_mcp_v2') return 'Verified Public Data';
      if (provider === 'mock_external') return 'External Data';
      return this.humanizeText(provider);
    },

    probeRecordLabel(key) {
      const labels = {
        base_details: 'Company master',
        open_charges: 'Open charges',
        kyc_details: 'KYC and directors',
        legal_history: 'Legal history',
        credit_ratings: 'Ratings',
        gst_details: 'GST profile',
        epfo_details: 'EPFO profile',
        suit_filed_cases: 'Suit-filed cases',
        director_network: 'Director network',
        data_status: 'Freshness',
      };
      return labels[key] || this.humanizeText(key);
    },

    probeRecordRows(snapshot) {
      const toolStatus = snapshot?.tool_status || {};
      return [
        'base_details',
        'kyc_details',
        'credit_ratings',
        'gst_details',
        'legal_history',
        'open_charges',
        'epfo_details',
        'suit_filed_cases',
        'director_network',
        'data_status',
      ].map((key) => ({
        key,
        label: this.probeRecordLabel(key),
        status: toolStatus[key] || 'not_fetched',
      }));
    },

    availableProbeRecordCount(snapshot) {
      return this.probeRecordRows(snapshot).filter(row => row.status === 'success').length;
    },

    sourceStatusLabel(status) {
      const value = (status || 'unknown').toLowerCase();
      if (value === 'success') return 'available';
      if (value === 'not_found') return 'not available';
      if (value === 'not_fetched') return 'not fetched';
      return this.humanizeText(value);
    },

    sourceStatusClass(status) {
      const value = (status || 'unknown').toLowerCase();
      if (value === 'success') return 'badge-green';
      if (value === 'not_found') return 'badge-amber';
      return 'badge-grey';
    },

    policyRuleLabel(code, fallbackDescription = '') {
      const labels = {
        HR_WILFUL_DEFAULTER: 'Wilful defaulter screening',
        HR_COMPANY_ACTIVE: 'Active company status',
        HR_NO_CRITICAL_EXCEPTIONS: 'Critical validation clearance',
        HR_KYC_COMPLETE: 'KYC package completeness',
        HR_BUREAU_STATUS: 'Public-record stress screening',
        HR_PUBLIC_RECORD_STATUS: 'Public-record stress screening',
        HR_MIN_VINTAGE: 'Minimum business vintage',
        HR_FRAUD_REGISTRY: 'Fraud registry screening',
        HR_RBI_DEFAULTER: 'RBI defaulter screening',
        HR_SUIT_FILED: 'Suit-filed exposure threshold',
      };
      return labels[code] || fallbackDescription || this.humanizeText(String(code || '').replace(/^HR_/, '').replace(/_/g, ' '));
    },

    exceptionLabel(code) {
      const labels = {
        XSRC_DEBT_BUREAU_MISMATCH: 'Debt vs public-record exposure mismatch',
        XSRC_BUREAU_DPD_ALERT: 'Public-record stress status alert',
        XSRC_BUREAU_WILFUL_DEFAULTER: 'Wilful defaulter alert',
        XSRC_REVENUE_MISMATCH: 'Cross-source revenue mismatch',
        DOC_REVENUE_CROSS_SOURCE: 'Document revenue mismatch',
        STRUCT_PAT_INCONSISTENT: 'PAT structure mismatch',
        STRUCT_EBITDA_INCONSISTENT: 'EBITDA structure mismatch',
      };
      return labels[code] || this.humanizeText(String(code || '').replace(/^(XSRC|DOC|STRUCT)_/, '').replace(/_/g, ' '));
    },

    presentationText(value) {
      return String(value || '')
        .replace(/\bBureau\b/g, 'Public-record')
        .replace(/\bbureau\b/g, 'public-record')
        .replace(/Wilful Defaulter in public-record records/g, 'Wilful Defaulter in public records')
        .replace(/â€”/g, '-')
        .replace(/—/g, '-');
    },

    titleCase(value) {
      return this.humanizeText(value);
    },

    caseTypeLabel(value) {
      const raw = String(value || '').trim();
      if (!raw) return '--';
      const upper = raw.toUpperCase();
      if (['NTB', 'ETB', 'TL', 'OD', 'CC', 'WC'].includes(upper)) return upper;
      return this.humanizeText(raw);
    },

    modeLabel(value) {
      const raw = String(value || '').trim();
      if (!raw) return 'Template';
      if (raw.toLowerCase() === 'llm') return 'LLM';
      if (raw.toLowerCase() === 'template') return 'Template';
      return this.humanizeText(raw);
    },

    displayScore(value) {
      const num = Number(value);
      if (Number.isNaN(num) || num <= 0) return '--';
      return Number.isInteger(num) ? num.toFixed(0) : num.toFixed(1);
    },

    cacheTtlLabel(hours) {
      const ttl = Number(hours || 0);
      if (!ttl) return 'Until deleted';
      if (ttl % 24 === 0) {
        const days = ttl / 24;
        return days === 1 ? '1 day' : (days + ' days');
      }
      return ttl + 'h';
    },

    formatCurrencyCr(value) {
      const num = Number(value || 0);
      if (!num) return 'Rs. 0 Cr';
      return 'Rs. ' + num.toLocaleString('en-IN', { maximumFractionDigits: num >= 100 ? 0 : 2 }) + ' Cr';
    },

    formatDecimal(value, digits = 1) {
      const num = Number(value);
      if (Number.isNaN(num)) return '--';
      return num.toLocaleString('en-IN', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
    },

    severityClass(severity) {
      const value = String(severity || '').toLowerCase();
      if (value === 'critical' || value === 'high') return 'badge-red';
      if (value === 'medium') return 'badge-amber';
      if (value === 'low') return 'badge-green';
      return 'badge-info';
    },

    severityCount(flags, severity) {
      const targets = Array.isArray(severity) ? severity : [severity];
      return (flags || []).filter(flag => targets.includes(String(flag?.severity || '').toLowerCase())).length;
    },

    stanceClass(stance) {
      const value = String(stance || '').toLowerCase();
      if (value.includes('favourable') || value.includes('positive')) return 'badge-green';
      if (value.includes('stable') || value.includes('mixed')) return 'badge-info';
      if (value.includes('watch')) return 'badge-amber';
      if (value.includes('cautious') || value.includes('negative')) return 'badge-red';
      return 'badge-grey';
    },

    escapeHtml(value) {
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    },

    formatRunTime(value) {
      if (!value) return 'Pending';
      const dt = new Date(value);
      if (Number.isNaN(dt.getTime())) return value;
      return dt.toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      });
    },

    /* Pipeline agent ids (src/agents) as business-readable step names. */
    agentLabel(name) {
      return ({
        data_ingestion: 'Collect data & documents',
        pep_screening: 'PEP & sanctions screening',
        financial_analysis: 'Financial analysis',
        validation: 'Validation checks',
        benchmark: 'Peer benchmarking',
        policy: 'Risk score & recommendation',
        narrative: 'Write CAM',
      })[name] || this.humanizeText(name);
    },

    formatDuration(ms) {
      const value = Number(ms);
      if (!value && value !== 0) return '--';
      if (value < 1000) return value + ' ms';
      const seconds = Math.round(value / 1000);
      if (seconds < 60) return seconds + 's';
      return Math.floor(seconds / 60) + 'm ' + String(seconds % 60).padStart(2, '0') + 's';
    },

    /* ─── Formatters ───────────────────────────────────────────────── */
    gradeCls(g) {
      if (!g) return '';
      if (g === 'A') return 'badge-green';
      if (g === 'B') return 'badge-blue';
      if (g === 'C') return 'badge-amber';
      return 'badge-red';
    },

    recCls(r) {
      if (!r) return '';
      if (r === 'approve') return 'badge-green';
      if (r === 'conditional_approve') return 'badge-blue';
      if (r === 'refer') return 'badge-amber';
      if (r === 'decline') return 'badge-red';
      return '';
    },

    sevCls(s) {
      if (s === 'critical') return 'badge-red';
      if (s === 'high') return 'badge-amber';
      if (s === 'medium') return 'badge-blue';
      return 'badge-info';
    },

    scoreCls(s) {
      if (s >= 65) return 'score-good';
      if (s >= 50) return 'score-ok';
      return 'score-bad';
    },

    fmtRec(r) {
      if (!r) return '';
      return this.humanizeText(r);
    },

    fmtTime(t) {
      if (!t) return '';
      try {
        const d = new Date(t);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      } catch { return t; }
    },

    /* ─── Markdown Renderer ────────────────────────────────────────── */
    renderMd(text) {
      if (!text) return '';
      let h = this._escHtml(text);

      /* Tables  —  | col | col | */
      h = h.replace(/((?:^\|.+\|$\n?)+)/gm, (block) => {
        const rows = block.trim().split('\n').filter(r => r.trim());
        if (rows.length < 2) return block;
        let tbl = '<table>';
        rows.forEach((row, i) => {
          // skip separator row  |---|
          if (/^\|[\s\-:|]+\|$/.test(row)) return;
          const cells = row.split('|').slice(1, -1);
          const tag = i === 0 ? 'th' : 'td';
          tbl += '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
        });
        tbl += '</table>';
        return tbl;
      });

      /* Headings */
      h = h.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
      h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
      h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
      h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>');

      /* Bold / italic */
      h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      h = h.replace(/\*(.+?)\*/g, '<em>$1</em>');

      /* Horizontal rule */
      h = h.replace(/^---+$/gm, '<hr>');

      /* Bullet lists */
      h = h.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
      h = h.replace(/((?:<li>.+<\/li>\n?)+)/g, '<ul>$1</ul>');

      /* Numbered lists */
      h = h.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

      /* Paragraphs */
      h = h.replace(/\n{2,}/g, '</p><p>');
      h = '<p>' + h + '</p>';
      h = h.replace(/<p>\s*<(h[1-4]|table|ul|ol|hr|li)/g, '<$1');
      h = h.replace(/<\/(h[1-4]|table|ul|ol|hr|li)>\s*<\/p>/g, '</$1>');
      return h;
    },

    _escHtml(s) {
      return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },
  };
}
