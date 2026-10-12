"""
Company (borrower) lifecycle: listing, manual entry, identifier-based
onboarding, enrichment from public records, and deletion.
"""

from datetime import date

from src.application.document_workspace import PROBE_PROVIDER, DocumentWorkspaceService
from src.application.errors import ConflictError, InvalidRequestError, NotFoundError
from src.application.state import AppState
from src.models.canonical_model import (
    Borrower, BorrowerType, CaseType, Collateral, DirectorPromoter, FacilityRequest,
    FacilityType, FinancialStatement, GroupEntity, Sector,
)

# Keys onboarding cannot rebuild well; curated seed values win over enriched stubs.
_SEED_PREFERRED_KEYS = ("group", "infra_metrics", "sector_kpis", "collateral",
                        "market_signals", "directors", "borrower", "facility", "provisional")
_SEED_ALWAYS_KEYS = ("group", "infra_metrics", "sector_kpis")
_LINE_ITEM_ALIASES = {
    "revenue": "revenue_operating",
    "net_worth": "total_equity",
    "interest_expense": "finance_cost",
    "cash_and_equivalents": "cash_equivalents",
}


def keep_curated_sector(prior_borrower, enriched_borrower, enriched_basis: str | None):
    """The enriched borrower, with the prior (curated) sector kept when the enriched sector is only a
    default placeholder (no industry text / unmapped NIC code) — a guess must not overwrite master data."""
    if (prior_borrower is None or enriched_borrower is None or enriched_basis != "default"
            or getattr(prior_borrower, "sector", None) is None):
        return enriched_borrower
    import dataclasses
    return dataclasses.replace(enriched_borrower, sector=prior_borrower.sector, subsector=prior_borrower.subsector)


def restore_curated_sector(seed_company: dict | None, stored_company: dict) -> bool:
    """Repair a stored record whose sector is the inference default while the curated catalogue has one.

    Records saved before sector_basis existed carry the default's signature: subsector equal to the
    sector code (no industry text was available). Returns True when the record was changed.
    """
    seed_b, b = (seed_company or {}).get("borrower"), stored_company.get("borrower")
    if seed_b is None or b is None or stored_company.get("sector_basis") not in (None, "default"):
        return False
    defaulted = stored_company.get("sector_basis") == "default" or b.subsector == getattr(b.sector, "value", None)
    if not defaulted or b.sector == seed_b.sector:
        return False
    stored_company["borrower"] = keep_curated_sector(seed_b, b, "default")
    stored_company["sector_basis"] = "reference_catalog"
    return True


def merge_overlay_company_data(base_company: dict, enriched_company: dict) -> dict:
    """Merge freshly enriched company data over an existing (often seeded) record.

    Enriched data wins by default; curated seed structures and materially
    richer seed financials are preserved.
    """
    merged = dict(enriched_company or {})
    prior = base_company or {}

    for key in ("catalog_source", "preferred_identifier", "reference_prefix",
                "missing_documents", "source_summary", "probe_summary"):
        if key in prior and key not in merged:
            merged[key] = prior[key]

    for key in ("core_banking", "conduct", "covenants"):
        if prior.get(key):
            merged[key] = prior[key]

    for key in _SEED_PREFERRED_KEYS:
        prior_val = prior.get(key)
        if not prior_val:
            continue
        enriched_val = merged.get(key)
        if key in _SEED_ALWAYS_KEYS:
            merged[key] = prior_val
        elif not enriched_val:
            merged[key] = prior_val
        elif isinstance(prior_val, list) and isinstance(enriched_val, list) and len(prior_val) > len(enriched_val):
            merged[key] = prior_val

    # A defaulted sector from the public-record lookup never replaces the curated sector.
    if merged.get("sector_basis") == "default" and prior.get("borrower") is not None:
        merged["borrower"] = keep_curated_sector(prior["borrower"], merged.get("borrower"), "default")
        merged["sector_basis"] = prior.get("sector_basis") or "reference_catalog"

    # Seed financials win when they have materially higher revenue or more periods
    # (prevents probe-estimated / GSTN turnover from overwriting real seed data).
    prior_fin = prior.get("financials") or {}
    enriched_fin = merged.get("financials") or {}
    if prior_fin and enriched_fin:
        prior_max = _max_revenue(prior_fin)
        enriched_max = _max_revenue(enriched_fin)
        if prior_max > 0 and (enriched_max == 0 or prior_max > enriched_max * 1.5):
            merged["financials"] = prior_fin
        elif len(prior_fin) > len(enriched_fin):
            merged["financials"] = prior_fin
    elif prior_fin and not enriched_fin:
        merged["financials"] = prior_fin

    overlay_exposure = prior.get("existing_exposure") or []
    enriched_exposure = merged.get("existing_exposure") or []
    if overlay_exposure:
        existing_ids = {getattr(item, "facility_id", None) for item in enriched_exposure}
        merged["existing_exposure"] = list(enriched_exposure) + [
            item for item in overlay_exposure
            if getattr(item, "facility_id", None) not in existing_ids
        ]

    return merged


def _enum_value(value) -> str:
    return getattr(value, "value", value) or ""


def _max_revenue(financials: dict) -> float:
    best = 0.0
    for fs in financials.values():
        if hasattr(fs, "line_items"):
            val = (fs.line_items or {}).get("revenue_operating", 0) or 0
        elif hasattr(fs, "get"):
            val = fs.get("revenue_operating", 0) or 0
        else:
            continue
        best = max(best, val)
    return best


class CompanyService:
    def __init__(self, state: AppState, persistence, doc_store, workspace: DocumentWorkspaceService,
                 onboard_fn, clear_probe_cache_fn):
        self.state = state
        self.persistence = persistence
        self.doc_store = doc_store
        self.workspace = workspace
        self._onboard = onboard_fn
        self._clear_probe_cache = clear_probe_cache_fn

    # ── Queries ──────────────────────────────────────────────────────────

    def get(self, entity_id: str) -> dict | None:
        return self.state.companies.get(entity_id)

    def require(self, entity_id: str, message: str | None = None) -> dict:
        company = self.state.companies.get(entity_id)
        if not company:
            raise NotFoundError(message or f"Company {entity_id} not found")
        return company

    def exists(self, entity_id: str) -> bool:
        return entity_id in self.state.companies

    def summaries(self, executed_only: bool = False) -> list[dict]:
        items = self.state.companies.items()
        if executed_only:
            items = [(eid, d) for eid, d in items if eid in self.state.cases]
        return [
            {
                "entity_id": eid,
                "company_name": d["borrower"].company_name,
                "sector": d["borrower"].sector.value,
                "borrower_type": d["borrower"].borrower_type.value,
                "case_type": d["facility"].case_type.value,
                "facility_type": _enum_value(d["facility"].facility_type),
                "requested_amount_cr": d["facility"].amount_requested_cr,
                "purpose": d["facility"].purpose,
                "preferred_identifier": d.get("preferred_identifier") or d["borrower"].company_name,
                **self._identifiers(eid, d),
                "data_provider": d.get("data_provider", "internal"),
                "has_result": eid in self.state.cases,
            }
            for eid, d in items
        ]

    @staticmethod
    def _identifiers(entity_id: str, company: dict) -> dict:
        """CIN / PAN / GSTIN for pickers: the borrower record first, then the reference table."""
        from src.services.external_systems import reference_identifiers

        borrower = company["borrower"]
        reference = reference_identifiers(entity_id)
        return {
            "cin": getattr(borrower, "cin", "") or reference.get("cin") or "",
            "pan": getattr(borrower, "pan", "") or reference.get("pan") or "",
            "gstin": company.get("gstin") or reference.get("gstin") or "",
        }

    # ── Commands ─────────────────────────────────────────────────────────

    def save(self, entity_id: str, company: dict, catalog_source: str, is_seeded: bool = False) -> None:
        self.state.companies[entity_id] = company
        self.persistence.upsert_company(entity_id, company, is_seeded=is_seeded, catalog_source=catalog_source)

    def create_from_payload(self, body: dict) -> dict:
        """Manual entry: build canonical objects from a JSON payload."""
        required = ["entity_id", "company_name", "sector", "case_type", "facility_type", "amount_requested_cr"]
        missing = [f for f in required if not body.get(f)]
        if missing:
            raise InvalidRequestError(f"Missing required fields: {', '.join(missing)}")

        eid = str(body["entity_id"]).strip()
        if eid in self.state.companies:
            raise ConflictError(f"Company {eid} already exists")

        try:
            sector = Sector(body["sector"])
        except ValueError:
            raise InvalidRequestError(f"Invalid sector. Must be one of: {[s.value for s in Sector]}")
        try:
            case_type = CaseType(body["case_type"])
        except ValueError:
            raise InvalidRequestError("Invalid case_type. Must be NTB or ETB")
        try:
            facility_type = FacilityType(body["facility_type"])
        except ValueError:
            raise InvalidRequestError(
                f"Invalid facility_type. Must be one of: {[f.value for f in FacilityType]}")

        borrower = Borrower(
            entity_id=eid,
            company_name=body["company_name"],
            cin=body.get("cin", f"U{eid}"),
            pan=body.get("pan", f"AADCP{eid[:4]}K"),
            borrower_type=BorrowerType(body.get("borrower_type", "unlisted")),
            sector=sector,
            subsector=body.get("subsector", sector.value),
            date_of_incorporation=(date.fromisoformat(body["date_of_incorporation"])
                                   if body.get("date_of_incorporation") else date(2010, 1, 1)),
            registered_state=body.get("registered_state", "Maharashtra"),
            registered_address=body.get("registered_address", "Mumbai"),
            authorized_capital=body.get("authorized_capital", 100.0),
            paid_up_capital=body.get("paid_up_capital", 50.0),
            credit_rating=body.get("credit_rating"),
            rating_agency=body.get("rating_agency"),
            employee_count=body.get("employee_count"),
            website=body.get("website"),
        )

        facility = FacilityRequest(
            facility_id=body.get("facility_id", f"FAC-{eid}"),
            entity_id=eid,
            case_type=case_type,
            facility_type=facility_type,
            amount_requested_cr=float(body["amount_requested_cr"]),
            purpose=body.get("purpose", "General corporate purpose"),
            tenor_months=body.get("tenor_months"),
            existing_limit_cr=body.get("existing_limit_cr"),
            proposed_limit_cr=body.get("proposed_limit_cr"),
        )

        group = None
        if body.get("group_name"):
            group = GroupEntity(
                group_id=body.get("group_id", f"GRP-{eid}"),
                group_name=body["group_name"],
                parent_entity_id=eid,
                entities=body.get("group_entities", []),
                promoter_holding_pct=body.get("promoter_holding_pct", 0),
            )

        directors = [
            DirectorPromoter(
                din=d.get("din", "00000000"),
                name=d["name"],
                designation=d.get("designation", "Director"),
                entity_id=eid,
                is_promoter=d.get("is_promoter", False),
                net_worth_cr=d.get("net_worth_cr"),
            )
            for d in body.get("directors", [])
        ]

        collateral = [
            Collateral(
                collateral_id=col.get("collateral_id", f"COL-{eid}"),
                entity_id=eid,
                collateral_type=col.get("collateral_type", "property"),
                description=col.get("description", ""),
                market_value_cr=col.get("market_value_cr", 0),
                forced_sale_value_cr=col.get("forced_sale_value_cr", 0),
                valuation_date=(date.fromisoformat(col["valuation_date"])
                                if col.get("valuation_date") else date.today()),
            )
            for col in body.get("collateral", [])
        ]

        company = {
            "borrower": borrower,
            "group": group,
            "directors": directors,
            "financials": self._financials_from_payload(eid, body),
            "provisional": None,
            "facility": facility,
            "collateral": collateral,
            "market_signals": [],
            "existing_exposure": [],
            "conduct": [],
            "covenants": [],
            "exchange_filing": None,
        }
        self.save(eid, company, catalog_source="manual_entry")
        return {
            "status": "created",
            "entity_id": eid,
            "company_name": borrower.company_name,
            "sector": sector.value,
            "message": f"Company {borrower.company_name} added. Run the pipeline to analyse.",
        }

    @staticmethod
    def _financials_from_payload(eid: str, body: dict) -> dict:
        financials = {}
        for fin in body.get("financials", []):
            period = fin.get("period", "FY2024")
            financials[period] = FinancialStatement(
                entity_id=eid, period=period,
                statement_type=fin.get("statement_type", "standalone"),
                source=fin.get("source", "borrower"),
                as_of_date=date.fromisoformat(fin["as_of_date"]) if fin.get("as_of_date") else date(2024, 3, 31),
                line_items=fin.get("line_items", {}),
            )
        if financials:
            return financials

        # No statements given: one FY2024 statement from flat line items,
        # mapping friendly names to canonical ones and deriving totals.
        mapped = {_LINE_ITEM_ALIASES.get(k, k): v for k, v in body.get("line_items", {}).items()}
        if "ebit" not in mapped and "ebitda" in mapped:
            mapped["ebit"] = mapped["ebitda"] - mapped.get("depreciation", 0)
        if "pbt" not in mapped and "ebit" in mapped:
            mapped["pbt"] = mapped["ebit"] - mapped.get("finance_cost", 0)
        if "total_income" not in mapped and "revenue_operating" in mapped:
            mapped["total_income"] = mapped["revenue_operating"] + mapped.get("other_income", 0)
        return {"FY2024": FinancialStatement(
            entity_id=eid, period="FY2024", statement_type="standalone", source="borrower",
            as_of_date=date(2024, 3, 31), line_items=mapped,
        )}

    def delete(self, entity_id: str) -> dict:
        company = self.require(entity_id)
        name = company["borrower"].company_name
        self._clear_probe_cache(*self.workspace.probe_identifiers(entity_id, company))
        self.workspace.clear_probe_documents(entity_id)
        self.doc_store.delete_company(entity_id)
        del self.state.companies[entity_id]
        self.state.cases.pop(entity_id, None)
        self.persistence.delete_company(entity_id)
        return {"status": "deleted", "entity_id": entity_id, "company_name": name}

    def clear_verified_public_data(self, entity_id: str) -> dict:
        company = self.require(entity_id, "Company not found")
        deleted_cache = self._clear_probe_cache(*self.workspace.probe_identifiers(entity_id, company))
        deleted_documents = self.workspace.clear_probe_documents(entity_id)

        company.pop("probe_bundle", None)
        company.pop("probe_summary", None)
        company.pop("source_summary", None)
        if company.get("data_provider") == PROBE_PROVIDER:
            company["data_provider"] = "internal"
        self.persistence.upsert_company(
            entity_id, company,
            is_seeded=bool(company.get("seeded")),
            catalog_source=company.get("catalog_source", "manual_entry"),
        )
        return {
            "status": "deleted",
            "entity_id": entity_id,
            "deleted_cache_files": deleted_cache.get("deleted_files", []),
            "deleted_cache_count": deleted_cache.get("deleted_count", 0),
            "deleted_snapshot_documents": deleted_documents,
            "message": "Retained verified public data deleted for this borrower.",
        }

    # ── Onboarding & enrichment ──────────────────────────────────────────

    def onboard(self, body: dict) -> dict:
        """Identifier-based onboarding (PAN / GSTIN / CIN / entity ID / name)."""
        identifier = body.get("identifier", "").strip()
        if not identifier:
            raise InvalidRequestError("Provide 'identifier' — PAN, GSTIN, CIN, Entity ID, or Company Name")
        # Mandatory: a silent default amount would drive the authority routing and the CAM.
        try:
            amount = float(body.get("amount_requested_cr"))
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            raise InvalidRequestError("Provide 'amount_requested_cr' — the requested amount in crore, above 0")

        result = self._onboard(
            identifier=identifier,
            case_type=body.get("case_type", "NTB"),
            facility_type=body.get("facility_type", "working_capital"),
            amount_requested_cr=amount,
            purpose=body.get("purpose", "General corporate purpose"),
            tenor_months=body.get("tenor_months"),
        )
        if result["status"] == "not_found":
            raise NotFoundError(result["message"])

        eid = result["entity_id"]
        existing = self.state.companies.get(eid)
        company = (merge_overlay_company_data(existing, result["company_data"])
                   if existing else result["company_data"])
        company["missing_documents"] = result.get("missing_documents", [])
        company["source_summary"] = result.get("source_summary", {})
        company["probe_summary"] = result.get("probe_summary")
        if result.get("provider"):
            company["data_provider"] = result["provider"]

        crilc_available = body.get("crilc_available", False)
        company["crilc_available"] = crilc_available
        if body.get("etb_data"):
            company["etb_lookup"] = body["etb_data"]
        self.save(eid, company, catalog_source="onboarding")

        return {
            "status": "onboarded",
            "entity_id": eid,
            "company_name": result["company_name"],
            "provider": result.get("provider", company.get("data_provider", "internal")),
            "profile": result.get("profile"),
            "cache": result.get("cache", {}),
            "resolved_from": result["resolved"],
            "source_summary": result["source_summary"],
            "probe_summary": result.get("probe_summary"),
            "missing_documents": result.get("missing_documents", []),
            "documents_stored": result["documents_stored"],
            "crilc_available": crilc_available,
            "message": f"{result['company_name']} auto-onboarded. Run pipeline to analyse.",
        }

    @staticmethod
    def needs_enrichment(company: dict) -> bool:
        if not company:
            return False
        if company.get("data_provider") == "verified_public_records":
            return False
        if company.get("probe_bundle") and company.get("external_data"):
            return False
        borrower = company.get("borrower")
        if borrower and getattr(borrower, "cin", "") and getattr(borrower, "pan", "") and company.get("external_data"):
            return False
        return True

    def ensure_enriched(self, entity_id: str) -> dict:
        """Pull public-record data for a company that has none yet, before a run."""
        company = self.state.companies.get(entity_id)
        if not company or not self.needs_enrichment(company):
            return company

        borrower = company.get("borrower")
        facility = company.get("facility")
        identifier = (
            company.get("preferred_identifier")
            or getattr(borrower, "cin", None)
            or getattr(borrower, "pan", None)
            or getattr(borrower, "company_name", None)
            or entity_id
        )
        case_type = getattr(getattr(facility, "case_type", None), "value", getattr(facility, "case_type", "NTB"))
        facility_type = getattr(getattr(facility, "facility_type", None), "value",
                                getattr(facility, "facility_type", "working_capital"))

        result = self._onboard(
            identifier=identifier,
            case_type=str(case_type),
            facility_type=str(facility_type),
            amount_requested_cr=float(getattr(facility, "amount_requested_cr", 100.0) or 100.0),
            purpose=getattr(facility, "purpose", "General corporate purpose"),
            tenor_months=getattr(facility, "tenor_months", None),
        )
        if not result or result.get("status") == "not_found":
            return company

        enriched = merge_overlay_company_data(company, result["company_data"])
        enriched["missing_documents"] = result.get("missing_documents", enriched.get("missing_documents", []))
        enriched["source_summary"] = result.get("source_summary", enriched.get("source_summary", {}))
        enriched["probe_summary"] = result.get("probe_summary", enriched.get("probe_summary"))
        if result.get("provider"):
            enriched["data_provider"] = result["provider"]
        self.save(entity_id, enriched, catalog_source="run_autoload")
        return enriched
