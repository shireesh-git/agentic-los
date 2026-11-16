"""
Credit knowledge graph (Wave 1, item 2): who is connected to whom across every borrower the bank has seen.

    nodes   companies (keyed by CIN), people (by DIN), groups, other lenders and the bank itself
    edges   director of · holds (%) · member of group · borrows from (another lender, from the bureau) ·
            borrows from us (our facilities: the LOS proposals and the loan book)

Built from what the LOS already holds — the borrower records (MCA directors, declared group, bureau lenders),
the proposals and their sanctions — plus, while the APIs are not connected, the demo director network
(storage/demo_registry/network.json, standing in for the MCA network, the bureau / CRILC status of connected
companies and the loan management system). Every edge keeps its source and whether it is demo data.

Three checks per proposal, added to the mandatory checks (src/flow/checks.py):

    KG_CONNECTED_STRESS   a company within two hops (common director, holding, group) is SMA / NPA / on a list
    KG_GROUP_EXPOSURE     our exposure to the borrower and to its group of connected counterparties vs the limits
                          (config/exposure.yaml)
    KG_CONNECTED_LENDING  a director or significant shareholder of the borrower is one of the bank's own
                          directors or senior officers

Each finding carries its path ("Arvind B. Chitale — director of → Chitale Infra Projects (SMA-2)"), so an
officer can see why. The same nodes and edges are exported to BigQuery as a property graph (src/core/mart.py).
"""

from __future__ import annotations

import json
import math
import re
from collections import deque
from pathlib import Path
from typing import Iterable, Optional

from src.core.runtime_paths import STORAGE_ROOT

NETWORK_FILE = STORAGE_ROOT / "demo_registry" / "network.json"
BANK = "bank:self"
# relationships a connection is traced through (not lenders: sharing a bank connects nobody)
LINK_KINDS = ("DIRECTOR_OF", "HOLDS", "MEMBER_OF")
_SUFFIX = re.compile(r"\b(?:the|limited|ltd|private|pvt|llp|company|co|inc|corporation|corp)\b\.?", re.I)
_LENDER_TYPES = re.compile(r"\s+(?:cash credit|term loan|wcdl|working capital(?: demand loan)?|bank guarantee|bg|"
                           r"letter of credit|lc|ncd|cc|od|overdraft|nfb|fb|loan)\b.*$", re.I)


def norm_name(name: str) -> str:
    s = _SUFFIX.sub(" ", str(name or "").lower().replace("&", " and "))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def same_person(a: str, b: str) -> bool:
    """Two spellings of one person's name ("D. P. Agarwal" / "D P AGARWAL"; "Arvind Chitale" / "Arvind B. Chitale")."""
    ta, tb = norm_name(a).split(), norm_name(b).split()
    if not ta or not tb:
        return False
    if "".join(ta) == "".join(tb):
        return True
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    rest = list(big)
    for t in small:                    # every part of the shorter name: the same word, or its initial
        hit = next((x for x in rest if x == t or (len(t) == 1 and x[0] == t) or (len(x) == 1 and t[0] == x)), None)
        if hit is None:
            return False
        rest.remove(hit)
    return sum(1 for t in small if len(t) > 1) >= 1


def _crore(v) -> str:
    return f"₹{v:,.2f} Cr" if isinstance(v, (int, float)) else "—"


class Graph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.adj: dict[str, list[int]] = {}
        self._by_name: dict[str, str] = {}
        self._by_entity: dict[str, str] = {}

    # ── building ─────────────────────────────────────────────────────────────

    def node(self, nid: str, kind: str, name: str, **props) -> str:
        n = self.nodes.get(nid)
        if n is None:
            n = self.nodes[nid] = {"id": nid, "kind": kind, "name": name, "cin": None, "din": None, "pan": None,
                                   "entity_id": None, "classification": None, "flags": [], "detail": None,
                                   "official": None, "source": props.get("source"), "demo": bool(props.get("demo"))}
            self.adj[nid] = []
        for k, v in props.items():
            if v in (None, "", []):
                continue
            if k == "flags":
                n["flags"] = sorted(set(n["flags"]) | set(v))
            elif k == "demo":
                continue
            elif n.get(k) in (None, "", []) or k in ("classification", "detail"):
                n[k] = v
        if not n["name"] and name:
            n["name"] = name
        if kind == "company" and name:
            self._by_name.setdefault(norm_name(name), nid)
        return nid

    def company(self, *, cin: Optional[str] = None, name: str = "", entity_id: Optional[str] = None, **props) -> str:
        cin = (cin or "").strip().upper() or None
        nid = None
        if cin:
            nid = f"co:{cin}"
            alias = self._by_name.get(norm_name(name)) if name else None
            if alias and alias != nid and alias.startswith("co:n:"):
                self._merge(alias, nid)          # a name-only node found earlier is this company
        elif entity_id and entity_id in self._by_entity:
            nid = self._by_entity[entity_id]
        elif name and norm_name(name) in self._by_name:
            nid = self._by_name[norm_name(name)]
        else:
            nid = f"co:n:{norm_name(name) or entity_id}"
        nid = self.node(nid, "company", name, cin=cin, entity_id=entity_id, **props)
        if entity_id:
            self._by_entity[entity_id] = nid
        return nid

    def person(self, *, din: Optional[str] = None, name: str = "", pan: Optional[str] = None, **props) -> str:
        din = re.sub(r"\D", "", din or "") or None
        nid = f"pe:{din}" if din else f"pe:n:{norm_name(name)}"
        n = self.nodes.get(nid)
        if din and n is not None and name and n["name"] and not same_person(n["name"], name):
            # the same DIN under a different name (a masked or mistyped identifier): never merge two people on it
            nid = f"pe:{din}~{norm_name(name)}"
            props = {**props, "detail": f"DIN {din} also recorded for {n['name']} — identifier conflict, not merged"}
        return self.node(nid, "person", name, din=din, pan=pan, **props)

    def _merge(self, old: str, new: str) -> None:
        o = self.nodes.pop(old)
        self.adj.pop(old, None)
        self.node(new, o["kind"], o["name"], **{k: v for k, v in o.items() if k not in ("id", "kind", "name")})
        for e in self.edges:
            e["src"] = new if e["src"] == old else e["src"]
            e["dst"] = new if e["dst"] == old else e["dst"]
        for k, v in list(self._by_name.items()):
            if v == old:
                self._by_name[k] = new
        for k, v in list(self._by_entity.items()):
            if v == old:
                self._by_entity[k] = new
        self.adj = {n: [] for n in self.nodes}
        for i, e in enumerate(self.edges):
            self.adj[e["src"]].append(i)
            self.adj[e["dst"]].append(i)

    def edge(self, src: str, dst: str, kind: str, *, detail: str = "", source: str = "", demo: bool = False,
             **props) -> None:
        if src == dst:
            return
        for i in self.adj.get(src, []):                  # one edge per (src, dst, kind, detail)
            e = self.edges[i]
            if e["src"] == src and e["dst"] == dst and e["kind"] == kind and e["detail"] == detail:
                return
        e = {"id": f"e{len(self.edges) + 1}", "src": src, "dst": dst, "kind": kind, "detail": detail,
             "holding_pct": props.get("holding_pct"), "amount_cr": props.get("amount_cr"),
             "outstanding_cr": props.get("outstanding_cr"), "status": props.get("status"),
             "promoter": props.get("promoter"), "source": source, "demo": bool(demo)}
        self.edges.append(e)
        self.adj[src].append(len(self.edges) - 1)
        self.adj[dst].append(len(self.edges) - 1)

    # ── reading ──────────────────────────────────────────────────────────────

    def entity_node(self, entity_id: str) -> Optional[str]:
        return self._by_entity.get(entity_id)

    def links(self, nid: str, kinds: Iterable[str] = LINK_KINDS) -> list[tuple[dict, str]]:
        out = []
        for i in self.adj.get(nid, []):
            e = self.edges[i]
            if e["kind"] in kinds:
                out.append((e, e["dst"] if e["src"] == nid else e["src"]))
        return out

    def paths_from(self, start: str, max_hops: int = 2) -> dict[str, list[dict]]:
        """Shortest path (list of edges) from ``start`` to every node within ``max_hops`` connection hops."""
        best: dict[str, list[dict]] = {start: []}
        q = deque([start])
        while q:
            cur = q.popleft()
            if len(best[cur]) >= max_hops:
                continue
            for e, nxt in self.links(cur):
                if nxt not in best:
                    best[nxt] = best[cur] + [e]
                    q.append(nxt)
        return best

    def describe(self, path: list[dict], start: str) -> str:
        """"Arvind B. Chitale (DIN 07112233) — Managing Director of → Chitale Infra Projects Pvt Ltd"."""
        parts, cur = [self._label(start)], start
        for e in path:
            nxt = e["dst"] if e["src"] == cur else e["src"]
            forward = e["src"] == cur
            parts.append(_verb(e, forward))
            parts.append(self._label(nxt))
            cur = nxt
        return " ".join(parts)

    def _label(self, nid: str) -> str:
        n = self.nodes[nid]
        if n["kind"] == "person" and n.get("din"):
            return f"{n['name']} (DIN {n['din']})"
        return n["name"]

    def stress_of(self, nid: str, cfg: dict) -> Optional[str]:
        n = self.nodes[nid]
        bad = [c.lower() for c in (cfg.get("stress") or {}).get("classifications") or []]
        flags = [f for f in n.get("flags") or [] if f in ((cfg.get("stress") or {}).get("flags") or [])]
        out = []
        if n.get("classification") and n["classification"].lower() in bad:
            out.append(n["classification"])
        out += [_FLAG.get(f, f) for f in flags]
        return ", ".join(out) or None


_FLAG = {"wilful_defaulter": "wilful defaulter", "fraud_flag": "reported as fraud",
         "rbi_defaulter_list": "on the RBI defaulter list"}


def _verb(e: dict, forward: bool) -> str:
    k = e["kind"]
    if k == "DIRECTOR_OF":
        d = e.get("detail") or "director"
        return f"— {d} of →" if forward else f"← {d} —"
    if k == "HOLDS":
        pct = f"{e['holding_pct']:g}% " if e.get("holding_pct") is not None else ""
        return f"— holds {pct}of →" if forward else f"← {pct}held by —"
    if k == "MEMBER_OF":
        return "— in group →" if forward else "← group member —"
    return f"— {k.lower()} →" if forward else f"← {k.lower()} —"


# ── the graph from the bank's records ────────────────────────────────────────

def load_network(path: Path = NETWORK_FILE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _company_status(company: dict, demo_enabled: bool) -> tuple[Optional[str], list[str], str, bool]:
    """(classification, flags, source, demo) of a borrower on record, from its bureau / registry data."""
    from src.data import demo_registry

    b = company.get("borrower")
    ext = dict(company.get("external_data") or {})
    demo = False
    if demo_enabled and b is not None and not (ext.get("bureau_data") or {}).get("payload"):
        d = demo_registry.external_data(getattr(b, "entity_id", None), getattr(b, "cin", None))
        if d.get("bureau_data"):
            ext["bureau_data"], demo = d["bureau_data"], True
    p = (ext.get("bureau_data") or {}).get("payload") or {}
    cls = p.get("worst_status_12m") or p.get("dpd_status")
    flags = [f for f in ("wilful_defaulter", "fraud_flag", "rbi_defaulter_list") if p.get(f) is True]
    return cls, flags, "Commercial bureau" + (" (demo)" if demo else ""), demo


def our_exposure_of(case: dict) -> tuple[float, str]:
    """What a proposal counts toward our exposure: the sanctioned limit once sanctioned, the requested amount
    while it is being decided, nothing once it is declined, withdrawn or archived."""
    if case.get("withdrawn") or case.get("archived") or case.get("status") in ("rejected", "withdrawn", "declined"):
        return 0.0, "closed"
    s = case.get("sanction") or {}
    if s.get("limit_cr") is not None:
        return float(s["limit_cr"]), "disbursed" if case.get("status") == "disbursed" else "sanctioned"
    return float((case.get("facility") or {}).get("amount_cr") or 0), "proposed"


def build(companies: dict, cases: list[dict], network: Optional[dict] = None, cfg: Optional[dict] = None,
          demo_enabled: bool = True) -> Graph:
    g = Graph()
    cfg = cfg or {}
    bank = (cfg.get("bank") or {}).get("name") or "Our bank"
    g.node(BANK, "bank", bank, source="Bank")

    # borrowers on record: identity, directors, declared group, other lenders
    for eid, company in companies.items():
        b = company.get("borrower")
        if b is None:
            continue
        cls, flags, src, demo = _company_status(company, demo_enabled)
        cid = g.company(cin=getattr(b, "cin", None), name=b.company_name, entity_id=eid, classification=cls,
                        flags=flags, source=src, pan=getattr(b, "pan", None))
        for d in company.get("directors") or []:
            pid = g.person(din=d.din, name=d.name, pan=getattr(d, "pan", None), source="MCA directors")
            g.edge(pid, cid, "DIRECTOR_OF", detail=d.designation or "Director", promoter=bool(d.is_promoter),
                   source="MCA directors (borrower record)")
            for other in d.other_directorships or []:
                oid = g.company(name=other, source="Borrower record")
                g.edge(pid, oid, "DIRECTOR_OF", detail="Director", promoter=bool(d.is_promoter),
                       source="Director's other directorships (borrower record)")
        grp = company.get("group")
        if grp is not None and len(getattr(grp, "entities", None) or []) > 1:
            gid = g.node(f"grp:{grp.group_id}", "group", grp.group_name, source="Borrower record")
            for member in grp.entities:
                mid = (g.entity_node(member) if member in companies else None) or (
                    g.company(entity_id=member) if member in companies else g.company(name=member, source="Borrower record"))
                g.edge(mid, gid, "MEMBER_OF", detail=grp.group_name, source="Declared group (borrower record)")
        for x in company.get("existing_exposure") or []:
            lender = _LENDER_TYPES.sub("", x.facility_type).strip() or x.facility_type
            lid = g.node(f"le:{norm_name(lender)}", "lender", lender, source="Commercial bureau")
            g.edge(cid, lid, "BORROWS_FROM", detail=x.facility_type, amount_cr=x.sanctioned_limit_cr,
                   outstanding_cr=x.outstanding_cr, status=x.classification, source="Commercial bureau")

    # the demo director network, the connected companies' status and our loan book
    if network and demo_enabled:
        src = "Director network (demo)"
        for c in network.get("companies") or []:
            g.company(cin=c.get("cin"), name=c.get("name", ""), classification=c.get("classification"),
                      flags=c.get("flags") or [], detail=c.get("detail"), source=c.get("source") or src, demo=True)
        for d in network.get("directorships") or []:
            pid = g.person(din=d.get("din"), name=d.get("name", ""), source=src)
            cid = g.company(cin=d.get("cin"), name=d.get("company", ""))
            g.edge(pid, cid, "DIRECTOR_OF", detail=d.get("designation") or "Director",
                   promoter=bool(d.get("promoter")), source=src, demo=True)
        for h in network.get("holdings") or []:
            holder = (g.company(cin=h["holder_cin"]) if h.get("holder_cin") else
                      g.person(din=h.get("holder_din"), name=h.get("holder_name", "")))
            g.edge(holder, g.company(cin=h.get("held_cin")), "HOLDS", holding_pct=h.get("pct"),
                   source="Shareholding (demo)", demo=True)
        for x in network.get("our_book") or []:
            g.edge(g.company(cin=x.get("cin")), BANK, "BORROWS_FROM_US", detail=x.get("product") or "",
                   amount_cr=x.get("sanctioned_cr"), outstanding_cr=x.get("outstanding_cr"), status="existing",
                   source=x.get("source") or "Loan management system (demo)", demo=True)

    # the bank's own directors and senior officers (connected lending)
    for o in cfg.get("bank_officials") or []:
        pid = g.person(din=o.get("din"), name=o.get("name", ""), pan=o.get("pan"), official=o.get("role"),
                       source="Bank's officials (config)")
        g.edge(pid, BANK, "OFFICIAL_OF", detail=o.get("role") or "", source="Bank's officials (config)")

    # our proposals: what each counts toward our exposure
    for case in cases:
        amt, status = our_exposure_of(case)
        nid = g.entity_node(case.get("entity_id") or "")
        if nid and status != "closed" and amt:
            g.edge(nid, BANK, "BORROWS_FROM_US", detail=f"{case['case_id']} · {(case.get('facility') or {}).get('product') or ''}",
                   amount_cr=amt, status=status, source="LOS proposal")
    return g


# ── analysis for one proposal ────────────────────────────────────────────────

def group_of(g: Graph, start: str, cfg: dict) -> dict[str, str]:
    """The group of connected counterparties (control): company node → why it is in the group."""
    rules = cfg.get("group_rules") or {}
    min_pct = float(rules.get("min_holding_pct", 50))
    out = {start: "the borrower"}
    q = deque([start])
    while q:
        cur = q.popleft()
        steps = []
        for e, other in g.links(cur, ("HOLDS",)):
            if g.nodes[other]["kind"] == "company" and (e.get("holding_pct") or 0) >= min_pct:
                steps.append((other, f"{e['holding_pct']:g}% holding"))
        if rules.get("declared_group", True):
            for e, grp in g.links(cur, ("MEMBER_OF",)):
                for _, other in g.links(grp, ("MEMBER_OF",)):
                    steps.append((other, f"declared group: {g.nodes[grp]['name']}"))
        if rules.get("common_promoter", True):
            for e, person in g.links(cur, ("DIRECTOR_OF", "HOLDS")):
                if g.nodes[person]["kind"] != "person":
                    continue
                if not (e.get("promoter") or (e["kind"] == "HOLDS" and (e.get("holding_pct") or 0) >= min_pct)):
                    continue
                for e2, other in g.links(person, ("DIRECTOR_OF", "HOLDS")):
                    if g.nodes[other]["kind"] == "company" and (
                            e2.get("promoter") or (e2["kind"] == "HOLDS" and (e2.get("holding_pct") or 0) >= min_pct)):
                        steps.append((other, f"common promoter: {g.nodes[person]['name']}"))
        for other, why in steps:
            if other not in out:
                out[other] = why
                q.append(other)
    return out


def our_exposure(g: Graph, nid: str) -> list[dict]:
    rows = []
    for e, other in g.links(nid, ("BORROWS_FROM_US",)):
        rows.append({"detail": e["detail"], "amount_cr": e.get("amount_cr") or 0.0, "status": e.get("status"),
                     "outstanding_cr": e.get("outstanding_cr"), "source": e["source"], "demo": e["demo"]})
    return rows


def assess(g: Graph, entity_id: str, cfg: dict, case: Optional[dict] = None) -> Optional[dict]:
    """The connections, exposure and checks for one borrower; None when it is not in the graph."""
    start = g.entity_node(entity_id)
    if not start:
        return None
    stress_cfg = cfg.get("stress") or {}
    paths = g.paths_from(start, int(stress_cfg.get("max_hops", 2)))

    # 1. connected parties in stress
    stressed = []
    for nid, path in paths.items():
        if nid == start or g.nodes[nid]["kind"] != "company":
            continue
        why = g.stress_of(nid, cfg)
        if why:
            n = g.nodes[nid]
            stressed.append({"name": n["name"], "cin": n.get("cin"), "status": why, "detail": n.get("detail"),
                             "source": n.get("source"), "path": g.describe(path, start),
                             "demo": n["demo"] or any(e["demo"] for e in path)})

    # 2. exposure: the borrower alone and its group of connected counterparties
    group = group_of(g, start, cfg)
    members = []
    for nid, why in group.items():
        rows = our_exposure(g, nid)
        n = g.nodes[nid]
        members.append({"name": n["name"], "cin": n.get("cin"), "why": why, "status": g.stress_of(nid, cfg),
                        "classification": n.get("classification"), "facilities": rows,
                        "exposure_cr": round(sum(r["amount_cr"] for r in rows), 2),
                        "demo": any(r["demo"] for r in rows) or n["demo"]})
    members.sort(key=lambda m: (m["why"] != "the borrower", -m["exposure_cr"]))
    tier1 = (cfg.get("bank") or {}).get("tier1_capital_cr")
    lim = cfg.get("limits") or {}
    single = members[0]["exposure_cr"] if members else 0.0
    group_total = round(sum(m["exposure_cr"] for m in members), 2)
    exposure = {"single_cr": single, "group_cr": group_total, "tier1_cr": tier1, "bank": (cfg.get("bank") or {}).get("name"),
                "single_limit_cr": round(tier1 * lim.get("single_counterparty_pct", 20) / 100, 2) if tier1 else None,
                "group_limit_cr": round(tier1 * lim.get("group_pct", 25) / 100, 2) if tier1 else None,
                "single_pct": lim.get("single_counterparty_pct"), "group_pct": lim.get("group_pct"),
                "warn_at": lim.get("warn_at_pct_of_limit", 85)}
    for k in ("single", "group"):
        limit = exposure[f"{k}_limit_cr"]
        exposure[f"{k}_used_pct"] = round(exposure[f"{k}_cr"] / limit * 100, 1) if limit else None

    # 3. connected lending: the bank's own officials among the borrower's directors / significant holders
    sig = float(cfg.get("significant_holding_pct", 10))
    officials = []
    for e, person in g.links(start, ("DIRECTOR_OF", "HOLDS")):
        p = g.nodes[person]
        if p["kind"] != "person" or not p.get("official"):
            continue
        if e["kind"] == "HOLDS" and (e.get("holding_pct") or 0) < sig:
            continue
        officials.append({"name": p["name"], "din": p.get("din"), "role": p["official"],
                          "relation": e.get("detail") or ("holds " + f"{e['holding_pct']:g}%"),
                          "path": g.describe([e], start)})

    directors = [{"name": g.nodes[p]["name"], "din": g.nodes[p].get("din"), "designation": e.get("detail"),
                  "promoter": bool(e.get("promoter")),
                  "other_companies": [g.nodes[c]["name"] for e2, c in g.links(p, ("DIRECTOR_OF",)) if c != start]}
                 for e, p in g.links(start, ("DIRECTOR_OF",)) if g.nodes[p]["kind"] == "person"]
    lenders = [{"lender": g.nodes[l]["name"], "facility": e["detail"], "sanctioned_cr": e.get("amount_cr"),
                "outstanding_cr": e.get("outstanding_cr"), "status": e.get("status")}
               for e, l in g.links(start, ("BORROWS_FROM",))]
    network_known = any(e["demo"] or e["kind"] in ("DIRECTOR_OF", "HOLDS") for e, _ in g.links(start, LINK_KINDS))
    return {"node": start, "name": g.nodes[start]["name"], "stressed": stressed, "group": members,
            "exposure": exposure, "officials": officials, "directors": directors, "lenders": lenders,
            "network_known": network_known, "reach": len(paths) - 1,
            "demo": any(s["demo"] for s in stressed) or any(m["demo"] for m in members),
            "picture": picture(g, start, paths, cfg)}


def checks(result: Optional[dict]) -> list[dict]:
    """The three graph checks as mandatory-check items (codes in src/flow/checks.py)."""
    from src.flow import checks as chk

    if not result:
        return [chk.item(c, "not_verified", "The borrower is not in the knowledge graph yet")
                for c in ("KG_CONNECTED_STRESS", "KG_GROUP_EXPOSURE", "KG_CONNECTED_LENDING")]
    out = []
    s = result["stressed"]
    if s:
        detail = "; ".join(f"{x['name']} — {x['status']}: {x['path']}" for x in s[:3]) + ("…" if len(s) > 3 else "")
        src = "; ".join(sorted({x["source"] for x in s if x.get("source")}))
        out.append({**chk.item("KG_CONNECTED_STRESS", "fail", detail), "source": src,
                    "demo": any(x["demo"] for x in s)})
    elif result["network_known"]:
        out.append(chk.item("KG_CONNECTED_STRESS", "pass",
                            f"No connected company in stress within two hops ({result['reach']} connections checked)"))
    else:
        out.append(chk.item("KG_CONNECTED_STRESS", "not_verified", "No director or shareholding network on record"))

    x = result["exposure"]
    if x.get("group_limit_cr"):
        over = [k for k in ("single", "group") if (x.get(f"{k}_used_pct") or 0) > 100]
        n = len(result["group"])
        parts = {"single": f"exposure to the borrower {_crore(x['single_cr'])} is {x['single_used_pct']}% of the "
                           f"{_crore(x['single_limit_cr'])} single-borrower limit",
                 "group": f"exposure to its group of {n} connected compan{'y' if n == 1 else 'ies'} "
                          f"{_crore(x['group_cr'])} is {x['group_used_pct']}% of the {_crore(x['group_limit_cr'])} group limit"}
        order = over + [k for k in ("single", "group") if k not in over]          # the breach first
        detail = ("Over the limit: " if over else "") + "; ".join(parts[k] for k in order)
        detail = detail[0].upper() + detail[1:] + (f" ({x['single_pct']}% / {x['group_pct']}% of Tier 1 capital "
                                                   f"{_crore(x['tier1_cr'])})")
        out.append({**chk.item("KG_GROUP_EXPOSURE", "fail" if over else "pass", detail),
                    "source": "LOS proposals; loan book; config/exposure.yaml", "demo": result["demo"]})
    else:
        out.append(chk.item("KG_GROUP_EXPOSURE", "not_verified", "The bank's Tier 1 capital is not configured"))

    o = result["officials"]
    if o:
        out.append({**chk.item("KG_CONNECTED_LENDING", "fail",
                               "; ".join(f"{p['name']} ({p['role']}) — {p['relation']} of the borrower" for p in o)),
                    "source": "Bank's officials (config); MCA directors"})
    elif result["directors"]:
        out.append(chk.item("KG_CONNECTED_LENDING", "pass",
                            f"No director or significant shareholder of the borrower ({len(result['directors'])} "
                            f"checked) is a director or senior officer of the bank"))
    else:
        out.append(chk.item("KG_CONNECTED_LENDING", "not_verified", "No directors on record"))
    return out


def _edge_label(e: dict, forward: bool) -> str:
    k = e["kind"]
    if k == "DIRECTOR_OF":
        return (e.get("detail") or "Director") + (" · promoter" if e.get("promoter") else "")
    if k == "HOLDS":
        return f"holds {e['holding_pct']:g}%" if e.get("holding_pct") is not None else "shareholder"
    if k == "MEMBER_OF":
        return "same group"
    if k == "BORROWS_FROM_US":
        amt = e.get("amount_cr")
        return "our exposure" + (f" · ₹{amt:,.0f} Cr" if amt else "")
    if k == "BORROWS_FROM":
        amt = e.get("amount_cr")
        return (e.get("detail") or "lender") + (f" · ₹{amt:,.0f} Cr" if amt else "")
    return k.lower().replace("_", " ")


def picture(g: Graph, start: str, paths: dict[str, list[dict]], cfg: dict, per_col: int = 8) -> dict:
    """A relationship map read left to right (round 8, replacing the radial picture):

        other companies of these people | directors & shareholders | BORROWER | lenders & group companies | their links

    Each box is named; each line says how the two are connected (director, holds 60%, lender …)."""
    cols = {"far_left": [], "people": [], "right": [], "far_right": []}
    via: dict[str, tuple[str, dict]] = {}                      # node -> (the node it is reached from, the edge)
    for n, path in paths.items():
        if n == start or len(path) > 2:
            continue
        prev = start
        for e in path[:-1]:
            prev = e["dst"] if e["src"] == prev else e["src"]
        via[n] = (prev, path[-1])
        kind = g.nodes[n]["kind"]
        if len(path) == 1:
            cols["people" if kind == "person" else "right"].append(n)
        else:
            first = g.nodes[prev]["kind"]
            cols["far_left" if first == "person" and kind != "person" else "far_right"].append(n)
    for e, other in g.links(start, ("BORROWS_FROM", "BORROWS_FROM_US")):
        if other not in via:
            via[other] = (start, e)
            cols["right"].append(other)
    stressed = {n for n in via if g.stress_of(n, cfg)}
    hidden = 0
    for k, ids in cols.items():
        ids.sort(key=lambda n: (n not in stressed, not g.nodes[n].get("official"), g.nodes[n]["name"]))
        hidden += max(len(ids) - per_col, 0)
        cols[k] = ids[:per_col]
    xs = {"far_left": 95, "people": 285, "centre": 500, "right": 715, "far_right": 905}
    titles = {"far_left": "Other companies of these people", "people": "Directors & shareholders",
              "centre": "Borrower", "right": "Lenders & group companies", "far_right": "Their links"}
    rows = max([len(v) for v in cols.values()] + [1])
    top, step = 50, 44
    height = top + rows * step + 10
    pos = {start: (xs["centre"], top + (rows - 1) * step / 2)}
    for k, ids in cols.items():
        y0 = top + (rows - len(ids)) * step / 2
        for i, n in enumerate(ids):
            pos[n] = (xs[k], y0 + i * step)
    rel = {}
    for n, (prev, e) in via.items():
        r, name = _edge_label(e, e["src"] == prev), g.nodes[n]["name"]
        rel[n] = r[len(name):].lstrip(" ·") or "lender" if r.startswith(name) else r
    nodes = [{"id": n, "x": x, "y": round(y), "kind": g.nodes[n]["kind"],
              "label": g.nodes[n]["name"][:34 if n == start else 24], "relation": rel.get(n, "")[:30],
              "full": g.nodes[n]["name"], "stress": n in stressed, "status": g.stress_of(n, cfg) or "",
              "official": g.nodes[n].get("official") or "", "center": n == start,
              "demo": bool(g.nodes[n].get("demo"))} for n, (x, y) in pos.items()]
    lines = []
    for n, (prev, e) in via.items():
        if n in pos and prev in pos:
            lines.append({"x1": pos[prev][0], "y1": round(pos[prev][1]), "x2": pos[n][0], "y2": round(pos[n][1]),
                          "kind": e["kind"], "demo": bool(e.get("demo")), "stress": n in stressed,
                          "label": _edge_label(e, e["src"] == prev)})
    used = {k for k, v in cols.items() if v} | {"centre"}
    return {"nodes": nodes, "lines": lines, "hidden": hidden, "width": 1000, "height": height,
            "columns": [{"x": xs[k], "title": titles[k]} for k in xs if k in used]}


def export(g: Graph) -> tuple[list[dict], list[dict]]:
    """Rows for the BigQuery tables kg_nodes and kg_edges."""
    nodes = [{"node_id": n["id"], "kind": n["kind"], "name": n["name"], "cin": n.get("cin"), "din": n.get("din"),
              "entity_id": n.get("entity_id"), "classification": n.get("classification"),
              "flags": ",".join(n.get("flags") or []) or None, "official": n.get("official"),
              "source": n.get("source"), "demo": bool(n.get("demo"))} for n in g.nodes.values()]
    edges = [{"edge_id": e["id"], "src": e["src"], "dst": e["dst"], "kind": e["kind"], "detail": e["detail"] or None,
              "holding_pct": e.get("holding_pct"), "amount_cr": e.get("amount_cr"),
              "outstanding_cr": e.get("outstanding_cr"), "status": e.get("status"),
              "promoter": e.get("promoter"), "source": e.get("source"), "demo": bool(e.get("demo"))}
             for e in g.edges]
    return nodes, edges
