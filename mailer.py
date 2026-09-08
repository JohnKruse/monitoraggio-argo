"""HTML email rendering and SMTP delivery."""

from __future__ import annotations

import csv
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Any, Iterable

from settings import recipients


STYLE = """
body{font-family:Arial,sans-serif;color:#17233b;line-height:1.4;margin:0;padding:0}
.wrap{max-width:760px;margin:auto;padding:18px}.header{width:100%;height:auto;border-radius:12px}
h1{font-size:24px;color:#123d73}h2{font-size:19px;margin-top:26px;color:#15558d}
table{width:100%;border-collapse:collapse;margin:8px 0 18px}th{background:#15558d;color:white;text-align:left}
th,td{padding:9px;border:1px solid #d8e2ec;vertical-align:top}tr:nth-child(even){background:#f4f8fb}
.important{color:#b42318;font-weight:bold}.muted{color:#667085}.new{border-left:5px solid #ef6a52}
a{color:#1266a8}.footer{font-size:12px;color:#667085;margin-top:28px}
"""


def _table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    head = "".join(f"<th>{escape(str(value))}</th>" for value in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{escape(str(value or ''))}</td>" for value in row) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


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
) -> str:
    items: list[tuple[str, str, str, str]] = []
    important_words = ("test", "exam", "verific", "interrog", "invalsi", "esame", "recuper")
    for item in homework:
        text = str(item.get("compito") or "")
        subject = str(item.get("materia") or "")
        flag = "IMPORTANT" if any(word in f"{subject} {text}".lower() for word in important_words) else ""
        items.append((str(item.get("dataConsegna") or "")[:10], subject, text, flag))
    for item in reminders:
        text = str(item.get("desAnnotazioni") or item.get("annotazione") or item.get("descrizione") or "")
        subject = str(item.get("materia") or "Reminder")
        items.append((str(item.get("datGiorno") or "")[:10], subject, text, ""))
    for item in manual_events:
        items.append((item.get("Date", ""), item.get("Subject", "Manual event"), item.get("Assignment", ""), item.get("Important", "")))
    items.sort(key=lambda row: (row[0], row[1], row[2]))

    title = f"Upcoming schoolwork — {escape(label)}"
    sections = [f"<h1>{title}</h1>"]
    if items:
        rows = []
        last_date = None
        for due, subject, text, flag in items:
            shown_date = due if due != last_date else ""
            rows.append((shown_date, subject, text, flag))
            last_date = due
        sections.append(_table(["Date", "Subject", "Assignment / event", ""], rows))
    else:
        sections.append("<p class='muted'>No upcoming assignments, reminders, or manual events.</p>")

    if schedule_path and schedule_path.exists():
        with schedule_path.open(newline="", encoding="utf-8-sig") as handle:
            schedule = list(csv.reader(handle))
        if schedule:
            next_day = _next_school_day(today)
            sections.append(f"<h2>Class schedule — {next_day.strftime('%A, %d %B %Y')}</h2>")
            sections.append(_table(schedule[0], schedule[1:]))
    return _document("".join(sections))


def render_bacheca_email(rows: list[dict[str, Any]], new_ids: set[str], today: date) -> str:
    sections = [f"<h1>Argo Bacheca — {today.strftime('%d %B %Y')}</h1>"]
    for item in rows:
        marker = " <span class='important'>NEW</span>" if item["id"] in new_ids else ""
        sections.append(f"<div class='new'><h2>{escape(item.get('message') or 'Notice')}{marker}</h2>")
        metadata = " · ".join(filter(None, [item.get("publish_date"), item.get("category"), item.get("author")]))
        sections.append(f"<p class='muted'>{escape(metadata)}</p>")
        links = []
        for attachment in item.get("attachments") or []:
            url = attachment.get("drive_url") or item.get("source_url")
            name = escape(attachment.get("filename") or "Document")
            links.append(f"<a href='{escape(url, quote=True)}'>{name}</a>" if url else name)
        if links:
            sections.append("<p>Documents: " + " · ".join(links) + "</p>")
        sections.append("</div>")
    if not rows:
        sections.append("<p class='muted'>No Bacheca notices are stored yet.</p>")
    return _document("".join(sections))


def _document(body: str) -> str:
    return f"<html><head><style>{STYLE}</style></head><body><div class='wrap'><img class='header' src='cid:argo-header' alt='Argo monitoring header'>{body}<p class='footer'>Generated by Argo Monitoring.</p></div></body></html>"


def send_html(config: dict[str, Any], subject: str, html: str, audience: str, header_path: Path | None) -> int:
    test_mode = bool(config.get("test_mode", True))
    target = recipients(config.get("dev_recipients") if test_mode else config.get(f"{audience}_recipients"))
    if not target:
        raise RuntimeError(f"No recipients configured for {audience} email")
    sender = str(config.get("sender") or "").strip()
    password = str(config.get("app_password") or "").strip()
    if not sender or not password:
        raise RuntimeError("Email sender and app_password are required")
    message = EmailMessage()
    message["Subject"] = ("[TEST] " if test_mode else "") + subject
    message["From"] = sender
    message["To"] = ", ".join(target)
    message.set_content("This message contains an HTML school monitoring report.")
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
