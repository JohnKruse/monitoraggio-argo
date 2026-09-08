"""Small locale loader used by the email renderers and document summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


SUPPORTED_LANGUAGES = {"it", "en"}


def normalize_language(value: Any) -> str:
    language = str(value or "it").lower().replace("_", "-").split("-", 1)[0]
    return language if language in SUPPORTED_LANGUAGES else "it"


class Translator:
    def __init__(self, language: str = "it"):
        self.language = normalize_language(language)
        path = Path(__file__).resolve().parent / "locales" / f"{self.language}.yaml"
        self.messages = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def text(self, key: str, **values: Any) -> str:
        result: Any = self.messages
        for part in key.split("."):
            result = result[part]
        return str(result).format(**values)
