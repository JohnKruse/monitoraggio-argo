# Argo Monitoring

An API-first, deliberately small replacement for a browser-scraping Argo Famiglia monitor.

It stores homework, reminders, Bacheca notices, attachment metadata, and notification state in
one SQLite database. It sends a daily schoolwork email and a Bacheca email when new notices
arrive (plus an optional weekly recap). Bacheca documents can be uploaded to Google Drive;
by default they are not retained locally after upload.

The monitor never calls Argo's “presa visione” or “adesione” endpoints.

## Set up

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
cp config.example.yaml config.yaml
cp data/schedule.example.csv data/schedule.csv
cp data/manual_events.example.csv data/manual_events.csv
```

Fill in `config.yaml`. It is private and ignored by Git. Never put real credentials in
`config.example.yaml`.

To migrate the few relevant values from the 2024 project:

```sh
.venv/bin/python migrate_2024_config.py \
  /path/to/Argo_Monitoring_2024/config/config.json
```

## Run

Start with an offline/no-email check against an existing exporter result:

```sh
python3 argo_monitor.py --dry-run --saved-export output/20260908-184413
```

For a normal browser-assisted run:

```sh
python3 argo_monitor.py
```

The dedicated browser profile can preserve the Argo session. When Argo shows its current SSO
form, the monitor fills the school code, username, and password from private `config.yaml` and
selects “remember me.” Interactive authentication may still be needed if Argo adds another step.

For API-only use, set `argo.mode: api` and configure a fresh HAR or private token file. Argo's
captured access token normally lasts about one hour and is not suitable for unattended daily
runs by itself.

Use `--dry-run` to update SQLite and HTML previews without uploading or sending email. Preview
files are written below `data/previews/` and ignored by Git.

## What was intentionally left behind

The new project does not include Selenium/Helium scraping, pandas merge CSVs, debug captures,
duplicate scripts, AI/OCR dependencies, historical PDF downloads, or the old virtual
environment. The email text comes from Argo's API message and attachment metadata, keeping the
normal run deterministic and inexpensive.

## Public-repository safety

The ignore rules exclude `config.yaml`, the real schedule/manual-events CSVs, OAuth/HAR
material, the SQLite database, downloaded documents, browser state, logs, previews, and virtual
environments. Only generic example configuration and CSV files are public.
