-- Rebuild flag_award correctly from the (good) fact Parquet files.
-- Fix: tender_id is NOT unique, so collapse the notice side to ONE row per
-- non-blank tender_id before joining. Result = exactly 1 flag row per award.
COPY (
  WITH notice AS (
    SELECT tender_id, bid_window_days, emd_inr, tender_fee_inr, has_corrigendum
    FROM (
      SELECT *,
             row_number() OVER (PARTITION BY tender_id
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
    (n.tender_fee_inr > 10000)                                AS f_high_fee,
    coalesce(n.has_corrigendum, FALSE)                        AS f_corrigendum,
    ( (a.bids_received = 1)::INT * 3
    + (a.bids_received = 0)::INT * 2
    + (n.bid_window_days IS NOT NULL AND n.bid_window_days < 7)::INT * 2
    + (a.contract_value_inr > 1e6 AND n.emd_inr < a.contract_value_inr * 0.005)::INT * 2
    + (n.tender_fee_inr > 10000)::INT * 1
    + coalesce(n.has_corrigendum, FALSE)::INT * 1 )           AS risk_score
  FROM 'data/fact_award.parquet' a
  LEFT JOIN notice n
    ON a.tender_id IS NOT NULL AND a.tender_id <> '' AND n.tender_id = a.tender_id
) TO 'data/flag_award.parquet' (FORMAT parquet);

-- verify: row count must equal fact_award (4,921,960), plus the flag tallies
SELECT 'flag_award rows'  m, count(*)                              v FROM 'data/flag_award.parquet'
UNION ALL SELECT 'single_bid',     count(*) FILTER (WHERE f_single_bid)   FROM 'data/flag_award.parquet'
UNION ALL SELECT 'zero_bid',       count(*) FILTER (WHERE f_zero_bid)     FROM 'data/flag_award.parquet'
UNION ALL SELECT 'short_window',   count(*) FILTER (WHERE f_short_window) FROM 'data/flag_award.parquet'
UNION ALL SELECT 'low_emd',        count(*) FILTER (WHERE f_low_emd)      FROM 'data/flag_award.parquet'
UNION ALL SELECT 'high_fee',       count(*) FILTER (WHERE f_high_fee)     FROM 'data/flag_award.parquet'
UNION ALL SELECT 'corrigendum',    count(*) FILTER (WHERE f_corrigendum)  FROM 'data/flag_award.parquet'
UNION ALL SELECT 'risk_score>=5',  count(*) FILTER (WHERE risk_score >= 5) FROM 'data/flag_award.parquet';
