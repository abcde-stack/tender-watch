-- ============================================================================
-- 10_central_hierarchy.sql: Central portal hierarchy (Organisation -> sub-unit).
-- Re-extracts the '||' sub-unit chain (dropped when org names were collapsed to
-- top-level) for portal_type='central' awards, then builds disclosure-aware
-- per-org and per-org-unit summaries. org_id is taken from fact_award (already
-- normalized) via internal_id, so joins are exact.
--   duckdb :memory: ".read etl/10_central_hierarchy.sql"
-- ============================================================================
INSTALL sqlite; LOAD sqlite;
ATTACH 'aoc_tenders.db' AS aoc (TYPE sqlite, READ_ONLY);

CREATE OR REPLACE MACRO clean_unit(s) AS
  nullif(trim(regexp_replace(coalesce(s,''), '\s+', ' ', 'g')), '');

-- 1) central award -> sub-unit (everything after the first '||' segment)
COPY (
  SELECT t.internal_id,
         CASE WHEN len(string_split(t.org_name, '||')) > 1
              THEN clean_unit(array_to_string(string_split(t.org_name, '||')[2:], ' / '))
              ELSE NULL END AS sub_unit
  FROM aoc.aoc_tenders t
  WHERE t.portal_type = 'central'
) TO 'data/central_award.parquet' (FORMAT parquet);

-- 2) per-organisation summary (disclosure-aware)
COPY (
  SELECT fa.org_id,
         any_value(o.org_name_raw)                                     AS org_name,
         any_value(o.org_type)                                         AS org_type,
         count(*)                                                      AS awards,
         round(100.0 * count(*) FILTER (WHERE NOT fa.value_is_suspect) / count(*), 1) AS value_disclosed_pct,
         sum(fa.contract_value_inr) FILTER (WHERE NOT fa.value_is_suspect)            AS total_value,
         count(*) FILTER (WHERE fl.f_single_bid)                       AS n_single_bid,
         round(100.0 * count(*) FILTER (WHERE fl.f_single_bid) / count(*), 1)         AS single_bid_pct,
         count(DISTINCT ca.sub_unit)                                   AS n_units,
         count(DISTINCT fa.vendor_id)                                  AS n_vendors
  FROM 'data/fact_award.parquet'  fa
  JOIN 'data/dim_org.parquet'     o  ON o.org_id = fa.org_id
  LEFT JOIN 'data/flag_award.parquet'   fl USING (internal_id)
  LEFT JOIN 'data/central_award.parquet' ca USING (internal_id)
  WHERE fa.portal_type = 'central'
  GROUP BY fa.org_id ORDER BY awards DESC
) TO 'data/sum_central.parquet' (FORMAT parquet);

-- 3) per-organisation-per-sub-unit summary (drives the drill-down)
COPY (
  SELECT fa.org_id,
         any_value(o.org_name_raw)                                     AS org_name,
         ca.sub_unit,
         count(*)                                                      AS awards,
         sum(fa.contract_value_inr) FILTER (WHERE NOT fa.value_is_suspect)            AS total_value,
         round(100.0 * count(*) FILTER (WHERE fl.f_single_bid) / count(*), 1)         AS single_bid_pct,
         count(DISTINCT fa.vendor_id)                                  AS n_vendors
  FROM 'data/fact_award.parquet'  fa
  JOIN 'data/central_award.parquet' ca USING (internal_id)
  JOIN 'data/dim_org.parquet'     o  ON o.org_id = fa.org_id
  LEFT JOIN 'data/flag_award.parquet'   fl USING (internal_id)
  WHERE fa.portal_type = 'central' AND ca.sub_unit IS NOT NULL
  GROUP BY fa.org_id, ca.sub_unit
) TO 'data/sum_central_unit.parquet' (FORMAT parquet);

SELECT 'central orgs' m, count(*) v FROM 'data/sum_central.parquet'
UNION ALL SELECT 'central_award rows', count(*) FROM 'data/central_award.parquet'
UNION ALL SELECT 'org+subunit rows',   count(*) FROM 'data/sum_central_unit.parquet';
