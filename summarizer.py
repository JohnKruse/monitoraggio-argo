"""Generate a translated title and summary for a Bacheca notice."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from i18n import normalize_language


RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6-luna"


class SummaryError(RuntimeError):
    pass


def _output_text(response: dict[str, Any]) -> str:
    for item in response.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    raise SummaryError("OpenAI non ha restituito il testo del riassunto")


def summarize_bacheca(
    message: str,
    *,
    category: str = "",
    author: str = "",
    files: list[Path] | None = None,
    language: str = "it",
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
) -> dict[str, str]:
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SummaryError("OPENAI_API_KEY non è configurata")
    language = normalize_language(language)
    output_language = "Italian" if language == "it" else "English"
    prompt = (
        f"Read this Italian school notice and any attached documents. Return a short, useful title "
        f"and a concise summary in {output_language}. Preserve all dates, times, places, deadlines, "
        "costs, links, and actions required of students or parents. Ignore repeated letterheads, "
        "headers, footers, signatures, and administrative boilerplate. Do not invent information.\n\n"
        f"Argo category: {category}\nAuthor: {author}\nOriginal notice: {message}"
    )
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for path in (files or [])[:4]:
        if not path.exists() or not path.is_file():
            continue
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({
            "type": "input_file",
            "filename": path.name,
            "file_data": f"data:{mime};base64,{encoded}",
        })
    payload = {
        "model": model,
        "store": False,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "bacheca_summary",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["title", "summary"],
                    "additionalProperties": False,
                },
            }
        },
    }
    request = Request(
        RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise SummaryError(f"Impossibile creare il riassunto: {exc}") from exc
    parsed = json.loads(_output_text(result))
    return {"title": str(parsed["title"]).strip(), "summary": str(parsed["summary"]).strip()}
