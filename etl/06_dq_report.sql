-- ============================================================================
-- 06_dq_report.sql: transparency report over the FINAL Parquet artifacts.
-- Publish this so users can see coverage, parse-failure rates, and flag tallies.
--   duckdb :memory: ".read etl/06_dq_report.sql"
-- ============================================================================
COPY (
  SELECT 'fact_award' AS tbl, 'rows'              AS metric, count(*)::BIGINT AS v FROM 'data/fact_award.parquet'
  UNION ALL SELECT 'fact_award','has_detail',         count(*) FILTER (WHERE has_detail)        FROM 'data/fact_award.parquet'
  UNION ALL SELECT 'fact_award','value_suspect',      count(*) FILTER (WHERE value_is_suspect)  FROM 'data/fact_award.parquet'
  UNION ALL SELECT 'fact_award','misaligned_scrape',  count(*) FILTER (WHERE misaligned_scrape) FROM 'data/fact_award.parquet'
  UNION ALL SELECT 'fact_award','null_value',         count(*) FILTER (WHERE contract_value_inr IS NULL) FROM 'data/fact_award.parquet'
  UNION ALL SELECT 'fact_award','null_bids',          count(*) FILTER (WHERE bids_received IS NULL)       FROM 'data/fact_award.parquet'
  UNION ALL SELECT 'fact_award','matched_to_notice',  count(*) FILTER (WHERE tender_id IN (SELECT tender_id FROM 'data/fact_tender.parquet' WHERE tender_id IS NOT NULL AND tender_id<>'')) FROM 'data/fact_award.parquet'
  UNION ALL SELECT 'fact_tender','rows',              count(*)                                  FROM 'data/fact_tender.parquet'
  UNION ALL SELECT 'fact_tender','has_detail',        count(*) FILTER (WHERE has_detail)        FROM 'data/fact_tender.parquet'
  UNION ALL SELECT 'fact_tender','short_window',      count(*) FILTER (WHERE bid_window_days < 7) FROM 'data/fact_tender.parquet'
  UNION ALL SELECT 'flag_award','rows',               count(*)                                  FROM 'data/flag_award.parquet'
  UNION ALL SELECT 'flag_award','single_bid',         count(*) FILTER (WHERE f_single_bid)      FROM 'data/flag_award.parquet'
  UNION ALL SELECT 'flag_award','zero_bid',           count(*) FILTER (WHERE f_zero_bid)        FROM 'data/flag_award.parquet'
  UNION ALL SELECT 'dim_vendor','rows',               count(*)                                  FROM 'data/dim_vendor.parquet'
  UNION ALL SELECT 'dim_org','rows',                  count(*)                                  FROM 'data/dim_org.parquet'
) TO 'data/dq_report.parquet' (FORMAT parquet);
SELECT * FROM 'data/dq_report.parquet' ORDER BY tbl, metric;
