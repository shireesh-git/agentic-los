"""Static contracts between the LOS governance UI and its API models."""

import re
from pathlib import Path

from src.los.service import _PARTY_ROLES


ROOT = Path(__file__).resolve().parents[1]
LOS_JS = ROOT / "src" / "ui" / "static" / "js" / "los" / "los.js"
APPLICATION_HTML = ROOT / "src" / "ui" / "templates" / "los" / "application.html"


def test_governance_saves_use_the_workspace_payload_envelope():
    js = LOS_JS.read_text(encoding="utf-8")
    block = js[js.index("async govSave("):js.index("async saveParty(")]
    assert "this.post(" in block
    assert ", { payload });" in block
    assert "return true" in block and "return false" in block


def test_party_role_dropdown_matches_the_server_roles():
    html = APPLICATION_HTML.read_text(encoding="utf-8")
    start = html.index('<select x-model="gov.party.role">')
    end = html.index("</select>", start)
    values = set(re.findall(r'<option value="([^"]+)">', html[start:end]))
    values.discard("")
    assert values == _PARTY_ROLES


def test_party_form_exposes_maintenance_fields_and_actions():
    html = APPLICATION_HTML.read_text(encoding="utf-8")
    for marker in (
        'x-model="gov.party.cin"',
        'x-model.number="gov.party.ownership_pct"',
        '@click="editParty(p)"',
        "'Update party'",
        '@click="openPartyEvidence(p)"',
    ):
        assert marker in html
