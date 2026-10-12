/* CAM Intelligence Platform — Final CAM workspace: CAM viewer, comments, section edits, PDF, memo, 360 view, chat.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camReports() {
  return {
    async loadReportProbe() {
      if (!this.reportEntity) {
        this.reportProbe = null;
        return;
      }
      try {
        this.reportProbe = await this.api('companies/' + this.reportEntity + '/probe');
      } catch {
        this.reportProbe = { available: false };
      }
    },

    chatMessageHtml(content, role = 'assistant') {
      const text = this.presentationText(content);
      if (role === 'assistant') {
        return this.renderMd(text)
          .replace(/^<p>\s*<\/p>/, '')
          .replace(/<p>\s*<\/p>$/,'');
      }
      return this.escapeHtml(text).replace(/\n/g, '<br>');
    },

    /* ─── Report Entity Change Event ─────────────────────────────── */
    async onReportEntityChange() {
      this.camHtml = '';
      this.camSections = [];
      this.camActiveSection = 0;
      this.camComments = {};
      this.camCommentDrafts = {};
      this.camCommentSaving = false;
      this.memoHtml = '';
      this.view360Data = null;
      this.chatMessages = [];
      this.reportProbe = null;
      this.approvalStatus = null;
      this.reportRunId = '';
      this.camEditMode = false;
      await Promise.all([this.loadReportProbe(), this.loadReportRuns()]);
    },

    /* ─── Runs: the CAM of an earlier run, read-only ─────────────────── */
    /* reportRunId '' = the latest run; otherwise a completed earlier run's case_run_id. */
    async loadReportRuns() {
      this.reportRuns = [];
      if (!this.reportEntity) return;
      try {
        const runs = (await this.api('cases/' + this.reportEntity + '/runs', undefined, { quiet: true })).runs || [];
        this.reportRuns = runs.filter(run => run.status === 'completed' && run.case_run_id);
      } catch {}
    },

    runQuery() {
      return this.reportRunId ? '?run_id=' + encodeURIComponent(this.reportRunId) : '';
    },

    isOldRun() {
      return !!this.reportRunId;
    },

    selectedReportRun() {
      return this.reportRuns.find(run => run.case_run_id === this.reportRunId) || null;
    },

    /* "Run 3 · 07 Oct, 07:16 · Grade C · latest" — numbered oldest = 1. */
    reportRunLabel(run) {
      if (!run.case_run_id) return '';
      const number = this.reportRuns.length - this.reportRuns.indexOf(run);
      return 'Run ' + number + ' · ' + this.formatRunTime(run.started_at)
        + (run.risk_grade ? ' · Grade ' + run.risk_grade : '') + (run.is_current ? ' · latest' : '');
    },

    async onReportRunChange() {
      this.camEditMode = false;
      this.camSections = [];
      this.camHtml = '';
      this.memoHtml = '';
      if (this.wtab === 'cam') await (this.camView === 'banker' ? this.loadFinalCam() : this.loadCAMReport());
      if (this.wtab === 'memo') await this.loadOnePager();
      if (this.wtab === 'observations') await this.loadObservations();
      if (this.wtab === 'investigations') await this.loadInvestigations();
      if (this.wtab === 'challenges') await this.loadChallenges();
      if (this.wtab === 'repayment') await this.loadRepayment();
      if (this.wtab === 'stress') await this.loadStress();
      if (this.wtab === 'reassessment') await this.loadReassessment();
    },

    /* ─── CAM Report Viewer ───────────────────────────────────────── */
    /* Open a borrower's workspace on its CAM; runId opens an earlier run's CAM ('' = latest). */
    openCamFor(entityId, runId = '') {
      return this.openWorkspace(entityId, 'cam', runId);
    },

    /* Previous / next section in the CAM viewer. */
    stepCamSection(delta) {
      const next = this.camActiveSection + delta;
      if (next >= 0 && next < this.camSections.length) {
        this.camActiveSection = next;
        document.querySelector('.cam-content-panel')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    },

    async loadCAMReport() {
      if (!this.reportEntity) return;
      this.loading = true;
      try {
        await this.loadReportProbe();
        // Fetch raw markdown for sectioned navigation
        const mdRes = await fetch('/api/cases/' + this.reportEntity + '/cam' + this.runQuery());
        if (!mdRes.ok) throw new Error('Failed to load CAM report');
        const mdData = await mdRes.json();
        const rawMd = mdData.cam_text || '';
        await this.loadCAMComments();

        // Parse markdown into sections — split on H2 headings (## )
        const parts = rawMd.split(/(?=\n## )/);
        if (parts.length > 1) {
          this.camSections = parts.map((part, idx) => {
            const trimmed = part.replace(/^\n/, '');
            const firstNL = trimmed.indexOf('\n');
            const heading = firstNL > 0 ? trimmed.slice(0, firstNL) : trimmed;
            const title = heading.replace(/^#+\s*/, '').trim() || ('Section ' + (idx + 1));
            return { id: idx, key: this.camSectionKey(title), title, html: this.renderMd(trimmed) };
          })
          // Drop cover/TOC fragments so the report nav stays focused on substantive CAM sections.
          .filter((s) => /^(\d+[a-z]?\.|annexure|appendix|disclaimer)/i.test(s.title));
          this.camActiveSection = 0;
          this.camHtml = '';
          await this.loadCamSectionEdits();
        } else {
          // Fallback: no section headings found, use HTML iframe
          this.camSections = [];
          const htmlRes = await fetch('/api/cases/' + this.reportEntity + '/cam-html' + this.runQuery());
          if (!htmlRes.ok) throw new Error('Failed to load CAM HTML');
          this.camHtml = await htmlRes.text();
        }
      } catch(e) {
        this.notify(e.message, 'error');
      } finally { this.loading = false; }
    },

    camSectionKey(title) {
      return (title || '').replace(/\s+/g, ' ').trim();
    },

    async loadCAMComments() {
      if (!this.reportEntity) {
        this.camComments = {};
        this.camCommentDrafts = {};
        return;
      }
      const r = await this.api('cases/' + this.reportEntity + '/comments' + this.runQuery());
      this.camComments = r.comments || {};
      this.camCommentDrafts = { ...this.camComments };
    },

    async saveCamComment() {
      const section = this.camSections[this.camActiveSection];
      if (!section || !this.reportEntity) return;
      this.camCommentSaving = true;
      try {
        const comments = { ...this.camComments };
        const value = (this.camCommentDrafts[section.key] || '').trim();
        if (value) comments[section.key] = value;
        else delete comments[section.key];
        const r = await this.api('cases/' + this.reportEntity + '/comments', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ comments }),
        });
        this.camComments = r.comments || comments;
        this.camCommentDrafts = { ...this.camCommentDrafts, [section.key]: this.camComments[section.key] || '' };
        this.notify('Section comment saved', 'ok');
      } catch {} finally { this.camCommentSaving = false; }
    },

    resetCamComment() {
      const section = this.camSections[this.camActiveSection];
      if (!section) return;
      this.camCommentDrafts = {
        ...this.camCommentDrafts,
        [section.key]: this.camComments[section.key] || '',
      };
    },

    toggleCamEditMode() {
      this.camEditMode = !this.camEditMode;
    },

    async loadCamSectionEdits() {
      if (!this.reportEntity) return;
      try {
        const r = await this.api('cases/' + this.reportEntity + '/cam-section-edits' + this.runQuery());
        this.camSectionEdits = r.edits || {};
        // Apply saved edits to section HTML
        for (const sec of this.camSections) {
          if (this.camSectionEdits[sec.key]) {
            sec.editedHtml = this.camSectionEdits[sec.key].html;
            sec.editedBy = this.camSectionEdits[sec.key].edited_by;
            sec.editedAt = this.camSectionEdits[sec.key].updated_at;
          }
        }
      } catch {}
    },

    async saveCamSectionEdit() {
      const section = this.camSections[this.camActiveSection];
      if (!section || !this.reportEntity) return;
      this.camEditSaving = true;
      try {
        const el = document.getElementById('cam-edit-area');
        if (!el) return;
        const editedHtml = el.innerHTML;
        const r = await this.api('cases/' + this.reportEntity + '/cam-section-edits', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ section_key: section.key, edited_html: editedHtml }),
        });
        this.camSectionEdits = r.edits || {};
        section.editedHtml = editedHtml;
        section.editedBy = 'RM';
        section.editedAt = new Date().toISOString();
        this.notify('Section edit saved', 'ok');
      } catch(e) {
        this.notify('Failed to save edit: ' + e.message, 'error');
      } finally { this.camEditSaving = false; }
    },

    revertCamSectionEdit() {
      const section = this.camSections[this.camActiveSection];
      if (!section) return;
      section.editedHtml = null;
      section.editedBy = null;
      section.editedAt = null;
      // Also delete from server
      if (this.reportEntity) {
        this.api('cases/' + this.reportEntity + '/cam-section-edits', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ section_key: section.key, edited_html: '' }),
        }).then(r => {
          this.camSectionEdits = r.edits || {};
          this.notify('Section reverted to original', 'ok');
        }).catch(() => {});
      }
    },

    async downloadCAMPdf() {
      if (!this.reportEntity) return;
      if (this.camView === 'banker') {   // the final 12-section CAM
        window.open('/api/cases/' + this.reportEntity + '/final-cam-pdf' + this.runQuery(), '_blank');
        return;
      }
      const section = this.camSections[this.camActiveSection];
      if (section) {
        const draft = (this.camCommentDrafts[section.key] || '').trim();
        const saved = this.camComments[section.key] || '';
        if (draft !== saved) await this.saveCamComment();
      }
      window.open('/api/cases/' + this.reportEntity + '/cam-pdf' + this.runQuery(), '_blank');
    },

    openCamNewTab() {
      if (!this.reportEntity) return;
      window.open('/api/cases/' + this.reportEntity + '/cam-html' + this.runQuery(), '_blank');
    },

    /* ─── One-Page Memo ────────────────────────────────────────────── */
    async loadOnePager() {
      if (!this.reportEntity) return;
      this.loading = true;
      try {
        const r = await fetch('/api/cases/' + this.reportEntity + '/one-pager' + this.runQuery());
        if (!r.ok) throw new Error('Failed to load one-page memo');
        this.memoHtml = await r.text();
      } catch(e) {
        this.notify(e.message, 'error');
      } finally { this.loading = false; }
    },

    openMemoNewTab() {
      if (!this.reportEntity) return;
      window.open('/api/cases/' + this.reportEntity + '/one-pager' + this.runQuery(), '_blank');
    },

    /* ─── Analyst Chat ─────────────────────────────────────────────── */
    async loadChatHistory() {
      if (!this.reportEntity) { this.chatMessages = []; return; }
      try {
        await this.loadReportProbe();
        const r = await this.api('chat/' + this.reportEntity + '/history');
        this.chatMessages = r.messages || [];
        this.$nextTick(() => this.scrollChat());
      } catch { this.chatMessages = []; }
    },

    async sendChat() {
      if (!this.reportEntity || !this.chatInput.trim()) return;
      const msg = this.chatInput.trim();
      this.chatInput = '';
      this.chatMessages.push({ role: 'user', content: msg });
      this.chatLoading = true;
      this.$nextTick(() => this.scrollChat());
      try {
        const r = await this.api('chat/' + this.reportEntity, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: msg }),
        });
        this.chatMessages.push({ role: 'assistant', content: r.response });
      } catch(e) {
        this.chatMessages.push({ role: 'assistant', content: 'Error: ' + e.message });
      } finally {
        this.chatLoading = false;
        this.$nextTick(() => this.scrollChat());
      }
    },

    /* Suggested questions shown beside the chat. */
    chatSuggestions() {
      return [
        { label: 'Explain the decision', question: 'Explain the credit decision and key factors' },
        { label: 'Credit positives', question: 'Summarize the strongest credit positives and what supports them' },
        { label: 'Unresolved risks', question: 'List the main unresolved risk items and why they matter' },
        { label: 'Governance & compliance', question: 'Summarize the governance and compliance findings for this case' },
        { label: 'Ratings, legal & charges', question: 'What do the current ratings, legal matters and open charges show?' },
        { label: 'Market signals', question: 'Summarize the market signals, ratings and legal matters for this case' },
        { label: 'Missing documents', question: 'Which documents are still missing before this CAM should be treated as credit-ready?' },
        { label: 'How to strengthen the CAM', question: 'What additional documents or analyst actions would strengthen this CAM?' },
      ];
    },

    chatQuick(msg) {
      this.chatInput = msg;
      this.sendChat();
    },

    async clearChat() {
      if (!this.reportEntity) return;
      try {
        await this.api('chat/' + this.reportEntity, { method: 'DELETE' });
        this.chatMessages = [];
        this.notify('Chat cleared', 'ok');
      } catch {}
    },

    scrollChat() {
      const el = document.getElementById('chatMessages');
      if (el) el.scrollTop = el.scrollHeight;
    },

    /* ─── 360° View ────────────────────────────────────────────────── */
    async load360() {
      if (!this.reportEntity) return;
      this.loading = true;
      this.view360Data = null;
      try {
        this.view360Data = await this.api('companies/' + this.reportEntity + '/360');
        this.v360tab = 'overview';
      } catch {} finally { this.loading = false; }
    },
  };
}
