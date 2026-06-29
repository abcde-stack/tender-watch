-- ============================================================================
-- 02_clean.sql: Tender Watch ETL, stage 2: staging -> typed/normalized model
-- ----------------------------------------------------------------------------
-- Builds the analytics model from the staging views created in 01_staging.sql:
--   dim_org, dim_vendor, fact_award, fact_tender, flag_award
-- then exports everything to Parquet under ./data.
--
-- Assumes 01_staging.sql ran in the SAME duckdb session (macros + staging views
-- + attached aoc/vps live in the session). Use etl/run.sql to run both in order.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- DIM: organisation  (union of award-side and tender-side org names)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_org AS
WITH src AS (
    SELECT org_name_raw AS name_raw, NULL AS type_raw, portal_type FROM stg_award
    UNION ALL
    SELECT org_name_raw,             org_type_raw,      portal_type FROM stg_tender
),
norm AS (
    SELECT
        trim(split_part(name_raw, '||', 1))                   AS name_raw,
        org_canon(name_raw)                                   AS name_norm,
        -- canonical org type (fixes typos/dupes seen in the data)
        CASE lower(trim(coalesce(type_raw,'')))
            WHEN 'central govt. ministry/department' THEN 'Central'
            WHEN 'public sector undertakings'        THEN 'PSU'
            WHEN 'public sector banks'               THEN 'Bank'
            WHEN 'state govt. and ut'                THEN 'State'
            WHEN 'state government'                  THEN 'State'
            WHEN 'autonomous bos'                    THEN 'Autonomous Body'
            WHEN 'autonomous bodies'                 THEN 'Autonomous Body'
            WHEN 'statutory bos'                     THEN 'Statutory Body'
            WHEN 'statutory bodies'                  THEN 'Statutory Body'
            WHEN 'other govt. organization'          THEN 'Other'
            WHEN ''                                  THEN NULL
            ELSE trim(type_raw)
        END                                                    AS org_type,
        portal_type
    FROM src
    WHERE name_raw IS NOT NULL
)
SELECT
    surrogate(name_norm)                                       AS org_id,
    any_value(name_raw)                                        AS org_name_raw,
    name_norm,
    -- pick the most frequent non-null org_type per org
    mode(org_type)                                             AS org_type,
    CASE
        WHEN mode(org_type) IN ('Central')              THEN 'central'
        WHEN mode(org_type) IN ('State')                THEN 'state'
        WHEN mode(org_type) IN ('PSU')                  THEN 'psu'
        WHEN mode(org_type) IN ('Bank')                 THEN 'bank'
        WHEN max(portal_type) = 'central'               THEN 'central'
        WHEN max(portal_type) = 'state'                 THEN 'state'
        ELSE 'other'
    END                                                        AS govt_level
FROM norm
GROUP BY name_norm;

-- ----------------------------------------------------------------------------
-- DIM: vendor  (winners from awards). name_norm = entity-resolution key.
-- NOTE: this is the deterministic SQL pass (strip legal tokens). The fuzzy
-- clustering pass (rapidfuzz) runs separately in Python over this table.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_vendor AS
WITH v AS (
    SELECT DISTINCT winner_name_raw AS name_raw, winner_addr_raw AS addr_raw
    FROM stg_award
    WHERE winner_name_raw IS NOT NULL
),
norm AS (
    SELECT
        name_raw,
        addr_raw,
        trim(regexp_replace(                       -- collapse leftover spaces
            regexp_replace(                        -- drop legal prefixes/suffixes
                regexp_replace(lower(name_raw), '[^a-z0-9 ]', ' ', 'g'),
            '\b(m s|m/s|messrs|pvt|private|ltd|limited|llp|inc|co|company|and co|enterprises|enterprise|constructions|construction|industries|india|the)\b', ' ', 'g'),
        '\s+', ' ', 'g'))                          AS name_norm
    FROM v
)
SELECT
    surrogate(name_norm)                           AS vendor_id,
    any_value(name_raw)                            AS name_raw,
    name_norm,
    any_value(addr_raw)                            AS address_raw,
    md5(lower(coalesce(any_value(addr_raw),'')))   AS address_hash
FROM norm
WHERE name_norm <> ''
GROUP BY name_norm;

-- ----------------------------------------------------------------------------
-- FACT: award
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_award AS
SELECT
    a.internal_id,
    a.tender_id,
    a.ref_no,
    -- best searchable identifier: standard CPPP Tender ID, else the Reference No.
    CASE WHEN std_tid(a.tender_id) THEN a.tender_id ELSE a.ref_no END         AS portal_id,
    CASE WHEN std_tid(a.tender_id) THEN 'Tender ID'
         WHEN a.ref_no IS NOT NULL THEN 'Reference Number' ELSE 'none' END    AS portal_id_kind,
    a.source_url,
    a.portal_type,
    o.org_id,
    ve.vendor_id,
    a.title,
    a.description,
    -- normalized tender type; numeric leakage (column-shift) -> NULL + flag
    CASE lower(trim(coalesce(a.tender_type_raw,'')))
        WHEN 'works'    THEN 'Works'
        WHEN 'goods'    THEN 'Goods'
        WHEN 'services' THEN 'Services'
        WHEN 'limited'  THEN 'Limited'
        WHEN 'open'     THEN 'Open'
        WHEN ''         THEN NULL
        ELSE CASE WHEN regexp_full_match(trim(a.tender_type_raw), '[0-9]+')
                  THEN NULL ELSE trim(a.tender_type_raw) END
    END                                                        AS tender_type,
    regexp_full_match(trim(coalesce(a.tender_type_raw,'x')), '[0-9]+') AS misaligned_scrape,
    a.contract_value_raw,                                     -- raw string, for the DQ page + tiering
    money(a.contract_value_raw)                                AS contract_value_inr,
    value_quality(a.contract_value_raw)                        AS value_quality,
    a.bids_received,
    a.published_at,
    a.contract_at,
    a.closing_at,
    a.award_year,
    a.scraped_at,
    a.has_detail,
    -- data-quality exclusion flag: TRUE for the tiers we keep OUT of money totals.
    -- Strict superset of the old rule (now also excludes junk_sequence).
    (value_quality(a.contract_value_raw)
        IN ('missing','too_small','junk_magnitude','junk_sequence'))  AS value_is_suspect,
    a.winner_name_raw,
    a.winner_addr_raw
FROM stg_award a
LEFT JOIN dim_org    o  ON o.name_norm  = org_canon(a.org_name_raw)
LEFT JOIN dim_vendor ve ON ve.name_raw = a.winner_name_raw
-- DE-DUPLICATION: the source scrape captured many awards more than once (same
-- record, different internal_id and scrape time). Keep ONE row per genuine award,
-- keyed on the full identifying content, preferring the row that has detail and the
-- latest scrape. This is the single dedup point: flag_award, the 04 summaries, and
-- the 08/10 hierarchies all derive from fact_award by internal_id, so they inherit it.
QUALIFY row_number() OVER (
    PARTITION BY a.org_name_raw, a.tender_id, a.ref_no, a.title,
                 a.winner_name_raw, a.contract_value_raw, a.contract_at, a.bids_received
    ORDER BY a.has_detail DESC, a.scraped_at DESC, a.internal_id
) = 1;

-- ----------------------------------------------------------------------------
-- FACT: tender notice
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_tender AS
SELECT
    t.internal_id,
    t.tender_id,
    t.source_url,
    t.status,
    o.org_id,
    t.title,
    t.work_description,
    trim(nullif(trim(coalesce(t.tender_category,'')),'')) AS tender_category,
    CASE lower(trim(coalesce(t.tender_type_raw,'')))
        WHEN 'works'    THEN 'Works'
        WHEN 'goods'    THEN 'Goods'
        WHEN 'services' THEN 'Services'
        WHEN 'limited'  THEN 'Limited'
        WHEN 'open/advertised' THEN 'Open'
        WHEN 'open'     THEN 'Open'
        WHEN ''         THEN NULL
        ELSE trim(t.tender_type_raw)
    END                                                       AS tender_type,
    t.product_category,
    t.product_subcat,
    t.location,
    t.emd_inr,
    t.tender_fee_inr,
    t.epublished_at,
    t.bid_open_at,
    t.bid_start_at,
    t.bid_end_at,
    t.doc_dl_start_at,
    t.doc_dl_end_at,
    t.has_corrigendum,
    t.scraped_at,
    t.has_detail,
    -- bid window length in days (publish -> submission close)
    date_diff('day', t.epublished_at, t.bid_end_at)           AS bid_window_days
FROM stg_tender t
LEFT JOIN dim_org o ON o.name_norm = org_canon(t.org_name_raw);

-- ----------------------------------------------------------------------------
-- DERIVED: red-flag table (award joined to its tender notice by tender_id)
-- Flags are STATISTICAL INDICATORS, not accusations.
-- ----------------------------------------------------------------------------
-- IMPORTANT: tender_id is NOT unique in fact_tender (blank/duplicate ids), so a
-- naive join fans out into billions of rows. Collapse the notice side to ONE row
-- per non-blank tender_id first → exactly one flag row per award.
CREATE OR REPLACE TABLE flag_award AS
WITH notice AS (
    SELECT tender_id, bid_window_days, emd_inr, tender_fee_inr, has_corrigendum
    FROM (
        SELECT *,
               row_number() OVER (PARTITION BY tender_id
                                  ORDER BY has_detail DESC, epublished_at) AS rn
        FROM fact_tender
        WHERE tender_id IS NOT NULL AND tender_id <> ''
    ) WHERE rn = 1
)
SELECT
    a.internal_id,
    a.tender_id,
    a.org_id,
    a.vendor_id,
    (a.bids_received = 1)                                      AS f_single_bid,
    (a.bids_received = 0)                                      AS f_zero_bid,
    a.value_is_suspect                                        AS f_value_suspect,
    (n.bid_window_days IS NOT NULL AND n.bid_window_days < 7)  AS f_short_window,
    (a.contract_value_inr > 1e6
        AND n.emd_inr IS NOT NULL
        AND n.emd_inr < a.contract_value_inr * 0.005)         AS f_low_emd,
    (n.tender_fee_inr > 10000)                                AS f_high_fee,
    coalesce(n.has_corrigendum, FALSE)                        AS f_corrigendum,
    -- weighted composite risk score. Every term is coalesced to FALSE so a NULL
    -- (e.g. unmatched notice -> NULL emd/fee, or unknown bid count) cannot poison
    -- the whole sum into NULL.
    ( coalesce(a.bids_received = 1, FALSE)::INT * 3
    + coalesce(a.bids_received = 0, FALSE)::INT * 2
    + (n.bid_window_days IS NOT NULL AND n.bid_window_days < 7)::INT * 2
    + (a.contract_value_inr > 1e6 AND n.emd_inr IS NOT NULL
         AND n.emd_inr < a.contract_value_inr * 0.005)::INT * 2
    + coalesce(n.tender_fee_inr > 10000, FALSE)::INT * 1
    + coalesce(n.has_corrigendum, FALSE)::INT * 1
    )                                                         AS risk_score
FROM fact_award a
LEFT JOIN notice n
  ON a.tender_id IS NOT NULL AND a.tender_id <> '' AND n.tender_id = a.tender_id;

-- ----------------------------------------------------------------------------
-- EXPORT to Parquet (the portable, public-ready release artifacts)
-- ----------------------------------------------------------------------------
COPY dim_org     TO 'data/dim_org.parquet'     (FORMAT parquet);
COPY dim_vendor  TO 'data/dim_vendor.parquet'  (FORMAT parquet);
COPY fact_award  TO 'data/fact_award.parquet'  (FORMAT parquet);
COPY fact_tender TO 'data/fact_tender.parquet' (FORMAT parquet);
COPY flag_award  TO 'data/flag_award.parquet'  (FORMAT parquet);

-- ----------------------------------------------------------------------------
-- DATA-QUALITY REPORT (publish this for transparency)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE dq_report AS
SELECT 'fact_award'  AS tbl, 'rows'              AS metric, count(*)::BIGINT v FROM fact_award
UNION ALL SELECT 'fact_award','has_detail',         count(*) FILTER (WHERE has_detail)        FROM fact_award
UNION ALL SELECT 'fact_award','value_suspect',      count(*) FILTER (WHERE value_is_suspect)  FROM fact_award
UNION ALL SELECT 'fact_award','misaligned_scrape',  count(*) FILTER (WHERE misaligned_scrape) FROM fact_award
UNION ALL SELECT 'fact_award','null_value',         count(*) FILTER (WHERE contract_value_inr IS NULL) FROM fact_award
UNION ALL SELECT 'fact_award','null_bids',          count(*) FILTER (WHERE bids_received IS NULL)       FROM fact_award
UNION ALL SELECT 'flag_award','single_bid',         count(*) FILTER (WHERE f_single_bid)      FROM flag_award
UNION ALL SELECT 'fact_tender','rows',              count(*)                                  FROM fact_tender
UNION ALL SELECT 'fact_tender','has_detail',        count(*) FILTER (WHERE has_detail)        FROM fact_tender
UNION ALL SELECT 'fact_tender','short_window',      count(*) FILTER (WHERE bid_window_days < 7) FROM fact_tender
UNION ALL SELECT 'dim_vendor','rows',               count(*)                                  FROM dim_vendor
UNION ALL SELECT 'dim_org','rows',                  count(*)                                  FROM dim_org;

COPY dq_report TO 'data/dq_report.parquet' (FORMAT parquet);
SELECT * FROM dq_report ORDER BY tbl, metric;
