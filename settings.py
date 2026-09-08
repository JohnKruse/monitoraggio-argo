"""Caricamento della configurazione di Monitoraggio Argo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(RuntimeError):
    pass


def load_settings(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise ConfigurationError(
            f"File di configurazione non trovato: {config_path}. "
            "Copia config.example.yaml come config.yaml e inserisci i dati privati."
        )
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigurationError("Il livello principale di config.yaml deve essere una mappa YAML.")
    data["_config_dir"] = config_path.parent
    return data


def resolve_path(settings: dict[str, Any], value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(settings["_config_dir"]) / path
    return path.resolve()


def recipients(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []
