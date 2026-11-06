"""
API connectors for the data-acquisition agents. Each returns a record in the platform's
standard envelope (the same shape the CAM engine reads from ``company["external_data"]``):

    {"source", "record_type", "entity_key", "as_of_date", "payload_version",
     "source_status": "success" | "not_found", "payload": {...},
     "provenance": {"via": "api", "provider", "url", "from_cache", "fetched_at"}}

A document reader (readers.py) produces the same envelope with ``via: "document"``, so
downstream code does not care how a record was obtained.

Live connectors use only free, public endpoints, through the PoliteClient:
  * GLEIF LEI records            https://api.gleif.org
  * OFAC SDN list (+ aliases)    https://sanctionslistservice.ofac.treas.gov
  * UN Security Council list     https://scsanctions.un.org
  * GDELT DOC 2.0 news search    https://api.gdeltproject.org
Probe42 (MCA21 data) is a commercial API: used only when PROBE42_API_KEY is set.
"""

from __future__ import annotations

import csv
import io
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Optional

from src.flow.acquire.polite import PoliteClient

GLEIF = "https://api.gleif.org/api/v1/lei-records"
OFAC_SDN = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
OFAC_ALT = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ALT.CSV"
UN_LIST = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"


def envelope(source: str, record_type: str, key: str, payload: dict, *, found: bool = True,
             provenance: Optional[dict] = None, as_of: Optional[str] = None) -> dict:
    return {"source": source, "record_type": record_type, "entity_key": key,
            "as_of_date": as_of or date.today().isoformat(), "payload_version": "v1",
            "source_status": "success" if found else "not_found", "payload": payload,
            "provenance": provenance or {}}


def _api(provider: str, resp) -> dict:
    return {"via": "api", "provider": provider, "url": resp.url, "from_cache": resp.from_cache,
            "fetched_at": datetime.fromtimestamp(resp.fetched_at).isoformat(timespec="seconds")}


# ── names ────────────────────────────────────────────────────────────────────

_LEGAL = {"LIMITED", "LTD", "PRIVATE", "PVT", "THE", "CO", "COMPANY", "INC", "LLP", "CORP", "CORPORATION",
          "MR", "MS", "MRS", "DR", "SHRI", "SMT"}


def name_tokens(name: str, *, drop_legal: bool = True) -> list[str]:
    toks = re.sub(r"[^A-Z0-9 ]", " ", str(name or "").upper().replace("&", " AND ")).split()
    return [t for t in toks if not (drop_legal and t in _LEGAL)]


def name_score(a: str, b: str) -> float:
    """0..1 similarity of two names, ignoring legal suffixes, case, punctuation and word order."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    jacc = len(sa & sb) / len(sa | sb)
    seq = SequenceMatcher(None, " ".join(sorted(sa)), " ".join(sorted(sb))).ratio()
    return round(max(jacc, seq) if jacc >= 0.5 else min(jacc, seq), 3)


# ── GLEIF ────────────────────────────────────────────────────────────────────

def gleif(client: PoliteClient, *, name: str, cin: Optional[str] = None, cache_hours: float = 168) -> dict:
    """The LEI record of the company: by its registration number (CIN) when known, else by name."""
    tried = []
    for params in ([{"filter[entity.registeredAs]": cin, "page[size]": 5}] if cin else []) + \
                  [{"filter[entity.legalName]": name, "page[size]": 5},
                   {"filter[fulltext]": name, "page[size]": 10}]:
        resp = client.get(GLEIF, params=params, cache_hours=cache_hours, accept="application/vnd.api+json")
        tried.append(resp)
        best = _gleif_best(resp.json().get("data") or [], name, cin)
        if best:
            return envelope("gleif", "lei_record", best["lei"], best, provenance=_api("GLEIF", resp))
    last = tried[-1]
    return envelope("gleif", "lei_record", cin or name, {"query": name}, found=False,
                    provenance=_api("GLEIF", last))


def _gleif_best(records: list, name: str, cin: Optional[str]) -> Optional[dict]:
    best, best_score = None, 0.0
    for rec in records:
        a = rec.get("attributes") or {}
        ent = a.get("entity") or {}
        legal = (ent.get("legalName") or {}).get("name") or ""
        reg_as = ent.get("registeredAs") or ""
        score = 1.0 if cin and reg_as.upper() == cin.upper() else name_score(legal, name)
        if ent.get("jurisdiction") not in (None, "", "IN"):
            score -= 0.2
        if score > best_score:
            addr = ent.get("legalAddress") or {}
            hq = ent.get("headquartersAddress") or {}
            reg = a.get("registration") or {}
            best_score, best = score, {
                "lei": a.get("lei") or rec.get("id"), "legal_name": legal, "registered_as": reg_as,
                "jurisdiction": ent.get("jurisdiction"), "legal_form": (ent.get("legalForm") or {}).get("id"),
                "entity_status": ent.get("status"), "registration_status": reg.get("status"),
                "initial_registration": (reg.get("initialRegistrationDate") or "")[:10],
                "next_renewal": (reg.get("nextRenewalDate") or "")[:10],
                "legal_address": ", ".join([*(addr.get("addressLines") or []), addr.get("city") or "",
                                            addr.get("region") or "", addr.get("postalCode") or ""]).strip(", "),
                "headquarters": ", ".join([*(hq.get("addressLines") or []), hq.get("city") or ""]).strip(", "),
                "match_score": round(score, 3)}
    return best if best_score >= 0.85 else None


# ── Sanctions (OFAC SDN + UN consolidated) ───────────────────────────────────

class SanctionsLists:
    """The two public lists, downloaded at most once per ``cache_hours`` and matched locally:
    a name being screened never leaves this machine."""

    def __init__(self, client: PoliteClient, cache_hours: float = 24):
        self.client, self.cache_hours = client, cache_hours
        self._lock = threading.Lock()
        self._entries: Optional[list[dict]] = None
        self._index: dict[str, list[int]] = {}
        self._meta: dict = {}
        self._loaded_at = 0.0

    def load(self) -> dict:
        with self._lock:
            if self._entries is not None and time.time() - self._loaded_at < self.cache_hours * 3600:
                return self._meta
            entries, meta = [], {"lists": []}
            sdn = self.client.get(OFAC_SDN, cache_hours=self.cache_hours, accept="text/csv")
            alt = self.client.get(OFAC_ALT, cache_hours=self.cache_hours, accept="text/csv")
            n = _ofac_entries(sdn.text(), alt.text(), entries)
            meta["lists"].append({"list": "OFAC SDN", "entries": n, "url": OFAC_SDN, "from_cache": sdn.from_cache,
                                  "fetched_at": datetime.fromtimestamp(sdn.fetched_at).isoformat(timespec="seconds")})
            un = self.client.get(UN_LIST, cache_hours=self.cache_hours, accept="application/xml")
            n = _un_entries(un.content, entries)
            meta["lists"].append({"list": "UN Security Council consolidated", "entries": n, "url": UN_LIST,
                                  "from_cache": un.from_cache,
                                  "fetched_at": datetime.fromtimestamp(un.fetched_at).isoformat(timespec="seconds")})
            index: dict[str, list[int]] = {}
            for i, e in enumerate(entries):
                for t in set(name_tokens(e["name"])):
                    index.setdefault(t, []).append(i)
            self._entries, self._index, self._meta, self._loaded_at = entries, index, meta, time.time()
            return meta

    def screen(self, names: list[dict], threshold: float = 0.9) -> dict:
        """names: [{"name", "role"}]. Returns the lists used and, per name, any matches."""
        meta = self.load()
        results = []
        for subject in names:
            toks = set(name_tokens(subject["name"]))
            cand = set()
            for t in toks:
                if len(t) > 2:
                    cand.update(self._index.get(t, [])[:5000])
            hits = []
            for i in cand:
                e = self._entries[i]
                s = name_score(subject["name"], e["name"])
                if s >= threshold and len(toks & set(name_tokens(e["name"]))) >= min(2, len(toks)):
                    hits.append({**e, "score": s})
            hits.sort(key=lambda h: -h["score"])
            results.append({**subject, "matches": hits[:5], "status": "match" if hits else "clear"})
        return {"lists": meta["lists"], "screened": results,
                "matches": sum(1 for r in results if r["matches"])}


def _ofac_entries(sdn_csv: str, alt_csv: str, out: list) -> int:
    names: dict[str, dict] = {}
    for row in csv.reader(io.StringIO(sdn_csv)):
        if len(row) < 4 or not row[0].strip().isdigit():
            continue
        e = {"list": "OFAC SDN", "ref": row[0].strip(), "name": _ofac_name(row[1]),
             "type": (row[2].strip().strip('"') or "entity").replace("-0-", "entity"), "program": row[3].strip()}
        names[e["ref"]] = e
        out.append(e)
    for row in csv.reader(io.StringIO(alt_csv)):
        if len(row) < 4 or row[1].strip() not in names:
            continue
        base = names[row[1].strip()]
        out.append({**base, "name": _ofac_name(row[3]), "alias": True})
    return len(names)


def _ofac_name(raw: str) -> str:
    n = raw.strip().strip('"')
    if n.count(",") == 1:                     # "LAST, First" (individuals)
        last, first = [p.strip() for p in n.split(",")]
        n = f"{first} {last}"
    return n


def _un_entries(xml_bytes: bytes, out: list) -> int:
    root = ET.fromstring(xml_bytes)
    count = 0
    for kind, alias_tag in (("INDIVIDUAL", "INDIVIDUAL_ALIAS"), ("ENTITY", "ENTITY_ALIAS")):
        for node in root.iter(kind):
            parts = [node.findtext(t) or "" for t in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")]
            name = " ".join(p.strip() for p in parts if p and p.strip())
            if not name:
                continue
            count += 1
            base = {"list": "UN consolidated", "ref": (node.findtext("REFERENCE_NUMBER") or "").strip(),
                    "name": name, "type": kind.lower(), "program": (node.findtext("UN_LIST_TYPE") or "").strip()}
            out.append(base)
            for al in node.iter(alias_tag):
                an = (al.findtext("ALIAS_NAME") or "").strip()
                if an:
                    out.append({**base, "name": an, "alias": True})
    return count


# ── Adverse media (GDELT) ────────────────────────────────────────────────────

ADVERSE_TERMS = ("fraud", "raid", "probe", "default", "insolven", "bankrupt", "penalt", "fine ", "fined", "sebi order",
                 "enforcement directorate", " ed ", "cbi", "arrest", "lawsuit", "sued", "scam", "money laundering",
                 "tax evasion", "income tax search", "fire", "accident", "recall", "downgrad", "strike",
                 "layoff", "plant shut", "sanction", "blacklist", "whistleblower", "forensic", "restat")


def gdelt(client: PoliteClient, *, name: str, months: int = 6, cache_hours: float = 24) -> dict:
    """News that names the company in the last ``months`` (titles and links only)."""
    q = " ".join(name_tokens(name)[:4])
    params = {"query": f'"{q}"', "mode": "ArtList", "format": "json", "maxrecords": 75,
              "timespan": f"{months * 30}d", "sort": "DateDesc"}
    resp = client.get(GDELT, params=params, cache_hours=cache_hours)
    try:
        data = resp.json() if resp.content.strip() else {}
    except ValueError:                        # GDELT answers plain text for a malformed query
        data = {}
    arts, seen_titles = [], set()
    for a in data.get("articles") or []:
        title = (a.get("title") or "").strip()
        key = " ".join(name_tokens(title, drop_legal=False))[:90]
        if not title or key in seen_titles:                   # syndicated copies of one story
            continue
        seen_titles.add(key)
        seen = a.get("seendate") or ""
        arts.append({"title": title, "url": a.get("url"), "source": a.get("domain"),
                     "date": f"{seen[:4]}-{seen[4:6]}-{seen[6:8]}" if len(seen) >= 8 else "",
                     "language": a.get("language"), "country": a.get("sourcecountry")})
    return envelope("gdelt", "news_search", name, {"query": params["query"], "window_months": months,
                                                   "articles": arts}, provenance=_api("GDELT", resp))


_GENERIC = {"INDIA", "TECHNOLOGIES", "TECHNOLOGY", "INDUSTRIES", "ENTERPRISES", "HOLDINGS", "GROUP", "INTERNATIONAL",
            "SERVICES", "SOLUTIONS", "SYSTEMS", "PRODUCTS", "AND", "OF"}


def names_company(title: str, company: str) -> bool:
    """Whether a headline is about the company (its distinctive name word appears), not just its sector."""
    key = [t for t in name_tokens(company) if t not in _GENERIC and len(t) > 2]
    words = set(name_tokens(title, drop_legal=False))
    return bool(key) and key[0] in words


def keyword_adverse(title: str) -> Optional[str]:
    t = f" {title.lower()} "
    return next((w.strip() for w in ADVERSE_TERMS if w in t), None)


# ── Probe42 (commercial; only with a key) ────────────────────────────────────

def probe42(cin_or_name: str) -> dict:
    """The MCA record through Probe42's MCP API (requires PROBE42_API_KEY)."""
    from src.models.canonical_model import Borrower, BorrowerType, Sector
    from src.services import probe_service as ps
    bundle = ps.fetch_probe_bundle(cin_or_name)
    if not bundle or not ps._bundle_has_valid_data(bundle):
        raise RuntimeError("Probe42 returned no company data")
    resolved = bundle.get("resolved") or {}
    borrower = Borrower(entity_id="PROBE", company_name=resolved.get("company_name") or cin_or_name,
                        cin=resolved.get("cin"), pan=resolved.get("pan"), borrower_type=BorrowerType.UNLISTED,
                        sector=Sector.MANUFACTURING, subsector="", date_of_incorporation=None,
                        registered_state=None, registered_address=None, authorized_capital=None,
                        paid_up_capital=None)
    ext = ps._build_probe_external_data(bundle, borrower)
    mca = ext.get("mca_data") or {}
    payload = dict(mca.get("payload") or {})
    payload["directors"] = [{"din": d.din, "name": d.name, "designation": d.designation,
                             "is_promoter": d.is_promoter}
                            for d in ps._build_probe_directors("PROBE", bundle)]
    payload["charges"] = [{"charge_holder": e.facility_type, "amount_cr": e.sanctioned_limit_cr}
                          for e in ps._build_probe_exposure("PROBE", bundle)]
    return envelope("probe42", "company_master", resolved.get("cin") or cin_or_name, payload,
                    provenance={"via": "api", "provider": "Probe42", "url": "probe42 MCP",
                                "from_cache": bool(bundle.get("from_cache")),
                                "fetched_at": bundle.get("fetched_at") or datetime.now().isoformat(timespec="seconds")})
