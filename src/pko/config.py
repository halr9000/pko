"""pko configuration management.

Stores named connection profiles (host, port) so users don't need to
specify --host/--port on every command. The name is an internal
implementation detail exposed as an *optional* flag — most users never
need to think about it and can just use `pko connect host:port`, which
defaults to a profile named "default".
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .models import PinokioInstance


CONFIG_DIR = Path.home() / ".config" / "pko"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_PROFILE_NAME = "default"


def _ensure_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps({"profiles": {}, "default_profile": None}))


def load_config() -> dict:
    _ensure_config()
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return {"profiles": {}, "default_profile": None}


def save_config(config: dict) -> None:
    _ensure_config()
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def _is_local(host: str) -> bool:
    return host in ("localhost", "127.0.0.1", "::1")


def add_profile(host: str, port: int, name: str = DEFAULT_PROFILE_NAME, set_default: bool = True) -> None:
    """Save a host:port under a profile name (defaults to "default").
    Sets it as the default profile unless set_default=False AND a
    default is already configured."""
    config = load_config()
    profiles = config.setdefault("profiles", {})
    profiles[name] = {"host": host, "port": port}
    if set_default or config.get("default_profile") is None:
        config["default_profile"] = name
    save_config(config)


def get_profile(name: str = DEFAULT_PROFILE_NAME) -> Optional[dict]:
    """Look up a profile by name. Returns None if it doesn't exist."""
    config = load_config()
    return config.get("profiles", {}).get(name)


def set_default_profile(name: str) -> bool:
    """Set an already-saved profile as the default. Returns False if
    the profile doesn't exist."""
    config = load_config()
    if name not in config.get("profiles", {}):
        return False
    config["default_profile"] = name
    save_config(config)
    return True


def remove_profile(name: str) -> bool:
    """Delete a saved profile by name."""
    config = load_config()
    profiles = config.get("profiles", {})
    if name not in profiles:
        return False
    del profiles[name]
    if config.get("default_profile") == name:
        config["default_profile"] = next(iter(profiles.keys())) if profiles else None
    save_config(config)
    return True


def list_profiles() -> list[dict]:
    """List saved profiles, flagging which one is default."""
    config = load_config()
    default = config.get("default_profile")
    return [
        {"name": name, "host": data.get("host", "localhost"), "port": data.get("port", 42000), "default": name == default}
        for name, data in config.get("profiles", {}).items()
    ]


def get_default_instance() -> PinokioInstance:
    """Get the default instance: env vars > default profile > localhost fallback."""
    host = os.environ.get("PKO_HOST") or os.environ.get("PINOKIO_HOST")
    port_str = os.environ.get("PKO_PORT") or os.environ.get("PINOKIO_PORT")

    if host and port_str:
        return PinokioInstance(
            host=host,
            port=int(port_str),
            source="env",
            is_local=_is_local(host),
        )

    config = load_config()
    default_name = config.get("default_profile")
    if default_name:
        profile = config.get("profiles", {}).get(default_name)
        if profile:
            host = profile.get("host", "localhost")
            return PinokioInstance(
                host=host,
                port=profile.get("port", 42000),
                source="config",
                is_local=_is_local(host),
            )

    return PinokioInstance(
        host="localhost",
        port=42000,
        source="default",
        is_local=True,
    )
