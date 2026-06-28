-- Orchestrator: runs the full ETL in one session.
--   cd /path/to/tender-watch
--   duckdb tender_watch.duckdb < etl/run.sql
.read etl/01_staging.sql
.read etl/02_clean.sql
