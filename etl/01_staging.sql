-- ============================================================================
-- 01_staging.sql: Tender Watch ETL, stage 1: raw SQLite -> typed staging
-- ----------------------------------------------------------------------------
-- Reads the two scraped SQLite DBs READ-ONLY and explodes their JSON detail
-- blobs into flat, typed staging views. No source mutation. No data dropped
-- here, only parsed/typed. Junk is KEPT and FLAGGED downstream (02_clean.sql).
--
-- Run:   duckdb tender_watch.duckdb -init etl/01_staging.sql
-- (or)   duckdb tender_watch.duckdb < etl/01_staging.sql
-- ============================================================================

INSTALL sqlite; LOAD sqlite;
INSTALL json;   LOAD json;

-- Adjust these two paths if you move the DBs ------------------------------------
ATTACH 'aoc_tenders.db'  AS aoc (TYPE sqlite, READ_ONLY);
ATTACH 'tenders_vps.db'  AS vps (TYPE sqlite, READ_ONLY);

-- ----------------------------------------------------------------------------
-- Reusable text-cleaning macros (HTML noise, currency, dates, integers)
-- ----------------------------------------------------------------------------
-- Strip the HTML/entity artifacts seen in the data (&ampamp#x0d, &amp;, CR/LF)
-- and collapse whitespace. Returns NULL for empty/whitespace-only strings.
CREATE OR REPLACE MACRO clean_text(s) AS
  nullif(
    trim(
      regexp_replace(
        regexp_replace(coalesce(s,''), '&[a-z]*amp[a-z]*#?x?[0-9a-fA-F]*;?', ' ', 'g'),
      '\s+', ' ', 'g')
    ),
  '');

-- '₹ 20441' / '₹ 20,441' / '1874075' / '4263176.4'  ->  DECIMAL
-- Keeps digits and a single decimal point; empty -> NULL.
CREATE OR REPLACE MACRO money(s) AS
  try_cast(
    nullif(regexp_replace(coalesce(s,''), '[^0-9.]', '', 'g'), '')
  AS DECIMAL(18,2));

-- 'DD-Mon-YYYY hh:mm AM/PM'  ->  TIMESTAMP  (NULL on any parse failure)
CREATE OR REPLACE MACRO ts(s) AS
  try_strptime(nullif(trim(coalesce(s,'')), ''), '%d-%b-%Y %I:%M %p');

-- clean integer (bids, etc.); non-numeric / empty -> NULL
CREATE OR REPLACE MACRO whole(s) AS
  try_cast(nullif(regexp_replace(coalesce(s,''), '[^0-9]', '', 'g'), '') AS INTEGER);

-- digits-only integer part of a money string ('INR 1,23,456.50' -> '123456')
CREATE OR REPLACE MACRO cv_intpart(s) AS
  split_part(regexp_replace(coalesce(s,''), '[^0-9.]', '', 'g'), '.', 1);

-- Tiered contract-value quality label. These are SOURCE DATA-QUALITY tiers, not
-- accusations. junk_* are clerical/placeholder errors and are excluded from money
-- totals (via value_is_suspect, see 02_clean.sql). review/suspect are KEPT in totals
-- but surfaced on the Data Quality page. See docs/superpowers/plans/2026-06-29-value-anomaly-data-quality.md
--   missing/too_small : no usable value
--   junk_magnitude    : over 1e11 (INR 10,000 cr), physically implausible
--   junk_sequence     : contains the sequential placeholder run '1234567'/'12345678'
--   review            : over 1e10 (INR 1,000 cr), plausible-but-large, needs a human eye
--   suspect_placeholder: value is exactly 123456 / 1123456 / a single repeated digit
CREATE OR REPLACE MACRO value_quality(s) AS
  CASE
    WHEN money(s) IS NULL                           THEN 'missing'
    WHEN money(s) < 100                             THEN 'too_small'
    WHEN money(s) > 1e11                            THEN 'junk_magnitude'
    WHEN regexp_matches(coalesce(s,''), '1234567')  THEN 'junk_sequence'
    WHEN money(s) > 1e10                            THEN 'review'
    WHEN regexp_matches(cv_intpart(s), '^1?123456$')
      OR ( length(cv_intpart(s)) >= 6
           AND cv_intpart(s) = repeat(left(cv_intpart(s),1), length(cv_intpart(s))) )
                                                    THEN 'suspect_placeholder'
    ELSE 'clean'
  END;

-- deterministic surrogate key from a normalized string
CREATE OR REPLACE MACRO surrogate(s) AS md5(coalesce(s,''));

-- canonical org key: collapse '||' sub-unit hierarchy to top-level body,
-- lowercase + whitespace-collapse + merge known spelling variants.
CREATE OR REPLACE MACRO org_canon(s) AS (
  CASE regexp_replace(lower(trim(split_part(coalesce(s,''), '||', 1))), '\s+', ' ', 'g')
    WHEN 'telegana'    THEN 'telangana'
    WHEN 'telengana'   THEN 'telangana'
    WHEN 'orissa'      THEN 'odisha'
    WHEN 'pondicherry' THEN 'puducherry'
    WHEN 'uttaranchal' THEN 'uttarakhand'
    WHEN 'chattisgarh' THEN 'chhattisgarh'
    ELSE regexp_replace(lower(trim(split_part(coalesce(s,''), '||', 1))), '\s+', ' ', 'g')
  END
);

-- a standard CPPP tender id looks like  YYYY_ORG_NNNNN_N ; otherwise the field is
-- a scrape counter / junk and the Reference Number is the searchable identifier.
CREATE OR REPLACE MACRO std_tid(x) AS regexp_matches(coalesce(x,''), '^(19|20)[0-9]{2}_[A-Za-z]');

-- ============================================================================
-- STAGING TABLE: awards  (aoc_tenders ⨝ aoc_details)
-- Materialized (TABLE not VIEW) so the expensive JSON parse runs ONCE, not
-- every time a downstream query references it.
-- ============================================================================
CREATE OR REPLACE TABLE stg_award AS
SELECT
    t.internal_id,
    t.tender_id,
    replace(t.detail_url, 'A13h1', '/')                       AS source_url,  -- fix mangled path delimiter
    t.portal_type,
    t.year                                                   AS award_year,
    clean_text(t.title)                                      AS title,
    clean_text(t.org_name)                                   AS org_name_raw,

    -- detail JSON (may be absent: LEFT JOIN)
    clean_text(json_extract_string(d.details_json, '$."Tender Description"'))           AS description,
    json_extract_string(d.details_json, '$."Tender Type"')                              AS tender_type_raw,
    json_extract_string(d.details_json, '$."Contract Value"')                           AS contract_value_raw,
    whole(json_extract_string(d.details_json, '$."Number of bids received"'))           AS bids_received,
    clean_text(json_extract_string(d.details_json, '$."Name of the selected bidder(s)"'))     AS winner_name_raw,
    clean_text(json_extract_string(d.details_json, '$."Address of the selected bidder(s)"'))  AS winner_addr_raw,
    clean_text(json_extract_string(d.details_json, '$."Organisation Name"'))            AS org_name_detail,
    nullif(trim(coalesce(json_extract_string(d.details_json, '$."Tender Ref. No."'), t.ref_no, '')), '') AS ref_no,

    ts(json_extract_string(d.details_json, '$."Published Date"'))                       AS published_at,
    ts(json_extract_string(d.details_json, '$."Contract Date"'))                        AS contract_at,
    ts(t.closing_date)                                                                  AS closing_at,
    d.scraped_at,
    (d.internal_id IS NOT NULL)                                                         AS has_detail,
    d.details_json                                                                      AS raw_json
FROM aoc.aoc_tenders  t
LEFT JOIN aoc.aoc_details d ON d.internal_id = t.internal_id;

-- ============================================================================
-- STAGING TABLE: tenders  (tenders ⨝ tender_details), materialized, see above
-- ============================================================================
CREATE OR REPLACE TABLE stg_tender AS
SELECT
    t.internal_id,
    t.tender_id,
    replace(t.detail_url, 'A13h1', '/')                      AS source_url,  -- fix mangled path delimiter
    t.status,
    t.portal_type,
    clean_text(t.title)                                      AS title,
    clean_text(t.organisation_name)                          AS org_name_raw,
    clean_text(t.corrigendum_url) IS NOT NULL                AS has_corrigendum,

    clean_text(json_extract_string(d.details_json, '$."Work Description"'))   AS work_description,
    json_extract_string(d.details_json, '$."Tender Category"')                AS tender_category,
    json_extract_string(d.details_json, '$."Tender Type"')                    AS tender_type_raw,
    json_extract_string(d.details_json, '$."Organisation Type"')              AS org_type_raw,
    clean_text(json_extract_string(d.details_json, '$."Product Category"'))   AS product_category,
    clean_text(json_extract_string(d.details_json, '$."Product Sub-Category"')) AS product_subcat,
    clean_text(json_extract_string(d.details_json, '$."Location"'))           AS location,

    money(json_extract_string(d.details_json, '$."EMD"'))                     AS emd_inr,
    money(json_extract_string(d.details_json, '$."Tender Fee"'))              AS tender_fee_inr,

    -- prefer detail dates, fall back to listing dates
    coalesce(ts(json_extract_string(d.details_json, '$."ePublished Date"')), ts(t.e_published_date))             AS epublished_at,
    coalesce(ts(json_extract_string(d.details_json, '$."Bid Opening Date"')), ts(t.tender_opening_date))         AS bid_open_at,
    ts(json_extract_string(d.details_json, '$."Bid Submission Start Date"'))                                     AS bid_start_at,
    coalesce(ts(json_extract_string(d.details_json, '$."Bid Submission End Date"')), ts(t.bid_submission_closing_date)) AS bid_end_at,
    ts(json_extract_string(d.details_json, '$."Document Download Start Date"'))                                  AS doc_dl_start_at,
    ts(json_extract_string(d.details_json, '$."Document Download End Date"'))                                    AS doc_dl_end_at,

    t.scraped_at,
    (d.internal_id IS NOT NULL)                                               AS has_detail,
    d.details_json                                                            AS raw_json
FROM vps.tenders t
LEFT JOIN vps.tender_details d ON d.internal_id = t.internal_id;
