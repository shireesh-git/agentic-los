-- Credit knowledge graph on BigQuery Graph (Wave 1, item 2).
--
-- The LOS loads kg_nodes and kg_edges into the mart dataset (src/core/mart.py, MART_BQ_DATASET, default
-- `los_mart` in project kpmg-lending-trans-sol, region asia-south1) and declares this property graph on the first
-- sync. Run these in BigQuery Studio. Replace `los_mart` if the dataset is named differently.
-- Some BigQuery editions do not offer graph queries; the same questions in plain SQL are at the end.

-- 1. The property graph over the two tables (the mart creates it; kept here for reference) -----------------------
CREATE OR REPLACE PROPERTY GRAPH `los_mart.credit_graph`
  NODE TABLES (
    `los_mart.kg_nodes` KEY (node_id)
      LABEL Entity PROPERTIES (node_id, kind, name, cin, din, entity_id, classification, flags, official, source, demo)
  )
  EDGE TABLES (
    `los_mart.kg_edges` KEY (edge_id)
      SOURCE KEY (src) REFERENCES `los_mart.kg_nodes` (node_id)
      DESTINATION KEY (dst) REFERENCES `los_mart.kg_nodes` (node_id)
      LABEL Relation PROPERTIES (edge_id, kind, detail, holding_pct, amount_cr, outstanding_cr, status, promoter, source, demo)
  );

-- 2. Connected parties in stress: a borrower's directors who sit on a company that is SMA / NPA ------------------
GRAPH `los_mart.credit_graph`
MATCH (b:Entity {entity_id: 'ABCE001'})<-[d1:Relation {kind: 'DIRECTOR_OF'}]-(p:Entity)
      -[d2:Relation {kind: 'DIRECTOR_OF'}]->(x:Entity)
WHERE x.node_id != b.node_id AND x.classification IN ('SMA-1', 'SMA-2', 'NPA', 'Substandard', 'Doubtful', 'Loss')
RETURN b.name AS borrower, p.name AS director, p.din AS din, d2.detail AS role_there,
       x.name AS connected_company, x.classification AS status, x.source AS source;

-- 3. Every borrower with a connected party in stress, across the whole book ---------------------------------------
GRAPH `los_mart.credit_graph`
MATCH (b:Entity)-[l:Relation {kind: 'BORROWS_FROM_US'}]->(bank:Entity {kind: 'bank'}),
      (b)<-[:Relation {kind: 'DIRECTOR_OF'}]-(p:Entity)-[:Relation {kind: 'DIRECTOR_OF'}]->(x:Entity)
WHERE x.classification IN ('SMA-1', 'SMA-2', 'NPA')
RETURN DISTINCT b.name AS borrower, l.amount_cr AS our_exposure_cr, p.name AS via_director, x.name AS stressed_company,
       x.classification AS status;

-- 4. Group exposure: our exposure to the borrower and to companies it holds 50% or more of -----------------------
GRAPH `los_mart.credit_graph`
MATCH (b:Entity {entity_id: 'ABCE001'})-[h:Relation {kind: 'HOLDS'}]->(s:Entity)-[l:Relation {kind: 'BORROWS_FROM_US'}]->(:Entity {kind: 'bank'})
WHERE h.holding_pct >= 50
RETURN s.name AS group_company, h.holding_pct AS held_pct, l.detail AS facility, l.amount_cr AS our_exposure_cr;

-- 5. Connected lending: the bank's own directors / officers on any borrower's board ------------------------------
GRAPH `los_mart.credit_graph`
MATCH (o:Entity)-[:Relation {kind: 'OFFICIAL_OF'}]->(:Entity {kind: 'bank'}),
      (o)-[d:Relation {kind: 'DIRECTOR_OF'}]->(b:Entity)
RETURN o.name AS bank_official, o.official AS role_at_bank, b.name AS company, d.detail AS role_there;

-- 6. The same as query 2 in plain SQL (any edition) ----------------------------------------------------------------
SELECT b.name AS borrower, p.name AS director, x.name AS connected_company, x.classification AS status
FROM `los_mart.kg_nodes` b
JOIN `los_mart.kg_edges` d1 ON d1.dst = b.node_id AND d1.kind = 'DIRECTOR_OF'
JOIN `los_mart.kg_nodes` p ON p.node_id = d1.src
JOIN `los_mart.kg_edges` d2 ON d2.src = p.node_id AND d2.kind = 'DIRECTOR_OF' AND d2.dst != b.node_id
JOIN `los_mart.kg_nodes` x ON x.node_id = d2.dst
WHERE b.entity_id = 'ABCE001' AND x.classification IN ('SMA-1', 'SMA-2', 'NPA');

-- 7. Portfolio view for Conversational Analytics / Looker: exposure by sector and status -------------------------
SELECT sector, status, COUNT(*) AS proposals, SUM(COALESCE(sanctioned_cr, requested_cr)) AS amount_cr
FROM `los_mart.proposals`
GROUP BY sector, status
ORDER BY amount_cr DESC;
