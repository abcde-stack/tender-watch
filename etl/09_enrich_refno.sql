-- ============================================================================
-- 09_enrich_refno.sql: add ref_no + portal_id to fact_award.
-- Many tender_ids are bare scrape counters (not real CPPP IDs). Re-extract the
-- 'Tender Ref. No.' from the detail JSON and build portal_id = the best
-- searchable identifier: standard CPPP Tender ID when valid, else the Ref No.
-- Writes fact_award_new.parquet (PowerShell swaps it in).
-- ============================================================================
INSTALL sqlite; LOAD sqlite;
ATTACH 'aoc_tenders.db' AS aoc (TYPE sqlite, READ_ONLY);

-- standard CPPP tender id looks like  YYYY_ORG_NNNNN_N
CREATE OR REPLACE MACRO std_tid(x) AS regexp_matches(coalesce(x,''), '^(19|20)[0-9]{2}_[A-Za-z]');

COPY (
  SELECT fa.*,
         nullif(trim(coalesce(
            json_extract_string(d.details_json,'$."Tender Ref. No."'),
            t.ref_no, '')), '')                               AS ref_no,
         CASE
           WHEN std_tid(fa.tender_id) THEN fa.tender_id
           ELSE nullif(trim(coalesce(
                  json_extract_string(d.details_json,'$."Tender Ref. No."'),
                  t.ref_no, '')), '')
         END                                                  AS portal_id,
         CASE
           WHEN std_tid(fa.tender_id) THEN 'Tender ID'
           WHEN nullif(trim(coalesce(json_extract_string(d.details_json,'$."Tender Ref. No."'), t.ref_no, '')),'') IS NOT NULL
                THEN 'Reference Number'
           ELSE 'none'
         END                                                  AS portal_id_kind
  FROM 'data/fact_award.parquet' fa
  LEFT JOIN aoc.aoc_tenders t USING (internal_id)
  LEFT JOIN aoc.aoc_details d USING (internal_id)
) TO 'data/fact_award_new.parquet' (FORMAT parquet);

SELECT 'rows' m, count(*) v FROM 'data/fact_award_new.parquet'
UNION ALL SELECT portal_id_kind, count(*) FROM 'data/fact_award_new.parquet' GROUP BY portal_id_kind;
