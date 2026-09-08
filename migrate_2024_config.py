#!/usr/bin/env python3
"""Create a minimal private config.yaml from the 2024 project's JSON config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def split_recipients(value):
    if isinstance(value, list):
        return value
    return [part.strip() for part in str(value or "").replace(";", ",").split(",") if part.strip()]


def migrate(source: Path, destination: Path) -> None:
    old = json.loads(source.expanduser().read_text(encoding="utf-8"))
    new = {
        "argo": {
            "mode": "browser",
            "school_code": old.get("argo_school_code", ""),
            "username": old.get("argo_username", ""),
            "password": old.get("argo_password", ""),
            "browser_profile": ".argo-browser-profile",
            "remember_me": True,
            "headless": False,
        },
        "storage": {
            "database": "data/argo_monitoring.db",
            "keep_local_documents": False,
            "documents_dir": "data/documents",
        },
        "email": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 465,
            "sender": old.get("email_sender", ""),
            "app_password": old.get("EMAIL_KEY", ""),
            "test_mode": True,
            "dev_recipients": split_recipients(old.get("dev_emails")),
            "daily_recipients": split_recipients(old.get("prod_emails")),
            "bacheca_recipients": split_recipients(old.get("bacheca_emails")),
        },
        "notifications": {
            "days_forward": old.get("days_forward", 17),
            "max_daily_items": old.get("max_assignments", 12),
            "bacheca_recent_items": 10,
            "bacheca_weekly_day": "sunday",
            "send_daily": True,
            "send_bacheca": True,
        },
        "files": {
            "schedule": "data/schedule.csv",
            "manual_events": "data/manual_events.csv",
            "email_header": "assets/email_header.png",
        },
        "google_drive": {
            "folder_id": old.get("google_drive_folder_id", ""),
            "oauth_keys_file": old.get("google_drive_oauth_keys", "~/.google-identities/client_secret.json"),
            "token_file": old.get("google_drive_token_file", "~/.google-identities/google-identity.json"),
            "share_with_link": True,
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(new, sort_keys=False, allow_unicode=True), encoding="utf-8")
    destination.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, nargs="?", default=Path("config.yaml"))
    args = parser.parse_args()
    migrate(args.source, args.destination)
    print(f"Private configuration written to {args.destination}; Git will ignore it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
