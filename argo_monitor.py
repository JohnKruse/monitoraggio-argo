#!/usr/bin/env python3
"""Esegue Monitoraggio Argo: SQLite, documenti su Drive e riepiloghi via email."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

from argo_exporter import (
    API_BASE,
    ArgoError,
    _access_token,
    _api_json,
    _browser_snapshot,
    _direct_snapshot,
    _download,
    extract_collections,
    profile_label,
    safe_filename,
)
from drive_uploader import DriveUploader
from mailer import read_manual_events, render_bacheca_email, render_daily_email, save_preview, send_html
from settings import ConfigurationError, load_settings, resolve_path
from storage import ArgoStore, stable_id


def _token_args(config: dict[str, Any]) -> argparse.Namespace:
    har = config.get("har_file")
    token_file = config.get("token_file")
    return argparse.Namespace(
        har=Path(har).expanduser() if har else None,
        token_file=Path(token_file).expanduser() if token_file else None,
    )


def _api_attachment_url(access_token: str, item: dict[str, Any], document: dict[str, Any]) -> str:
    profile = item.get("profile") or {}
    response = _api_json(
        access_token,
        "/famiglia/downloadallegatobacheca",
        method="POST",
        token=item.get("token"),
        cod_min=item.get("codMin"),
        body={"uid": document["pk"], "pkScheda": (profile.get("scheda") or {}).get("pk")},
    )
    if not response.get("url"):
        raise ArgoError("Argo non ha restituito l'indirizzo per scaricare un documento della Bacheca")
    return urljoin(API_BASE + "/", response["url"])


def _load_saved_export(path: Path) -> dict[str, Any]:
    profiles = []
    for index, folder in enumerate(sorted(path.glob("profile_*"))):
        bacheca_path = folder / "bacheca.json"
        if not bacheca_path.exists():
            continue
        profiles.append({
            "index": index,
            "profile": {"alunno": {"nominativo": folder.name.split("_", 3)[-1].replace("_", " ")}},
            "dashboard": {
                "bacheca": json.loads(bacheca_path.read_text(encoding="utf-8")),
                "promemoria": json.loads((folder / "promemoria.json").read_text(encoding="utf-8")),
                "registro": [],
            },
            "saved_folder": folder,
        })
        homework = json.loads((folder / "homework.json").read_text(encoding="utf-8"))
        profiles[-1]["preextracted_homework"] = homework
    if not profiles:
        raise ArgoError(f"Nessuna esportazione di profilo trovata in {path}")
    return {"profiles": profiles}


def run(config_path: Path, *, dry_run: bool = False, saved_export: Path | None = None) -> dict[str, Any]:
    settings = load_settings(config_path)
    storage_config = settings.get("storage") or {}
    db_path = resolve_path(settings, storage_config.get("database") or "data/argo_monitoring.db")
    store = ArgoStore(db_path)
    run_id = store.start_run()
    browser = context = None
    try:
        argo_config = settings.get("argo") or {}
        attachment_url: Callable[[dict[str, Any], dict[str, Any]], str] | None = None
        if saved_export:
            snapshot = _load_saved_export(saved_export)
        elif str(argo_config.get("mode") or "browser").lower() == "api":
            access_token = _access_token(_token_args(argo_config))
            snapshot = _direct_snapshot(access_token)
            attachment_url = lambda item, doc: _api_attachment_url(access_token, item, doc)
        else:
            profile_dir = resolve_path(settings, argo_config.get("browser_profile") or ".argo-browser-profile")
            browser, context, snapshot = _browser_snapshot(
                profile_dir,
                argo_config,
                headless=bool(argo_config.get("headless", False)),
            )
            page = context.pages[0]
            from argo_exporter import _attachment_url
            attachment_url = lambda item, doc: _attachment_url(
                page, snapshot["accessToken"], {"token": item["token"], "codMin": item["codMin"]},
                doc["pk"], ((item.get("profile") or {}).get("scheda") or {}).get("pk"),
            )

        today = date.today()
        notification = settings.get("notifications") or {}
        days_forward = int(notification.get("days_forward", 17))
        end = today + timedelta(days=days_forward)
        all_homework: list[dict[str, Any]] = []
        all_reminders: list[dict[str, Any]] = []
        new_ids: list[str] = []
        document_lookup: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        labels: list[str] = []
        for item in snapshot.get("profiles") or []:
            profile = item.get("profile") or {}
            label = profile_label(profile, int(item.get("index") or 0))
            labels.append(label)
            profile_id = store.save_profile(profile, label, int(item.get("index") or 0))
            collections = extract_collections(item.get("dashboard") or {}, today.isoformat())
            homework = item.get("preextracted_homework") or collections.homework
            homework = [row for row in homework if str(row.get("dataConsegna") or "")[:10] <= end.isoformat()]
            reminders = [row for row in collections.reminders if str(row.get("datGiorno") or "")[:10] <= end.isoformat()]
            all_homework.extend(homework)
            all_reminders.extend(reminders)
            new_ids.extend(store.save_collections(profile_id, homework, reminders, collections.bacheca))
            for message in collections.bacheca:
                message_id = stable_id(profile_id, str(message.get("pk") or stable_id(message.get("data"), message.get("messaggio"))))
                for doc in message.get("listaAllegati") or []:
                    attachment_id = stable_id(message_id, str(doc.get("pk") or stable_id(doc.get("nomeFile"))))
                    document_lookup[attachment_id] = (item, doc)

        drive = DriveUploader(settings.get("google_drive") or {})
        keep_local = bool(storage_config.get("keep_local_documents", False))
        documents_dir = resolve_path(settings, storage_config.get("documents_dir") or "data/documents")
        if (drive.enabled or keep_local) and attachment_url:
            documents_dir.mkdir(parents=True, exist_ok=True)
            for row in store.pending_attachments(new_ids):
                source = document_lookup.get(row["id"])
                if not source:
                    continue
                item, document = source
                filename = safe_filename(row["filename"])
                target = documents_dir / f"{row['id'][:12]}_{filename}"
                try:
                    if not target.exists():
                        _download(attachment_url(item, document), target)
                    drive_url = drive_file_id = None
                    if drive.enabled and not dry_run:
                        drive_url, drive_file_id = drive.upload(target, row["argo_id"], filename)
                    local_path = str(target) if keep_local else None
                    store.update_attachment(row["id"], local_path=local_path, drive_file_id=drive_file_id, drive_url=drive_url)
                    if not keep_local:
                        target.unlink(missing_ok=True)
                except Exception as exc:
                    store.update_attachment(row["id"], error=str(exc))

        files = settings.get("files") or {}
        schedule_path = resolve_path(settings, files.get("schedule") or "data/schedule.csv")
        manual_path = resolve_path(settings, files.get("manual_events") or "data/manual_events.csv")
        header_path = resolve_path(settings, files.get("email_header") or "assets/email_header.png")
        manual_events = read_manual_events(manual_path, today, end)
        max_items = int(notification.get("max_daily_items", 12))
        daily_html = render_daily_email(
            ", ".join(labels), all_homework[:max_items], all_reminders[:max_items],
            manual_events, schedule_path, today,
        )
        recent_limit = int(notification.get("bacheca_recent_items", 10))
        bacheca_rows = store.bacheca_rows(recent_limit)
        bacheca_html = render_bacheca_email(bacheca_rows, set(new_ids), today)
        preview_dir = resolve_path(settings, "data/previews")
        save_preview(preview_dir / "daily.html", daily_html)
        save_preview(preview_dir / "bacheca.html", bacheca_html)

        sent = {"daily": 0, "bacheca": 0}
        email_config = settings.get("email") or {}
        if not dry_run and bool(notification.get("send_daily", True)):
            sent["daily"] = send_html(email_config, f"Compiti Argo — {today.isoformat()}", daily_html, "daily", header_path)
        weekday = _weekday_number(str(notification.get("bacheca_weekly_day") or "domenica"))
        weekly = today.weekday() == weekday
        if not dry_run and bool(notification.get("send_bacheca", True)) and (new_ids or weekly):
            prefix = "Nuovo avviso — " if new_ids else "Riepilogo settimanale — "
            sent["bacheca"] = send_html(email_config, prefix + f"Bacheca Argo — {today.isoformat()}", bacheca_html, "bacheca", header_path)
            store.mark_bacheca_notified(new_ids)
        detail = {"database": str(db_path), "counts": store.counts(), "new_bacheca": len(new_ids), "sent": sent, "dry_run": dry_run}
        store.finish_run(run_id, "OK", json.dumps(detail))
        return detail
    except BaseException as exc:
        store.finish_run(run_id, "ERROR", str(exc))
        raise
    finally:
        if context is not None:
            context.close()
        if browser is not None:
            browser.stop()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=Path("config.yaml"))
    result.add_argument("--dry-run", action="store_true", help="Aggiorna SQLite e le anteprime senza inviare email o caricare file")
    result.add_argument("--saved-export", type=Path, help="Usa una precedente esportazione per una prova offline")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        detail = run(args.config, dry_run=args.dry_run, saved_export=args.saved_export)
        print(json.dumps(detail, indent=2))
        return 0
    except (ArgoError, ConfigurationError, OSError, RuntimeError, ValueError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1


def _weekday_number(value: str) -> int:
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", value.lower().strip())
        if not unicodedata.combining(char)
    )
    weekdays = {
        "lunedi": 0, "monday": 0, "martedi": 1, "tuesday": 1,
        "mercoledi": 2, "wednesday": 2, "giovedi": 3, "thursday": 3,
        "venerdi": 4, "friday": 4, "sabato": 5, "saturday": 5,
        "domenica": 6, "sunday": 6,
    }
    if normalized not in weekdays:
        raise ValueError(f"Giorno settimanale non riconosciuto: {value}")
    return weekdays[normalized]


if __name__ == "__main__":
    raise SystemExit(main())
