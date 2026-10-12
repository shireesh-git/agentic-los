/* CAM Intelligence Platform — CAM Journey: borrower dropdowns, onboarding, uploads, CAM drafting, manual entry.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camJourney() {
  return {
    startCamJourney() {
      this.onboardMode = 'smart';
      this.journeyStage = 'select';
      this.resolvePreview = null;
      this.onboardResult = null;
      this.etbLookupResult = null;
      this.etbLookupError = '';
      this.onboardPick = '';
      this.onboardId = '';
      this.onboardPurpose = '';
      this.onboardAmount = null;
      this.onboardFacility = 'working_capital';
      this.onboardCaseType = 'NTB';
      this.onboardCrilcAvailable = false;
      this.navigate('onboard');
    },

    journeySteps() {
      return [
        { key: 'select', label: 'Journey' },
        { key: 'entity', label: 'Entity' },
        { key: 'retrieved', label: 'Verified Data' },
        { key: 'ready', label: 'Final CAM' },
      ];
    },

    journeyStepState(key) {
      const stageRank = {
        select: 0,
        entity: 1,
        aggregating: 1,
        retrieved: 2,
        prebuilt: 2,
        drafting: 3,
        ready: 3,
      };
      const current = stageRank[this.journeyStage] ?? 0;
      const target = stageRank[key] ?? 0;
      if (target < current) return 'done';
      if (target === current) return 'active';
      return 'upcoming';
    },

    selectJourney(mode) {
      this.onboardCaseType = mode;
      this.journeyStage = 'entity';
    },

    /* ─── Journey form dropdowns (options come from GET /api/companies test data) ── */
    journeyBorrowerOptions(matchingCaseType) {
      return this.companies
        .filter(c => (c.case_type === this.onboardCaseType) === matchingCaseType)
        .slice()
        .sort((a, b) => (a.company_name || '').localeCompare(b.company_name || ''));
    },

    journeyBorrowerLabel(company) {
      return this.displayCompanyName(company.company_name) + ' (' + company.entity_id + ')';
    },

    journeyPickedCompany() {
      if (!this.onboardPick || this.onboardPick === '__other__') return null;
      return this.companies.find(c => c.entity_id === this.onboardPick) || null;
    },

    journeyIdentifierLine(company) {
      if (!company) return '';
      return ['CIN ' + (company.cin || 'not on record'),
              'PAN ' + (company.pan || 'not on record'),
              'GSTIN ' + (company.gstin || 'not on record')].join(' · ');
    },

    /* Prefill the rest of the form from the borrower's test data. */
    onJourneyBorrowerPicked() {
      this.resolvePreview = null;
      this.etbLookupResult = null;
      this.etbLookupError = '';
      const company = this.journeyPickedCompany();
      if (!company) {
        this.onboardId = '';
        return;
      }
      this.onboardId = company.preferred_identifier || company.company_name || company.entity_id;
      if (company.facility_type) this.onboardFacility = company.facility_type;
      if (Number(company.requested_amount_cr) > 0) this.onboardAmount = Number(company.requested_amount_cr);
      if (company.purpose && !this.isPlaceholderPurpose(company.purpose)) this.onboardPurpose = company.purpose;
    },

    isPlaceholderPurpose(purpose) {
      return /to be captured/i.test(String(purpose || ''));
    },

    journeyAmountOptions() {
      const company = this.journeyPickedCompany();
      const testAmount = Number(company?.requested_amount_cr) || 0;
      const values = new Set([25, 50, 100, 250, 500, 1000, 1500, 2500]);
      if (testAmount > 0) values.add(testAmount);
      if (Number(this.onboardAmount) > 0) values.add(Number(this.onboardAmount));
      return [...values].sort((a, b) => a - b).map(value => ({
        value,
        label: this.formatCurrencyCr(value) + (value === testAmount ? ' — test data' : ''),
      }));
    },

    journeyPurposeOptions() {
      const options = [
        'Working capital augmentation',
        'Capital expenditure',
        'Refinancing of existing debt',
        'Renewal of existing limits',
        'Project finance',
        'General corporate purpose',
      ];
      const testPurpose = this.journeyPickedCompany()?.purpose;
      if (testPurpose && !this.isPlaceholderPurpose(testPurpose) && !options.includes(testPurpose)) {
        options.unshift(testPurpose);
      }
      if (this.onboardPurpose && !options.includes(this.onboardPurpose)) options.unshift(this.onboardPurpose);
      return options;
    },

    /* Mandatory journey fields: borrower identifier, facility type and amount. */
    journeyFormComplete() {
      return !!this.onboardId.trim() && !!this.onboardFacility && Number(this.onboardAmount) > 0;
    },

    journeyEntityId() {
      return this.onboardResult?.entity_id || this.resolvePreview?.entity_id || this.pipelineTarget || this.reportEntity || '';
    },

    activeJourneyCase() {
      const entityId = this.journeyEntityId();
      return entityId ? (this.caseMap[entityId] || null) : null;
    },

    journeyCurrentCase() {
      const entityId = this.journeyEntityId();
      if (!entityId) return null;
      if (this.caseMap[entityId]) return this.caseMap[entityId];
      if (this.pipelineDoneResult?.entity_id === entityId) return this.pipelineDoneResult;
      return null;
    },

    /* Badges only for checks the backend actually returned data for. */
    journeySourceBadges() {
      const preview = this.resolvePreview || {};
      return [
        preview.cin ? 'Company Registry Matched' : null,
        preview.pan ? 'PAN Identified' : null,
        preview.gstin ? 'GST Registration Found' : null,
        this.onboardResult?.probe_summary ? 'Ratings & Legal Snapshot' : null,
        this.probeStatus?.configured ? 'Connected Data Feed' : 'Cached Case Data',
      ].filter(Boolean);
    },

    journeyRetrievedInfo() {
      const preview = this.resolvePreview || {};
      const probe = this.onboardResult?.probe_summary || {};
      return [
        {
          title: 'Corporate Information',
          items: [
            'Legal Name: ' + (preview.company_name || 'Pending resolution'),
            'CIN: ' + (preview.cin || 'Not available'),
            'PAN: ' + (preview.pan || 'Not available'),
            'Listing Status: ' + (probe.listing_status || 'Not available'),
          ],
        },
        {
          title: 'Compliance & Registration',
          items: [
            'GSTIN: ' + (preview.gstin || 'Not available'),
            'Status: ' + (probe.status || 'Not available'),
            'Registry health: ' + (probe.compliance_status || 'Not available'),
            'Retention: Verified public records stay attached until removed',
          ],
        },
        {
          title: 'Directors & Management',
          items: [
            'Directors captured: ' + (probe.directors_count ?? 'Not available'),
            'KYC status: ' + (probe.kyc_status || 'Not available'),
            'Open charges: ' + (probe.open_charge_count ?? 'Not available'),
            'Legal cases: ' + (probe.legal_case_count ?? 'Not available'),
          ],
        },
        {
          title: 'Financial Filings Available',
          items: [
            'Ratings snapshot: ' + (probe.rating || 'Unrated'),
            'Validation mode: Public-record baseline + latest RM uploads override',
            'Requested facility: ' + this.titleCase(this.onboardFacility || 'working_capital'),
            'Coverage: ' + this.titleCase(this.onboardResult?.profile || this.probeStatus?.bundle_profile || 'full'),
          ],
        },
      ];
    },

    journeyRequiredUploads() {
      return [
        { title: 'Audited Financial Statements', roleKey: 'audited_financial_statements', category: 'financials', hint: 'Upload latest 3 years audited financials' },
        { title: 'Provisional Financials', roleKey: 'provisional_financials', category: 'financials', hint: 'Upload latest provisional or management financials' },
        { title: 'Debt Schedule', roleKey: 'debt_schedule', category: 'financials', hint: 'Upload detailed debt schedule & lender-wise exposure' },
        { title: 'Board Resolution', roleKey: 'board_resolution', category: 'kyc', hint: 'Upload board resolution / borrowing approval' },
        { title: 'CMA Or Projection', roleKey: 'cma_or_projection', category: 'request', hint: 'Upload CMA data / projections / repayment assumptions' },
      ];
    },

    journeyPendingRequiredCount() {
      const missing = this.docGaps?.required_missing_documents || [];
      return missing.length;
    },

    journeyMissingRequiredUploads() {
      const gaps = this.docGaps?.required_missing_documents || [];
      return gaps.map((item) => ({
        title: this.titleCase((item.type || 'document').replaceAll('_', ' ')),
        roleKey: item.type || '',
        category: item.category || 'misc',
        hint: item.description || 'Upload latest borrower-provided document',
      }));
    },

    journeyRetrievedDocuments() {
      const files = [];
      const categories = this.docData?.categories || {};
      Object.values(categories).forEach((info) => {
        (info.items || []).forEach((item) => {
          if (item.file_type !== 'document') return;
          files.push({
            filename: item.filename,
            category: item.category || '',
            displayLabel: item.document_role_label || this.humanizeText(item.category || 'document') || 'Document',
          });
        });
      });
      return files;
    },

    journeyVerifiedSourceCount() {
      const summary = this.onboardResult?.source_summary || {};
      const statuses = Object.values(summary).map(value => String(value || '').toLowerCase());
      const successCount = statuses.filter(value => value === 'success').length;
      if (successCount) return successCount;
      return this.availableProbeRecordCount(this.docProbe);
    },

    journeyWorkspaceDocumentCount() {
      const storedCount = this.onboardResult?.documents_stored?.document_file_count;
      if (typeof storedCount === 'number') return storedCount;
      const visibleCount = this.docData?.document_file_count;
      if (typeof visibleCount === 'number') return visibleCount;
      return this.journeyRetrievedDocuments().length;
    },

    journeyVerifiedCoverageLabel() {
      const verified = this.journeyVerifiedSourceCount();
      if (verified >= 9) return 'Comprehensive';
      if (verified >= 6) return 'Strong';
      if (verified >= 3) return 'Partial';
      return 'Pending';
    },

    journeyOptionalInputs() {
      return [
        {
          key: 'site_visit_report',
          title: 'Site Visit Report',
          category: 'request',
          hint: 'Branch visit notes, promoter meetings, and operating observations.',
          sourceHint: 'RM, branch team, or field visit partner',
          camSection: '2. Borrower Profile / 7. Risk Assessment',
        },
        {
          key: 'valuation_report',
          title: 'Valuation Report',
          category: 'collateral',
          hint: 'Security valuation, FSV assumptions, and collateral comfort.',
          sourceHint: 'Empanelled valuer or collateral team',
          camSection: '6. Security & Collateral',
        },
        {
          key: 'bank_statements',
          title: 'Bank Statements',
          category: 'banking',
          hint: 'Latest operating account conduct and cash flow validation.',
          sourceHint: 'Borrower bank statements or internal CBS for ETB cases',
          camSection: '10. Account Conduct',
        },
        {
          key: 'financial_projections',
          title: 'Financial Projections',
          category: 'request',
          hint: 'CMA, projected cash flows, and repayment assumptions.',
          sourceHint: 'Borrower CFO pack, CMA data, or RM projections sheet',
          camSection: '4. Financial Analysis / 5. Facility Details',
        },
        {
          key: 'credit_facility_details',
          title: 'Credit Facility Details',
          category: 'banking',
          hint: 'Existing sanctions, limits, and lender-wise exposure.',
          sourceHint: 'Internal LMS, sanction tracker, or lender-wise exposure note',
          camSection: '5. Credit Facility Details',
        },
        {
          key: 'internal_credit_notes',
          title: 'Internal Credit Notes',
          category: 'misc',
          hint: 'RM or analyst notes that strengthen the approval narrative.',
          sourceHint: 'RM, analyst, branch credit desk, or sanction memo',
          camSection: '1. Executive Summary / 12. Recommendation',
        },
        {
          key: 'property_documents',
          title: 'Property Documents',
          category: 'collateral',
          hint: 'Title deed, search report, and encumbrance certificate.',
          sourceHint: 'Collateral team / empanelled valuer / legal department',
          camSection: '6. Security & Collateral',
        },
        {
          key: 'cersai_search',
          title: 'CERSAI Search Report',
          category: 'legal',
          hint: 'Central registry search for existing security interests.',
          sourceHint: 'Central Registry (CERSAI) / legal & compliance team',
          camSection: '6. Security & Collateral',
        },
        {
          key: 'insurance_policies',
          title: 'Insurance Policies',
          category: 'collateral',
          hint: 'Property, stock, and key man insurance coverage.',
          sourceHint: 'Borrower / insurance broker / risk management team',
          camSection: '6. Security & Collateral / 7. Risk Assessment',
        },
        {
          key: 'undertakings',
          title: 'Undertakings & Declarations',
          category: 'legal',
          hint: 'Non-default declaration, information consent, end-use undertaking.',
          sourceHint: 'Borrower / Company Secretary / legal team',
          camSection: '8. Compliance / 12. Recommendation',
        },
        {
          key: 'board_resolution_borrowing',
          title: 'Board Resolution — Borrowing',
          category: 'kyc',
          hint: 'Board resolution authorising borrowing powers.',
          sourceHint: 'Company Secretary / legal team',
          camSection: '8. Compliance',
        },
      ];
    },

    /* Unified document checklist — merges retrieved, required, and optional into one list */
    journeyAllDocuments() {
      const rows = [];
      const claimedFiles = new Set();

      /* Build all visible files from docData */
      const allFiles = [];
      const categories = this.docData?.categories || {};
      Object.values(categories).forEach((info) => {
        (info.items || []).forEach((item) => {
          if (item.file_type !== 'document') return;
          allFiles.push({
            filename: item.filename,
            category: (item.category || '').toLowerCase(),
            document_role: item.document_role || '',
            document_role_label: item.document_role_label || '',
            source: item.source || '',
          });
        });
      });

      /* Claim files matching a role key within a category */
      const claimFiles = (category, roleKey) => {
        const catKey = (category || '').toLowerCase();
        const matched = [];
        allFiles.forEach((f) => {
          const key = f.category + '/' + f.filename;
          if (claimedFiles.has(key)) return;
          if (f.category !== catKey) return;
          if (roleKey && f.document_role === roleKey) {
            matched.push(f);
            claimedFiles.add(key);
          }
        });
        return matched;
      };

      /* 1. Required RM uploads — match files by document_role */
      const required = this.journeyRequiredUploads();
      required.forEach((doc) => {
        const matches = claimFiles(doc.category, doc.roleKey);
        rows.push({
          title: doc.title,
          status: matches.length > 0 ? 'uploaded' : 'missing',
          statusLabel: matches.length > 0 ? matches.length + ' file(s)' : doc.hint,
          camSection: '',
          category: doc.category,
          canUpload: true,
          group: 'required',
          roleKey: doc.roleKey,
          files: matches,
        });
      });

      /* 2. Optional / additional inputs — match files by key */
      this.journeyOptionalInputs().forEach((doc) => {
        const matches = claimFiles(doc.category, doc.key);
        rows.push({
          title: doc.title,
          status: matches.length > 0 ? 'uploaded' : 'pending',
          statusLabel: matches.length > 0 ? matches.length + ' file(s)' : doc.hint,
          camSection: doc.camSection,
          category: doc.category,
          canUpload: true,
          group: 'optional',
          key: doc.key,
          files: matches,
        });
      });

      /* 3. Unclaimed files — group by document_role or category */
      const unclaimed = allFiles.filter((f) => !claimedFiles.has(f.category + '/' + f.filename));
      const groups = {};
      unclaimed.forEach((f) => {
        const groupKey = f.document_role || f.category;
        if (!groups[groupKey]) groups[groupKey] = { files: [], category: f.category, label: f.document_role_label || this.humanizeText(f.category) || 'Other' };
        groups[groupKey].files.push(f);
      });
      Object.values(groups).forEach((g) => {
        rows.push({
          title: g.label,
          status: 'available',
          statusLabel: g.files.length + ' file(s)',
          camSection: '',
          category: g.category,
          canUpload: true,
          group: 'retrieved',
          files: g.files,
        });
      });

      return rows;
    },

    journeyReviewStats() {
      /* Case summaries carry these counts; the full fact pack is not loaded here. */
      const activeCase = this.journeyCurrentCase() || {};
      return [
        { value: activeCase.key_risk_count || 0, label: 'Key risk signals identified' },
        { value: activeCase.exception_count || 0, label: 'Validation exceptions requiring review' },
        { value: this.camSections.length || '--', label: 'CAM sections loaded for review' },
      ];
    },

    async launchJourneyPreparation() {
      if (!this.journeyFormComplete()) return;
      this.journeyStage = 'aggregating';
      this.loading = true;
      this.onboardResult = null;
      try {
        const payload = {
          identifier: this.onboardId.trim(),
          facility_type: this.onboardFacility || 'working_capital',
          amount_requested_cr: Number(this.onboardAmount),
          case_type: this.onboardCaseType || 'NTB',
          purpose: this.onboardPurpose || 'General corporate purpose',
          crilc_available: this.onboardCrilcAvailable,
        };
        if (this.onboardCaseType === 'ETB' && this.etbLookupResult) payload.etb_data = this.etbLookupResult;
        const result = await this.api('onboard', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        this.onboardResult = result;
        this.resolvePreview = result.resolved_from || this.resolvePreview;
        this.pipelineTarget = result.entity_id;
        this.docEntity = result.entity_id;
        this.reportEntity = result.entity_id;
        await this.loadCompanies();
        await this.loadDocumentWorkspace();
        this.journeyStage = 'retrieved';
        this.notify(result.message || 'Verified data retrieved', 'ok');
      } catch {
        this.journeyStage = 'entity';
      } finally {
        this.loading = false;
      }
    },

    proceedToCamBuild() {
      this.journeyStage = 'prebuilt';
    },

    async runJourneyPipeline({ entityId, workingStage, doneStage, doneMessage, errorStage, startProgress }) {
      if (!entityId || this.pipelineRunning) return false;
      this.journeyStage = workingStage;
      this.pipelineTarget = entityId;
      this.pipelineRunning = true;
      this.pipelineError = false;
      this.agentEvents = [];
      this.agentPct = 0;
      this.agentProgress = startProgress;
      this.pipelineDoneResult = null;
      this.camBuildSections = [];

      return await new Promise((resolve, reject) => {
        const es = new EventSource('/api/cases/' + entityId + '/run-stream');
        let settled = false;

        const fail = (message) => {
          if (settled) return;
          settled = true;
          this.pipelineRunning = false;
          this.pipelineError = true;
          this.agentProgress = message || 'Pipeline error';
          es.close();
          this.journeyStage = errorStage;
          this.notify('Pipeline error: ' + (message || 'unknown'), 'error');
          this.pushNotification('CAM run failed for ' + this.companyLabel(entityId) + ': ' + (message || 'unknown error'), 'error', entityId, 'runs');
          reject(new Error(message || 'Pipeline error'));
        };

        es.onmessage = async (e) => {
          try {
            const evt = JSON.parse(e.data);
            if (evt.type === 'agent_start' || evt.type === 'agent_complete' || evt.type === 'info' || evt.type === 'section_start' || evt.type === 'section_complete') {
              this.agentEvents = [...this.agentEvents, evt];
              if (evt.step && evt.total) {
                // Only agent completions move the bar; section events (a sub-step of the
                // narrative agent) just update the label, so the bar never jumps backwards.
                // `completed` counts finished agents, which can finish out of order in parallel.
                if (evt.type === 'agent_complete') this.agentPct = Math.round(((evt.completed ?? evt.step) / evt.total) * 100);
                this.agentProgress = evt.title || evt.section || this.humanizeText(evt.agent) || ('Step ' + evt.step + ' / ' + evt.total);
              }
              // Track section build progress for completion cards
              if (evt.type === 'section_start') {
                const idx = this.camBuildSections.findIndex(s => s.id === evt.section);
                if (idx >= 0) {
                  this.camBuildSections[idx].status = 'writing';
                } else {
                  this.camBuildSections = [...this.camBuildSections, { id: evt.section, title: evt.title || evt.section, status: 'writing', step: evt.step, total: evt.total }];
                }
              } else if (evt.type === 'section_complete') {
                const idx = this.camBuildSections.findIndex(s => s.id === evt.section);
                if (idx >= 0) {
                  this.camBuildSections[idx].status = 'done';
                  this.camBuildSections = [...this.camBuildSections];
                } else {
                  this.camBuildSections = [...this.camBuildSections, { id: evt.section, title: evt.title || evt.section, status: 'done', step: evt.step, total: evt.total }];
                }
              }
              return;
            }
            if (evt.type === 'done') {
              if (settled) return;
              settled = true;
              this.pipelineRunning = false;
              this.agentPct = 100;
              this.agentProgress = doneMessage;
              this.pipelineDoneResult = {
                entity_id: entityId,
                recommendation: evt.recommendation,
                risk_grade: evt.risk_grade,
                composite_score: evt.composite_score,
                narrative_mode: evt.narrative_mode,
              };
              es.close();
              try {
                await this.loadCases();
                await this.loadSummary();
                this.reportEntity = entityId;
                await this.loadCAMReport();
              } catch {}
              this.journeyStage = doneStage;
              this.notify(doneMessage, 'ok');
              this.pushNotification('CAM ready for ' + this.companyLabel(entityId) + ' — ' + this.fmtRec(evt.recommendation) + ', grade ' + (evt.risk_grade || '--'), 'ok', entityId, 'cam');
              resolve(evt);
              return;
            }
            if (evt.type === 'error') {
              fail(evt.message || 'unknown');
            }
          } catch (error) {
            fail(error?.message || 'Invalid pipeline response');
          }
        };

        es.onerror = () => {
          if (settled) return;
          fail('Pipeline connection lost');
        };
      });
    },

    async generateJourneyCam() {
      const entityId = this.journeyEntityId();
      if (!entityId || this.pipelineRunning) return;
      try {
        await this.runJourneyPipeline({
          entityId,
          workingStage: 'drafting',
          doneStage: 'ready',
          doneMessage: 'CAM generated with all uploaded inputs',
          errorStage: 'retrieved',
          startProgress: 'Starting CAM generation',
        });
      } catch {}
    },

    async uploadJourneyFile(category, event, documentRole) {
      const entityId = this.journeyEntityId();
      const files = event?.target?.files;
      if (!entityId || !files || !files.length) return;
      this.loading = true;
      try {
        for (const file of files) {
          const form = new FormData();
          form.append('category', category);
          form.append('file', file);
          if (documentRole) form.append('document_role', documentRole);
          const res = await fetch('/api/companies/' + entityId + '/upload', {
            method: 'POST',
            body: form,
          });
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Upload failed for ' + file.name);
          }
        }
        const names = Array.from(files).map(f => f.name).join(', ');
        this.notify(names + ' uploaded — running OCR extraction...', 'ok');
        try {
          await this.api('companies/' + entityId + '/extract', { method: 'POST' });
          this.notify(names + ' uploaded and extracted', 'ok');
        } catch (exErr) {
          const msg = exErr?.message || exErr?.detail || 'Extraction failed';
          this.notify('Extraction error: ' + msg, 'error');
        }
        this.docEntity = entityId;
        await this.loadDocumentWorkspace();
        await this.loadCases();
        this.pipelineDoneResult = null;
      } catch (e) {
        this.notify(e.message || 'Upload failed', 'error');
      } finally {
        event.target.value = '';
        this.loading = false;
      }
    },

    async deleteJourneyFile(category, filename) {
      const entityId = this.journeyEntityId();
      if (!entityId || !filename) return;
      this.loading = true;
      try {
        const res = await fetch('/api/companies/' + entityId + '/documents/' + encodeURIComponent(category) + '/' + encodeURIComponent(filename), {
          method: 'DELETE',
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Delete failed');
        }
        this.notify(filename + ' removed', 'ok');
        this.docEntity = entityId;
        await this.loadDocumentWorkspace();
        await this.loadCases();
        this.pipelineDoneResult = null;
      } catch (e) {
        this.notify(e.message || 'Delete failed', 'error');
      } finally {
        this.loading = false;
      }
    },

    async openJourneyWorkspace() {
      const entityId = this.journeyEntityId();
      if (!entityId) return;
      await this.openWorkspace(entityId, 'cam');
    },

    async previewResolve() {
      if (!this.onboardId.trim()) return;
      this.resolvePreview = null;
      try {
        const r = await this.api('resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier: this.onboardId.trim() }),
        });
        this.resolvePreview = r;
      } catch {}
    },

    async etbLookup() {
      if (!this.onboardId.trim()) return;
      this.etbLookupResult = null;
      this.etbLookupError = '';
      this.loading = true;
      try {
        // First resolve the identifier to get PAN
        const resolved = await this.api('resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier: this.onboardId.trim() }),
        });
        if (!resolved || !resolved.pan) {
          this.etbLookupError = 'Could not resolve identifier — no PAN found.';
          return;
        }
        this.resolvePreview = resolved;
        // Fetch CRILC data using PAN to check existing banking relationship.
        // An empty payload / source_status "not_found" means no CRILC data, not "zero exposure".
        const crilc = await this.api('external/crilc/' + encodeURIComponent(resolved.pan));
        const exposure = Number(crilc?.payload?.aggregate_exposure_cr);
        if (crilc?.source_status === 'not_found' || !Number.isFinite(exposure)) {
          const internal = this.companies.find(c => c.entity_id === resolved.entity_id);
          this.etbLookupError = 'CRILC exposure data is not available for PAN ' + resolved.pan
            + ', so the existing relationship could not be verified.'
            + (internal?.case_type === 'ETB' ? ' Internal records list this borrower as ETB.' : '');
          return;
        }
        if (exposure <= 0) {
          this.etbLookupError = 'Not an ETB customer — CRILC shows no existing exposure for this entity.';
          return;
        }
        this.etbLookupResult = {
          entity_name: crilc.payload.entity_name || resolved.company_name,
          pan: resolved.pan,
          cin: resolved.cin,
          aggregate_exposure_cr: crilc.payload.aggregate_exposure_cr,
          fund_based_cr: crilc.payload.fund_based_cr,
          non_fund_based_cr: crilc.payload.non_fund_based_cr,
          total_lenders: crilc.payload.total_lenders,
          classification: crilc.payload.classification,
          sma_status: crilc.payload.sma_status,
        };
        this.notify('ETB data fetched — existing exposure: ' + crilc.payload.aggregate_exposure_cr + ' Cr', 'ok');
      } catch {
        this.etbLookupError = 'Not an ETB customer — no internal conduct data found.';
      } finally { this.loading = false; }
    },

    async submitCompany() {
      const co = this.newCo;
      if (!co.entity_id || !co.company_name || !co.sector || !co.amount_requested_cr) {
        this.notify('Please fill all required fields (Entity ID, Name, Sector, Amount)', 'error');
        return;
      }
      // Clean line_items: remove null/zero
      const lineItems = {};
      for (const [k, v] of Object.entries(co.line_items)) {
        if (v != null && v !== 0) lineItems[k] = v;
      }
      const payload = {
        entity_id: co.entity_id,
        company_name: co.company_name,
        cin: co.cin || undefined,
        pan: co.pan || undefined,
        sector: co.sector,
        borrower_type: co.borrower_type,
        date_of_incorporation: co.date_of_incorporation || undefined,
        credit_rating: co.credit_rating || undefined,
        rating_agency: co.rating_agency || undefined,
        employee_count: co.employee_count || undefined,
        case_type: co.case_type,
        facility_type: co.facility_type,
        amount_requested_cr: co.amount_requested_cr,
        purpose: co.purpose || undefined,
        tenor_months: co.tenor_months || undefined,
        existing_limit_cr: co.existing_limit_cr || undefined,
        line_items: lineItems,
      };
      // Add collateral if provided
      if (co.collateral_type && co.collateral_market_value) {
        payload.collateral = [{
          collateral_type: co.collateral_type,
          description: co.collateral_desc,
          market_value_cr: co.collateral_market_value,
          forced_sale_value_cr: co.collateral_fsv || co.collateral_market_value * 0.7,
        }];
      }

      this.loading = true;
      try {
        const r = await this.api('companies', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        this.notify(r.message || 'Company added', 'ok');
        this.resetCompanyForm();
        await this.loadCompanies();
        this.navigate('pipeline');
      } catch {} finally { this.loading = false; }
    },

    resetCompanyForm() {
      this.newCo = {
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
      };
    },
  };
}
