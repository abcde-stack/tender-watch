-- ============================================================================
-- 04_build_summary.sql: precompute small aggregate artifacts for the dashboard
-- Reads the clean fact/dim/flag Parquet, writes tiny sum_*.parquet (a few MB)
-- so dashboard pages load instantly. Drill-downs query the big Parquet live.
--   duckdb :memory: ".read etl/04_build_summary.sql"
-- ============================================================================

-- yearly trend ---------------------------------------------------------------
COPY (
  SELECT award_year,
         count(*)                                        AS n_awards,
         sum(contract_value_inr) FILTER (WHERE NOT value_is_suspect) AS total_value,
         count(*) FILTER (WHERE bids_received = 1)        AS n_single_bid
  FROM 'data/fact_award.parquet'
  WHERE award_year IS NOT NULL
  GROUP BY award_year ORDER BY award_year
) TO 'data/sum_year.parquet' (FORMAT parquet);

-- monthly distribution by year: fiscal year-end (March) clustering -----------
COPY (
  SELECT year(contract_at)                                 AS award_year,
         month(contract_at)                                AS award_month,
         count(*)                                          AS n_awards
  FROM 'data/fact_award.parquet'
  WHERE contract_at IS NOT NULL
  GROUP BY year(contract_at), month(contract_at)
  ORDER BY award_year, award_month
) TO 'data/sum_month.parquet' (FORMAT parquet);

-- vendor leaderboard ---------------------------------------------------------
COPY (
  SELECT a.vendor_id,
         any_value(v.name_raw)                           AS vendor_name,
         count(*)                                        AS n_awards,
         sum(a.contract_value_inr) FILTER (WHERE NOT a.value_is_suspect) AS total_value,
         count(*) FILTER (WHERE f.f_single_bid)          AS n_single_bid,
         round(100.0 * count(*) FILTER (WHERE f.f_single_bid) / count(*), 1) AS single_bid_pct,
         count(DISTINCT a.org_id)                        AS n_orgs
  FROM 'data/fact_award.parquet' a
  JOIN 'data/dim_vendor.parquet' v USING (vendor_id)
  LEFT JOIN 'data/flag_award.parquet' f USING (internal_id)
  WHERE a.vendor_id IS NOT NULL
  GROUP BY a.vendor_id
) TO 'data/sum_vendor.parquet' (FORMAT parquet);

-- department / org scorecard -------------------------------------------------
-- HHI = Herfindahl-Hirschman Index per org on a 0..10000 scale (sum of squared
-- vendor shares). hhi_count uses share of award COUNT; hhi_value uses share of
-- disclosed VALUE (awards that are NOT value_is_suspect). Both are a LOWER BOUND,
-- since deterministic vendor resolution leaves some name variants unmerged, which
-- splits shares and lowers HHI. hhi_value is NULL where no value is disclosed.
COPY (
  WITH pv AS (   -- awards per (org, vendor), only awards with a known vendor
    SELECT org_id, vendor_id, count(*) AS vc
    FROM 'data/fact_award.parquet'
    WHERE org_id IS NOT NULL AND vendor_id IS NOT NULL
    GROUP BY org_id, vendor_id
  ),
  hhi AS (
    SELECT org_id, round(sum(power(share, 2)), 1) AS hhi_count
    FROM (
      SELECT org_id, 100.0 * vc / sum(vc) OVER (PARTITION BY org_id) AS share
      FROM pv
    )
    GROUP BY org_id
  ),
  pv_val AS ( -- disclosed value per (org, vendor)
    SELECT org_id, vendor_id, sum(contract_value_inr) AS vv
    FROM 'data/fact_award.parquet'
    WHERE org_id IS NOT NULL AND vendor_id IS NOT NULL AND NOT value_is_suspect
    GROUP BY org_id, vendor_id
  ),
  hhi_v AS (
    SELECT org_id, round(sum(power(share, 2)), 1) AS hhi_value
    FROM (
      SELECT org_id, 100.0 * vv / sum(vv) OVER (PARTITION BY org_id) AS share
      FROM pv_val
    )
    GROUP BY org_id
  )
  SELECT a.org_id,
         any_value(o.org_name_raw)                       AS org_name,
         any_value(o.govt_level)                         AS govt_level,
         count(*)                                        AS n_awards,
         sum(a.contract_value_inr) FILTER (WHERE NOT a.value_is_suspect) AS total_value,
         round(100.0 * count(*) FILTER (WHERE NOT a.value_is_suspect) / count(*), 1) AS value_disclosed_pct,
         count(*) FILTER (WHERE f.f_single_bid)          AS n_single_bid,
         round(100.0 * count(*) FILTER (WHERE f.f_single_bid) / count(*), 1) AS single_bid_pct,
         count(DISTINCT a.vendor_id)                     AS n_vendors,
         any_value(h.hhi_count)                          AS hhi_count,
         any_value(hv.hhi_value)                         AS hhi_value
  FROM 'data/fact_award.parquet' a
  JOIN 'data/dim_org.parquet' o USING (org_id)
  LEFT JOIN 'data/flag_award.parquet' f USING (internal_id)
  LEFT JOIN hhi   h  ON h.org_id  = a.org_id
  LEFT JOIN hhi_v hv ON hv.org_id = a.org_id
  WHERE a.org_id IS NOT NULL
  GROUP BY a.org_id
) TO 'data/sum_org.parquet' (FORMAT parquet);

-- flag totals ----------------------------------------------------------------
COPY (
  SELECT 'Single bid'   AS flag, count(*) FILTER (WHERE f_single_bid)   AS n FROM 'data/flag_award.parquet'
  UNION ALL SELECT 'Zero bids',    count(*) FILTER (WHERE f_zero_bid)     FROM 'data/flag_award.parquet'
  UNION ALL SELECT 'Value suspect',count(*) FILTER (WHERE f_value_suspect)FROM 'data/flag_award.parquet'
  UNION ALL SELECT 'Short window',  count(*) FILTER (WHERE f_short_window) FROM 'data/flag_award.parquet'
  UNION ALL SELECT 'Low EMD',       count(*) FILTER (WHERE f_low_emd)      FROM 'data/flag_award.parquet'
  UNION ALL SELECT 'High fee',      count(*) FILTER (WHERE f_high_fee)     FROM 'data/flag_award.parquet'
  UNION ALL SELECT 'Corrigendum',   count(*) FILTER (WHERE f_corrigendum)  FROM 'data/flag_award.parquet'
) TO 'data/sum_flag.parquet' (FORMAT parquet);

-- risk-score distribution ----------------------------------------------------
COPY (
  SELECT risk_score, count(*) AS n_awards
  FROM 'data/flag_award.parquet'
  GROUP BY risk_score ORDER BY risk_score
) TO 'data/sum_risk.parquet' (FORMAT parquet);

-- overview KPIs (single row) -------------------------------------------------
COPY (
  SELECT
    (SELECT count(*) FROM 'data/fact_award.parquet')                                  AS total_awards,
    (SELECT count(*) FROM 'data/fact_tender.parquet')                                 AS total_tenders,
    (SELECT count(*) FROM 'data/dim_vendor.parquet')                                  AS total_vendors,
    (SELECT count(*) FROM 'data/dim_org.parquet')                                     AS total_orgs,
    (SELECT sum(contract_value_inr) FROM 'data/fact_award.parquet' WHERE NOT value_is_suspect) AS total_value,
    (SELECT count(*) FROM 'data/flag_award.parquet' WHERE f_single_bid)               AS n_single_bid
) TO 'data/sum_overview.parquet' (FORMAT parquet);
