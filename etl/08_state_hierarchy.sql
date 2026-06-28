-- ============================================================================
-- 08_state_hierarchy.sql: State portal hierarchy (State -> procuring unit).
-- Re-extracts the procuring unit from the detail JSON 'Organisation Name'
-- (dropped during org flattening) for portal_type='state' awards, then builds
-- per-state and per-state-unit summary Parquet for the dashboard.
--   duckdb :memory: ".read etl/08_state_hierarchy.sql"
-- ============================================================================
INSTALL sqlite; LOAD sqlite;
ATTACH 'aoc_tenders.db' AS aoc (TYPE sqlite, READ_ONLY);

CREATE OR REPLACE MACRO clean_unit(s) AS
  nullif(trim(regexp_replace(coalesce(s,''), '\s+', ' ', 'g')), '');

-- 1) state award hierarchy: internal_id -> (state, procuring unit)
COPY (
  SELECT t.internal_id,
         CASE lower(trim(t.org_name))
           WHEN 'telegana'    THEN 'Telangana'
           WHEN 'telengana'   THEN 'Telangana'
           WHEN 'orissa'      THEN 'Odisha'
           WHEN 'pondicherry' THEN 'Puducherry'
           WHEN 'uttaranchal' THEN 'Uttarakhand'
           WHEN 'chattisgarh' THEN 'Chhattisgarh'
           ELSE t.org_name
         END                                                          AS state,
         clean_unit(json_extract_string(d.details_json,'$."Organisation Name"')) AS unit
  FROM aoc.aoc_tenders t JOIN aoc.aoc_details d USING (internal_id)
  WHERE t.portal_type = 'state'
) TO 'data/state_award.parquet' (FORMAT parquet);

-- 2) per-state summary
COPY (
  SELECT sa.state,
         count(*)                                                      AS awards,
         round(100.0 * count(*) FILTER (WHERE NOT fa.value_is_suspect) / count(*), 1) AS value_disclosed_pct,
         sum(fa.contract_value_inr) FILTER (WHERE NOT fa.value_is_suspect)            AS total_value,
         count(*) FILTER (WHERE fl.f_single_bid)                       AS n_single_bid,
         round(100.0 * count(*) FILTER (WHERE fl.f_single_bid) / count(*), 1)         AS single_bid_pct,
         count(DISTINCT sa.unit)                                       AS n_units,
         count(DISTINCT fa.vendor_id)                                  AS n_vendors
  FROM 'data/state_award.parquet' sa
  JOIN 'data/fact_award.parquet'  fa USING (internal_id)
  LEFT JOIN 'data/flag_award.parquet' fl USING (internal_id)
  GROUP BY sa.state ORDER BY awards DESC
) TO 'data/sum_state.parquet' (FORMAT parquet);

-- 3) per-state-per-unit summary (drives the drill-down)
COPY (
  SELECT sa.state, sa.unit,
         count(*)                                                      AS awards,
         sum(fa.contract_value_inr) FILTER (WHERE NOT fa.value_is_suspect)            AS total_value,
         round(100.0 * count(*) FILTER (WHERE fl.f_single_bid) / count(*), 1)         AS single_bid_pct,
         count(DISTINCT fa.vendor_id)                                  AS n_vendors
  FROM 'data/state_award.parquet' sa
  JOIN 'data/fact_award.parquet'  fa USING (internal_id)
  LEFT JOIN 'data/flag_award.parquet' fl USING (internal_id)
  WHERE sa.unit IS NOT NULL
  GROUP BY sa.state, sa.unit
) TO 'data/sum_state_unit.parquet' (FORMAT parquet);

SELECT 'states' m, count(*) v FROM 'data/sum_state.parquet'
UNION ALL SELECT 'state_award rows', count(*) FROM 'data/state_award.parquet'
UNION ALL SELECT 'state+unit rows',  count(*) FROM 'data/sum_state_unit.parquet';
