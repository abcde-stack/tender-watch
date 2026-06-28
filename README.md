# Tender Watch

Tender Watch is an open source data pipeline and dashboard that turns India's
Central Public Procurement Portal (CPPP) data into a clean, typed, queryable
dataset and surfaces statistical red flags in public procurement, such as single
bid awards, vendor concentration, short bid windows, and contracts won by
companies whose corporate records raise questions.

> Flags are statistical indicators, not accusations of wrongdoing. They mark
> contracts worth a closer human look, nothing more. Every figure can be traced
> back to a Tender ID or Reference Number on the official portal. Please read the
> [disclaimer and corrections policy](DISCLAIMER.md) before relying on anything here.

---

## Table of contents

1. What this does
2. Features
3. How it works (architecture)
4. Data model
5. Red flags
6. Prerequisites
7. Step by step setup
8. Building the dataset
9. Running the dashboard
10. Refreshing or rebuilding the data
11. Deployment options
12. Known limitations
13. Data source and record lookup
14. Project structure
15. License

---

## 1. What this does

Most large scale procurement irregularity is not hidden. It is just tedious to
find across millions of notices. This project removes the tedium. It cleans the
raw scraped data once, then gives journalists, researchers, and citizens a fast
way to ask questions like "who keeps winning, with no competition, from whom, and
are those winners even real, active companies".

The source is two scraped SQLite databases (awards and tender notices) which are a
public mirror of the CPPP portal. The pipeline normalizes and types that data into
Parquet files, and a Streamlit dashboard reads those files directly through DuckDB.

---

## 2. Features

The dashboard has the following pages:

- **Overview.** Headline counts (awards, notices, total value, single bid share),
  awards and value by year, the single bid trend, red flag totals, a risk score
  distribution, and a fiscal year-end (March) clustering chart with a year selector.
- **Red flag explorer.** Filter awards by flag, risk score, year, and organisation.
  Export the result to CSV.
- **States.** Rank states by single bid percentage, awards, or value, with a top
  states bar chart and an India choropleth map. Drill from a state into its procuring
  units (departments) and then into individual awards.
- **Central.** Rank central organisations (ministries, public sector undertakings,
  banks, autonomous bodies), with a value disclosed percentage so non disclosing
  bodies are visible, plus a single bid percentage by organisation type chart. Drill
  from an organisation into its sub units and awards.
- **Vendors.** A winner leaderboard plus a vendor drill down with an awards over time
  chart. The drill down can show a corporate identity card built from a name match
  against the Ministry of Corporate Affairs (MCA) registered company data, with all
  the appropriate hedging.
- **Departments.** An organisation scorecard with a vendor concentration index (HHI,
  by award count and by value) and a concentration versus competition scatter, plus
  an organisation drill down with an awards over time chart.
- **Search.** Keyword search over award and notice titles and descriptions.
- **Methodology.** Plain language definitions of every flag and metric, the known
  limitations, the disclaimer and corrections policy, and how to verify a record.

Every table can be exported to CSV, and every award row carries a Tender ID or
Reference Number for lookup on the official portal.

---

## 3. How it works (architecture)

```
  raw SQLite (aoc_tenders.db, tenders_vps.db)
        |
        |  DuckDB reads SQLite directly, parses JSON, types and normalizes
        v
  cleaned Parquet in data/  (fact_award, fact_tender, dim_org, dim_vendor,
        |                    flag_award, sum_*, state_*, central_*, vendor_cin)
        v
  Streamlit dashboard (app/dashboard.py) queries the Parquet through DuckDB
```

Key points:

- **DuckDB is the engine.** It reads the SQLite source directly (no migration
  needed) and later queries the Parquet files. Aggregates over millions of rows
  return in well under a second.
- **Parquet is the storage.** The cleaned tables are columnar and compressed, a few
  gigabytes in total. No database server is required.
- **Streamlit is the interface.** Small precomputed summary files load instantly,
  while drill downs query the large fact and flag files live.

---

## 4. Data model

| Table | Grain | Notes |
|---|---|---|
| `fact_award` | one row per award (about 3.47 million, after de-duplicating re-scraped rows) | typed `contract_value_inr`, `bids_received`, dates, a `value_is_suspect` flag, and `portal_id` (the searchable identifier) |
| `fact_tender` | one row per notice (about 3.95 million) | typed `emd_inr`, `tender_fee_inr`, computed `bid_window_days` |
| `dim_vendor` | resolved winners (about 862 thousand) | normalized name key, address hash for clustering |
| `dim_org` | organisations (about 3,272) | sub unit hierarchy collapsed to the top level body, with organisation type and government level |
| `flag_award` | one row per award | seven boolean flags plus a weighted `risk_score` |
| `sum_*` | precomputed aggregates | per state, per central org, per vendor, per org (with vendor-concentration HHI by count and value), per year, per month, and a risk-score distribution |
| `state_award`, `central_award` | hierarchy maps | award to procuring unit or sub unit |
| `vendor_cin` | crosswalk | vendor to MCA company (exact name match only) |

---

## 5. Red flags

Intrinsic flags (reliable for every award):

- `single_bid`: exactly one bid received.
- `zero_bid`: no bids recorded.
- `value_suspect`: contract value missing, zero, or implausible.

Notice linked flags (only fire for awards matched to a tender notice, so they
under state reality, see limitations):

- `short_window`: fewer than seven days from publication to bid close.
- `low_emd`: deposit under half a percent of a large contract value.
- `high_fee`: tender document fee over ten thousand rupees.
- `corrigendum`: the tender was amended after publication.

The `risk_score` is a weighted sum of these flags, computed in a null safe way so
that an unmatched notice cannot blank out the score.

---

## 6. Prerequisites

You need the following installed:

- **Python 3.11 or newer.**
- **DuckDB command line tool** (version 1.5 or newer). The Linux install command is in
  step 3 below.
- The Python packages in `requirements.txt` (DuckDB, Streamlit, pandas, Plotly,
  rapidfuzz).
- About 30 to 40 gigabytes of free disk space for the working DuckDB file and the
  Parquet outputs.
- The two source databases, `aoc_tenders.db` and `tenders_vps.db`, downloaded from
  the data source listed in section 13.
- Optional, for the MCA enrichment: the `registered_companies.csv` file of MCA
  registered companies.

---

## 7. Step by step setup

This section covers Linux. The build and run commands are the same on every operating
system, but the tool installation differs. **For Windows or macOS, follow
[docs/SETUP.md](docs/SETUP.md) instead**, which is written for non technical users and
covers installing Python and DuckDB step by step. Once your tools are installed, the
build and run sections below apply to you too.

**Step 1. Get the code.**

```
git clone https://github.com/abcde-stack/tender-watch.git
cd tender-watch
```

**Step 2. Install the Python packages.**

```
pip3 install -r requirements.txt
```

If you prefer an isolated environment, create a virtual environment first:
`python3 -m venv .venv` then `source .venv/bin/activate`, then run the install command
above.

**Step 3. Install the DuckDB command line tool.**

Official install script (installs to your home directory):

```
curl https://install.duckdb.org | sh
```

Alternatively, download the CLI binary from https://duckdb.org/docs/installation/, make
it executable with `chmod +x duckdb`, and move it onto your PATH (for example
`sudo mv duckdb /usr/local/bin/`).

After installing, open a new terminal so the `duckdb` command is found, and confirm it
works with `duckdb --version`.

**Step 4. Place the source data in the project root.**

Put all three files directly inside the `tender-watch` folder (the same folder that
holds `etl/` and `app/`):

- `aoc_tenders.db`
- `tenders_vps.db`
- `registered_companies.csv` (optional, only needed for the MCA enrichment)

The scripts reference these files by name relative to the project root, so there are
no paths to edit. These files are gitignored, so they are never committed. If you
prefer to keep the data elsewhere, edit the `ATTACH` lines near the top of
`etl/01_staging.sql`, `etl/08_state_hierarchy.sql`, and `etl/10_central_hierarchy.sql`,
and the `read_csv_auto` path in `etl/11_mca_crosswalk.sql`, to point at your location
(use forward slashes, which DuckDB accepts on every operating system).

The MCA file must be the Ministry of Corporate Affairs company master data from
data.gov.in (see [docs/PROVENANCE.md](docs/PROVENANCE.md) for the exact source). A
redacted 20 row sample showing the expected format is included at
[docs/registered_companies.sample.csv](docs/registered_companies.sample.csv) (the email
and address columns are blanked out). Your download should have the same header row;
save it as `registered_companies.csv` in the project root. The pipeline reads these
columns: `COMPANY_NAME`, `CORPORATE_IDENTIFICATION_NUMBER`, `COMPANY_STATUS`,
`DATE_OF_REGISTRATION`, `REGISTERED_STATE`, and `PAIDUP_CAPITAL`. The `EMAIL_ADDR`
column is never displayed or published.

---

## 8. Building the dataset

Run these commands from the project root, in order. The first one is the main
build and takes the longest. The rest read the Parquet output and are fast.

```
duckdb tender_watch.duckdb ".read etl/run.sql"
duckdb :memory: ".read etl/04_build_summary.sql"
duckdb :memory: ".read etl/06_dq_report.sql"
duckdb :memory: ".read etl/08_state_hierarchy.sql"
duckdb :memory: ".read etl/10_central_hierarchy.sql"
duckdb :memory: ".read etl/11_mca_crosswalk.sql"
```

What each step produces:

1. `run.sql` runs `01_staging.sql` then `02_clean.sql`. It parses the source JSON
   once into staging tables, then builds and writes the core Parquet files:
   `dim_org`, `dim_vendor`, `fact_award`, `fact_tender`, and `flag_award`.
2. `04_build_summary.sql` writes the small `sum_*` aggregates the dashboard loads
   instantly.
3. `06_dq_report.sql` writes a transparency report of row counts, coverage, and
   parse failure rates.
4. `08_state_hierarchy.sql` writes the state hierarchy and per state summaries.
5. `10_central_hierarchy.sql` writes the central hierarchy and per organisation
   summaries.
6. `11_mca_crosswalk.sql` writes the vendor to company crosswalk. Skip this step if
   you do not have the MCA CSV; the dashboard simply will not show the corporate
   identity card.

All outputs land in the `data/` folder. That folder, the source databases, the CSV,
and the working `tender_watch.duckdb` file are all excluded from git because they are
large.

Note on the numbered scripts: `run.sql`, `04`, `06`, `08`, `10`, and `11` are the
current build path. Scripts `03`, `05`, `07`, and `09` are earlier one time patches
whose logic is now folded into `01` and `02`. You do not need to run them on a
fresh build. They are kept for history.

---

## 9. Running the dashboard

```
streamlit run app/dashboard.py
```

Streamlit prints a local URL, by default `http://localhost:8501`. Open it in a
browser. The dashboard reads the Parquet files in `data/`, so once they are built
you can start and stop the dashboard freely without rebuilding anything.

To run it without opening a browser automatically, or on a fixed port:

```
streamlit run app/dashboard.py --server.headless true --server.port 8501
```

---

## 10. Refreshing or rebuilding the data

When you get a newer copy of the source databases, rebuild by running the same
sequence from section 8 again. The build is idempotent and overwrites the Parquet
files in place. After a rebuild, restart the dashboard so it drops any cached
query results.

---

## 11. Deployment options

The dashboard is a standard Streamlit app, but the data is several gigabytes and is
intentionally not committed to git, so deployment needs a plan for the data.

**Option A. Local use (simplest).**
Build the data and run `streamlit run app/dashboard.py` on your own machine. This is
the recommended way to work with it and needs no hosting.

**Option B. Self hosted server or virtual machine.**
Step-by-step Ubuntu VPS instructions (nginx, systemd, TLS): [docs/deploy.md](docs/deploy.md).

1. Provision a Linux virtual machine with Python 3.11 and enough disk (about 40 GB).
2. Copy the repository and the built `data/` folder to the machine.
3. Install the requirements with `pip install -r requirements.txt`.
4. Run `streamlit run app/dashboard.py --server.headless true --server.port 8501`.
5. Put a reverse proxy such as nginx in front of port 8501 for a clean domain and
   for TLS. Optionally run the Streamlit process under a service manager so it
   restarts automatically.

**Option C. Streamlit Community Cloud (free, with a data caveat).**
Streamlit Community Cloud deploys straight from a public GitHub repository, but it
will not have the large Parquet files because they are gitignored. To use it you
must make the data reachable in one of these ways:
- Reduce to the small summary Parquet files only and commit those (this disables
  the large drill downs but keeps the ranking pages working), or
- Host the Parquet files on object storage (for example S3 or Google Cloud Storage)
  and change the dashboard to read them over `https` using the DuckDB httpfs
  extension.
Treat this option as more involved than A or B because of the data hosting step.

Whichever option you choose, never deploy the raw MCA CSV publicly, because it
contains an email address field that is personal data.

---

## 12. Known limitations

Read these before drawing conclusions from any figure.

- **Award to notice linkage is about twenty four percent.** Only awards that match
  a tender notice get the notice linked flags, so those totals under state reality.
  The intrinsic flags cover all awards.
- **Value is missing or zero for many public sector undertakings.** These are
  flagged as value suspect and excluded from value totals and rankings, but kept for
  competition analysis. A value disclosed percentage is shown so a reporting gap is
  never mistaken for a real zero.
- **Vendor resolution is deterministic only.** Repeat winner counts are a lower
  bound, since a fuzzy pass would merge more name variants.
- **The MCA company match is by name only and probabilistic.** The corporate
  identity card is shown as a likely match to verify, only for unambiguous matches,
  and never as a confirmed link. Company status from MCA is a present day snapshot
  with no strike off date, so a current struck off status does not prove the company
  was inactive when it won.
- **Identifiers vary.** About seventy six percent of awards carry a standard CPPP
  Tender ID. The rest fall back to the Reference Number, and a small share have no
  usable identifier.
- **Some scraped fields show column misalignment** (about six percent of awards),
  which is flagged rather than dropped.
- **The source contained duplicate records.** About thirty percent of the raw rows were
  the same award scraped more than once. The pipeline de-duplicates them, so the figures
  reflect distinct awards (about 3.47 million, down from 4.92 million raw rows). A small
  residue (under one percent) of near-duplicates that have blank or missing identifiers
  is kept deliberately, to avoid wrongly merging genuinely separate awards, so totals may
  still be very slightly overstated.

---

## 13. Data source and record lookup

The two source SQLite databases (`aoc_tenders.db`, `tenders_vps.db`) are a public
mirror of the CPPP portal, available at https://tender.sarthaksidhant.com/.

To find a specific record on the official portal, use its Tender ID or Reference
Number shown in the dashboard:

- Award of Contract (AOC) results: https://eprocure.gov.in/cppp/resultoftendersnew/mmpdata
- Tenders: https://eprocure.gov.in/cppp/tendersearch/cpppdata/

Note that the portal's deep links to individual award pages are signed and expire,
so they cannot be permalinked. Searching by identifier is the reliable way to reach
the original record.

---

## 14. Project structure

```
tender-watch/
  app/
    dashboard.py            the Streamlit dashboard
    india_states.geojson    state boundaries for the choropleth map
  etl/
    01_staging.sql          raw SQLite to typed staging tables
    02_clean.sql            staging to dim_org, dim_vendor, fact_award, fact_tender, flag_award
    03_fix_flags.sql        legacy patch (logic folded into 02)
    04_build_summary.sql    precomputed sum_* aggregates
    05_normalize_org.sql    legacy patch (logic folded into 02)
    06_dq_report.sql        data quality and coverage report
    07_rebuild_flags.sql    legacy patch (logic folded into 02)
    08_state_hierarchy.sql  state hierarchy and per state summaries
    09_enrich_refno.sql     legacy patch (logic folded into 02)
    10_central_hierarchy.sql central hierarchy and per organisation summaries
    11_mca_crosswalk.sql    vendor to MCA company crosswalk
    run.sql                 orchestrates 01 and 02
  data/                     built Parquet (gitignored)
  docs/
    SETUP.md                beginner setup for Windows and macOS
    PROVENANCE.md           data sources, licensing, and open questions
    registered_companies.sample.csv   redacted 20 row MCA format sample
  DISCLAIMER.md             disclaimer and corrections policy
  README.md                 this file
  requirements.txt
  LICENSE
```

---

## 15. License

Code is released under the MIT License (see `LICENSE`). The underlying procurement
data is public information published by the Government of India via eprocure.gov.in.
The MCA registered company data is public information published by the Ministry of
Corporate Affairs. Handle the email address field in the MCA data as personal data
and do not republish it.

See [DISCLAIMER.md](DISCLAIMER.md) for the disclaimer and corrections policy, and
[docs/PROVENANCE.md](docs/PROVENANCE.md) for full data provenance and the open
licensing questions that must be confirmed before a public launch.
