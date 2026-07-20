"""pko configuration management.

Stores known Pinokio host:port targets and a default target, so users
don't need to specify --host/--port on every command. No named-profile
concept — pko refers to servers purely by host:port (see PLAN.md).
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
        CONFIG_FILE.write_text(json.dumps({"hosts": [], "default": None}))


def load_config() -> dict:
    _ensure_config()
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return {"hosts": [], "default": None}


def save_config(config: dict) -> None:
    _ensure_config()
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def _is_local(host: str) -> bool:
    return host in ("localhost", "127.0.0.1", "::1")


def add_host(host: str, port: int, set_default: bool = True) -> None:
    """Remember a host:port target. Sets it as the default target unless
    set_default=False AND a default is already configured."""
    config = load_config()
    hosts = config.setdefault("hosts", [])
    entry = {"host": host, "port": port}
    if entry not in hosts:
        hosts.append(entry)
    if set_default or config.get("default") is None:
        config["default"] = entry
    save_config(config)


def set_default_host(host: str, port: int) -> bool:
    """Set an already-known host:port as the default. Returns False if
    it isn't in the known-hosts list."""
    config = load_config()
    entry = {"host": host, "port": port}
    if entry not in config.get("hosts", []):
        return False
    config["default"] = entry
    save_config(config)
    return True


def forget_host(host: str, port: int) -> bool:
    """Remove a host:port from the known-hosts list."""
    config = load_config()
    hosts = config.get("hosts", [])
    entry = {"host": host, "port": port}
    if entry not in hosts:
        return False
    hosts.remove(entry)
    if config.get("default") == entry:
        config["default"] = hosts[0] if hosts else None
    save_config(config)
    return True


def list_hosts() -> list[dict]:
    """List known host:port targets, flagging which one is default."""
    config = load_config()
    default = config.get("default")
    return [
        {"host": h["host"], "port": h["port"], "default": h == default}
        for h in config.get("hosts", [])
    ]


def get_default_instance() -> PinokioInstance:
    """Get the default instance: env vars > saved default > localhost fallback."""
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
    default = config.get("default")
    if default:
        host = default.get("host", "localhost")
        return PinokioInstance(
            host=host,
            port=default.get("port", 42000),
            source="config",
            is_local=_is_local(host),
        )

    return PinokioInstance(
        host="localhost",
        port=42000,
        source="default",
        is_local=True,
    )
