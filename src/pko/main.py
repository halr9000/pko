"""pko — Pinokio CLI.

Usage:
    pko [--host HOST] [--port PORT] <command> [options]
"""

from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .client import Client
from .config import (
    add_profile,
    get_profile,
    list_profiles,
    remove_profile,
    set_default_profile,
)
from .discover import discover_local, discover_remote, resolve_instance
from .models import DEFAULT_PORT, KNOWN_PORTS, PinokioInstance

app = typer.Typer(
    name="pko",
    help=(
        "Pinokio CLI — automate Pinokio instances from anywhere. "
        "See 'pko COMMAND --help' for details; commands marked "
        "\\\\[Not implemented] are stubs."
    ),
    no_args_is_help=True,
)
console = Console()


# ── Helpers ──────────────────────────────────────────────────────────

def _instance(host: str | None = None, port: int | None = None) -> PinokioInstance:
    return resolve_instance(host, port)


def _label(inst: PinokioInstance) -> str:
    """Return a short display label for the server."""
    return f"[bold cyan]{inst.display_label}[/bold cyan]"


def _print_error(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")


def _print_ok(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def _app_identifier(app: dict) -> str:
    """Return the canonical identifier for an app listing item.

    pinokiod's /pinokio/info returns api items with a 'path' field (the dir name).
    The scripts array references apps by this same path in the 'app' field.
    Fall back to 'name' or 'title' if path is missing.
    """
    return app.get("path") or app.get("name") or app.get("title", "?")


def _run_client(
    host: str | None,
    port: int | None,
    handler,
) -> None:
    """Resolve instance, connect, health-check, then call handler(client, inst).

    Reduces the repetitive async-boilerplate pattern shared by most commands.
    Commands that need pre-async setup (confirmation prompts, etc.) handle
    the client lifecycle themselves.
    """
    async def run():
        inst = _instance(host, port)
        console.print(f"── {_label(inst)} ──")
        client = Client(inst)
        try:
            ok = await client.health()
            if not ok:
                _print_error(f"Cannot connect to {inst.base_url}")
                raise typer.Exit(1)
            await handler(client, inst)
        finally:
            await client.close()
    asyncio.run(run())


# Commands are defined in alphabetical order (by command name) so
# `pko --help` lists them alphabetically without needing manual grouping.


# ── Config ───────────────────────────────────────────────────────────

@app.command()
def config(
    key: str | None = typer.Argument(None, help="Config key to get"),
    value: str | None = typer.Argument(None, help="Config value to set"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
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


# ── Connect ──────────────────────────────────────────────────────────

@app.command()
def connect(
    address: str = typer.Argument(..., help="Host:port (e.g., '192.168.1.50:42000')"),
    name: str = typer.Option("default", "--name", help="Profile name (rarely needed — most users can ignore this)"),
):
    """Save a known Pinokio server and set it as the default."""
    parts = address.split(":")
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else DEFAULT_PORT

    add_profile(host, port, name=name, set_default=True)
    label = f"{host}:{port}" if name == "default" else f"{name} ({host}:{port})"
    _print_ok(f"Saved [bold]{label}[/bold] [dim](now default)[/dim]")


# ── Delete ───────────────────────────────────────────────────────────

@app.command()
def delete(
    app_name: str = typer.Argument(..., help="App name to delete"),
    delete_type: str = typer.Option("bin", "--type", "-t", help="What to delete: bin, cache, env, browser-cache"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
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


# ── Discover ─────────────────────────────────────────────────────────

@app.command()
def discover(
    host: str | None = typer.Option(None, "--host", help="Remote host to scan"),
    timeout: int = typer.Option(2, "--timeout", "-t", help="Timeout per probe (seconds)"),
    save: bool = typer.Option(False, "--save", help="Save the first found instance as the default host"),
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
            console.print("  • Try a specific host: [bold]pko discover --host 192.168.1.50[/bold]")
            console.print("  • Or connect directly: [bold]pko connect 192.168.1.50:42000[/bold]")
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

        if save:
            first = instances[0]
            add_profile(first.host, first.port, set_default=True)
            _print_ok(f"Saved [bold]{first.host}:{first.port}[/bold] [dim](now default)[/dim]")
        else:
            console.print("\n[dim]Save a host for quick access:[/dim]")
            console.print("  [bold]pko connect <host>:<port>[/bold]  (or re-run with --save)")

    asyncio.run(run())


# ── Info ─────────────────────────────────────────────────────────────

@app.command()
def info(
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show Pinokio system information (diagnostics only — see 'pko status' for app runtime state)."""
    async def _handler(client: Client, inst: PinokioInstance):
        sys_info = await client.info()

        if json_output:
            console.print(json.dumps({
                "platform": sys_info.platform,
                "arch": sys_info.arch,
                "version": sys_info.version,
                "memory": sys_info.memory,
                "gpu": sys_info.gpu,
                "home": sys_info.home,
            }, indent=2))
            return

        console.print(Panel(
            f"[bold]Platform:[/bold] {sys_info.platform}\n"
            f"[bold]Arch:[/bold] {sys_info.arch}\n"
            f"[bold]Version:[/bold] {sys_info.version}\n"
            f"[bold]Home:[/bold] {sys_info.home}",
            title=f"Pinokio @ {inst.base_url}",
        ))

        if sys_info.gpu:
            gpu_raw = sys_info.gpu
            if isinstance(gpu_raw, dict):
                gpu_str = gpu_raw.get("model", gpu_raw.get("name", str(gpu_raw)))
            else:
                gpu_str = str(gpu_raw)
            console.print(f"[bold]GPU:[/bold] {gpu_str}")
        if sys_info.memory:
            mem = sys_info.memory
            total = mem.get("total", 0)
            free = mem.get("free", 0)
            if total:
                used_pct = round((1 - free / total) * 100, 1) if total > 0 else 0
                console.print(f"[bold]Memory:[/bold] {used_pct}% used")

    _run_client(host, port, _handler)


# ── Inspect ──────────────────────────────────────────────────────────

@app.command()
def inspect(
    app_name: str = typer.Argument(..., help="App name to inspect"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show detailed metadata for an installed app (title, description, disk usage, running state)."""
    async def _handler(client: Client, inst: PinokioInstance):
        meta = await client.get_app_metadata(app_name)
        if meta is None:
            _print_error(f"App [bold]{app_name}[/bold] not found")
            raise typer.Exit(1)

        if json_output:
            console.print(json.dumps({
                "name": meta.name,
                "path": meta.path,
                "title": meta.title,
                "description": meta.description,
                "icon": meta.icon,
                "running": meta.running,
                "disk_usage": meta.disk_usage,
            }, indent=2))
            return

        status_str = "[green]running[/green]" if meta.running else "[dim]stopped[/dim]"
        body = (
            f"[bold]Title:[/bold] {meta.title or meta.name}\n"
            f"[bold]Status:[/bold] {status_str}\n"
        )
        if meta.description:
            body += f"[bold]Description:[/bold] {meta.description}\n"
        body += f"[bold]Path:[/bold] {meta.path}\n"
        if meta.disk_usage:
            body += f"[bold]Disk usage:[/bold] {meta.disk_usage}\n"

        console.print(Panel(body.rstrip(), title=f"App: {app_name}"))

    _run_client(host, port, _handler)


# ── Install (stub) ───────────────────────────────────────────────────

@app.command()
def install(
    source: str = typer.Argument(..., help="Git URL or org/repo shorthand"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """Install an app from a git repository. \\[Not implemented]"""
    console.print("[yellow]⚠[/yellow] Install via CLI is not yet implemented.")
    console.print("  For now, install apps through the Pinokio web UI:")
    console.print(f"  {_instance(host, port).base_url}/pinokio/install")
    console.print(f"  Source: [bold]{source}[/bold]")


# ── List Apps ────────────────────────────────────────────────────────

@app.command(name="list")
def list_apps(
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """List installed apps with running status."""
    async def _handler(client: Client, inst: PinokioInstance):
        # Get running scripts from info for status display
        running = set()
        try:
            scripts = await client.list_running_scripts()
            for s in scripts:
                if s.get("app"):
                    running.add(s["app"])
        except Exception:
            pass

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

    _run_client(host, port, _handler)


# ── Logs ─────────────────────────────────────────────────────────────

@app.command()
def logs(
    log_path: str = typer.Option("stdout.txt", "--path", help="Log file path"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    tail: int = typer.Option(50, "--tail", "-n", help="Number of lines to show"),
):
    """View Pinokio logs."""
    async def _handler(client: Client, inst: PinokioInstance):
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

    _run_client(host, port, _handler)


# ── Profile ──────────────────────────────────────────────────────────

@app.command()
def profile(
    name: str | None = typer.Argument(None, help="Profile name to show or delete (defaults to listing all)"),
    delete: bool = typer.Option(False, "--delete", help="Delete the profile"),
    default: bool = typer.Option(False, "--default", help="Set as default profile"),
):
    """Manage saved connection profiles. Most users won't need this —
    'pko connect' already manages a single default profile for you."""
    if name and delete:
        if remove_profile(name):
            _print_ok(f"Deleted profile [bold]{name}[/bold]")
        else:
            _print_error(f"Profile [bold]{name}[/bold] not found")
        return

    if name and default:
        if set_default_profile(name):
            _print_ok(f"Set [bold]{name}[/bold] as default profile")
        else:
            _print_error(f"Profile [bold]{name}[/bold] not found")
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
        console.print("  Create one: [bold]pko connect 192.168.1.50:42000[/bold]")
        return

    table = Table(title="Connection Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Host", style="green")
    table.add_column("Port", style="yellow")
    table.add_column("Default", style="blue")

    for p in profiles:
        table.add_row(p["name"], p["host"], str(p["port"]), "✓" if p["default"] else "—")
    console.print(table)


# ── Restart ──────────────────────────────────────────────────────────

@app.command()
def restart(
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
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


# ── Start (stub) ─────────────────────────────────────────────────────

@app.command()
def start(
    app_name: str = typer.Argument(..., help="App name to start"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """Start an app. \\[Not implemented]"""
    inst = _instance(host, port)
    console.print(f"── {_label(inst)} ──")
    console.print("[yellow]⚠[/yellow] Start via CLI is not yet implemented.")
    console.print("  This will run the app's pinokio.js script via WebSocket.")
    console.print(f"  App: [bold]{app_name}[/bold]")


# ── Status ───────────────────────────────────────────────────────────

@app.command()
def status(
    app_name: str | None = typer.Argument(None, help="App name to check (omit for --all)"),
    all_apps: bool = typer.Option(False, "--all", "-a", help="Show status for all apps"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """Check if an app is running. Use --all to show all apps."""
    async def _handler(client: Client, inst: PinokioInstance):
        show_all = all_apps or app_name is None

        if show_all:
            # --all needs the full running-scripts list anyway, so the
            # heavier /pinokio/info-backed call is the right tool here.
            running_scripts = await client.list_running_scripts()
            running_names = {s.get("app", "") for s in running_scripts if s.get("app")}

            apps = await client.list_apps_from_info()
            if not apps:
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
                    for s in running_scripts:
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

            # Check the app exists (one-time upfront lookup)
            installed = await client.list_apps_from_info()
            if not installed:
                installed = await client.list_apps()
            installed_ids = {_app_identifier(a) for a in installed}

            if app_name not in installed_ids:
                _print_error(f"App [bold]{app_name}[/bold] not found")
                console.print(f"  Installed apps: {', '.join(sorted(installed_ids))}")
                raise typer.Exit(1)

            # Single-app check uses /apps/status/:id (HTTP, one call,
            # returns running+ready+URL+metadata) rather than the
            # WebSocket check_status() probe or the heavy
            # /pinokio/info system-diagnostics call — see PLAN.md
            # ADR-004/ADR-005 (discovered via vendored pterm/util.js).
            app_status = await client.get_app_status(app_name)
            if app_status is None:
                _print_error(f"Could not get status for [bold]{app_name}[/bold]")
                raise typer.Exit(1)

            is_running = bool(app_status.get("running", False))
            if is_running:
                ready_url = app_status.get("ready_url", "")
                msg = f"[bold]{app_name}[/bold] is running"
                if ready_url:
                    msg += f" [dim]({ready_url})[/dim]"
                _print_ok(msg)
            else:
                console.print(f"[yellow]⚠[/yellow] [bold]{app_name}[/bold] is not running")

    _run_client(host, port, _handler)


# ── Stop (stub) ──────────────────────────────────────────────────────

@app.command()
def stop(
    app_name: str = typer.Argument(..., help="App name to stop"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """Stop a running app. \\[Not implemented]"""
    inst = _instance(host, port)
    console.print(f"── {_label(inst)} ──")
    console.print("[yellow]⚠[/yellow] Stop via CLI is not yet implemented.")
    console.print("  This will send a stop command to pinokiod.")
    console.print(f"  App: [bold]{app_name}[/bold]")


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
