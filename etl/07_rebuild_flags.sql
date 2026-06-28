-- ============================================================================
-- 07_rebuild_flags.sql: rebuild flag_award from the normalized Parquet with a
-- NULL-safe risk_score (every term coalesced so unmatched-notice NULLs cannot
-- poison the sum). Writes flag_award_new.parquet (swapped in by PowerShell).
-- ============================================================================
COPY (
  WITH notice AS (
    SELECT tender_id, bid_window_days, emd_inr, tender_fee_inr, has_corrigendum
    FROM (
      SELECT *, row_number() OVER (PARTITION BY tender_id
                                   ORDER BY has_detail DESC, epublished_at) AS rn
      FROM 'data/fact_tender.parquet'
      WHERE tender_id IS NOT NULL AND tender_id <> ''
    ) WHERE rn = 1
  )
  SELECT
    a.internal_id, a.tender_id, a.org_id, a.vendor_id,
    (a.bids_received = 1)                                      AS f_single_bid,
    (a.bids_received = 0)                                      AS f_zero_bid,
    a.value_is_suspect                                        AS f_value_suspect,
    (n.bid_window_days IS NOT NULL AND n.bid_window_days < 7)  AS f_short_window,
    (a.contract_value_inr > 1e6 AND n.emd_inr IS NOT NULL
        AND n.emd_inr < a.contract_value_inr * 0.005)         AS f_low_emd,
    coalesce(n.tender_fee_inr > 10000, FALSE)                 AS f_high_fee,
    coalesce(n.has_corrigendum, FALSE)                        AS f_corrigendum,
    ( coalesce(a.bids_received = 1, FALSE)::INT * 3
    + coalesce(a.bids_received = 0, FALSE)::INT * 2
    + (n.bid_window_days IS NOT NULL AND n.bid_window_days < 7)::INT * 2
    + (a.contract_value_inr > 1e6 AND n.emd_inr IS NOT NULL
         AND n.emd_inr < a.contract_value_inr * 0.005)::INT * 2
    + coalesce(n.tender_fee_inr > 10000, FALSE)::INT * 1
    + coalesce(n.has_corrigendum, FALSE)::INT * 1 )           AS risk_score
  FROM 'data/fact_award.parquet' a
  LEFT JOIN notice n
    ON a.tender_id IS NOT NULL AND a.tender_id <> '' AND n.tender_id = a.tender_id
) TO 'data/flag_award_new.parquet' (FORMAT parquet);

SELECT 'rows' m, count(*) v FROM 'data/flag_award_new.parquet'
UNION ALL SELECT 'risk_score NULL', count(*) FILTER (WHERE risk_score IS NULL) FROM 'data/flag_award_new.parquet'
UNION ALL SELECT 'risk_score>=1',   count(*) FILTER (WHERE risk_score >= 1)    FROM 'data/flag_award_new.parquet'
UNION ALL SELECT 'risk_score>=5',   count(*) FILTER (WHERE risk_score >= 5)    FROM 'data/flag_award_new.parquet';
