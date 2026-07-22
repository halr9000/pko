"""Shared UI helpers for pko CLI commands."""
from __future__ import annotations

from rich.console import Console

from .models import DEFAULT_PORT, PinokioInstance

console = Console()


def label(inst: PinokioInstance) -> str:
    """Return a short display label for the server."""
    return f"[bold cyan]{inst.display_label}[/bold cyan]"


def print_error(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")


def print_ok(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def app_identifier(app: dict) -> str:
    """Return the canonical identifier for an app listing item.

    pinokiod's /pinokio/info returns api items with a 'path' field (the dir name).
    The scripts array references apps by this same path in the 'app' field.
    Fall back to 'name' or 'title' if path is missing.
    """
    return app.get("path") or app.get("name") or app.get("title", "?")