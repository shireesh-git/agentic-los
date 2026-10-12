/* CAM Intelligence Platform — Pipeline page: agent list, streamed runs (GET /api/cases/{id}/run-stream), run-all.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camPipeline() {
  return {
    /* ─── Pipeline ─────────────────────────────────────────────────── */
    async loadAgents() {
      const r = await this.api('agents');
      this.agents = r.agents || [];
    },

    /* SSE-powered pipeline execution with live agent progress */
    runPipelineSSE() {
      if (!this.pipelineTarget || this.pipelineRunning) return;
      const entityId = this.pipelineTarget;
      this.pipelineRunning = true;
      this.pipelineError = false;
      this.agentEvents = [];
      this.agentPct = 0;
      this.agentProgress = '';
      this.pipelineDoneResult = null;
      this.camBuildSections = [];

      const es = new EventSource('/api/cases/' + entityId + '/run-stream');

      es.onmessage = (e) => {
        try {
          const evt = JSON.parse(e.data);
          if (evt.type === 'agent_start' || evt.type === 'agent_complete' || evt.type === 'info') {
            this.agentEvents = [...this.agentEvents, evt];
            if (evt.type === 'agent_complete' && evt.total) {
              // Agents can finish out of order when they run in parallel; `completed` is the true count.
              const done = evt.completed ?? evt.step;
              this.agentProgress = done + ' / ' + evt.total + ' agents done — ' + this.humanizeText(evt.agent);
              this.agentPct = Math.round((done / evt.total) * 100);
            } else if (evt.type === 'agent_start') {
              this.agentProgress = 'Running ' + this.humanizeText(evt.agent);
            }
          } else if (evt.type === 'section_start' || evt.type === 'section_complete') {
            this.agentEvents = [...this.agentEvents, evt];
            if (evt.type === 'section_complete' && evt.total) {
              this.agentProgress = 'Narrative: ' + (evt.completed ?? evt.step) + ' / ' + evt.total
                + ' sections written — ' + (evt.title || evt.section);
            } else if (evt.type === 'section_start') {
              this.agentProgress = 'Narrative: writing ' + (evt.title || evt.section);
            }
            // Track section build progress
            if (evt.type === 'section_start') {
              const idx = this.camBuildSections.findIndex(s => s.id === evt.section);
              if (idx >= 0) {
                this.camBuildSections[idx].status = 'writing';
              } else {
                this.camBuildSections = [...this.camBuildSections, { id: evt.section, title: evt.title || evt.section, status: 'writing', step: evt.step, total: evt.total }];
              }
            } else {
              const idx = this.camBuildSections.findIndex(s => s.id === evt.section);
              if (idx >= 0) {
                this.camBuildSections[idx].status = 'done';
                this.camBuildSections = [...this.camBuildSections];
              } else {
                this.camBuildSections = [...this.camBuildSections, { id: evt.section, title: evt.title || evt.section, status: 'done', step: evt.step, total: evt.total }];
              }
            }
          } else if (evt.type === 'done') {
            this.agentPct = 100;
            this.agentProgress = 'Complete';
            this.pipelineDoneResult = {
              entity_id: entityId,
              recommendation: evt.recommendation,
              risk_grade: evt.risk_grade,
              composite_score: evt.composite_score,
              narrative_mode: evt.narrative_mode,
            };
            this.pipelineRunning = false;
            es.close();
            this.notify('Pipeline complete — ' + (evt.recommendation || '').replace(/_/g, ' '), 'ok');
            this.pushNotification('CAM ready for ' + this.companyLabel(entityId) + ' — ' + this.fmtRec(evt.recommendation) + ', grade ' + (evt.risk_grade || '--'), 'ok', entityId, 'cam');
            this.loadCases();
            this.loadSummary();
          } else if (evt.type === 'error') {
            this.pipelineRunning = false;
            this.pipelineError = true;
            es.close();
            this.notify('Pipeline error: ' + (evt.message || 'unknown'), 'error');
            this.pushNotification('CAM run failed for ' + this.companyLabel(entityId) + ': ' + (evt.message || 'unknown error'), 'error', entityId, 'runs');
          }
        } catch {}
      };

      es.onerror = () => {
        this.pipelineRunning = false;
        this.pipelineError = true;
        es.close();
        if (!this.pipelineDoneResult) {
          this.notify('Pipeline connection lost', 'error');
        }
      };
    },

    async runAllPipeline() {
      this.loading = true;
      try {
        const r = await this.api('pipeline/run-all', { method: 'POST' });
        const total = r.results?.length || 0;
        if (r.failed) {
          const names = r.results.filter(x => x.error).map(x => x.entity_id).join(', ');
          this.notify((total - r.failed) + ' of ' + total + ' processed; failed: ' + names, 'error');
          this.pushNotification('Run all: ' + (total - r.failed) + ' of ' + total + ' borrowers processed; failed: ' + names, 'error');
        } else {
          this.notify('All ' + total + ' companies processed', 'ok');
          this.pushNotification('Run all: all ' + total + ' borrowers processed', 'ok');
        }
        await this.loadCases();
        await this.loadSummary();
      } catch {} finally { this.loading = false; }
    },

    selectedPipelineCase() {
      return this.caseMap[this.pipelineTarget] || null;
    },

    /* One row per pipeline agent, in pipeline order, with its status from the streamed events.
       Agents may run in parallel, so several can be 'running' at once. */
    runSteps() {
      const events = this.agentEvents;
      const names = this.agents.length
        ? this.agents.map(a => a.name)
        : [...new Set(events.filter(e => e.agent).map(e => e.agent))];
      return names.map(name => {
        const started = events.some(e => e.type === 'agent_start' && e.agent === name);
        const done = events.find(e => e.type === 'agent_complete' && e.agent === name);
        let status = 'pending';
        if (done) status = done.status === 'completed' ? 'done' : 'failed';
        else if (started && this.pipelineRunning) status = 'running';
        else if (started) status = 'failed';  // the run stopped before this agent finished
        return {
          name,
          status,
          duration_ms: done ? done.duration_ms : null,
          error: done?.error || '',
          detail: name === 'narrative' ? this.narrativeProgress(status) : '',
        };
      });
    },

    /* "8 of 21 sections written · writing: Financial Analysis" while the CAM is being written. */
    narrativeProgress(status) {
      const sections = this.agentEvents.filter(e => e.type === 'section_start' || e.type === 'section_complete');
      if (!sections.length) return '';
      const total = sections[sections.length - 1].total;
      const finished = new Set(sections.filter(e => e.type === 'section_complete').map(e => e.section));
      const writing = sections.filter(e => e.type === 'section_start' && !finished.has(e.section)).map(e => e.title || e.section);
      let text = finished.size + (total ? ' of ' + total : '') + ' sections written';
      if (status === 'running' && writing.length) text += ' · writing: ' + [...new Set(writing)].join(', ');
      return text;
    },
  };
}
