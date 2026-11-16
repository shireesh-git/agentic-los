"""
Credit data mart (Wave 1, item 1): the LOS's proposals, credit data fields, checks, challenges, deviations,
activity and knowledge graph, as tables in BigQuery — for portfolio analytics, Conversational Analytics,
Looker, and the BigQuery Graph property graph over the knowledge graph.

    snapshot(flow)   every table as rows, from the flow service (one row per proposal / field / event …)
    Mart.sync()      writes the snapshot when the LOS changed since the last one:
                       BigQuery   when MART_BQ_DATASET is set (Cloud Run): one load job per table, replacing
                                  the table (load jobs are free; the demo volumes are tiny); the dataset and the
                                  property graph are created on the first sync
                       local      otherwise: JSON-lines files under storage/mart/ (a laptop, tests)
    start() / stop() a background thread that syncs every MART_INTERVAL seconds (default 60) and once on stop

A full refresh keeps the mart exactly equal to the LOS — no streaming buffers, no duplicates — and is cheap at
demo scale. A bank deployment would switch to change events (Pub/Sub → BigQuery) without changing the tables.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from src.core.runtime_paths import STORAGE_ROOT

log = logging.getLogger(__name__)

LOCAL_DIR = STORAGE_ROOT / "mart"

# table → [(column, BigQuery type)]; descriptions go into the BigQuery schema (and Knowledge Catalog)
SCHEMA: dict[str, list[tuple[str, str, str]]] = {
    "proposals": [
        ("case_id", "STRING", "Proposal id"), ("entity_id", "STRING", "Borrower id in the LOS"),
        ("borrower", "STRING", "Borrower name"), ("cin", "STRING", "Corporate identity number"),
        ("sector", "STRING", "Sector"), ("product", "STRING", "Product"),
        ("requested_cr", "FLOAT", "Amount requested, ₹ crore"), ("recommended_cr", "FLOAT", "Recommended limit, ₹ crore"),
        ("sanctioned_cr", "FLOAT", "Sanctioned limit, ₹ crore"), ("disbursed_cr", "FLOAT", "Disbursed, ₹ crore"),
        ("stage", "STRING", "Current stage id"), ("stage_label", "STRING", "Current stage"),
        ("status", "STRING", "open / disbursed / rejected …"), ("verdict", "STRING", "Engine recommendation"),
        ("risk_grade", "STRING", "Internal risk grade"), ("is_prospect", "BOOL", "New-to-bank prospect"),
        ("cam_mode", "STRING", "generate (CAM engine) or upload (bank's CAM)"), ("rm", "STRING", "Relationship manager"),
        ("created_at", "TIMESTAMP", "Initiated"), ("updated_at", "TIMESTAMP", "Last change"),
        ("sanctioned_at", "TIMESTAMP", "Sanctioned"), ("disbursed_at", "TIMESTAMP", "Funds released")],
    "data_points": [
        ("case_id", "STRING", "Proposal id"), ("field_id", "STRING", "Credit data field"),
        ("value", "STRING", "Value as text"), ("value_num", "FLOAT", "Value when numeric"),
        ("status", "STRING", "filled / missing / skipped"), ("source_kind", "STRING", "agent / upload / record / person"),
        ("source_label", "STRING", "Where the value came from"), ("document", "STRING", "Source document"),
        ("page", "INT64", "Page in the source document"), ("confidence", "FLOAT", "Confidence score 0–100"),
        ("flag", "STRING", "Disagreement flagged for an officer")],
    "checks": [
        ("case_id", "STRING", "Proposal id"), ("code", "STRING", "Check code"), ("label", "STRING", "Check"),
        ("status", "STRING", "pass / fail / not_verified"), ("detail", "STRING", "Finding"),
        ("source", "STRING", "Source"), ("demo", "BOOL", "Decided on demo data"),
        ("note_kind", "STRING", "verified / justified by an officer"), ("note_by", "STRING", "Officer")],
    "challenges": [
        ("case_id", "STRING", "Proposal id"), ("challenge_id", "STRING", "Challenge id"),
        ("severity", "STRING", "Severity"), ("title", "STRING", "Challenge"),
        ("response", "STRING", "Officer's justification"), ("responded_by", "STRING", "Officer")],
    "deviations": [
        ("case_id", "STRING", "Proposal id"), ("label", "STRING", "Deviation"), ("policy", "STRING", "Policy"),
        ("status", "STRING", "open / proposed / approved / rejected"), ("deviable", "BOOL", "Can be approved"),
        ("mitigant", "STRING", "Mitigant proposed"), ("decided_by", "STRING", "Approver")],
    "events": [
        ("case_id", "STRING", "Proposal id"), ("at", "TIMESTAMP", "When"), ("kind", "STRING", "What happened"),
        ("stage", "STRING", "Stage"), ("actor", "STRING", "Officer or agent"), ("role", "STRING", "Role"),
        ("detail", "STRING", "Detail (JSON)")],
    "kg_nodes": [
        ("node_id", "STRING", "Node key (co:<CIN>, pe:<DIN>, grp:…, le:…, bank:self)"),
        ("kind", "STRING", "company / person / group / lender / bank"), ("name", "STRING", "Name"),
        ("cin", "STRING", "CIN"), ("din", "STRING", "DIN"), ("entity_id", "STRING", "LOS borrower id"),
        ("classification", "STRING", "Account status (Standard / SMA / NPA)"), ("flags", "STRING", "List flags"),
        ("official", "STRING", "Role at the bank, for its own directors / officers"),
        ("source", "STRING", "Source"), ("demo", "BOOL", "Demo data")],
    "kg_edges": [
        ("edge_id", "STRING", "Edge key"), ("src", "STRING", "From node"), ("dst", "STRING", "To node"),
        ("kind", "STRING", "DIRECTOR_OF / HOLDS / MEMBER_OF / BORROWS_FROM / BORROWS_FROM_US / OFFICIAL_OF"),
        ("detail", "STRING", "Designation, product or facility"), ("holding_pct", "FLOAT", "Holding %"),
        ("amount_cr", "FLOAT", "Sanctioned / proposed, ₹ crore"), ("outstanding_cr", "FLOAT", "Outstanding, ₹ crore"),
        ("status", "STRING", "Status"), ("promoter", "BOOL", "Promoter director"),
        ("source", "STRING", "Source"), ("demo", "BOOL", "Demo data")],
}

GRAPH_DDL = """CREATE OR REPLACE PROPERTY GRAPH `{ds}.credit_graph`
  NODE TABLES (
    `{ds}.kg_nodes` KEY (node_id)
      LABEL Entity PROPERTIES (node_id, kind, name, cin, din, entity_id, classification, flags, official, source, demo)
  )
  EDGE TABLES (
    `{ds}.kg_edges` KEY (edge_id)
      SOURCE KEY (src) REFERENCES `{ds}.kg_nodes` (node_id)
      DESTINATION KEY (dst) REFERENCES `{ds}.kg_nodes` (node_id)
      LABEL Relation PROPERTIES (edge_id, kind, detail, holding_pct, amount_cr, outstanding_cr, status, promoter, source, demo)
  )"""


def _ts(v) -> Optional[str]:
    return str(v).replace(" ", "T")[:19] if v else None


def _num(v) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def snapshot(flow) -> dict[str, list[dict]]:
    """Every mart table as rows, from the flow service."""
    from src.flow import graph as kg

    out = {t: [] for t in SCHEMA}
    stages = {s["id"]: s.get("label") for s in flow.stages()}
    for case in flow.store.all():
        cid = case["case_id"]
        company = flow.companies.get(case.get("entity_id")) or {}
        b = company.get("borrower")
        s = case.get("sanction") or {}
        rel = case.get("release") or {}
        dp = case.get("dp") or {}
        risk = case.get("risk") or {}
        out["proposals"].append({
            "case_id": cid, "entity_id": case.get("entity_id"), "borrower": case.get("borrower_name"),
            "cin": getattr(b, "cin", None), "sector": getattr(getattr(b, "sector", None), "value", None),
            "product": (case.get("facility") or {}).get("product"), "requested_cr": _num((case.get("facility") or {}).get("amount_cr")),
            "recommended_cr": _num((dp.get("recommended_cr") or {}).get("value")), "sanctioned_cr": _num(s.get("limit_cr")),
            "disbursed_cr": _num(rel.get("amount_cr")) or (_num(s.get("limit_cr")) if case.get("status") == "disbursed" else None),
            "stage": case.get("stage"), "stage_label": stages.get(case.get("stage")), "status": case.get("status"),
            "verdict": risk.get("recommendation"), "risk_grade": risk.get("rating") if isinstance(risk.get("rating"), str) else None,
            "is_prospect": bool(case.get("is_prospect")), "cam_mode": (case.get("cam") or {}).get("mode"),
            "rm": case.get("rm_name"), "created_at": _ts(case.get("created_at")), "updated_at": _ts(case.get("updated_at")),
            "sanctioned_at": _ts(s.get("at")), "disbursed_at": _ts(rel.get("at"))})
        for fid, p in dp.items():
            src = p.get("source") or {}
            val = p.get("value")
            conf = (src.get("confidence") or {}) if isinstance(src.get("confidence"), dict) else {}
            out["data_points"].append({
                "case_id": cid, "field_id": fid, "value": None if val is None else str(val)[:2000],
                "value_num": _num(val), "status": p.get("status"), "source_kind": src.get("kind"),
                "source_label": src.get("label"), "document": src.get("document"),
                "page": src.get("page") if isinstance(src.get("page"), int) else None,
                "confidence": _num(conf.get("score")), "flag": p.get("flag")})
        for i in (flow._checks_view(case) or {}).get("items") or []:
            n = i.get("note") or {}
            out["checks"].append({"case_id": cid, "code": i["code"], "label": i["label"], "status": i["status"],
                                  "detail": (i.get("detail") or "")[:2000], "source": i.get("source") or None,
                                  "demo": bool(i.get("demo")), "note_kind": n.get("kind"), "note_by": n.get("by")})
        responses = case.get("responses") or {}
        for a in case.get("against") or []:
            r = responses.get(a.get("id")) or {}
            out["challenges"].append({"case_id": cid, "challenge_id": a.get("id"), "severity": a.get("severity"),
                                      "title": a.get("title"), "response": (r.get("note") or r.get("text"))
                                      if isinstance(r, dict) else None, "responded_by": r.get("by") if isinstance(r, dict) else None})
        for d in case.get("register") or []:
            out["deviations"].append({"case_id": cid, "label": d.get("label"), "policy": d.get("policy"),
                                      "status": d.get("status"), "deviable": bool(d.get("deviable")),
                                      "mitigant": d.get("mitigant"), "decided_by": d.get("decided_by") or d.get("approved_by")})
        for e in flow.store.events(cid):
            out["events"].append({"case_id": cid, "at": _ts(e.get("at")), "kind": e.get("kind"), "stage": e.get("stage"),
                                  "actor": e.get("actor_name"), "role": e.get("role"),
                                  "detail": json.dumps(e.get("detail") or {}, ensure_ascii=False, default=str)[:4000]})
    nodes, edges = kg.export(flow.graph())
    out["kg_nodes"], out["kg_edges"] = nodes, edges
    return out


class Mart:
    def __init__(self, flow, dataset: Optional[str] = None, location: str = "asia-south1",
                 local_dir: Path = LOCAL_DIR, interval: float = 60.0):
        self.flow = flow
        self.dataset = dataset                          # "project.dataset" or "dataset" (project from credentials)
        self.location = location
        self.local_dir = Path(local_dir)
        self.interval = interval
        self._version = None
        self._graph_ready = False
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.last: dict = {}

    # ── writing ──────────────────────────────────────────────────────────────

    def sync(self, force: bool = False) -> Optional[dict]:
        """Write the snapshot when the LOS changed since the last sync. Returns what was written."""
        with self._lock:
            version = getattr(self.flow, "version", None)
            if not force and version is not None and version == self._version:
                return None
            try:
                tables = snapshot(self.flow)
                where = self._to_bigquery(tables) if self.dataset else self._to_local(tables)
                self._version = version
                self.last = {"where": where, "rows": {t: len(r) for t, r in tables.items()}, "error": None}
                log.info("Mart synced to %s: %s", where, self.last["rows"])
            except Exception as e:                       # never break the LOS on the mart
                log.exception("Mart sync failed")
                self.last = {"where": self.dataset or str(self.local_dir), "error": str(e)[:300]}
            return self.last

    def _to_local(self, tables: dict[str, list[dict]]) -> str:
        self.local_dir.mkdir(parents=True, exist_ok=True)
        for t, rows in tables.items():
            with open(self.local_dir / f"{t}.jsonl", "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        return str(self.local_dir)

    def _client(self):
        from google.cloud import bigquery
        project = self.dataset.split(".")[0] if "." in self.dataset else None
        return bigquery.Client(project=project, location=self.location)

    def _ds(self, client) -> str:
        return self.dataset if "." in self.dataset else f"{client.project}.{self.dataset}"

    def _to_bigquery(self, tables: dict[str, list[dict]]) -> str:
        from google.cloud import bigquery

        client = self._client()
        ds = self._ds(client)
        dataset = bigquery.Dataset(ds)
        dataset.location = self.location
        dataset.description = "Agentic LOS credit data mart: proposals, credit data fields, checks, challenges, " \
                              "deviations, activity and the credit knowledge graph (demo data)."
        client.create_dataset(dataset, exists_ok=True)
        for t, rows in tables.items():
            schema = [bigquery.SchemaField(c, typ, description=desc) for c, typ, desc in SCHEMA[t]]
            cfg = bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE",
                                         source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON)
            clean = [{c: r.get(c) for c, _, _ in SCHEMA[t]} for r in rows]
            client.load_table_from_json(clean, f"{ds}.{t}", job_config=cfg).result()
        if not self._graph_ready:
            self._graph_ready = self.ensure_graph(client, ds)
        return f"bigquery:{ds}"

    def ensure_graph(self, client, ds: str) -> bool:
        """Declare the BigQuery Graph property graph over kg_nodes / kg_edges. Some BigQuery editions do not
        offer graphs; then the tables are still there for SQL, and this is logged once."""
        try:
            client.query(GRAPH_DDL.format(ds=ds)).result()
            log.info("BigQuery property graph %s.credit_graph is ready", ds)
            return True
        except Exception as e:
            log.warning("BigQuery Graph not created (%s) — the knowledge graph tables are still loaded", str(e)[:200])
            return True                                   # do not retry every minute

    # ── background ───────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self.sync()

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="mart-sync", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.sync()


_mart: Optional[Mart] = None


def from_env(flow) -> Optional[Mart]:
    """The mart for this process: BigQuery when MART_BQ_DATASET is set, local files when MART_LOCAL is not 0."""
    global _mart
    dataset = os.getenv("MART_BQ_DATASET", "").strip() or None
    if not dataset and os.getenv("MART_LOCAL", "1").strip() == "0":
        return None
    if _mart is None:
        _mart = Mart(flow, dataset=dataset, location=os.getenv("MART_BQ_LOCATION", "asia-south1"),
                     interval=float(os.getenv("MART_INTERVAL", "60")))
    return _mart
