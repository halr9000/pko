"""Data models for pko."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PinokioInstance:
    """A discovered or configured Pinokio instance, identified by host:port."""
    host: str
    port: int
    source: str = "manual"  # "manual", "discover", "env", "config", "cli", "default"
    is_local: bool = False

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def display_label(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass
class AppStatus:
    """Rich per-app status from /apps/status/:id."""
    app_id: str
    running: bool = False
    ready_url: str = ""
    title: str = ""
    description: str = ""
    icon: str = ""
    path: str = ""
    running_scripts: list = field(default_factory=list)


@dataclass
class AppInfo:
    """Information about an installed app."""
    name: str
    path: str
    title: str = ""
    description: str = ""
    icon: str = ""
    running: bool = False
    disk_usage: str = ""


@dataclass
class SystemInfo:
    """System information from pinokiod. System diagnostics only —
    app-runtime data (running scripts, installed apps) lives elsewhere;
    see Client.list_running_scripts() / Client.list_apps_from_info().
    """
    platform: str = ""
    arch: str = ""
    version: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)
    gpu: dict = field(default_factory=dict)
    home: str = ""


@dataclass
class ScriptStep:
    """A single step in a pinokio.js script."""
    method: str
    params: dict = field(default_factory=dict)


@dataclass
class PinokioScript:
    """A parsed pinokio.js launcher file."""
    name: str
    title: str = ""
    description: str = ""
    icon: str = ""
    run: list[ScriptStep] = field(default_factory=list)
    menu: list[dict] = field(default_factory=list)
    pre: list[ScriptStep] = field(default_factory=list)
    start: list | None = None
    version: str = ""


@dataclass
class WsPacket:
    """A WebSocket packet from pinokiod."""
    type: str  # stream, result, event, error, start, connect, disconnect, wait, input, modal, notify
    id: str = ""
    data: dict = field(default_factory=dict)
    index: int = 0


DEFAULT_PORT = 42000
KNOWN_PORTS = [42000, 42001, 42002, 43000]
