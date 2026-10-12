/* CAM Intelligence Platform — Documents workspace: listing, upload, extraction, document packs, verified data.
   Merged into the Alpine component by camApp() in app.js; `this` is that component. */

function camDocuments() {
  return {
    /* ─── Document packs & verified public data ────────────────────── */
    async loadSupportedDownloads() {
      try {
        const r = await this.api('companies/supported-downloads');
        this.supportedDownloadIds = (r || []).map(c => c.entity_id);
      } catch { this.supportedDownloadIds = []; }
    },

    supportsDocumentPack(entityId) {
      return !!entityId && this.supportedDownloadIds.includes(entityId);
    },

    async clearVerifiedPublicData() {
      if (!this.docEntity) return;
      if (!confirm('Remove the retained verified public-record snapshot for ' + this.docEntity
                   + '? It will be fetched again on the next onboarding or pipeline run.')) return;
      this.loading = true;
      try {
        const r = await this.api('companies/' + this.docEntity + '/verified-public-data', { method: 'DELETE' });
        this.notify(r.message || 'Verified public data removed', 'ok');
        await this.loadDocuments();
      } catch {} finally { this.loading = false; }
    },

    documentUploadCoverageClass(value) {
      const num = Number(value || 0);
      if (num >= 75) return 'score-good';
      if (num >= 40) return 'score-mid';
      return 'score-bad';
    },

    documentCategoryStatus(info) {
      const required = Number(info?.upload_required_count || 0);
      const coverage = Number(info?.upload_coverage_pct || 0);
      const visibleDocs = (info?.items || []).filter(item => item.file_type === 'document').length;
      const extraFiles = (info?.legacy_items || []).length + (info?.system_items || []).length;
      if (required > 0) return coverage + '%';
      if (visibleDocs > 0) return 'Available';
      if (extraFiles > 0) return 'Available';
      return 'Optional';
    },

    documentCategoryStatusClass(info) {
      const required = Number(info?.upload_required_count || 0);
      const coverage = Number(info?.upload_coverage_pct || 0);
      const visibleDocs = (info?.items || []).filter(item => item.file_type === 'document').length;
      const extraFiles = (info?.legacy_items || []).length + (info?.system_items || []).length;
      if (required > 0) {
        if (coverage >= 75) return 'badge-green';
        if (coverage >= 40) return 'badge-amber';
        return 'badge-red';
      }
      if (visibleDocs > 0) return 'badge-green';
      if (extraFiles > 0) return 'badge-info';
      return 'badge-grey';
    },

    documentCategorySuggestionLabel(info) {
      return Number(info?.upload_required_count || 0) > 0 ? 'Required uploads' : 'If available';
    },

    documentCategorySuggestedItems(info) {
      if (Number(info?.upload_required_count || 0) > 0 && Array.isArray(info?.upload_missing_descriptions) && info.upload_missing_descriptions.length) {
        return info.upload_missing_descriptions;
      }
      return info?.missing || [];
    },

    documentCategoryEmptyMessage(info) {
      const extraFiles = (info?.legacy_items || []).length + (info?.system_items || []).length;
      if (extraFiles > 0) return 'No uploaded borrower files in this category yet.';
      return 'No files in this category yet.';
    },

    documentCategoryArchiveNote(info) {
      const extraFiles = (info?.legacy_items || []).length + (info?.system_items || []).length;
      if (!extraFiles) return '';
      return extraFiles + ' additional source/system files are available below. They do not count toward RM upload coverage.';
    },

    documentCategoryEntries(categories) {
      return Object.entries(categories || {}).filter(([, info]) => {
        const visibleDocuments = (info.items || []).filter(item => item.file_type === 'document');
        return visibleDocuments.length > 0 || (info.missing || []).length > 0;
      });
    },

    /* ─── Documents Page ───────────────────────────────────────────── */
    async loadDocuments() {
      if (!this.docEntity) return;
      this.docLoading = true;
      this.docExtraction = null;
      this.docGaps = null;
      this.docProbe = null;
      const [docs, gaps, extraction, probe] = await Promise.allSettled([
        this.api('companies/' + this.docEntity + '/documents'),
        this.api('companies/' + this.docEntity + '/data-gaps'),
        this.api('companies/' + this.docEntity + '/extraction'),
        this.api('companies/' + this.docEntity + '/probe'),
      ]);

      this.docData = docs.status === 'fulfilled' ? docs.value : null;
      this.docGaps = gaps.status === 'fulfilled' ? gaps.value : null;
      this.docExtraction = extraction.status === 'fulfilled' ? extraction.value : null;
      this.docProbe = probe.status === 'fulfilled' ? probe.value : null;
      await this.loadDocumentOperations(this.docEntity);
      this.docLoading = false;
    },

    async loadDocumentOperations(entityId) {
      try {
        const path = entityId ? ('companies/' + entityId + '/document-operations') : 'document-operations';
        const result = await this.api(path);
        this.docOpsHistory = (result.operations || []).filter(op => !String(op.operation_type || '').includes('generation'));
      } catch {
        this.docOpsHistory = [];
      }
    },

    async loadDocumentWorkspace() {
      if (!this.docEntity && this.companies.length) this.docEntity = this.companies[0].entity_id;
      await this.loadDocuments();
      if (!this.docOpsHistory.length) await this.loadDocumentOperations();
    },

    async generateDocumentsForWorkspace() {
      if (!this.docEntity) return;
      this.loading = true;
      try {
        const result = await this.api('companies/' + this.docEntity + '/fetch-documents', { method: 'POST' });
        await this.loadDocuments();
        this.notify('Generated ' + (result.files_generated?.length || 0) + ' document artifacts for ' + this.docEntity, 'ok');
      } catch {} finally { this.loading = false; }
    },

    async runExtraction() {
      if (!this.docEntity) return;
      this.docExtracting = true;
      try {
        await this.api('companies/' + this.docEntity + '/extract', { method: 'POST' });
        this.docExtraction = await this.api('companies/' + this.docEntity + '/extraction');
        this.notify('Extraction complete: ' + (this.docExtraction?.document_count || 0) + ' documents processed', 'ok');
      } catch {} finally { this.docExtracting = false; }
    },

    async previewDoc(eid, cat, filename) {
      window.open('/api/companies/' + encodeURIComponent(eid) + '/documents/'
                  + encodeURIComponent(cat) + '/' + encodeURIComponent(filename), '_blank');
    },

    async uploadWorkspaceFile(event) {
      const file = event?.target?.files?.[0];
      if (!this.docEntity || !file) return;
      this.docUploading = true;
      try {
        const form = new FormData();
        form.append('category', this.docUploadCategory || 'misc');
        form.append('file', file);
        const res = await fetch('/api/companies/' + this.docEntity + '/upload', {
          method: 'POST',
          body: form,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Upload failed');
        }
        this.notify(file.name + ' uploaded — running OCR extraction...', 'ok');
        try {
          await this.api('companies/' + this.docEntity + '/extract', { method: 'POST' });
          this.docExtraction = await this.api('companies/' + this.docEntity + '/extraction');
          this.notify(file.name + ' uploaded and extracted', 'ok');
        } catch (exErr) {
          const msg = exErr?.message || exErr?.detail || 'Extraction failed';
          this.notify('Extraction error: ' + msg, 'error');
        }
        await this.loadDocuments();
        await this.loadCases();
      } catch (e) {
        this.notify(e.message || 'Upload failed', 'error');
      } finally {
        event.target.value = '';
        this.docUploading = false;
      }
    },
  };
}
