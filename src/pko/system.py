"""System and config CLI commands for pko."""
from __future__ import annotations

import asyncio
import json

import typer

from .client import Client, run_client
from .discover import resolve_instance
from .models import PinokioInstance
from .ui import console, label, print_error, print_ok


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


# ── Info ─────────────────────────────────────────────────────────────


def info(
    host: str | None = None,
    port: int | None = None,
    json_output: bool = False,
) -> None:
    """Show Pinokio system information (diagnostics only)."""
    async def handler(client: Client, inst: PinokioInstance):
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

        from rich.panel import Panel
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

    _run(handler, host, port)


# ── Config ───────────────────────────────────────────────────────────


def config(
    key: str | None = None,
    value: str | None = None,
    host: str | None = None,
    port: int | None = None,
    json_output: bool = False,
) -> None:
    """Get or set Pinokio configuration values."""
    async def handler(client: Client, inst: PinokioInstance):
        if key and value is not None:
            print_error("Setting config via CLI not yet supported -- use the web UI at /env")
            console.print("  Config values are stored in the Pinokio ENVIRONMENT file.")
            console.print(f"  To set [bold]{key}={value}[/bold], edit the ENVIRONMENT file in your Pinokio home directory")
            return

        env = await client.get_config()

        if json_output:
            console.print(json.dumps(env, indent=2))
            return

        if key:
            if key in env:
                console.print(f"{key}={env[key]}")
            else:
                print_error(f"Key [bold]{key}[/bold] not found in config")
            return

        from rich.table import Table
        table = Table(title=f"Pinokio Configuration @ {inst.display_label}")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")

        for k, v in sorted(env.items()):
            table.add_row(k, str(v))

        if table.row_count:
            console.print(table)
        else:
            console.print("[yellow]No configuration values found.[/yellow]")

    _run(handler, host, port)


# ── Logs ─────────────────────────────────────────────────────────────


def logs(
    app_name: str | None = None,
    host: str | None = None,
    port: int | None = None,
    script: str = "start.js",
    tail: int = 50,
    list_logs: bool = False,
) -> None:
    """View Pinokio logs. Provide an app name to view its logs, or use --list to enumerate."""
    async def _list_handler(client: Client, inst: PinokioInstance):
        """Show available logs for each installed app."""
        from rich.table import Table

        apps = await client.list_apps_from_info()
        if not apps:
            apps = await client.list_apps()
        if not apps:
            console.print("[yellow]No apps installed.[/yellow]")
            return

        table = Table(title="Available Logs")
        table.add_column("App", style="cyan")
        table.add_column("Script", style="green")
        table.add_column("Lines", style="yellow")
        table.add_column("Modified", style="white")

        for app in apps:
            app_id = app.get("path") or app.get("name", "?")
            log_data = await client.get_app_logs(app_id, script=script, tail=1)
            if log_data:
                lines = log_data.get("line_count", 0)
                modified = log_data.get("modified", "")
                table.add_row(app_id, script, str(lines), modified[:19] if modified else "")
            else:
                table.add_row(app_id, script, "[dim]—[/dim]", "[dim]—[/dim]")

        console.print(table)
        console.print(f"\n[dim]Tip: [bold]pko logs <app_name>[/bold] to view a specific app's logs[/dim]")

    async def handler(client: Client, inst: PinokioInstance):
        if not app_name:
            # No app name given — show list
            await _list_handler(client, inst)
            return

        log_data = await client.get_app_logs(app_name, script=script, tail=tail)
        if log_data is None:
            print_error(f"No logs found for [bold]{app_name}[/bold] (script: {script})")
            console.print("  Try: [bold]pko logs --list[/bold] to see available apps")
            console.print("  Or: [bold]pko logs <app_name> --script <script>[/bold]")
            return

        text = log_data.get("text", "")
        lines = log_data.get("lines", [])
        modified = log_data.get("modified", "")
        from rich.panel import Panel
        console.print(Panel(
            text,
            title=f"Log: {app_name} ({script}) — {log_data.get('line_count', 0)} lines",
            subtitle=f"Modified: {modified[:19]}" if modified else None,
        ))

    if list_logs:
        _run(_list_handler, host, port)
    else:
        _run(handler, host, port)


# ── Restart ──────────────────────────────────────────────────────────


def restart(
    host: str | None = None,
    port: int | None = None,
    force: bool = False,
) -> None:
    """Restart the Pinokio server."""
    if not force:
        confirm = typer.confirm("Restart Pinokio server?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

    async def handler(client: Client, inst: PinokioInstance):
        await client.restart()
        print_ok(f"Restart signal sent to {inst.base_url}")

    _run(handler, host, port)