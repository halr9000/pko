"""pko — Pinokio CLI.

Usage:
    pko [--host HOST] [--port PORT] <command> [options]
"""

from __future__ import annotations

import asyncio

import typer

from . import __version__
from .app import delete as _delete
from .app import inspect as _inspect
from .app import install as _install
from .app import list_apps
from .app import start as _start
from .app import status as _status
from .app import stop as _stop
from .config import add_profile, get_profile, list_profiles, remove_profile, set_default_profile
from .discover import discover_local, discover_remote
from .models import DEFAULT_PORT, KNOWN_PORTS
from .system import config as _config
from .system import info as _info
from .system import logs as _logs
from .system import restart as _restart
from .ui import console, print_error, print_ok

app = typer.Typer(
    name="pko",
    help=(
        "Pinokio CLI -- automate Pinokio instances from anywhere. "
        "See 'pko COMMAND --help' for details."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# Commands are defined in alphabetical order (by command name) so
# `pko --help` lists them alphabetically without needing manual grouping.


# ── Config ───────────────────────────────────────────────────────────

@app.command(rich_help_panel="System")
def config(
    key: str | None = typer.Argument(None, help="Config key to get"),
    value: str | None = typer.Argument(None, help="Config value to set"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get or set Pinokio configuration values."""
    _config(key=key, value=value, host=host, port=port, json_output=json_output)


# ── Connect ──────────────────────────────────────────────────────────

@app.command(rich_help_panel="Discovery")
def connect(
    address: str = typer.Argument(..., help="Host:port (e.g., '192.168.1.50:42000')"),
    name: str = typer.Option("default", "--name", help="Profile name (rarely needed -- most users can ignore this)"),
):
    """Save a known Pinokio server and set it as the default."""
    parts = address.split(":")
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else DEFAULT_PORT

    add_profile(host, port, name=name, set_default=True)
    label_str = f"{host}:{port}" if name == "default" else f"{name} ({host}:{port})"
    print_ok(f"Saved [bold]{label_str}[/bold] [dim](now default)[/dim]")


# ── Delete ───────────────────────────────────────────────────────────

@app.command(rich_help_panel="App Lifecycle")
def delete(
    app_name: str = typer.Argument(..., help="App name to delete"),
    delete_type: str = typer.Option("bin", "--type", "-t", help="What to delete: bin, cache, env, browser-cache"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete an app or its components."""
    _delete(app_name=app_name, delete_type=delete_type, host=host, port=port, force=force)


# ── Discover ─────────────────────────────────────────────────────────

@app.command(rich_help_panel="Discovery")
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
            print_error("No Pinokio instances found")
            console.print("\nTips:")
            console.print("  . Make sure Pinokio is running")
            console.print("  . Try a specific host: [bold]pko discover --host 192.168.1.50[/bold]")
            console.print("  . Or connect directly: [bold]pko connect 192.168.1.50:42000[/bold]")
            return

        from rich.table import Table
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
                "\u2713" if inst.is_local else "--",
            )
        console.print(table)

        if save:
            first = instances[0]
            add_profile(first.host, first.port, set_default=True)
            print_ok(f"Saved [bold]{first.host}:{first.port}[/bold] [dim](now default)[/dim]")
        else:
            console.print("\n[dim]Save a host for quick access:[/dim]")
            console.print("  [bold]pko connect <host>:<port>[/bold]  (or re-run with --save)")

    asyncio.run(run())


# ── Info ─────────────────────────────────────────────────────────────

@app.command(rich_help_panel="System")
def info(
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show Pinokio system information (diagnostics only)."""
    _info(host=host, port=port, json_output=json_output)


# ── Inspect ──────────────────────────────────────────────────────────

@app.command(rich_help_panel="App Lifecycle")
def inspect(
    app_name: str = typer.Argument(..., help="App name to inspect"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show detailed metadata for an installed app (title, description, disk usage, running state)."""
    _inspect(app_name=app_name, host=host, port=port, json_output=json_output)


# ── Install ──────────────────────────────────────────────────────────

@app.command(rich_help_panel="App Lifecycle")
def install(
    source: str = typer.Argument(..., help="Git URL or org/repo shorthand"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """Install an app from a git repository."""
    _install(source=source, host=host, port=port)


# ── List ─────────────────────────────────────────────────────────────

@app.command(name="list", rich_help_panel="App Lifecycle")
def list_cmd(
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """List installed apps with running status."""
    list_apps(host=host, port=port)


# ── Logs ─────────────────────────────────────────────────────────────

@app.command(rich_help_panel="System")
def logs(
    app_name: str | None = typer.Argument(None, help="App name to view logs for"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    script: str = typer.Option("start.js", "--script", "-s", help="Script name (default: start.js)"),
    tail: int = typer.Option(50, "--tail", "-n", help="Number of lines to show"),
    list_logs: bool = typer.Option(False, "--list", "-l", help="List available logs for all apps"),
):
    """View Pinokio logs. Provide an app name to view its logs, or use --list to enumerate."""
    _logs(app_name=app_name, host=host, port=port, script=script, tail=tail, list_logs=list_logs)


# ── Profile ──────────────────────────────────────────────────────────

@app.command(rich_help_panel="Discovery")
def profile(
    name: str | None = typer.Argument(None, help="Profile name to show or delete (defaults to listing all)"),
    delete_: bool = typer.Option(False, "--delete", help="Delete the profile"),
    default: bool = typer.Option(False, "--default", help="Set as default profile"),
):
    """Manage saved connection profiles. Most users won't need this --
    'pko connect' already manages a single default profile for you."""
    if name and delete_:
        if remove_profile(name):
            print_ok(f"Deleted profile [bold]{name}[/bold]")
        else:
            print_error(f"Profile [bold]{name}[/bold] not found")
        return

    if name and default:
        if set_default_profile(name):
            print_ok(f"Set [bold]{name}[/bold] as default profile")
        else:
            print_error(f"Profile [bold]{name}[/bold] not found")
        return

    if name:
        profile_data = get_profile(name)
        if not profile_data:
            print_error(f"Profile [bold]{name}[/bold] not found")
            return
        from rich.panel import Panel
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

    from rich.table import Table
    table = Table(title="Connection Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Host", style="green")
    table.add_column("Port", style="yellow")
    table.add_column("Default", style="blue")

    for p in profiles:
        table.add_row(p["name"], p["host"], str(p["port"]), "\u2713" if p["default"] else "--")
    console.print(table)


# ── Restart ──────────────────────────────────────────────────────────

@app.command(rich_help_panel="System")
def restart(
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Restart the Pinokio server."""
    _restart(host=host, port=port, force=force)


# ── Start ────────────────────────────────────────────────────────────

@app.command(rich_help_panel="App Lifecycle")
def start(
    app_name: str = typer.Argument(..., help="App name to start"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    script: str = typer.Option("index.json", "--script", help="Script to run (default: index.json)"),
):
    """Start an app via WebSocket. Streams output to console."""
    _start(app_name=app_name, host=host, port=port, script=script)


# ── Status ───────────────────────────────────────────────────────────

@app.command(rich_help_panel="App Lifecycle")
def status(
    app_name: str | None = typer.Argument(None, help="App name to check (omit for --all)"),
    all_apps: bool = typer.Option(False, "--all", "-a", help="Show status for all apps"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
):
    """Check if an app is running. Use --all to show all apps."""
    _status(app_name=app_name, all_apps=all_apps, host=host, port=port)


# ── Stop ─────────────────────────────────────────────────────────────

@app.command(rich_help_panel="App Lifecycle")
def stop(
    app_name: str = typer.Argument(..., help="App name to stop"),
    host: str | None = typer.Option(None, "--host", help="Pinokio host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Pinokio port"),
    script: str = typer.Option("index.json", "--script", help="Script to stop (default: index.json)"),
):
    """Stop a running app via WebSocket."""
    _stop(app_name=app_name, host=host, port=port, script=script)


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