"""pko — Pinokio CLI.

Usage:
    pko [--host HOST] [--port PORT] <command> [options]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from . import __version__
from .client import Client, WsClient
from .discover import discover_local, discover_remote, probe_instance, resolve_instance
from .config import (
    get_default_instance,
    get_profile,
    list_profiles,
    set_profile,
    set_default_profile,
    remove_profile,
    load_config,
    save_config,
)
from .models import PinokioInstance, DEFAULT_PORT, KNOWN_PORTS

app = typer.Typer(
    name="pko",
    help="Pinokio CLI — automate Pinokio instances from anywhere. See 'pko COMMAND --help' for details; commands marked \\[Not implemented] are stubs.",
    no_args_is_help=True,
)
console = Console()


# ── Helpers ──────────────────────────────────────────────────────────

def _instance(host: Optional[str] = None, port: Optional[int] = None) -> PinokioInstance:
    return resolve_instance(host, port)


def _label(inst: PinokioInstance) -> str:
    """Return a short display label for the server."""
    return f"[bold cyan]{inst.display_label}[/bold cyan]"


def _print_error(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")


def _print_ok(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def _running_apps(info_data: dict) -> set[str]:
    """Extract set of running app identifiers (path names) from scripts array."""
    running = set()
    for script in info_data.get("scripts", []):
        app = script.get("app", "")
        if app:
            running.add(app)
    return running


def _app_identifier(app: dict) -> str:
    """Return the canonical identifier for an app listing item.
    
    pinokiod's /pinokio/info returns api items with a 'path' field (the dir name).
    The scripts array references apps by this same path in the 'app' field.
    Fall back to 'name' or 'title' if path is missing.
    """
    return app.get("path") or app.get("name") or app.get("title", "?")


# ── Discover ─────────────────────────────────────────────────────────

@app.command()
def discover(
    host: Optional[str] = typer.Option(None, "--host", help="Remote host to scan"),
    timeout: int = typer.Option(2, "--timeout", "-t", help="Timeout per probe (seconds)"),
):
    """Find Pinokio instances on localhost or a remote host."""
    async def run():
        if host:
            console.print(f"[bold]Scanning {host} on ports: {', '.join(map(str, KNOWN_PORTS))}[/bold]")
            instances = await discover_remote(host, timeout)
        else:
            console.print(f"[bold]Scanning localhost on ports: {', '.join(map(str, KNOWN_PORTS))}[/bold]")
            instances = await discover_local(timeout)

        if not instances:
            _print_error("No Pinokio instances found")
            console.print("\nTips:")
            console.print("  • Make sure Pinokio is running")
            console.print(f"  • Try a specific host: [bold]pko discover --host 192.168.1.50[/bold]")
            console.print(f"  • Or connect directly: [bold]pko connect my-server 192.168.1.50:42000[/bold]")
            return

        table = Table(title=f"Found {len(instances)} Pinokio instance(s)")
        table.add_column("Host", style="cyan")
        table.add_column("Port", style="green")
        table.add_column("Source", style="yellow")
        table.add_column("Local", style="blue")

        for inst in instances:
            table.add_row(
                inst.host,
                str(inst.port),
                inst.source,
                "✓" if inst.is_local else "—",
            )
        console.print(table)

        console.print("\n[dim]Save a profile for quick access:[/dim]")
        console.print("  [bold]pko connect <name> <host>:<port>[/bold]")

    asyncio.run(run())


# ── Connect / Profile ────────────────────────────────────────────────

@app.command()
def connect(
    name: str = typer.Argument(..., help="Profile name (e.g., 'home', 'server')"),
    address: str = typer.Argument(..., help="Host:port (e.g., '192.168.1.50:42000')"),
):
    """Save a connection profile and set it as the default."""
    parts = address.split(":")
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else DEFAULT_PORT

    instance = PinokioInstance(
        host=host,
        port=port,
        name=name,
        source="manual",
        is_local=host in ("localhost", "127.0.0.1", "::1"),
    )
    set_profile(name, instance)
    set_default_profile(name)
    _print_ok(f"Saved profile [bold]{name}[/bold] → {host}:{port} [dim](now default)[/dim]")


@app.command()
def profile(
    name: Optional[str] = typer.Argument(None, help="Profile name to show or delete"),
    delete: bool = typer.Option(False, "--delete", help="Delete the profile"),
    default: bool = typer.Option(False, "--default", help="Set as default profile"),
):
    """Manage connection profiles."""
    if name and delete:
        if remove_profile(name):
            _print_ok(f"Deleted profile [bold]{name}[/bold]")
        else:
            _print_error(f"Profile [bold]{name}[/bold] not found")
        return

    if name and default:
        set_default_profile(name)
        _print_ok(f"Set [bold]{name}[/bold] as default profile")
        return

    if name:
        profile_data = get_profile(name)
        if not profile_data:
            _print_error(f"Profile [bold]{name}[/bold] not found")
            return
        console.print(Panel(
            f"Host: [cyan]{profile_data.get('host', '?')}[/cyan]\n"
            f"Port: [green]{profile_data.get('port', '?')}[/green]",
            title=f"Profile: {name}",
        ))
        return

    profiles = list_profiles()
    if not profiles:
        console.print("No profiles configured.")
        console.print(f"  Create one: [bold]pko connect my-server 192.168.1.50:42000[/bold]")
        return

    table = Table(title="Connection Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Host", style="green")
    table.add_column("Port", style="yellow")
    table.add_column("Default", style="blue")

    for p in profiles:
        table.add_row(p["name"], p["host"], str(p["port"]), "✓" if p["default"] else "—")
    console.print(table)


# ── List Apps ────────────────────────────────────────────────────────

@app.command(name="list")
def list_apps(
    host: Optional[str] = typer.Option(None, "--host", help="Pinokio host"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """List installed apps with running status."""
    async def run():
        inst = _instance(host, port)
        console.print(f"── {_label(inst)} ──")
        client = Client(inst)
        try:
            ok = await client.health()
            if not ok:
                _print_error(f"Cannot connect to {inst.base_url}")
                raise typer.Exit(1)

            # Get running scripts from info for status display
            info_data = None
            try:
                r = await client._http.get("/pinokio/info")
                if r.status_code == 200:
                    info_data = r.json()
            except Exception:
                pass

            running = _running_apps(info_data) if info_data else set()

            apps = await client.list_apps_from_info()
            if not apps:
                apps = await client.list_apps()
            if not apps:
                console.print("[yellow]No apps installed yet.[/yellow]")
                return

            table = Table(title=f"Installed Apps ({len(apps)})")
            table.add_column("Name", style="cyan")
            table.add_column("Title", style="white")
            table.add_column("Status", style="green")

            for app in apps:
                app_id = _app_identifier(app)
                title = app.get("title", app_id)
                is_running = app_id in running

                try:
                    meta = await client.read_pinokio_js(app_id)
                    if meta:
                        title = meta.get("title", meta.get("name", title))
                except Exception:
                    pass
                status = "[green]running[/green]" if is_running else "—"
                table.add_row(app_id, title, status)

            console.print(table)
        finally:
            await client.close()

    asyncio.run(run())


# ── Info ─────────────────────────────────────────────────────────────

@app.command()
def info(
    host: Optional[str] = typer.Option(None, "--host", help="Pinokio host"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Pinokio port"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show Pinokio system information."""
    async def run():
        inst = _instance(host, port)
        console.print(f"── {_label(inst)} ──")
        client = Client(inst)
        try:
            ok = await client.health()
            if not ok:
                _print_error(f"Cannot connect to {inst.base_url}")
                raise typer.Exit(1)

            sys_info = await client.info()

            if json_output:
                console.print(json.dumps({
                    "platform": sys_info.platform,
                    "arch": sys_info.arch,
                    "version": sys_info.version,
                    "memory": sys_info.memory,
                    "gpu": sys_info.gpu,
                    "home": sys_info.home,
                    "running_scripts": len(sys_info.running_scripts),
                }, indent=2))
                return

            console.print(Panel(
                f"[bold]Platform:[/bold] {sys_info.platform}\n"
                f"[bold]Arch:[/bold] {sys_info.arch}\n"
                f"[bold]Version:[/bold] {sys_info.version}\n"
                f"[bold]Home:[/bold] {sys_info.home}\n"
                f"[bold]Running:[/bold] {len(sys_info.running_scripts)} script(s)",
                title=f"Pinokio @ {inst.base_url}",
            ))

            if sys_info.gpu:
                gpu_str = sys_info.gpu.get("model", sys_info.gpu.get("name", str(sys_info.gpu))) if isinstance(sys_info.gpu, dict) else str(sys_info.gpu)
                console.print(f"[bold]GPU:[/bold] {gpu_str}")
            if sys_info.memory:
                mem = sys_info.memory
                total = mem.get("total", 0)
                free = mem.get("free", 0)
                if total:
                    used_pct = round((1 - free / total) * 100, 1) if total > 0 else 0
                    console.print(f"[bold]Memory:[/bold] {used_pct}% used")

        finally:
            await client.close()

    asyncio.run(run())


# ── Status ───────────────────────────────────────────────────────────

@app.command()
def status(
    app_name: Optional[str] = typer.Argument(None, help="App name to check (omit for --all)"),
    all_apps: bool = typer.Option(False, "--all", "-a", help="Show status for all apps"),
    host: Optional[str] = typer.Option(None, "--host", help="Pinokio host"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """Check if an app is running. Use --all to show all apps."""
    async def run():
        inst = _instance(host, port)
        console.print(f"── {_label(inst)} ──")
        client = Client(inst)
        try:
            ok = await client.health()
            if not ok:
                _print_error(f"Cannot connect to {inst.base_url}")
                raise typer.Exit(1)

            # Fetch info to get running scripts
            info = await client.info()
            running_names = {s.get("app", "") for s in info.running_scripts if s.get("app")}

            show_all = all_apps or app_name is None

            if show_all:
                apps = await client.list_apps_from_info()
                if not apps:
                    # Fallback to fs-based listing
                    apps = await client.list_apps()
                if not apps:
                    console.print("[yellow]No apps installed.[/yellow]")
                    return

                table = Table(title="App Status")
                table.add_column("App", style="cyan")
                table.add_column("Status", style="green")
                table.add_column("URL", style="yellow")

                for app in apps:
                    app_id = _app_identifier(app)
                    title = app.get("title", app_id)
                    is_running = app_id in running_names
                    status_str = "[green]running[/green]" if is_running else "[dim]stopped[/dim]"
                    url = ""
                    if is_running:
                        for s in info.running_scripts:
                            if s.get("app") == app_id:
                                local = s.get("local", {})
                                if isinstance(local, dict):
                                    url = local.get("url", "")
                                break
                    table.add_row(title, status_str, url)
                console.print(table)

            else:
                if not app_name:
                    _print_error("Specify an app name or use --all")
                    raise typer.Exit(1)

                # Check the app exists
                installed = await client.list_apps_from_info()
                if not installed:
                    installed = await client.list_apps()
                installed_ids = {_app_identifier(a) for a in installed}

                if app_name not in installed_ids:
                    _print_error(f"App [bold]{app_name}[/bold] not found")
                    console.print(f"  Installed apps: {', '.join(sorted(installed_ids))}")
                    raise typer.Exit(1)

                is_running = app_name in running_names
                if is_running:
                    url = ""
                    for s in info.running_scripts:
                        if s.get("app") == app_name:
                            local = s.get("local", {})
                            if isinstance(local, dict):
                                url = local.get("url", "")
                            break
                    msg = f"[bold]{app_name}[/bold] is running"
                    if url:
                        msg += f" [dim]({url})[/dim]"
                    _print_ok(msg)
                else:
                    console.print(f"[yellow]⚠[/yellow] [bold]{app_name}[/bold] is not running")

        finally:
            await client.close()

    asyncio.run(run())


# ── Config ───────────────────────────────────────────────────────────

@app.command()
def config(
    key: Optional[str] = typer.Argument(None, help="Config key to get"),
    value: Optional[str] = typer.Argument(None, help="Config value to set"),
    host: Optional[str] = typer.Option(None, "--host", help="Pinokio host"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Pinokio port"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get or set Pinokio configuration values."""
    async def run():
        inst = _instance(host, port)
        client = Client(inst)
        try:
            ok = await client.health()
            if not ok:
                _print_error(f"Cannot connect to {inst.base_url}")
                raise typer.Exit(1)

            if key and value is not None:
                _print_error("Setting config via CLI not yet supported — use the web UI at /env")
                console.print("  Config values are stored in the ENVIRONMENT file.")
                console.print(f"  To set [bold]{key}={value}[/bold], edit ~/pinokio/ENVIRONMENT")
                return

            env = await client.get_config()

            if json_output:
                console.print(json.dumps(env, indent=2))
                return

            if key:
                if key in env:
                    console.print(f"{key}={env[key]}")
                else:
                    _print_error(f"Key [bold]{key}[/bold] not found in config")
                return

            table = Table(title=f"Pinokio Configuration @ {inst.display_label}")
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="green")

            for k, v in sorted(env.items()):
                table.add_row(k, str(v))

            if table.row_count:
                console.print(table)
            else:
                console.print("[yellow]No configuration values found.[/yellow]")

        finally:
            await client.close()

    asyncio.run(run())


# ── Logs ─────────────────────────────────────────────────────────────

@app.command()
def logs(
    log_path: str = typer.Option("stdout.txt", "--path", help="Log file path"),
    host: Optional[str] = typer.Option(None, "--host", help="Pinokio host"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Pinokio port"),
    tail: int = typer.Option(50, "--tail", "-n", help="Number of lines to show"),
):
    """View Pinokio logs."""
    async def run():
        inst = _instance(host, port)
        console.print(f"── {_label(inst)} ──")
        client = Client(inst)
        try:
            ok = await client.health()
            if not ok:
                _print_error(f"Cannot connect to {inst.base_url}")
                raise typer.Exit(1)

            log_content = await client.get_logs(log_path)
            if not log_content:
                _print_error(f"Log file not found: {log_path}")
                return

            lines = log_content.splitlines()
            shown = lines[-tail:] if tail else lines
            console.print(Panel(
                "\n".join(shown),
                title=f"Log: {log_path} (last {len(shown)} of {len(lines)} lines)",
            ))
        finally:
            await client.close()

    asyncio.run(run())


# ── Restart ──────────────────────────────────────────────────────────

@app.command()
def restart(
    host: Optional[str] = typer.Option(None, "--host", help="Pinokio host"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Pinokio port"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Restart the Pinokio server."""
    if not force:
        confirm = typer.confirm("Restart Pinokio server?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

    async def run():
        inst = _instance(host, port)
        client = Client(inst)
        try:
            ok = await client.health()
            if not ok:
                _print_error(f"Cannot connect to {inst.base_url}")
                raise typer.Exit(1)

            await client.restart()
            _print_ok(f"Restart signal sent to {inst.base_url}")
        finally:
            await client.close()

    asyncio.run(run())


# ── Install (stub) ───────────────────────────────────────────────────

@app.command()
def install(
    source: str = typer.Argument(..., help="Git URL or org/repo shorthand"),
    host: Optional[str] = typer.Option(None, "--host", help="Pinokio host"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """Install an app from a git repository. \\[Not implemented]"""
    console.print("[yellow]⚠[/yellow] Install via CLI is not yet implemented.")
    console.print("  For now, install apps through the Pinokio web UI:")
    console.print(f"  {_instance(host, port).base_url}/pinokio/install")
    console.print(f"  Source: [bold]{source}[/bold]")


# ── Start (stub) ─────────────────────────────────────────────────────

@app.command()
def start(
    app_name: str = typer.Argument(..., help="App name to start"),
    host: Optional[str] = typer.Option(None, "--host", help="Pinokio host"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """Start an app. \\[Not implemented]"""
    inst = _instance(host, port)
    console.print(f"── {_label(inst)} ──")
    console.print("[yellow]⚠[/yellow] Start via CLI is not yet implemented.")
    console.print("  This will run the app's pinokio.js script via WebSocket.")
    console.print(f"  App: [bold]{app_name}[/bold]")


# ── Stop (stub) ──────────────────────────────────────────────────────

@app.command()
def stop(
    app_name: str = typer.Argument(..., help="App name to stop"),
    host: Optional[str] = typer.Option(None, "--host", help="Pinokio host"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """Stop a running app. \\[Not implemented]"""
    inst = _instance(host, port)
    console.print(f"── {_label(inst)} ──")
    console.print("[yellow]⚠[/yellow] Stop via CLI is not yet implemented.")
    console.print("  This will send a stop command to pinokiod.")
    console.print(f"  App: [bold]{app_name}[/bold]")


# ── Delete ───────────────────────────────────────────────────────────

@app.command()
def delete(
    app_name: str = typer.Argument(..., help="App name to delete"),
    delete_type: str = typer.Option("bin", "--type", "-t", help="What to delete: bin, cache, env, browser-cache"),
    host: Optional[str] = typer.Option(None, "--host", help="Pinokio host"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Pinokio port"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete an app or its components."""
    if not force:
        confirm = typer.confirm(f"Delete {delete_type} for [bold]{app_name}[/bold]?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

    async def run():
        inst = _instance(host, port)
        console.print(f"── {_label(inst)} ──")
        client = Client(inst)
        try:
            ok = await client.health()
            if not ok:
                _print_error(f"Cannot connect to {inst.base_url}")
                raise typer.Exit(1)

            success = await client.delete_app(app_name, delete_type)
            if success:
                _print_ok(f"Deleted {delete_type} for [bold]{app_name}[/bold]")
            else:
                _print_error(f"Failed to delete {delete_type} for [bold]{app_name}[/bold]")
        finally:
            await client.close()

    asyncio.run(run())


# ── Version ──────────────────────────────────────────────────────────

@app.callback(invoke_without_command=True)
def main_callback(
    version: bool = typer.Option(False, "--version", "-V", help="Show version"),
):
    if version:
        console.print(f"pko v{__version__}")
        raise typer.Exit()


# ── Entry Point ──────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()