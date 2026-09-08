#!/usr/bin/env python3
"""Export future work and bulletin-board documents from Argo Famiglia.

API-only mode accepts a current short-lived access token. Optional browser mode
can obtain that token through Argo's own login page.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


APP_URL = "https://www.portaleargo.it/famiglia/"
API_BASE = "https://didattica.portaleargo.it/famiglia/api"
CLIENT_VERSION = "4.0.0"
LOGIN_TIMEOUT_MS = 10 * 60 * 1000


class ArgoError(RuntimeError):
    """A user-facing Argo export error."""


@dataclass(frozen=True)
class Collections:
    homework: list[dict[str, Any]]
    reminders: list[dict[str, Any]]
    bacheca: list[dict[str, Any]]


def _date_at_or_after(value: Any, start: str) -> bool:
    return isinstance(value, str) and value[:10] >= start


def extract_collections(dashboard: dict[str, Any], start: str) -> Collections:
    """Convert Argo's dashboard shape into the three requested collections."""
    homework: list[dict[str, Any]] = []
    for lesson in dashboard.get("registro") or []:
        if not isinstance(lesson, dict):
            continue
        for assignment in lesson.get("compiti") or []:
            if not isinstance(assignment, dict):
                continue
            due = assignment.get("dataConsegna")
            if _date_at_or_after(due, start):
                homework.append(
                    {
                        "materia": lesson.get("materia"),
                        "docente": lesson.get("docente"),
                        "compito": assignment.get("compito"),
                        "dataAssegnazione": lesson.get("datGiorno"),
                        "dataConsegna": due,
                    }
                )

    reminders = [
        item
        for item in (dashboard.get("promemoria") or [])
        if isinstance(item, dict) and _date_at_or_after(item.get("datGiorno"), start)
    ]
    bacheca = [item for item in (dashboard.get("bacheca") or []) if isinstance(item, dict)]

    homework.sort(key=lambda item: (item.get("dataConsegna") or "", item.get("materia") or ""))
    reminders.sort(key=lambda item: (item.get("datGiorno") or "", item.get("oraInizio") or ""))
    bacheca.sort(key=lambda item: item.get("data") or "", reverse=True)
    return Collections(homework=homework, reminders=reminders, bacheca=bacheca)


def safe_filename(value: str, fallback: str = "document") -> str:
    name = Path(value).name.strip()
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or fallback)[:180]


def short_id(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:10]


def profile_label(profile: dict[str, Any], index: int) -> str:
    pupil = profile.get("alunno") or {}
    label = pupil.get("nominativo")
    if not label:
        label = " ".join(str(pupil.get(k) or "").strip() for k in ("cognome", "nome")).strip()
    return label or f"profilo-{index + 1}"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _browser_snapshot(
    profile_dir: Path,
    credentials: dict[str, Any] | None = None,
    *,
    headless: bool = False,
) -> tuple[Any, Any, dict[str, Any]]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ArgoError(
            "Playwright is not installed. Run: python3 -m pip install -r requirements.txt"
        ) from exc

    playwright = sync_playwright().start()
    try:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir), channel="chrome", headless=headless
        )
        page = context.pages[0] if context.pages else context.new_page()
        if not headless:
            print("A Chrome window has opened. Complete Argo login there if prompted.")
        page.goto(APP_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            """
            () => location.pathname.startsWith('/auth/sso/login/') ||
                  Object.keys(sessionStorage).some((key) => {
                    try {
                      const value = JSON.parse(sessionStorage.getItem(key));
                      return Boolean(value && value.access_token);
                    } catch (_) { return false; }
                  })
            """,
            timeout=30_000,
        )
        credentials = credentials or {}
        school_code = str(credentials.get("school_code") or "").strip()
        username = str(credentials.get("username") or "").strip()
        password = str(credentials.get("password") or "").strip()
        if school_code and username and password and "/auth/sso/login/" in page.url:
            try:
                page.locator("#codiceScuola").fill(school_code)
                page.locator('input[name="username"], #username').first.fill(username)
                page.locator('input[name="password"], #password').first.fill(password)
                if credentials.get("remember_me", True):
                    remember = page.locator("#shared_remember_me")
                    if remember.count() and remember.is_visible() and not remember.is_checked():
                        remember.check()
                page.locator("#accediBtn").click()
            except Exception as exc:
                print(f"Automatic login was not completed ({exc}); please finish it in the browser.")
        try:
            page.wait_for_function(
                """
                () => location.hostname === 'www.portaleargo.it' &&
                      location.pathname.startsWith('/famiglia/') &&
                      Object.keys(sessionStorage).some((key) => {
                        try {
                          const value = JSON.parse(sessionStorage.getItem(key));
                          return Boolean(value && value.access_token);
                        } catch (_) { return false; }
                      })
                """,
                timeout=LOGIN_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError as exc:
            raise ArgoError("Timed out waiting for Argo login to finish.") from exc

        snapshot = page.evaluate(
            """
            async ({apiBase, clientVersion}) => {
              let accessToken = null;
              for (const key of Object.keys(sessionStorage)) {
                try {
                  const value = JSON.parse(sessionStorage.getItem(key));
                  if (value && value.access_token) {
                    accessToken = value.access_token;
                    break;
                  }
                } catch (_) {}
              }
              if (!accessToken) throw new Error('No Argo access token found after login.');

              async function api(path, {method = 'GET', token = null, codMin = null, body = null} = {}) {
                const headers = {
                  'Accept': 'application/json',
                  'Authorization': `Bearer ${accessToken}`,
                  'argo-client-version': clientVersion,
                  'os-type': 'WEB'
                };
                if (token) headers['x-auth-token'] = token;
                if (codMin) headers['x-cod-min'] = codMin;
                if (body !== null) headers['Content-Type'] = 'application/json';
                const response = await fetch(`${apiBase}${path}`, {
                  method,
                  headers,
                  body: body === null ? undefined : JSON.stringify(body)
                });
                let data;
                try { data = await response.json(); }
                catch (_) { data = {}; }
                if (!response.ok || data.success === false) {
                  throw new Error(data.msg || data.message || `Argo API ${response.status} on ${path}`);
                }
                return data;
              }

              const login = await api('/login', {method: 'POST', body: {}});
              const records = Array.isArray(login.data) ? login.data : [];
              if (!records.length) throw new Error('Argo returned no student profiles.');
              const profiles = [];
              for (let index = 0; index < records.length; index++) {
                const record = records[index];
                const token = record.token;
                const codMin = record.codMin;
                const profileResponse = await api('/profilo', {token, codMin});
                const profile = profileResponse.data && profileResponse.data.profilo
                  ? profileResponse.data.profilo : profileResponse.data;
                const start = profile && profile.anno && profile.anno.dataInizio;
                if (!start) throw new Error(`Profile ${index + 1} has no school-year start date.`);
                const dashboardResponse = await api('/dashboard/dashboard', {
                  method: 'POST', token, codMin,
                  body: {dataultimoaggiornamento: `${start} 00:00:00`, opzioni: null}
                });
                const dashboards = dashboardResponse.data && dashboardResponse.data.dati;
                profiles.push({
                  index,
                  token,
                  codMin,
                  profile,
                  dashboard: Array.isArray(dashboards) ? (dashboards[0] || {}) : {}
                });
              }
              return {accessToken, profiles};
            }
            """,
            {"apiBase": API_BASE, "clientVersion": CLIENT_VERSION},
        )
        return playwright, context, snapshot
    except (PlaywrightError, Exception):
        playwright.stop()
        raise


def _attachment_url(page: Any, access_token: str, auth: dict[str, str], uid: Any, pk_scheda: Any) -> str:
    result = page.evaluate(
        """
        async ({apiBase, clientVersion, accessToken, token, codMin, uid, pkScheda}) => {
          const response = await fetch(`${apiBase}/famiglia/downloadallegatobacheca`, {
            method: 'POST',
            headers: {
              'Accept': 'application/json',
              'Authorization': `Bearer ${accessToken}`,
              'Content-Type': 'application/json',
              'argo-client-version': clientVersion,
              'os-type': 'WEB',
              'x-auth-token': token,
              'x-cod-min': codMin
            },
            body: JSON.stringify({uid, pkScheda})
          });
          const data = await response.json();
          if (!response.ok || data.success === false || !data.url) {
            throw new Error(data.msg || data.message || `Unable to get attachment URL (${response.status}).`);
          }
          return data.url;
        }
        """,
        {
            "apiBase": API_BASE,
            "clientVersion": CLIENT_VERSION,
            "accessToken": access_token,
            "token": auth["token"],
            "codMin": auth["codMin"],
            "uid": uid,
            "pkScheda": pk_scheda,
        },
    )
    return urljoin(API_BASE + "/", result)


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ArgoExporter/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("xb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def _api_json(
    access_token: str,
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    cod_min: str | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "argo-client-version": CLIENT_VERSION,
        "os-type": "WEB",
        "User-Agent": "ArgoExporter/1.0",
    }
    if token:
        headers["x-auth-token"] = token
    if cod_min:
        headers["x-cod-min"] = cod_min
    encoded = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        encoded = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        API_BASE + path, data=encoded, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            message = detail.get("msg") or detail.get("message")
        except Exception:
            message = None
        if exc.code in (401, 403):
            raise ArgoError("The Argo access token is expired or unauthorized.") from exc
        raise ArgoError(message or f"Argo API returned HTTP {exc.code} for {path}.") from exc
    if result.get("success") is False:
        raise ArgoError(result.get("msg") or result.get("message") or f"Argo rejected {path}.")
    return result


def _direct_snapshot(access_token: str) -> dict[str, Any]:
    login = _api_json(access_token, "/login", method="POST", body={})
    records = login.get("data") or []
    if not records:
        raise ArgoError("Argo returned no student profiles.")
    profiles = []
    for index, record in enumerate(records):
        token = record.get("token")
        cod_min = record.get("codMin")
        profile_response = _api_json(
            access_token, "/profilo", token=token, cod_min=cod_min
        )
        profile_data = profile_response.get("data") or {}
        profile = profile_data.get("profilo") or profile_data
        start = (profile.get("anno") or {}).get("dataInizio")
        if not start:
            raise ArgoError(f"Profile {index + 1} has no school-year start date.")
        dashboard_response = _api_json(
            access_token,
            "/dashboard/dashboard",
            method="POST",
            token=token,
            cod_min=cod_min,
            body={"dataultimoaggiornamento": f"{start} 00:00:00", "opzioni": None},
        )
        dashboards = (dashboard_response.get("data") or {}).get("dati") or []
        profiles.append(
            {
                "index": index,
                "token": token,
                "codMin": cod_min,
                "profile": profile,
                "dashboard": dashboards[0] if dashboards else {},
            }
        )
    return {"accessToken": access_token, "profiles": profiles}


def _token_from_har(path: Path) -> str:
    with path.expanduser().open("r", encoding="utf-8") as handle:
        har = json.load(handle)
    candidates = []
    for entry in har.get("log", {}).get("entries", []):
        if not str((entry.get("request") or {}).get("url") or "").endswith("/oauth2/token"):
            continue
        text = ((entry.get("response") or {}).get("content") or {}).get("text")
        if not text:
            continue
        payload = json.loads(text)
        if payload.get("access_token"):
            candidates.append((entry.get("startedDateTime") or "", payload))
    if not candidates:
        raise ArgoError("No OAuth access token was found in the HAR.")
    started, payload = max(candidates, key=lambda item: item[0])
    if started and payload.get("expires_in"):
        issued = datetime.fromisoformat(started.replace("Z", "+00:00"))
        age = (datetime.now().astimezone() - issued).total_seconds()
        if age >= int(payload["expires_in"]):
            raise ArgoError("The access token in this HAR has expired; capture a fresh login or paste a current token.")
    return str(payload["access_token"])


def _access_token(args: argparse.Namespace) -> str:
    if args.har:
        return _token_from_har(args.har)
    if args.token_file:
        token = args.token_file.expanduser().read_text(encoding="utf-8").strip()
    else:
        token = os.environ.get("ARGO_ACCESS_TOKEN", "").strip()
    if not token:
        token = getpass.getpass("Paste the current Argo access token: ").strip()
    if not token:
        raise ArgoError("No access token was supplied.")
    return token


def _write_snapshot(args: argparse.Namespace, snapshot: dict[str, Any], attachment_url: Any) -> int:
    start = args.from_date or date.today().isoformat()
    datetime.strptime(start, "%Y-%m-%d")
    selected = set(args.profile or [])
    profiles = snapshot.get("profiles") or []
    if selected and not selected.issubset(set(range(1, len(profiles) + 1))):
        raise ArgoError(f"Profile selection must be between 1 and {len(profiles)}.")

    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output.expanduser().resolve() / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "exportedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "futureFrom": start,
        "profiles": [],
    }

    for item in profiles:
        number = int(item["index"]) + 1
        if selected and number not in selected:
            continue
        profile = item.get("profile") or {}
        label = profile_label(profile, number - 1)
        folder = run_dir / f"profile_{number:02d}_{safe_filename(label, 'profile')}"
        folder.mkdir()
        collections = extract_collections(item.get("dashboard") or {}, start)
        write_json(folder / "homework.json", collections.homework)
        write_json(folder / "promemoria.json", collections.reminders)
        write_json(folder / "bacheca.json", collections.bacheca)

        summary: dict[str, Any] = {
            "profile": number,
            "label": label,
            "homework": len(collections.homework),
            "promemoria": len(collections.reminders),
            "bachecaMessages": len(collections.bacheca),
            "attachmentsDownloaded": 0,
            "attachmentErrors": [],
        }
        if not args.no_downloads:
            attachment_dir = folder / "bacheca_documents"
            for message in collections.bacheca:
                for document in message.get("listaAllegati") or []:
                    if not isinstance(document, dict) or document.get("pk") is None:
                        continue
                    attachment_dir.mkdir(exist_ok=True)
                    filename = safe_filename(str(document.get("nomeFile") or "document"))
                    destination = attachment_dir / (
                        f"message-{short_id(message.get('pk'))}_file-{short_id(document['pk'])}_{filename}"
                    )
                    try:
                        url = attachment_url(item, message, document)
                        _download(url, destination)
                        summary["attachmentsDownloaded"] += 1
                    except Exception as exc:
                        summary["attachmentErrors"].append({"file": filename, "error": str(exc)})
        manifest["profiles"].append(summary)
        print(
            f"{label}: {summary['homework']} future homework, "
            f"{summary['promemoria']} future promemoria, "
            f"{summary['bachecaMessages']} bacheca messages, "
            f"{summary['attachmentsDownloaded']} documents downloaded."
        )

    write_json(run_dir / "manifest.json", manifest)
    print(f"Export saved to: {run_dir}")
    return 0



def export_api(args: argparse.Namespace) -> int:
    access_token = _access_token(args)
    snapshot = _direct_snapshot(access_token)

    def attachment_url(item: dict[str, Any], _message: dict[str, Any], document: dict[str, Any]) -> str:
        profile = item.get("profile") or {}
        result = _api_json(
            access_token,
            "/famiglia/downloadallegatobacheca",
            method="POST",
            token=item.get("token"),
            cod_min=item.get("codMin"),
            body={"uid": document["pk"], "pkScheda": (profile.get("scheda") or {}).get("pk")},
        )
        if not result.get("url"):
            raise ArgoError("Argo returned no download URL for a bacheca document.")
        return urljoin(API_BASE + "/", result["url"])

    return _write_snapshot(args, snapshot, attachment_url)


def export_live(args: argparse.Namespace) -> int:
    profile_dir = args.profile_dir.expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    playwright = context = None
    try:
        playwright, context, snapshot = _browser_snapshot(profile_dir)
        page = context.pages[0]

        def attachment_url(item: dict[str, Any], _message: dict[str, Any], document: dict[str, Any]) -> str:
            profile = item.get("profile") or {}
            return _attachment_url(
                page,
                snapshot["accessToken"],
                {"token": item["token"], "codMin": item["codMin"]},
                document["pk"],
                (profile.get("scheda") or {}).get("pk"),
            )

        return _write_snapshot(args, snapshot, attachment_url)
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()


def inspect_har(path: Path) -> int:
    """Report only collection counts; never print credentials or personal fields."""
    with path.expanduser().open("r", encoding="utf-8") as handle:
        har = json.load(handle)
    dashboard = None
    endpoints: set[str] = set()
    for entry in har.get("log", {}).get("entries", []):
        request = entry.get("request") or {}
        url = str(request.get("url") or "").split("?", 1)[0]
        if "/famiglia/api/" in url and request.get("method") != "OPTIONS":
            endpoints.add(url)
        if url.endswith("/famiglia/api/dashboard/dashboard") and request.get("method") == "POST":
            text = ((entry.get("response") or {}).get("content") or {}).get("text")
            if text:
                payload = json.loads(text)
                data = ((payload.get("data") or {}).get("dati") or [])
                dashboard = data[0] if data else {}
    if dashboard is None:
        raise ArgoError("No dashboard response was found in this HAR.")
    all_work = sum(
        len(item.get("compiti") or [])
        for item in (dashboard.get("registro") or [])
        if isinstance(item, dict)
    )
    attachments = sum(
        len(item.get("listaAllegati") or [])
        for item in (dashboard.get("bacheca") or [])
        if isinstance(item, dict)
    )
    print(f"Captured API endpoints: {len(endpoints)}")
    print(f"Homework assignments in capture: {all_work}")
    print(f"Promemoria in capture: {len(dashboard.get('promemoria') or [])}")
    print(f"Bacheca messages in capture: {len(dashboard.get('bacheca') or [])}")
    print(f"Bacheca attachments listed: {attachments}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command")
    def add_export_options(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--from-date", metavar="YYYY-MM-DD", help="First due/event date to include (default: today)"
        )
        command.add_argument(
            "--output", type=Path, default=Path("output"), help="Parent folder for timestamped exports"
        )
        command.add_argument(
            "--profile", type=int, action="append", help="Export only this 1-based profile; may repeat"
        )
        command.add_argument(
            "--no-downloads", action="store_true", help="Do not download bacheca attachments"
        )

    api = sub.add_parser("api", help="Use a current access token and call the API directly")
    add_export_options(api)
    api.add_argument("--har", type=Path, help="Read a still-valid access token from a recent HAR")
    api.add_argument("--token-file", type=Path, help="Read the access token from a private text file")

    live = sub.add_parser("browser", help="Use optional browser-assisted login")
    add_export_options(live)
    live.add_argument(
        "--profile-dir",
        type=Path,
        default=Path(".argo-browser-profile"),
        help="Private Chrome profile used only for Argo login",
    )
    inspect = sub.add_parser("inspect-har", help="Safely report collection counts from a HAR")
    inspect.add_argument("path", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    args = parser().parse_args(argv)
    if args.command is None:
        args = parser().parse_args(["api"])
    try:
        if args.command == "inspect-har":
            return inspect_har(args.path)
        if args.command == "api":
            return export_api(args)
        return export_live(args)
    except (ArgoError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
