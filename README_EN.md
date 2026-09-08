# Argo Monitoring

[Leggi questa documentazione in italiano](README.md)

A small API-based monitor for Argo Famiglia, designed to replace fragile website-scraping
workflows.

The program stores homework, reminders, Bacheca notices, attachment metadata, and notification
state in a single SQLite database. It sends a daily schoolwork email and another email whenever
new Bacheca notices appear, with an optional weekly digest. Bacheca attachments can be uploaded
to Google Drive; by default, they are not retained locally after upload.

The program never calls Argo's “presa visione” or “adesione” functions.

## Installation

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
cp config.example.yaml config.yaml
cp data/schedule.example.csv data/schedule.csv
cp data/manual_events.example.csv data/manual_events.csv
```

Enter your details in `config.yaml`. This file is private and excluded from Git. Never put real
credentials in `config.example.yaml`.

To import only the useful settings from the 2024 project:

```sh
.venv/bin/python migrate_2024_config.py \
  /path/to/Argo_Monitoring_2024/config/config.json
```

## Usage

You can start with an offline test that sends no email and uploads no files, using an existing
export:

```sh
python3 argo_monitor.py --dry-run --saved-export output/20260908-184413
```

For a normal browser-assisted run:

```sh
python3 argo_monitor.py
```

The dedicated browser profile can preserve the Argo session. When the new SSO form appears, the
program enters the school code, username, and password from the private `config.yaml` file and
selects “Remember me.” Manual interaction may still be required if Argo adds another
authentication step.

For API-only operation, set `argo.mode: api` and provide either a recent HAR file or a private
file containing the token. The captured token normally lasts about one hour, so it is not
suitable by itself for unattended daily operation.

The `--dry-run` option updates SQLite and the HTML previews but sends no email and uploads no
files. Previews are saved under `data/previews/` and excluded from Git.

## What was intentionally excluded

The project does not include Selenium/Helium scraping, pandas-generated intermediate CSV files,
debug captures, duplicate scripts, AI/OCR dependencies, historical PDF downloads, or the old
virtual environment. Emails use the text and metadata supplied by the Argo API, keeping normal
runs deterministic and inexpensive.

## Public repository security

The ignore rules protect `config.yaml`, the real timetable and events, HAR and OAuth material,
the SQLite database, downloaded documents, browser state, logs, previews, and virtual
environments. Only example configuration and CSV files are included in the public repository.

## License

Distributed under the MIT License. This independent project is not affiliated with Argo
Software.
