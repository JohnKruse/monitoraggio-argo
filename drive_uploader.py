"""Caricamento facoltativo su Google Drive con dipendenze importate su richiesta."""

from __future__ import annotations

import mimetypes
import hashlib
from pathlib import Path
from typing import Any


DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
DRIVE_FULL_SCOPE = "https://www.googleapis.com/auth/drive"


class DriveUploader:
    def __init__(self, config: dict[str, Any]):
        self.folder_id = str(config.get("folder_id") or "").strip()
        self.oauth_keys = Path(str(config.get("oauth_keys_file") or "~/.google-identities/client_secret.json")).expanduser()
        self.token_file = Path(str(config.get("token_file") or "~/.google-identities/google-identity.json")).expanduser()
        self.share_anyone = bool(config.get("share_with_link", False))
        self._service = None

    @property
    def enabled(self) -> bool:
        return bool(self.folder_id)

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError("Installa le dipendenze Google Drive indicate in requirements.txt") from exc

        credentials = None
        if self.token_file.exists():
            credentials = Credentials.from_authorized_user_file(str(self.token_file))
        scopes = set(credentials.scopes or []) if credentials else set()
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        elif not credentials or not credentials.valid or not scopes.intersection({DRIVE_FILE_SCOPE, DRIVE_FULL_SCOPE}):
            from google_auth_oauthlib.flow import InstalledAppFlow
            if not self.oauth_keys.exists():
                raise FileNotFoundError(f"Chiavi OAuth di Google non trovate: {self.oauth_keys}")
            flow = InstalledAppFlow.from_client_secrets_file(str(self.oauth_keys), [DRIVE_FILE_SCOPE])
            credentials = flow.run_local_server(port=0)
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(credentials.to_json(), encoding="utf-8")
            self.token_file.chmod(0o600)
        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return self._service

    def upload(self, local_path: str | Path, attachment_id: str, filename: str) -> tuple[str, str]:
        service = self._get_service()
        property_id = self._property_id(attachment_id)
        query = (
            f"'{self.folder_id}' in parents and trashed=false and "
            f"appProperties has {{ key='argoAttachmentId' and value='{property_id}' }}"
        )
        existing = service.files().list(q=query, fields="files(id,webViewLink)").execute().get("files", [])
        if existing:
            return existing[0].get("webViewLink") or self._link(existing[0]["id"]), existing[0]["id"]
        from googleapiclient.http import MediaFileUpload
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        metadata = {
            "name": filename,
            "parents": [self.folder_id],
            "appProperties": {"argoAttachmentId": property_id},
        }
        created = service.files().create(
            body=metadata,
            media_body=MediaFileUpload(str(local_path), mimetype=mime, resumable=True),
            fields="id,webViewLink",
        ).execute()
        file_id = created["id"]
        if self.share_anyone:
            service.permissions().create(fileId=file_id, body={"type": "anyone", "role": "reader"}).execute()
        return created.get("webViewLink") or self._link(file_id), file_id

    @staticmethod
    def _link(file_id: str) -> str:
        return f"https://drive.google.com/file/d/{file_id}/view"

    @staticmethod
    def _property_id(attachment_id: str) -> str:
        """Produce a stable value below Google Drive's 124-byte property limit."""
        return hashlib.sha256(attachment_id.encode("utf-8")).hexdigest()
