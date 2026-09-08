"""Faithful 2024-style HTML email rendering and SMTP delivery."""

from __future__ import annotations

import csv
import smtplib
import unicodedata
from datetime import date, timedelta
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Any, Iterable

from i18n import Translator
from settings import recipients


WEEKDAYS = {
    0: ("lunedì", "monday"), 1: ("martedì", "tuesday"),
    2: ("mercoledì", "wednesday"), 3: ("giovedì", "thursday"),
    4: ("venerdì", "friday"), 5: ("sabato", "saturday"),
    6: ("domenica", "sunday"),
}
MONTHS = {
    "it": ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
}


def localized_date(value: date, language: str, with_weekday: bool = False) -> str:
    language = Translator(language).language
    weekday = WEEKDAYS[value.weekday()][0 if language == "it" else 1]
    if language == "en":
        weekday = weekday.capitalize()
    if language == "it":
        result = f"{value.day} {MONTHS['it'][value.month - 1]} {value.year}"
    else:
        result = f"{MONTHS['en'][value.month - 1]} {value.day}, {value.year}"
    return f"{weekday}, {result}" if with_weekday else result


def _normal(value: Any) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", str(value or "").lower().strip())
        if not unicodedata.combining(char)
    )


def _styled_table(
    headers: list[str], rows: Iterable[Iterable[Any]], *, font_size: str,
    accentuated_columns: set[int] | None = None,
) -> str:
    accents = accentuated_columns or set()
    base = "border:1px solid Gainsboro;padding:8px;min-width:120px;vertical-align:top;"
    header_cells = []
    for index, value in enumerate(headers):
        accent = "background-color:whitesmoke;font-weight:bold;" if index in accents else "background-color:#f2f2f2;"
        header_cells.append(f'<th style="{base}padding:10px;{accent}">{escape(str(value))}</th>')
    body_rows = []
    for row in rows:
        cells = []
        for index, value in enumerate(row):
            accent = "background-color:whitesmoke;font-weight:bold;" if index in accents else ""
            cells.append(f'<td style="{base}{accent}">{escape(str(value or ""))}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f'<table style="border-collapse:collapse;font-family:Arial;font-size:{font_size};">'
        f'<thead><tr>{"".join(header_cells)}</tr></thead><tbody>{"".join(body_rows)}</tbody></table>'
    )


def _next_school_day(today: date) -> date:
    result = today + timedelta(days=1)
    while result.weekday() >= 5:
        result += timedelta(days=1)
    return result


def read_manual_events(path: Path, start: date, end: date) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        result = []
        for row in csv.DictReader(handle):
            try:
                event_date = date.fromisoformat(str(row.get("Date") or "")[:10])
            except ValueError:
                continue
            if start <= event_date <= end:
                result.append(row)
        return result


def render_daily_email(
    label: str,
    homework: list[dict[str, Any]],
    reminders: list[dict[str, Any]],
    manual_events: list[dict[str, str]],
    schedule_path: Path | None,
    today: date,
    language: str = "it",
) -> str:
    tr = Translator(language)
    items: list[tuple[str, str, str, str]] = []
    important_words = ("test", "exam", "verific", "interrog", "invalsi", "esame", "recuper")
    for item in homework:
        assignment = str(item.get("compito") or "")
        subject = str(item.get("materia") or "")
        flag = tr.text("daily.important") if any(word in f"{subject} {assignment}".lower() for word in important_words) else ""
        items.append((str(item.get("dataConsegna") or "")[:10], assignment, subject, flag))
    for item in reminders:
        assignment = str(item.get("desAnnotazioni") or item.get("annotazione") or item.get("descrizione") or "")
        subject = str(item.get("materia") or tr.text("daily.reminder"))
        items.append((str(item.get("datGiorno") or "")[:10], assignment, subject, ""))
    for item in manual_events:
        items.append((item.get("Date", ""), item.get("Assignment", ""), item.get("Subject", tr.text("daily.manual_event")), item.get("Important", "")))
    items.sort(key=lambda row: (row[0], row[2], row[1]))

    sections = [f"<h1>{escape(tr.text('daily.title', label=label))}</h1>"]
    if items:
        rows = []
        last_date = None
        for due, assignment, subject, flag in items:
            rows.append((due if due != last_date else "", assignment, subject, flag))
            last_date = due
        headers = [tr.text(f"daily.columns.{name}") for name in ("date", "assignment", "subject", "important")]
        sections.append(_styled_table(headers, rows, font_size="16px"))
    else:
        sections.append(f"<p>{escape(tr.text('daily.no_items'))}</p>")

    if schedule_path and schedule_path.exists():
        with schedule_path.open(newline="", encoding="utf-8-sig") as handle:
            schedule = list(csv.reader(handle))
        if schedule:
            next_day = _next_school_day(today)
            aliases = {_normal(value) for value in WEEKDAYS[next_day.weekday()]}
            target_column = next((i for i, heading in enumerate(schedule[0]) if _normal(heading) in aliases), -1)
            accents = {0}
            if target_column >= 0:
                accents.add(target_column)
            heading = tr.text("daily.schedule", date=localized_date(next_day, tr.language, with_weekday=True))
            sections.append(f"<h1>{escape(heading)}</h1>")
            sections.append(_styled_table(schedule[0], schedule[1:], font_size="14px", accentuated_columns=accents))
    return _document("".join(sections))


def _document(body: str) -> str:
    return (
        '<html><body style="font-family:Arial,sans-serif;color:#111;">'
        '<img src="cid:argo-header" width="700" style="max-width:100%;height:auto;" alt="Argo"><br>'
        f"{body}</body></html>"
    )


def _file_links(item: dict[str, Any], tr: Translator) -> str:
    links = []
    for attachment in item.get("attachments") or []:
        url = attachment.get("drive_url") or item.get("source_url")
        name = escape(str(attachment.get("filename") or tr.text("bacheca.document")))
        if url:
            links.append(
                f'<a href="{escape(str(url), quote=True)}" target="_blank" '
                'style="color:#0589C5;font-weight:bold;text-decoration:underline;">'
                f"{name}</a>"
            )
        else:
            links.append(name)
    return "<br>".join(links)


def render_bacheca_email(
    rows: list[dict[str, Any]], new_ids: set[str], today: date, language: str = "it",
) -> str:
    tr = Translator(language)
    sections = []
    if new_ids:
        sections.append(f"<h1>{escape(tr.text('bacheca.new_heading'))}</h1>")
    sections.append(f"<h1>{escape(tr.text('bacheca.title'))}</h1>")
    if not rows:
        sections.append(f"<p>{escape(tr.text('bacheca.empty'))}</p>")
        return _document("".join(sections))

    fields = tr.messages["bacheca"]["fields"]
    table = ['<table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif;">']
    for item in rows:
        bold = "font-weight:bold;" if item.get("id") in new_ids else ""
        table.append('<tr><td colspan="2" style="background-color:#0589C5;height:10px;padding:0;"></td></tr>')
        values = (
            (fields["subject"], item.get("summary_title") or item.get("message") or tr.text("bacheca.fallback_subject")),
            (fields["date"], item.get("publish_date") or ""),
            (fields["summary"], item.get("summary") or ""),
            (fields["original_subject"], item.get("message") or ""),
            (fields["file"], _file_links(item, tr)),
        )
        for field_key, (label, value) in zip(("subject", "date", "summary", "original_subject", "file"), values):
            shown = value if field_key == "file" else escape(str(value or ""))
            table.append(
                f'<tr style="{bold}"><td style="border:1px solid lightgray;padding:8px;width:145px;vertical-align:top;">'
                f'<strong>{escape(str(label))}</strong></td><td style="border:1px solid lightgray;padding:8px;vertical-align:top;">'
                f'{shown}</td></tr>'
            )
        table.append('<tr><td colspan="2" style="height:16px;border:0;"></td></tr>')
    table.append("</table>")
    sections.extend(table)
    return _document("".join(sections))


def email_subject(audience: str, today: date, *, language: str, has_new: bool = False) -> str:
    tr = Translator(language)
    key = "daily.subject" if audience == "daily" else ("bacheca.subject_new" if has_new else "bacheca.subject_weekly")
    return tr.text(key, date=today.isoformat())


def send_html(config: dict[str, Any], subject: str, html: str, audience: str, header_path: Path | None) -> int:
    test_mode = bool(config.get("test_mode", True))
    target = recipients(config.get("dev_recipients") if test_mode else config.get(f"{audience}_recipients"))
    if not target:
        raise RuntimeError(f"Nessun destinatario configurato per l'email {audience}")
    sender = str(config.get("sender") or "").strip()
    password = str(config.get("app_password") or "").strip()
    if not sender or not password:
        raise RuntimeError("Sono necessari il mittente e la password per app dell'email")
    tr = Translator(config.get("language") or "it")
    message = EmailMessage()
    message["Subject"] = (tr.text("test_prefix") if test_mode else "") + subject
    message["From"] = sender
    message["To"] = ", ".join(target)
    message.set_content(tr.text("plain_text_fallback"))
    message.add_alternative(html, subtype="html")
    if header_path and header_path.exists():
        html_part = message.get_payload()[-1]
        html_part.add_related(header_path.read_bytes(), maintype="image", subtype="png", cid="<argo-header>", filename=header_path.name)
    host = str(config.get("smtp_host") or "smtp.gmail.com")
    port = int(config.get("smtp_port") or 465)
    with smtplib.SMTP_SSL(host, port, timeout=60) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)
    return len(target)


def save_preview(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
