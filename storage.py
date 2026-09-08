"""Small SQLite persistence layer for API data and notification state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def stable_id(*parts: Any) -> str:
    material = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ArgoStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS homework (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL REFERENCES profiles(id),
                    due_date TEXT NOT NULL,
                    subject TEXT,
                    teacher TEXT,
                    assignment TEXT NOT NULL,
                    assigned_date TEXT,
                    raw_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS homework_due_idx ON homework(due_date);
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL REFERENCES profiles(id),
                    event_date TEXT NOT NULL,
                    description TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS reminders_date_idx ON reminders(event_date);
                CREATE TABLE IF NOT EXISTS bacheca (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL REFERENCES profiles(id),
                    argo_id TEXT NOT NULL,
                    publish_date TEXT,
                    category TEXT,
                    message TEXT NOT NULL,
                    author TEXT,
                    source_url TEXT,
                    raw_json TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    notified_at TEXT,
                    summary_title TEXT,
                    summary TEXT,
                    summary_language TEXT,
                    summary_model TEXT,
                    summary_error TEXT,
                    summarized_at TEXT,
                    UNIQUE(profile_id, argo_id)
                );
                CREATE INDEX IF NOT EXISTS bacheca_date_idx ON bacheca(publish_date DESC);
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    bacheca_id TEXT NOT NULL REFERENCES bacheca(id),
                    argo_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    local_path TEXT,
                    drive_file_id TEXT,
                    drive_url TEXT,
                    error TEXT,
                    raw_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(bacheca_id, argo_id)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    detail TEXT
                );
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(bacheca)")}
            for name in (
                "summary_title", "summary", "summary_language", "summary_model",
                "summary_error", "summarized_at",
            ):
                if name not in columns:
                    db.execute(f"ALTER TABLE bacheca ADD COLUMN {name} TEXT")

    def start_run(self) -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO runs(started_at, status) VALUES (?, 'RUNNING')",
                (datetime.now().astimezone().isoformat(timespec="seconds"),),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, detail: str = "") -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET finished_at = ?, status = ?, detail = ? WHERE id = ?",
                (datetime.now().astimezone().isoformat(timespec="seconds"), status, detail, run_id),
            )

    def save_profile(self, profile: dict[str, Any], label: str, index: int) -> str:
        pupil = profile.get("alunno") or {}
        profile_id = str((profile.get("scheda") or {}).get("pk") or pupil.get("pk") or stable_id(index, label))
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as db:
            db.execute(
                """INSERT INTO profiles(id, label, raw_json, updated_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET label=excluded.label,
                   raw_json=excluded.raw_json, updated_at=excluded.updated_at""",
                (profile_id, label, json.dumps(profile, ensure_ascii=False), now),
            )
        return profile_id

    def save_collections(
        self,
        profile_id: str,
        homework: Iterable[dict[str, Any]],
        reminders: Iterable[dict[str, Any]],
        bacheca: Iterable[dict[str, Any]],
    ) -> list[str]:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        new_bacheca_ids: list[str] = []
        with self.connect() as db:
            for item in homework:
                row_id = stable_id(profile_id, item.get("dataConsegna"), item.get("materia"), item.get("compito"))
                db.execute(
                    """INSERT INTO homework VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET subject=excluded.subject,
                       teacher=excluded.teacher, assignment=excluded.assignment,
                       assigned_date=excluded.assigned_date, raw_json=excluded.raw_json,
                       updated_at=excluded.updated_at""",
                    (row_id, profile_id, item.get("dataConsegna", ""), item.get("materia"),
                     item.get("docente"), item.get("compito", ""), item.get("dataAssegnazione"),
                     json.dumps(item, ensure_ascii=False), now),
                )
            for item in reminders:
                description = str(item.get("desAnnotazioni") or item.get("annotazione") or item.get("descrizione") or "")
                row_id = stable_id(profile_id, item.get("pk"), item.get("datGiorno"), description)
                db.execute(
                    """INSERT INTO reminders VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET event_date=excluded.event_date,
                       description=excluded.description, raw_json=excluded.raw_json,
                       updated_at=excluded.updated_at""",
                    (row_id, profile_id, item.get("datGiorno", ""), description,
                     json.dumps(item, ensure_ascii=False), now),
                )
            for item in bacheca:
                argo_id = str(item.get("pk") or stable_id(item.get("data"), item.get("messaggio")))
                row_id = stable_id(profile_id, argo_id)
                existing = db.execute("SELECT notified_at FROM bacheca WHERE id = ?", (row_id,)).fetchone()
                if existing is None or existing["notified_at"] is None:
                    new_bacheca_ids.append(row_id)
                db.execute(
                    """INSERT INTO bacheca(
                           id, profile_id, argo_id, publish_date, category, message, author,
                           source_url, raw_json, first_seen_at, updated_at, notified_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                       ON CONFLICT(id) DO UPDATE SET publish_date=excluded.publish_date,
                       category=excluded.category, message=excluded.message, author=excluded.author,
                       source_url=excluded.source_url, raw_json=excluded.raw_json,
                       updated_at=excluded.updated_at""",
                    (row_id, profile_id, argo_id, item.get("data"), item.get("categoria"),
                     str(item.get("messaggio") or ""), item.get("autore"), item.get("url"),
                     json.dumps(item, ensure_ascii=False), now, now),
                )
                for document in item.get("listaAllegati") or []:
                    if not isinstance(document, dict):
                        continue
                    attachment_argo_id = str(document.get("pk") or stable_id(document.get("nomeFile")))
                    attachment_id = stable_id(row_id, attachment_argo_id)
                    db.execute(
                        """INSERT INTO attachments(
                               id, bacheca_id, argo_id, filename, raw_json, updated_at
                           ) VALUES (?, ?, ?, ?, ?, ?)
                           ON CONFLICT(id) DO UPDATE SET filename=excluded.filename,
                           raw_json=excluded.raw_json, updated_at=excluded.updated_at""",
                        (attachment_id, row_id, attachment_argo_id,
                         str(document.get("nomeFile") or "document"),
                         json.dumps(document, ensure_ascii=False), now),
                    )
        return new_bacheca_ids

    def pending_attachments(self, bacheca_ids: Iterable[str] | None = None) -> list[sqlite3.Row]:
        sql = """SELECT a.*, b.profile_id, b.argo_id AS message_argo_id
                 FROM attachments a JOIN bacheca b ON b.id = a.bacheca_id
                 WHERE a.drive_url IS NULL"""
        values: list[str] = []
        ids = list(bacheca_ids or [])
        if ids:
            sql += f" AND a.bacheca_id IN ({','.join('?' for _ in ids)})"
            values.extend(ids)
        with self.connect() as db:
            return list(db.execute(sql, values).fetchall())

    def update_attachment(
        self, attachment_id: str, *, local_path: str | None = None,
        drive_file_id: str | None = None, drive_url: str | None = None,
        error: str | None = None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """UPDATE attachments SET local_path=?, drive_file_id=?, drive_url=?,
                   error=?, updated_at=? WHERE id=?""",
                (local_path, drive_file_id, drive_url, error,
                 datetime.now().astimezone().isoformat(timespec="seconds"), attachment_id),
            )

    def bacheca_needs_summary(self, bacheca_id: str, language: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT summary, summary_language FROM bacheca WHERE id=?", (bacheca_id,)
            ).fetchone()
            return bool(row and (not row["summary"] or row["summary_language"] != language))

    def update_bacheca_summary(
        self,
        bacheca_id: str,
        *,
        title: str | None = None,
        summary: str | None = None,
        language: str | None = None,
        model: str | None = None,
        error: str | None = None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """UPDATE bacheca SET summary_title=?, summary=?, summary_language=?,
                   summary_model=?, summary_error=?, summarized_at=? WHERE id=?""",
                (title, summary, language, model, error,
                 datetime.now().astimezone().isoformat(timespec="seconds"), bacheca_id),
            )

    def attachment_rows(self, bacheca_id: str) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(db.execute(
                "SELECT * FROM attachments WHERE bacheca_id=? ORDER BY filename", (bacheca_id,)
            ).fetchall())

    def bacheca_rows(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT b.*, p.label AS profile_label FROM bacheca b
                   JOIN profiles p ON p.id=b.profile_id
                   ORDER BY (b.notified_at IS NULL) DESC, b.publish_date DESC, b.message LIMIT ?""",
                (max(limit, int(db.execute("SELECT COUNT(*) FROM bacheca WHERE notified_at IS NULL").fetchone()[0])),),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["attachments"] = [dict(a) for a in db.execute(
                    "SELECT * FROM attachments WHERE bacheca_id=? ORDER BY filename", (row["id"],)
                ).fetchall()]
                result.append(item)
            return result

    def mark_bacheca_notified(self, ids: Iterable[str]) -> None:
        values = [(datetime.now().astimezone().isoformat(timespec="seconds"), row_id) for row_id in ids]
        if not values:
            return
        with self.connect() as db:
            db.executemany("UPDATE bacheca SET notified_at=? WHERE id=?", values)

    def counts(self) -> dict[str, int]:
        with self.connect() as db:
            return {
                table: int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("profiles", "homework", "reminders", "bacheca", "attachments")
            }
