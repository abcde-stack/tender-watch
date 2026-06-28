-- ============================================================================
-- 11_mca_crosswalk.sql: link procurement winners (dim_vendor) to MCA companies.
-- Builds a dedicated match key (strip leading M/s + legal-form suffixes, keep
-- descriptive words), exact-matches both sides, and reports coverage.
-- Fuzzy matching (rapidfuzz) is a later Python stage for the remainder.
--   duckdb :memory: ".read etl/11_mca_crosswalk.sql"
-- ============================================================================

-- match key: lower -> strip leading "M/s" -> punctuation to space -> collapse
--            -> strip legal-form tokens (Pvt/Ltd/Co/LLP...) -> collapse
CREATE OR REPLACE MACRO mnorm(x) AS
  nullif(trim(regexp_replace(
    regexp_replace(
      regexp_replace(
        regexp_replace(
          regexp_replace(lower(coalesce(x,'')),
            '^\s*m\s*[/.]?\s*s[.,]?\s+', '', 'g'),               -- drop leading M/s
          '[^a-z0-9 ]', ' ', 'g'),                              -- punctuation -> space
        '\s+', ' ', 'g'),                                       -- collapse
      '\b(private limited|pvt ltd|pvt limited|private ltd|p ltd|opc|llp|limited|ltd|pvt|private|company|co|corporation|corp|incorporated|inc)\b', ' ', 'g'),
    '\s+', ' ', 'g')), '');                                     -- collapse + trim

-- MCA side: one representative company per normalized name (prefer active/newest),
-- and how many companies share that name (ambiguity).
CREATE OR REPLACE TABLE mca_norm AS
SELECT * EXCLUDE (rn) FROM (
  SELECT mnorm(COMPANY_NAME)                          AS nm,
         CORPORATE_IDENTIFICATION_NUMBER             AS cin,
         COMPANY_NAME                                AS company_name,
         COMPANY_STATUS                              AS status,
         DATE_OF_REGISTRATION                        AS reg_date,
         REGISTERED_STATE                            AS reg_state,
         PAIDUP_CAPITAL                              AS paidup_capital,
         count(*)      OVER (PARTITION BY mnorm(COMPANY_NAME))                        AS mca_namesakes,
         row_number()  OVER (PARTITION BY mnorm(COMPANY_NAME)
                             ORDER BY (COMPANY_STATUS='ACTV') DESC, DATE_OF_REGISTRATION DESC) AS rn
  FROM read_csv_auto('registered_companies.csv')
  WHERE mnorm(COMPANY_NAME) IS NOT NULL
) WHERE rn = 1;

-- vendor side
CREATE OR REPLACE TABLE vend AS
SELECT vendor_id, name_raw, mnorm(name_raw) AS nm
FROM 'data/dim_vendor.parquet'
WHERE mnorm(name_raw) IS NOT NULL;

-- exact-match crosswalk
COPY (
  SELECT v.vendor_id, v.name_raw, m.cin, m.company_name, m.status,
         m.reg_date, m.reg_state, m.paidup_capital, m.mca_namesakes,
         'exact' AS match_type
  FROM vend v JOIN mca_norm m ON m.nm = v.nm
) TO 'data/vendor_cin.parquet' (FORMAT parquet);

-- coverage report
SELECT 'vendors total' m, count(*) v FROM 'data/dim_vendor.parquet'
UNION ALL SELECT 'vendors matched (exact)', count(DISTINCT vendor_id) FROM 'data/vendor_cin.parquet'
UNION ALL SELECT 'matched - unambiguous (1 namesake)', count(*) FILTER (WHERE mca_namesakes=1) FROM 'data/vendor_cin.parquet'
UNION ALL SELECT 'matched - STRUCK OFF / dead', count(*) FILTER (WHERE status IN ('STOF','UPSO','ULQD','AMAL','DISD','CLLD')) FROM 'data/vendor_cin.parquet';
