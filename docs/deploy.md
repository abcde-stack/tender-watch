# Deploy Tender Watch on an Ubuntu VPS

This guide walks through hosting the Tender Watch dashboard on a Linux virtual
private server (VPS). It assumes **Ubuntu 22.04 or 24.04** and that you can SSH in
as a user with `sudo`.

The dashboard is a Streamlit app that reads pre-built Parquet files from the
`data/` folder. The heavy ETL build is a separate step and is optional on the VPS
itself.

---

## Table of contents

1. [Choose your deployment path](#1-choose-your-deployment-path)
2. [VPS sizing](#2-vps-sizing)
3. [Initial server setup](#3-initial-server-setup)
4. [Install Python and dependencies](#4-install-python-and-dependencies)
5. [Get the code](#5-get-the-code)
6. [Get the data onto the server](#6-get-the-data-onto-the-server)
7. [Path A: Build the dataset on the VPS (optional)](#7-path-a-build-the-dataset-on-the-vps-optional)
8. [Path B: Copy a pre-built data folder (recommended)](#8-path-b-copy-a-pre-built-data-folder-recommended)
9. [Run the dashboard manually (smoke test)](#9-run-the-dashboard-manually-smoke-test)
10. [Run the dashboard as a systemd service](#10-run-the-dashboard-as-a-systemd-service)
11. [Put nginx in front (HTTPS)](#11-put-nginx-in-front-https)
12. [Firewall](#12-firewall)
13. [Updating after a data rebuild](#13-updating-after-a-data-rebuild)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Choose your deployment path

| Path | When to use it |
|------|----------------|
| **A. Build on the VPS** | The VPS has **16 GB+ RAM** and **~40 GB** free disk. You download the raw SQLite files and run the DuckDB pipeline on the server. |
| **B. Copy pre-built data** | The VPS is smaller (e.g. 2–4 GB RAM). You build on a powerful machine locally, then upload only the `data/` folder. **This is the usual production approach.** |

Either way, day-to-day hosting only needs the app code, Python packages, and the
`data/` folder. You do **not** need the raw `aoc_tenders.db` / `tenders_vps.db`
files on the VPS if you already have Parquet outputs.

---

## 2. VPS sizing

| Role | RAM | CPU | Disk |
|------|-----|-----|------|
| **Dashboard only** | 2 GB minimum, **4 GB recommended** | 1+ cores | **20 GB+** (several GB for `data/`, plus OS and Python) |
| **Full build + dashboard** | **16 GB+** | 4+ cores helps | **40 GB+** |

A 1 GB RAM VPS is too small for reliable dashboard hosting and cannot run the
ETL build. See [docs/SETUP.md](SETUP.md) for build-time memory requirements.

---

## 3. Initial server setup

SSH into the VPS:

```bash
ssh your-user@your-server-ip
```

Update packages and install basics:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y git curl ufw
```

Install nginx and Let's Encrypt tooling (reverse proxy and HTTPS):

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

| Package | Purpose |
|---------|---------|
| `nginx` | Reverse proxy in front of Streamlit |
| `certbot` | Issues and renews TLS certificates from Let's Encrypt |
| `python3-certbot-nginx` | Certbot plugin that configures nginx for HTTPS automatically |

Confirm nginx is running:

```bash
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl status nginx
```

Create a dedicated system user (optional but recommended):

```bash
sudo adduser --disabled-password --gecos "" tenderwatch
sudo usermod -aG sudo tenderwatch   # skip if this user should not use sudo
```

The rest of this guide assumes the app lives at `/opt/tender-watch` and runs as
your normal SSH user. Adjust paths if you prefer `/home/your-user/tender-watch`.

---

## 4. Install Python and dependencies

Ubuntu 22.04 ships Python 3.10; Ubuntu 24.04 ships 3.12. Tender Watch needs
**Python 3.11 or newer**.

### Ubuntu 24.04 (Python 3.12 already installed)

```bash
python3 --version
sudo apt install -y python3-venv python3-pip
```

### Ubuntu 22.04 (install Python 3.11)

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip
```

Use `python3.11` instead of `python3` in the venv steps below on 22.04.

---

## 5. Get the code

```bash
sudo mkdir -p /opt/tender-watch
sudo chown "$USER":"$USER" /opt/tender-watch
cd /opt/tender-watch

git clone https://github.com/abcde-stack/tender-watch.git .
```

Create a virtual environment and install packages:

```bash
# On Ubuntu 22.04 with deadsnakes:
# python3.11 -m venv .venv

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Confirm Streamlit is available:

```bash
streamlit --version
```

---

## 6. Get the data onto the server

The dashboard reads Parquet files from `data/` at the project root. Without that
folder, pages will be empty or error.

Pick **Path A** (build on VPS) or **Path B** (upload pre-built data) in the
next sections.

---

## 7. Path A: Build the dataset on the VPS (optional)

Only follow this if the VPS has **16 GB+ RAM** and **~40 GB** free disk.

### 7.1 Install the DuckDB CLI

```bash
curl https://install.duckdb.org | sh
```

Add DuckDB to your PATH for this session (the installer prints the exact line;
typically):

```bash
export PATH="$HOME/.duckdb/cli/latest:$PATH"
echo 'export PATH="$HOME/.duckdb/cli/latest:$PATH"' >> ~/.bashrc
duckdb --version
```

### 7.2 Download source files

Download `aoc_tenders.db` and `tenders_vps.db` from the source listed in the
[README](../README.md#13-data-source-and-record-lookup) and place them in
`/opt/tender-watch/`.

Optionally add `registered_companies.csv` for MCA company enrichment (see
[PROVENANCE.md](PROVENANCE.md)).

### 7.3 Run the build

From `/opt/tender-watch` with the venv activated:

```bash
cd /opt/tender-watch
source .venv/bin/activate

duckdb tender_watch.duckdb ".read etl/run.sql"
duckdb :memory: ".read etl/04_build_summary.sql"
duckdb :memory: ".read etl/06_dq_report.sql"
duckdb :memory: ".read etl/08_state_hierarchy.sql"
duckdb :memory: ".read etl/10_central_hierarchy.sql"
duckdb :memory: ".read etl/11_mca_crosswalk.sql"
```

The first command takes **45+ minutes** and peaks at about **16 GB RAM**. Skip
the last command if you do not have the MCA CSV.

Verify output:

```bash
ls -lh data/
```

You may delete the raw SQLite files and `tender_watch.duckdb` after a successful
build to reclaim disk space. Keep `data/`.

---

## 8. Path B: Copy a pre-built data folder (recommended)

Build on a machine with enough RAM (see [SETUP.md](SETUP.md)), then upload
`data/` to the VPS.

### From your local machine (rsync)

```bash
rsync -avz --progress /path/to/tender-watch/data/ \
  your-user@your-server-ip:/opt/tender-watch/data/
```

### From your local machine (scp)

```bash
scp -r /path/to/tender-watch/data \
  your-user@your-server-ip:/opt/tender-watch/
```

### Verify on the VPS

```bash
ls -lh /opt/tender-watch/data/
```

You should see files such as `fact_award.parquet`, `sum_overview.parquet`,
`flag_award.parquet`, and others.

---

## 9. Run the dashboard manually (smoke test)

```bash
cd /opt/tender-watch
source .venv/bin/activate
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
streamlit run app/dashboard.py --server.headless true --server.port 8501
```

On your laptop, open an SSH tunnel if the VPS firewall blocks port 8501:

```bash
ssh -L 8501:127.0.0.1:8501 your-user@your-server-ip
```

Then visit `http://localhost:8501` in your browser. Confirm pages load and
charts render. Press `Ctrl+C` on the server to stop Streamlit when done testing.

---

## 10. Run the dashboard as a systemd service

Running under systemd keeps the app up after logout and restarts it on failure.

Streamlit sends anonymous usage telemetry to `webhooks.fivetran.com` by default.
The service below disables that in production.

Create `/etc/systemd/system/tender-watch.service`:

```bash
sudo nano /etc/systemd/system/tender-watch.service
```

Paste (adjust `User` if needed):

```ini
[Unit]
Description=Tender Watch Streamlit dashboard
After=network.target

[Service]
Type=simple
User=your-user
Group=your-user
WorkingDirectory=/opt/tender-watch
Environment=PATH=/opt/tender-watch/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ExecStart=/opt/tender-watch/.venv/bin/streamlit run app/dashboard.py \
  --server.headless true \
  --server.port 8501 \
  --server.address 127.0.0.1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Replace `your-user` with your SSH username. Binding to `127.0.0.1` is intentional:
only nginx (on the same machine) should reach Streamlit directly.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable tender-watch
sudo systemctl start tender-watch
sudo systemctl status tender-watch
```

View logs:

```bash
journalctl -u tender-watch -f
```

---

## 11. Put nginx in front (HTTPS)

If you skipped section 3, install nginx and certbot first:

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

Streamlit uses WebSockets. The nginx config must forward upgrade headers.

Replace `dashboard.example.com` with your domain. DNS must already point at the
VPS IP.

Create `/etc/nginx/sites-available/tender-watch`:

```bash
sudo nano /etc/nginx/sites-available/tender-watch
```

```nginx
server {
    listen 80;
    server_name dashboard.example.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

Enable the site and test:

```bash
sudo ln -s /etc/nginx/sites-available/tender-watch /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Issue a TLS certificate with Let's Encrypt:

```bash
sudo certbot --nginx -d dashboard.example.com
```

Certbot updates the nginx config for HTTPS and sets up auto-renewal. Visit
`https://dashboard.example.com` and confirm the dashboard loads.

### Streamlit config file (optional)

The systemd unit above sets `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false`. You can
also pin server settings in `/opt/tender-watch/.streamlit/config.toml`:

```toml
[server]
headless = true
port = 8501
address = "127.0.0.1"
enableCORS = false
enableXsrfProtection = true

[browser]
gatherUsageStats = false
```

Restart the service after changes:

```bash
sudo systemctl restart tender-watch
```

---

## 12. Firewall

Allow SSH and HTTPS; do not expose Streamlit port 8501 publicly if nginx handles
traffic.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

---

## 13. Updating after a data rebuild

When you have newer Parquet files:

1. Upload the new `data/` folder (rsync/scp as in section 8).
2. Restart the dashboard so cached query results are cleared:

```bash
sudo systemctl restart tender-watch
```

To update application code:

```bash
cd /opt/tender-watch
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart tender-watch
```

---

## 14. Troubleshooting

### Dashboard starts but pages are empty

- Confirm `data/` exists and contains Parquet files:
  `ls -lh /opt/tender-watch/data/`
- Re-run all six build commands (section 7.3) if you are building on the VPS.
- Check service logs: `journalctl -u tender-watch -n 100 --no-pager`

### `502 Bad Gateway` from nginx

- Streamlit may not be running: `sudo systemctl status tender-watch`
- Confirm it listens on localhost:
  `ss -tlnp | grep 8501`
- Check nginx error log: `sudo tail -f /var/log/nginx/error.log`

### Web page loads but widgets are broken / disconnects

- Ensure the nginx `Upgrade` and `Connection` headers from section 11 are present.
- Reload nginx after config changes: `sudo systemctl reload nginx`

### Out of memory on the VPS

- **During ETL build:** the build needs ~16 GB RAM. Build elsewhere and use Path B.
- **During dashboard use:** upgrade to at least 2 GB RAM (4 GB recommended), or add
  swap as a temporary measure:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Slow search or drill-down queries

- Normal on a small single-core VPS; DuckDB still scans millions of rows for some
  pages. More CPU helps. Results are capped (typically 300–500 rows per view).

### MCA email field

Never deploy `registered_companies.csv` to a public web root. The pipeline reads it
only at build time; the dashboard never displays email addresses. See
[PROVENANCE.md](PROVENANCE.md).

---

## Quick reference

| Item | Value |
|------|-------|
| App directory | `/opt/tender-watch` |
| Data directory | `/opt/tender-watch/data/` |
| Streamlit (local only) | `http://127.0.0.1:8501` |
| systemd unit | `tender-watch.service` |
| Restart dashboard | `sudo systemctl restart tender-watch` |
| View logs | `journalctl -u tender-watch -f` |

For local development setup on Windows or macOS, see [SETUP.md](SETUP.md). For
architecture, data model, and build details, see the [README](../README.md).
