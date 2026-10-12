"""
External Systems — Identifier resolution & API stubs.

All company data is sourced from Probe42 MCP.  These functions provide
identifier-resolution lookups and return ``not_found`` responses when
the Probe42 bundle has not been fetched.
"""

from datetime import date
import logging

_log = logging.getLogger(__name__)


def _today():
    return date.today().isoformat()


def _not_found(source: str, record_type: str, entity_key: str, version: str = "v2") -> dict:
    return {
        "source": source,
        "record_type": record_type,
        "entity_key": entity_key,
        "as_of_date": _today(),
        "payload_version": version,
        "source_status": "not_found",
        "payload": {},
    }


# ══════════════════════════════════════════════════════════════════════════════
# Identifier Reference Lookups  (CIN ↔ PAN ↔ GSTIN ↔ Entity-ID ↔ Name)
# ══════════════════════════════════════════════════════════════════════════════

# CIN → company name (reference only — actual details from Probe42)
_CIN_TO_NAME = {
    "L29100MH2008PLC185432": "Bharat Manufacturing Ltd",
    "L45200DL2005PLC134567": "Pinnacle Infra Projects Ltd",
    "U24230GJ2012PTC068945": "Sunrise Pharma Pvt Ltd",
    "U63090KA2010PTC052345": "Omega Logistics Pvt Ltd",
    "L27100MH1907PLC000260": "Tara Steels Industries Ltd",
    "L17110MH1973PLC019786": "Reliable Energy Industries Ltd",
    "L85110KA1981PLC013115": "Infosys Limited",
    "L63090GJ1998PLC034182": "Advik Ports & SEZ Ltd",
    "L65910MH1987PLC042961": "Bajrang Finance Ltd",
    "L24239MH1935PLC002380": "Ciplex Pharmaceuticals Ltd",
    "L70101HR1963PLC002484": "Delhi Land & Realty Ltd",
    "L27102MH1994PLC083190": "JSW Alloys & Steel Ltd",
    "L34103HR1981PLC013258": "Maruti Auto Industries Ltd",
    "L74999TN1984PLC010491": "Titan Luxe Retail Ltd",
    "L40101DL1975GOI007966": "National Thermal Power Corp Ltd",
    "L65190MH2003PLC143249": "Yashwant Commercial Bank Ltd",
    "L85110TN1979PLC008035": "Apollo Hospitals Enterprise Limited",
    "L45201DL1999PLC195937": "PNC Infratech Limited",
}

# PAN → CIN
_PAN_TO_CIN = {
    "AABCB1234F": "L29100MH2008PLC185432",
    "AABCP5678G": "L45200DL2005PLC134567",
    "AABCS9012H": "U24230GJ2012PTC068945",
    "AABCO3456J": "U63090KA2010PTC052345",
    "AAACT1234A": "L27100MH1907PLC000260",
    "AAACR2345B": "L17110MH1973PLC019786",
    "AAACI3456C": "L85110KA1981PLC013115",
    "AAACA4567D": "L63090GJ1998PLC034182",
    "AABCB5678E": "L65910MH1987PLC042961",
    "AAACC6789F": "L24239MH1935PLC002380",
    "AAACD7890G": "L70101HR1963PLC002484",
    "AAACJ8901H": "L27102MH1994PLC083190",
    "AAACM9012J": "L34103HR1981PLC013258",
    "AAACT0123K": "L74999TN1984PLC010491",
    "AAACN1234L": "L40101DL1975GOI007966",
    "AAACY2345M": "L65190MH2003PLC143249",
    "AAACA1234K": "L85110TN1979PLC008035",
    "AABCP1234R": "L45201DL1999PLC195937",
}

# Company name (lowercase) → CIN
_NAME_TO_CIN = {
    "bharat manufacturing ltd": "L29100MH2008PLC185432",
    "bharat manufacturing": "L29100MH2008PLC185432",
    "pinnacle infra projects ltd": "L45200DL2005PLC134567",
    "pinnacle infra projects": "L45200DL2005PLC134567",
    "pinnacle infra": "L45200DL2005PLC134567",
    "sunrise pharma pvt ltd": "U24230GJ2012PTC068945",
    "sunrise pharma": "U24230GJ2012PTC068945",
    "omega logistics pvt ltd": "U63090KA2010PTC052345",
    "omega logistics": "U63090KA2010PTC052345",
    "tara steels industries ltd": "L27100MH1907PLC000260",
    "tara steels": "L27100MH1907PLC000260",
    "reliable energy industries ltd": "L17110MH1973PLC019786",
    "reliable energy": "L17110MH1973PLC019786",
    "infosys limited": "L85110KA1981PLC013115",
    "infosys": "L85110KA1981PLC013115",
    "advik ports & sez ltd": "L63090GJ1998PLC034182",
    "advik ports": "L63090GJ1998PLC034182",
    "bajrang finance ltd": "L65910MH1987PLC042961",
    "bajrang finance": "L65910MH1987PLC042961",
    "ciplex pharmaceuticals ltd": "L24239MH1935PLC002380",
    "ciplex pharma": "L24239MH1935PLC002380",
    "delhi land & realty ltd": "L70101HR1963PLC002484",
    "delhi land realty": "L70101HR1963PLC002484",
    "jsw alloys & steel ltd": "L27102MH1994PLC083190",
    "jsw alloys": "L27102MH1994PLC083190",
    "maruti auto industries ltd": "L34103HR1981PLC013258",
    "maruti auto": "L34103HR1981PLC013258",
    "titan luxe retail ltd": "L74999TN1984PLC010491",
    "titan luxe": "L74999TN1984PLC010491",
    "national thermal power corp ltd": "L40101DL1975GOI007966",
    "ntpc power": "L40101DL1975GOI007966",
    "yashwant commercial bank ltd": "L65190MH2003PLC143249",
    "yashwant bank": "L65190MH2003PLC143249",
    "apollo hospitals enterprise limited": "L85110TN1979PLC008035",
    "apollo hospitals": "L85110TN1979PLC008035",
    "pnc infratech limited": "L45201DL1999PLC195937",
    "pnc infratech": "L45201DL1999PLC195937",
    "pnc infra": "L45201DL1999PLC195937",
}

# Entity ID → CIN / PAN / GSTIN
_ENTITY_TO_IDS = {
    "BMFG001": {"cin": "L29100MH2008PLC185432", "pan": "AABCB1234F", "gstin": "27AABCB1234F1Z5"},
    "PINF001": {"cin": "L45200DL2005PLC134567", "pan": "AABCP5678G", "gstin": "07AABCP5678G1Z8"},
    "SPHR001": {"cin": "U24230GJ2012PTC068945", "pan": "AABCS9012H", "gstin": "24AABCS9012H1Z2"},
    "OLOG001": {"cin": "U63090KA2010PTC052345", "pan": "AABCO3456J", "gstin": "29AABCO3456J1Z1"},
    "TSTL001": {"cin": "L27100MH1907PLC000260", "pan": "AAACT1234A", "gstin": "27AAACT1234A1Z8"},
    "REIL001": {"cin": "L17110MH1973PLC019786", "pan": "AAACR2345B", "gstin": "27AAACR2345B1Z6"},
    "INFY001": {"cin": "L85110KA1981PLC013115", "pan": "AAACI3456C", "gstin": "29AAACI3456C1Z4"},
    "ADPT001": {"cin": "L63090GJ1998PLC034182", "pan": "AAACA4567D", "gstin": "24AAACA4567D1Z2"},
    "BJFN001": {"cin": "L65910MH1987PLC042961", "pan": "AABCB5678E", "gstin": "27AABCB5678E1Z3"},
    "CIPL001": {"cin": "L24239MH1935PLC002380", "pan": "AAACC6789F", "gstin": "27AAACC6789F1Z1"},
    "DLFR001": {"cin": "L70101HR1963PLC002484", "pan": "AAACD7890G", "gstin": "06AAACD7890G1Z9"},
    "JSWL001": {"cin": "L27102MH1994PLC083190", "pan": "AAACJ8901H", "gstin": "27AAACJ8901H1Z7"},
    "MRUT001": {"cin": "L34103HR1981PLC013258", "pan": "AAACM9012J", "gstin": "06AAACM9012J1Z5"},
    "TITN001": {"cin": "L74999TN1984PLC010491", "pan": "AAACT0123K", "gstin": "33AAACT0123K1Z3"},
    "NTPC001": {"cin": "L40101DL1975GOI007966", "pan": "AAACN1234L", "gstin": "07AAACN1234L1Z1"},
    "YESB001": {"cin": "L65190MH2003PLC143249", "pan": "AAACY2345M", "gstin": "27AAACY2345M1Z9"},
    "APOL001": {"cin": "L85110TN1979PLC008035", "pan": "AAACA1234K", "gstin": "33AAACA1234K1Z1"},
    "PNCR001": {"cin": "L45201DL1999PLC195937", "pan": "AABCP1234R", "gstin": "09AABCP1234R1Z6"},
}

# PAN → GSTIN (derived from _ENTITY_TO_IDS)
_PAN_TO_GSTIN = {ids["pan"]: ids["gstin"] for ids in _ENTITY_TO_IDS.values()}


def reference_identifiers(entity_id: str) -> dict:
    """CIN / PAN / GSTIN from the reference table for an entity ID ({} if unknown)."""
    return dict(_ENTITY_TO_IDS.get((entity_id or "").upper(), {}))


# ══════════════════════════════════════════════════════════════════════════════
# Company Resolution
# ══════════════════════════════════════════════════════════════════════════════

def resolve_company(identifier: str) -> dict | None:
    """
    Smart company resolution — accepts PAN, CIN, GSTIN, Entity ID, or company name.
    Returns { cin, pan, gstin, entity_id, company_name } or None.
    Uses only reference lookup tables; actual company data comes from Probe42.
    """
    identifier = identifier.strip()

    # Try CIN direct match
    if identifier in _CIN_TO_NAME:
        cin = identifier
        pan = next((p for p, c in _PAN_TO_CIN.items() if c == cin), None)
        eid = next((e for e, ids in _ENTITY_TO_IDS.items() if ids["cin"] == cin), None)
        gstin = _ENTITY_TO_IDS.get(eid, {}).get("gstin") if eid else None
        return {
            "cin": cin, "pan": pan, "gstin": gstin, "entity_id": eid,
            "company_name": _CIN_TO_NAME[cin],
        }

    # Try PAN
    cin = _PAN_TO_CIN.get(identifier.upper())
    if cin:
        eid = next((e for e, ids in _ENTITY_TO_IDS.items() if ids["cin"] == cin), None)
        gstin = _ENTITY_TO_IDS.get(eid, {}).get("gstin") if eid else None
        return {
            "cin": cin, "pan": identifier.upper(), "gstin": gstin, "entity_id": eid,
            "company_name": _CIN_TO_NAME.get(cin, ""),
        }

    # Try GSTIN (extract PAN from positions 2-12)
    if len(identifier) == 15:
        pan_from_gstin = identifier[2:12]
        cin = _PAN_TO_CIN.get(pan_from_gstin)
        if cin:
            eid = next((e for e, ids in _ENTITY_TO_IDS.items() if ids["cin"] == cin), None)
            return {
                "cin": cin, "pan": pan_from_gstin, "gstin": identifier, "entity_id": eid,
                "company_name": _CIN_TO_NAME.get(cin, ""),
            }

    # Try Entity ID
    ids = _ENTITY_TO_IDS.get(identifier.upper())
    if ids:
        cin = ids["cin"]
        return {
            "cin": cin, "pan": ids["pan"], "gstin": ids["gstin"],
            "entity_id": identifier.upper(),
            "company_name": _CIN_TO_NAME.get(cin, ""),
        }

    # Try company name (fuzzy-ish)
    name_lower = identifier.lower().strip()
    cin = _NAME_TO_CIN.get(name_lower)
    if not cin:
        for known_name, known_cin in _NAME_TO_CIN.items():
            if name_lower in known_name or known_name in name_lower:
                cin = known_cin
                break
    if cin:
        eid = next((e for e, ids in _ENTITY_TO_IDS.items() if ids["cin"] == cin), None)
        pan = next((p for p, c in _PAN_TO_CIN.items() if c == cin), None)
        gstin = _ENTITY_TO_IDS.get(eid, {}).get("gstin") if eid else None
        return {
            "cin": cin, "pan": pan, "gstin": gstin, "entity_id": eid,
            "company_name": _CIN_TO_NAME.get(cin, ""),
        }

    return None


# ══════════════════════════════════════════════════════════════════════════════
# API Stubs — All return not_found.  Actual data comes via Probe42 MCP bundle.
# ══════════════════════════════════════════════════════════════════════════════

def mca_company_master(cin: str) -> dict:
    """MCA V3 API — Company Master Data.  Data sourced from Probe42."""
    return _not_found("mca", "company_master", cin)


def mca_directors(cin: str) -> dict:
    """MCA — Board of Directors.  Data sourced from Probe42."""
    return _not_found("mca", "directors", cin)


def mca_charges(cin: str) -> dict:
    """MCA — Charges Register.  Data sourced from Probe42."""
    return _not_found("mca", "charges", cin)


def gstin_details(gstin: str) -> dict:
    """GSTIN API — Registration + compliance.  Data sourced from Probe42."""
    return _not_found("gstin", "registration", gstin)


def gstin_turnover(pan: str) -> dict:
    """GST Turnover summary by PAN.  Data sourced from Probe42."""
    return _not_found("gstin", "turnover", pan)


def bureau_commercial_report(pan: str) -> dict:
    """Credit Bureau commercial report.  Data sourced from Probe42."""
    return _not_found("bureau", "commercial_report", pan)


def rating_action(entity_id: str) -> dict:
    """Credit Rating Agency actions.  Data sourced from Probe42."""
    return _not_found("rating", "rating_action", entity_id)


def market_intelligence(entity_id: str) -> dict:
    """Market intelligence & sentiment.  Data sourced from Probe42."""
    return _not_found("market", "intelligence", entity_id)


def crilc_report(pan: str) -> dict:
    """RBI CRILC large credit report.  Data sourced from Probe42."""
    return _not_found("crilc", "borrower_report", pan)


def epfo_compliance(pan: str) -> dict:
    """EPFO compliance status.  Data sourced from Probe42."""
    return _not_found("epfo", "compliance", pan)


def itr_filing_status(pan: str) -> dict:
    """Income Tax filing status.  Data sourced from Probe42."""
    return _not_found("itr", "filing_status", pan)


def exchange_financial_results(entity_id: str) -> dict:
    """BSE/NSE financial results.  Data sourced from Probe42."""
    return _not_found("exchange", "financial_results", entity_id, "v1")


def exchange_governance_filings(entity_id: str) -> dict:
    """Exchange governance filings.  Data sourced from Probe42."""
    return _not_found("exchange", "governance_filings", entity_id, "v1")


def social_reputation_signals(entity_id: str) -> dict:
    """Social reputation signals.  Data sourced from Probe42."""
    return _not_found("social", "reputation_signals", entity_id, "v1")
