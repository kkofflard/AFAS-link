"""Configuratiebeheer voor AFAS-link.

Laadt instellingen uit omgevingsvariabelen en YAML-bestanden.
"""
import os
import re
from pathlib import Path
from typing import Optional
import yaml
from dotenv import load_dotenv

load_dotenv()


def _resolve_env_vars(value: str) -> str:
    """Vervang ${VAR_NAME} placeholders door omgevingsvariabelen."""
    if not isinstance(value, str):
        return value
    pattern = re.compile(r'\$\{([^}]+)\}')
    def replacer(match):
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))
    return pattern.sub(replacer, value)


def _resolve_dict_env_vars(d: dict) -> dict:
    """Recursief env vars in een dict vervangen."""
    result = {}
    for key, value in d.items():
        if isinstance(value, dict):
            result[key] = _resolve_dict_env_vars(value)
        elif isinstance(value, list):
            result[key] = [
                _resolve_dict_env_vars(item) if isinstance(item, dict)
                else _resolve_env_vars(item) if isinstance(item, str)
                else item
                for item in value
            ]
        elif isinstance(value, str):
            result[key] = _resolve_env_vars(value)
        else:
            result[key] = value
    return result


class AppConfig:
    """Centrale configuratieklasse voor de applicatie."""

    def __init__(self):
        self._raw: dict = {}
        self._mappings: dict = {}
        self._load()

    def _load(self):
        config_path = Path(os.getenv("CONFIG_PATH", "config/config.yaml"))
        mappings_path = config_path.parent / "mappings.yaml"

        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._raw = yaml.safe_load(f) or {}
            self._raw = _resolve_dict_env_vars(self._raw)

        if mappings_path.exists():
            with open(mappings_path, "r", encoding="utf-8") as f:
                self._mappings = yaml.safe_load(f) or {}

    @property
    def demo_mode(self) -> bool:
        return os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")

    @property
    def database_url(self) -> str:
        return os.getenv("DATABASE_URL", "sqlite:///./afas_link.db")

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO")

    @property
    def environments(self) -> list[dict]:
        return self._raw.get("environments", [])

    @property
    def entra_id(self) -> dict:
        return self._raw.get("entra_id", {})

    @property
    def active_directory(self) -> dict:
        return self._raw.get("active_directory", {})

    @property
    def naming(self) -> dict:
        return self._raw.get("naming", {
            "pattern": "{initials}.{lastname}@{domain}",
            "fallback_patterns": [
                "{initials}.{lastname}{n}@{domain}",
                "{firstname}.{lastname}@{domain}",
            ],
            "username_pattern": "{initials}.{lastname}",
        })

    @property
    def sync(self) -> dict:
        return self._raw.get("sync", {
            "full_sync_cron": "0 2 * * *",
            "max_workers": 5,
        })

    @property
    def attribute_mapping(self) -> list[dict]:
        return self._mappings.get("attribute_mapping", [])

    @property
    def group_mappings(self) -> list[dict]:
        return self._mappings.get("group_mappings", [])

    @property
    def ou_mappings(self) -> list[dict]:
        return self._mappings.get("ou_mappings", [])

    def get_afas_token(self, token_env_var: str) -> Optional[str]:
        """Haal het AFAS-token op uit de omgevingsvariabele."""
        return os.getenv(token_env_var)

    def reload(self):
        """Herlaad de configuratie vanuit bestanden."""
        self._load()


# Singleton configuratie-instantie
config = AppConfig()
