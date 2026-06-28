-- ============================================================================
-- 05_normalize_org.sql: collapse duplicate organisation spellings.
-- Operates on the existing clean Parquet (no JSON re-parse). Rebuilds org_id
-- from a canonicalized name, remaps the fact/flag tables, writes *_new.parquet
-- (a PowerShell step then swaps them in, and 04_build_summary.sql is rerun).
-- ============================================================================

-- canonical org name: collapse '||' sub-unit hierarchy to the top-level body,
-- lowercase, whitespace-collapsed, known-typo aliases merged.
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

-- crosswalk: old org_id -> canonical org_id (display = clean top-level name)
CREATE OR REPLACE TEMP TABLE xwalk AS
SELECT org_id                                     AS old_id,
       md5(org_canon(org_name_raw))               AS new_id,
       org_canon(org_name_raw)                    AS new_norm,
       trim(split_part(org_name_raw, '||', 1))    AS display_name,
       org_type, govt_level
FROM 'data/dim_org.parquet';

-- new dim_org (one row per canonical top-level org)
COPY (
  SELECT new_id                 AS org_id,
         any_value(display_name) AS org_name_raw,
         new_norm               AS name_norm,
         mode(org_type)         AS org_type,
         mode(govt_level)       AS govt_level
  FROM xwalk GROUP BY new_id, new_norm
) TO 'data/dim_org_new.parquet' (FORMAT parquet);

-- remap org_id in the three big tables
COPY (SELECT a.* REPLACE (x.new_id AS org_id)
      FROM 'data/fact_award.parquet'  a LEFT JOIN xwalk x ON x.old_id = a.org_id)
  TO 'data/fact_award_new.parquet'  (FORMAT parquet);

COPY (SELECT t.* REPLACE (x.new_id AS org_id)
      FROM 'data/fact_tender.parquet' t LEFT JOIN xwalk x ON x.old_id = t.org_id)
  TO 'data/fact_tender_new.parquet' (FORMAT parquet);

COPY (SELECT f.* REPLACE (x.new_id AS org_id)
      FROM 'data/flag_award.parquet'  f LEFT JOIN xwalk x ON x.old_id = f.org_id)
  TO 'data/flag_award_new.parquet'  (FORMAT parquet);

-- report the merge effect
SELECT (SELECT count(*) FROM 'data/dim_org.parquet')     AS orgs_before,
       (SELECT count(*) FROM 'data/dim_org_new.parquet') AS orgs_after;
