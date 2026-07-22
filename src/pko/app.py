"""App lifecycle CLI commands for pko."""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import typer

from .client import Client, WsClient, run_client
from .discover import resolve_instance
from .models import PinokioInstance
from .ui import app_identifier, console, label, print_error, print_ok


def _run(handler, host: str | None, port: int | None) -> None:
    """Resolve instance, connect, health-check, then call handler(client, inst)."""
    inst = resolve_instance(host, port)
    console.print(f"-- {label(inst)} --")

    async def run():
        ok = await run_client(inst, handler)
        if not ok:
            print_error(f"Cannot connect to {inst.base_url}")
            raise typer.Exit(1)

    asyncio.run(run())


# ── List ────────────────────────────────────────────────────────────


def list_apps(
    host: str | None = None,
    port: int | None = None,
) -> None:
    """List installed apps with running status."""
    async def handler(client: Client, inst: PinokioInstance):
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

        from rich.table import Table
        table = Table(title=f"Installed Apps ({len(apps)})")
        table.add_column("Name", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Status", style="green")

        for app in apps:
            app_id = app_identifier(app)
            title = app.get("title", app_id)
            is_running = app_id in running

            try:
                meta = await client.read_pinokio_js(app_id)
                if meta:
                    title = meta.get("title", meta.get("name", title))
            except Exception:
                pass
            status = "[green]running[/green]" if is_running else "--"
            table.add_row(app_id, title, status)

        console.print(table)

    _run(handler, host, port)


# ── Status ──────────────────────────────────────────────────────────


def status(
    app_name: str | None = None,
    all_apps: bool = False,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Check if an app is running. Use --all to show all apps."""
    async def handler(client: Client, inst: PinokioInstance):
        show_all = all_apps or app_name is None

        if show_all:
            running_scripts = await client.list_running_scripts()
            running_names = {s.get("app", "") for s in running_scripts if s.get("app")}

            apps = await client.list_apps_from_info()
            if not apps:
                apps = await client.list_apps()
            if not apps:
                console.print("[yellow]No apps installed.[/yellow]")
                return

            from rich.table import Table
            table = Table(title="App Status")
            table.add_column("App", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("URL", style="yellow")

            for app in apps:
                app_id = app_identifier(app)
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
                print_error("Specify an app name or use --all")
                raise typer.Exit(1)

            installed = await client.list_apps_from_info()
            if not installed:
                installed = await client.list_apps()
            installed_ids = {app_identifier(a) for a in installed}

            if app_name not in installed_ids:
                print_error(f"App [bold]{app_name}[/bold] not found")
                console.print(f"  Installed apps: {', '.join(sorted(installed_ids))}")
                raise typer.Exit(1)

            app_status = await client.get_app_status(app_name)
            if app_status is None:
                print_error(f"Could not get status for [bold]{app_name}[/bold]")
                raise typer.Exit(1)

            if app_status.running:
                msg = f"[bold]{app_name}[/bold] is running"
                if app_status.ready_url:
                    msg += f" [dim]({app_status.ready_url})[/dim]"
                print_ok(msg)
            else:
                console.print(f"[yellow]&#9888;[/yellow] [bold]{app_name}[/bold] is not running")

    _run(handler, host, port)


# ── Inspect ──────────────────────────────────────────────────────────


def inspect(
    app_name: str,
    host: str | None = None,
    port: int | None = None,
    json_output: bool = False,
) -> None:
    """Show detailed metadata for an installed app (title, description, disk usage, running state)."""
    async def handler(client: Client, inst: PinokioInstance):
        meta = await client.get_app_metadata(app_name)
        if meta is None:
            print_error(f"App [bold]{app_name}[/bold] not found")
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

        from rich.panel import Panel
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

    _run(handler, host, port)


# ── Install ──────────────────────────────────────────────────────────


def install(
    source: str,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Install an app from a git repository.

    Clones the repo into the Pinokio API directory. For local instances
    the clone is direct; for remote instances instructions are printed.
    """
    inst = resolve_instance(host, port)

    # Extract app name from git URL
    app_name = source.rstrip("/").split("/")[-1]
    if app_name.endswith(".git"):
        app_name = app_name[:-4]

    console.print(f"-- {label(inst)} --")

    if inst.is_local:
        # Local install: clone directly to pinokio api dir
        pinokio_home = Path.home() / "pinokio" / "api" / app_name
        if pinokio_home.exists():
            console.print(f"[yellow]&#9888;[/yellow] App [bold]{app_name}[/bold] already exists at {pinokio_home}")
            overwrite = typer.confirm("Overwrite?")
            if not overwrite:
                console.print("[yellow]Cancelled.[/yellow]")
                raise typer.Exit()

        console.print(f"Cloning [bold]{source}[/bold] to [bold]{pinokio_home}[/bold]...")
        try:
            result = subprocess.run(
                ["git", "clone", source, str(pinokio_home)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                print_error(f"Clone failed: {result.stderr.strip()}")
                raise typer.Exit(1)
            print_ok(f"Installed [bold]{app_name}[/bold]")
        except FileNotFoundError:
            print_error("git is not installed or not on PATH")
            console.print("  Install git and try again, or use the Pinokio web UI:")
            console.print(f"  {inst.base_url}/pinokio/install")
            console.print(f"  Source: [bold]{source}[/bold]")
            raise typer.Exit(1)
        except subprocess.TimeoutExpired:
            print_error("Clone timed out (120s)")
            raise typer.Exit(1)
    else:
        # Remote install: print instructions
        console.print("[yellow]&#9888;[/yellow] Remote install via CLI is not yet supported.")
        console.print("  Install through the Pinokio web UI:")
        console.print(f"  {inst.base_url}/pinokio/install")
        console.print(f"  Source: [bold]{source}[/bold]")


# ── Start ────────────────────────────────────────────────────────────


def start(
    app_name: str,
    host: str | None = None,
    port: int | None = None,
    script: str = "index.json",
) -> None:
    """Start an app via WebSocket.

    Runs the app's script (default: index.json) and streams output to the console.
    Press Ctrl+C to stop streaming (the app continues running in the background).
    """
    inst = resolve_instance(host, port)

    console.print(f"-- {label(inst)} --")
    console.print(f"Starting [bold]{app_name}[/bold]...")

    async def run():
        # Resolve the absolute script path from pinokio home
        client = Client(inst)
        try:
            ok = await client.health()
            if not ok:
                print_error(f"Cannot connect to {inst.base_url}")
                raise typer.Exit(1)
            abs_uri = await client.resolve_script_path(app_name, script)
        finally:
            await client.close()

        console.print(f"  [dim]Script: {abs_uri}[/dim]")

        ws = WsClient(inst)
        try:
            async for packet in ws.run_script(uri=abs_uri):
                if packet.type == "stream":
                    text = packet.data.get("data", "")
                    if text:
                        console.print(text, end="")
                elif packet.type == "error":
                    error_msg = packet.data.get("message", str(packet.data))
                    print_error(f"Script error: {error_msg}")
                elif packet.type == "result":
                    result_data = packet.data
                    if result_data:
                        console.print(f"\n[dim]Result: {result_data}[/dim]")
                elif packet.type == "start":
                    console.print("[dim]Script started[/dim]")
                elif packet.type == "disconnect":
                    console.print("\n[dim]Connection closed[/dim]")
                    break
        except typer.Exit:
            raise
        except Exception as e:
            print_error(f"Failed to start app: {e}")
            raise typer.Exit(1)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped streaming (app continues running in background)[/yellow]")


# ── Stop ─────────────────────────────────────────────────────────────


def stop(
    app_name: str,
    host: str | None = None,
    port: int | None = None,
    script: str = "index.json",
) -> None:
    """Stop a running app via WebSocket."""
    inst = resolve_instance(host, port)

    console.print(f"-- {label(inst)} --")
    console.print(f"Stopping [bold]{app_name}[/bold]...")

    async def run():
        # Resolve the absolute script path
        client = Client(inst)
        try:
            ok = await client.health()
            if not ok:
                print_error(f"Cannot connect to {inst.base_url}")
                raise typer.Exit(1)
            abs_uri = await client.resolve_script_path(app_name, script)
        finally:
            await client.close()

        ws = WsClient(inst)
        try:
            await ws.stop_script(abs_uri)
            print_ok(f"Stop signal sent to [bold]{app_name}[/bold]")
        except Exception as e:
            print_error(f"Failed to stop app: {e}")
            raise typer.Exit(1)

    asyncio.run(run())


# ── Delete ───────────────────────────────────────────────────────────


def delete(
    app_name: str,
    delete_type: str = "bin",
    host: str | None = None,
    port: int | None = None,
    force: bool = False,
) -> None:
    """Delete an app or its components."""
    if not force:
        confirm = typer.confirm(f"Delete {delete_type} for [bold]{app_name}[/bold]?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

    async def handler(client: Client, inst: PinokioInstance):
        success = await client.delete_app(app_name, delete_type)
        if success:
            print_ok(f"Deleted {delete_type} for [bold]{app_name}[/bold]")
        else:
            print_error(f"Failed to delete {delete_type} for [bold]{app_name}[/bold]")

    _run(handler, host, port)