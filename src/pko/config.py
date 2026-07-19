"""pko configuration management.

Stores connection profiles (host, port, name) so users don't need to
specify --host on every command. Supports multiple profiles for
managing multiple Pinokio instances.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .models import PinokioInstance


CONFIG_DIR = Path.home() / ".config" / "pko"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _ensure_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps({"profiles": {}, "default_profile": "default"}))


def load_config() -> dict:
    _ensure_config()
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return {"profiles": {}, "default_profile": "default"}


def save_config(config: dict) -> None:
    _ensure_config()
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def get_profile(name: str = "default") -> Optional[dict]:
    config = load_config()
    return config.get("profiles", {}).get(name)


def set_profile(name: str, instance: PinokioInstance) -> None:
    config = load_config()
    config.setdefault("profiles", {})[name] = {
        "host": instance.host,
        "port": instance.port,
        "name": instance.name or name,
    }
    save_config(config)


def get_default_instance() -> PinokioInstance:
    """Get the default instance, checking env vars and config."""
    # Env var overrides
    host = os.environ.get("PKO_HOST") or os.environ.get("PINOKIO_HOST")
    port_str = os.environ.get("PKO_PORT") or os.environ.get("PINOKIO_PORT")

    if host and port_str:
        return PinokioInstance(
            host=host,
            port=int(port_str),
            name="env",
            source="env",
            is_local=host in ("localhost", "127.0.0.1", "::1"),
        )

    # Config file
    profile = get_profile()
    if profile:
        return PinokioInstance(
            host=profile.get("host", "localhost"),
            port=profile.get("port", 42000),
            name=profile.get("name", "default"),
            source="config",
            is_local=profile.get("host", "localhost") in ("localhost", "127.0.0.1", "::1"),
        )

    # Fallback to localhost
    return PinokioInstance(
        host="localhost",
        port=42000,
        name="default",
        source="default",
        is_local=True,
    )


def list_profiles() -> list[dict]:
    config = load_config()
    profiles = config.get("profiles", {})
    default = config.get("default_profile", "default")
    result = []
    for name, data in profiles.items():
        result.append({
            "name": name,
            "host": data.get("host", "localhost"),
            "port": data.get("port", 42000),
            "default": name == default,
        })
    return result


def set_default_profile(name: str) -> None:
    config = load_config()
    config["default_profile"] = name
    save_config(config)


def remove_profile(name: str) -> bool:
    config = load_config()
    profiles = config.get("profiles", {})
    if name not in profiles:
        return False
    del profiles[name]
    if config.get("default_profile") == name:
        config["default_profile"] = next(iter(profiles.keys())) if profiles else "default"
    save_config(config)
    return True