-- tests/test_value_anomaly_artifacts.sql
-- Run after a full rebuild. Asserts the DQ artifacts exist and are well-formed.
-- Run: duckdb :memory: ".read tests/test_value_anomaly_artifacts.sql"   (expects all rows PASS)
WITH checks AS (
  SELECT 'sum_value_quality has all clean+anomaly tiers' AS check_name,
         (SELECT count(DISTINCT value_quality) FROM 'data/sum_value_quality.parquet') >= 5 AS ok
  UNION ALL
  SELECT 'sum_value_anomaly only holds the 4 anomaly tiers',
         (SELECT count(*) FROM 'data/sum_value_anomaly.parquet'
          WHERE value_quality NOT IN ('junk_magnitude','junk_sequence','review','suspect_placeholder')) = 0
  UNION ALL
  SELECT 'junk fixture 2021_UAD_167291_1 is present and junk',
         (SELECT count(*) FROM 'data/sum_value_anomaly.parquet'
          WHERE portal_id = '2021_UAD_167291_1' AND value_quality LIKE 'junk%') >= 1
  UNION ALL
  SELECT 'no junk value leaks into the overview total',
         (SELECT count(*) FROM 'data/fact_award.parquet'
          WHERE value_quality IN ('junk_magnitude','junk_sequence') AND NOT value_is_suspect) = 0
)
SELECT check_name AS check, ok, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result
FROM checks ORDER BY result, check_name;
