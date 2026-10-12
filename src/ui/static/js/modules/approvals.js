/* CAM Intelligence Platform — Approval workflow: authority matrix, queue, maker-checker actions.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camApprovals() {
  return {
    /* ─── Approval Workflow ────────────────────────────────────────── */
    async loadApprovalMatrix() {
      try {
        const r = await this.api('approvals/authority-matrix');
        this.approvalLevels = r.levels || [];
        this.approvalMakerRoles = r.maker_roles || [];
        this.decisionTatDays = Number(r.decision_tat_days) || 3;
      } catch {
        this.approvalLevels = [];
        this.approvalMakerRoles = [];
      }
    },

    async loadApproval() {
      if (!this.reportEntity || !this.caseMap[this.reportEntity]) { this.approvalStatus = null; return; }
      try { this.approvalStatus = await this.api('cases/' + this.reportEntity + '/workflow'); }
      catch { this.approvalStatus = null; }
      await this.loadApprovalQueue();
    },

    /* Cases waiting for the selected authority level (makers have no queue). */
    async loadApprovalQueue() {
      const isAuthority = this.approvalLevels.some(l => l.id === this.approvalRole);
      if (!isAuthority) { this.approvalQueue = []; return; }
      try {
        const r = await this.api('approvals/queue?authority=' + encodeURIComponent(this.approvalRole));
        this.approvalQueue = r.cases || [];
      } catch { this.approvalQueue = []; }
    },

    /* A submitted case waiting longer than the configured decision TAT (config/approval.yaml). */
    isOverdue(waitingSince) {
      const days = this.daysSince(waitingSince);
      return days !== null && days > this.decisionTatDays;
    },

    approvalCommentsRequired() {
      // Mirrors ApprovalService.act: reject/return always, approve only against a system decline.
      const actions = this.approvalStatus?.allowed_actions || [];
      return actions.includes('reject') || actions.includes('return')
        || (actions.includes('approve') && this.approvalStatus?.system_recommendation === 'decline');
    },

    approvalActionClass(action) {
      if (action === 'approve' || action === 'submit') return 'btn-primary';
      if (action === 'reject') return 'btn-danger';
      return 'btn-outline';
    },

    async takeApprovalAction(action) {
      if (!this.reportEntity || !this.approvalRole || !this.approvalUserId.trim()) return;
      this.loading = true;
      try {
        const conditions = this.approvalConditions.split('\n').map(s => s.trim()).filter(Boolean);
        this.approvalStatus = await this.api('cases/' + this.reportEntity + '/workflow/' + action, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-User-Id': this.approvalUserId.trim(),
            'X-User-Role': this.approvalRole,
          },
          body: JSON.stringify({ comments: this.approvalComments, conditions }),
        });
        this.approvalComments = '';
        this.approvalConditions = '';
        this.notify('Case ' + this.titleCase(this.approvalStatus?.status || action), 'ok');
        await Promise.all([this.loadApprovalQueue(), this.loadSummary()]);
      } catch {} finally { this.loading = false; }
    },
  };
}
