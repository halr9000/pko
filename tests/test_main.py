"""Tests for pko CLI commands (app.py and system.py)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from pko.client import Client
from pko.main import app
from pko.models import AppStatus, PinokioInstance, SystemInfo

runner = CliRunner()
LOCAL = PinokioInstance(host="localhost", port=42000, is_local=True)


class TestInfoCommand:
    def test_info_success(self):
        mock_info = SystemInfo(
            platform="linux",
            arch="x64",
            version={"pinokiod": "8.0.36"},
            memory={"total": 16000000, "free": 8000000},
            gpu={"model": "Intel"},
            home="/home/user/pinokio",
        )

        async def mock_health(*a, **kw):
            return True

        async def mock_info_method(*a, **kw):
            return mock_info

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "info", mock_info_method),
        ):
            result = runner.invoke(app, ["info", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 0
            assert "linux" in result.stdout
            assert "Intel" in result.stdout

    def test_info_json(self):
        mock_info = SystemInfo(
            platform="linux",
            arch="x64",
            version={"pinokiod": "8.0.36"},
            memory={"total": 16000000, "free": 8000000},
            gpu={"model": "Intel"},
            home="/home/user/pinokio",
        )

        async def mock_health(*a, **kw):
            return True

        async def mock_info_method(*a, **kw):
            return mock_info

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "info", mock_info_method),
        ):
            result = runner.invoke(app, ["info", "--json", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 0
            assert '"platform": "linux"' in result.stdout

    def test_info_connection_failed(self):
        async def mock_health(*a, **kw):
            return False

        with patch.object(Client, "health", mock_health):
            result = runner.invoke(app, ["info", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 1
            assert "Cannot connect" in result.stdout


class TestStatusCommand:
    def test_status_single_running(self):
        app_status = AppStatus(
            app_id="comfyui",
            running=True,
            ready_url="http://127.0.0.1:7860",
            title="ComfyUI",
        )

        async def mock_health(*a, **kw):
            return True

        async def mock_list_apps(*a, **kw):
            return [{"path": "comfyui", "title": "ComfyUI"}]

        async def mock_get_status(*a, **kw):
            return app_status

        async def mock_list_apps_from_info(*a, **kw):
            return [{"path": "comfyui", "title": "ComfyUI"}]

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "list_apps_from_info", mock_list_apps_from_info),
            patch.object(Client, "get_app_status", mock_get_status),
        ):
            result = runner.invoke(app, ["status", "comfyui", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 0
            assert "comfyui" in result.stdout
            assert "running" in result.stdout

    def test_status_not_found(self):
        async def mock_health(*a, **kw):
            return True

        async def mock_list_apps_from_info(*a, **kw):
            return [{"path": "other-app", "title": "Other App"}]

        async def mock_get_status(*a, **kw):
            return None

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "list_apps_from_info", mock_list_apps_from_info),
        ):
            result = runner.invoke(app, ["status", "nonexistent", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 1
            assert "not found" in result.stdout


class TestListCommand:
    def test_list_empty(self):
        async def mock_health(*a, **kw):
            return True

        async def mock_list_apps_from_info(*a, **kw):
            return []

        async def mock_list_apps(*a, **kw):
            return []

        async def mock_list_running_scripts(*a, **kw):
            return []

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "list_apps_from_info", mock_list_apps_from_info),
            patch.object(Client, "list_apps", mock_list_apps),
            patch.object(Client, "list_running_scripts", mock_list_running_scripts),
        ):
            result = runner.invoke(app, ["list", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 0
            assert "No apps installed" in result.stdout

    def test_list_with_apps(self):
        async def mock_health(*a, **kw):
            return True

        async def mock_list_apps_from_info(*a, **kw):
            return [{"path": "comfyui", "title": "ComfyUI"}]

        async def mock_list_running_scripts(*a, **kw):
            return [{"app": "comfyui", "local": {"url": "http://127.0.0.1:7860"}}]

        async def mock_read_pinokio_js(*a, **kw):
            return {"title": "ComfyUI", "description": "Stable Diffusion UI"}

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "list_apps_from_info", mock_list_apps_from_info),
            patch.object(Client, "list_running_scripts", mock_list_running_scripts),
            patch.object(Client, "read_pinokio_js", mock_read_pinokio_js),
        ):
            result = runner.invoke(app, ["list", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 0
            assert "comfyui" in result.stdout
            assert "running" in result.stdout


class TestVersionCommand:
    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "pko v" in result.stdout


class TestConnectCommand:
    def test_connect(self):
        with patch("pko.main.add_profile") as mock_add:
            result = runner.invoke(app, ["connect", "192.168.1.50:42000"])
            assert result.exit_code == 0
            mock_add.assert_called_once_with("192.168.1.50", 42000, name="default", set_default=True)
            assert "Saved" in result.stdout


class TestProfileCommand:
    def test_profile_list_empty(self):
        with patch("pko.main.list_profiles", return_value=[]):
            result = runner.invoke(app, ["profile"])
            assert result.exit_code == 0
            assert "No profiles" in result.stdout

    def test_profile_list(self):
        profiles = [
            {"name": "default", "host": "10.0.0.1", "port": 42000, "default": True},
        ]
        with patch("pko.main.list_profiles", return_value=profiles):
            result = runner.invoke(app, ["profile"])
            assert result.exit_code == 0
            assert "default" in result.stdout
            assert "10.0.0.1" in result.stdout


class TestDiscoverCommand:
    def test_discover_local_none(self):
        async def mock_discover(*a, **kw):
            return []

        with patch("pko.main.discover_local", mock_discover):
            result = runner.invoke(app, ["discover", "--host", "localhost"])
            assert result.exit_code == 0
            assert "No Pinokio instances" in result.stdout


class TestRestartCommand:
    def test_restart_force(self):
        async def mock_health(*a, **kw):
            return True

        async def mock_restart(*a, **kw):
            return True

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "restart", mock_restart),
        ):
            result = runner.invoke(app, ["restart", "--force", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 0
            assert "Restart signal sent" in result.stdout


class TestConfigCommand:
    def test_config_get(self):
        async def mock_health(*a, **kw):
            return True

        async def mock_get_config(*a, **kw):
            return {"KEY1": "value1", "KEY2": "value2"}

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "get_config", mock_get_config),
        ):
            result = runner.invoke(app, ["config", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 0
            assert "KEY1" in result.stdout
            assert "value1" in result.stdout


class TestLogsCommand:
    def test_logs_success(self):
        async def mock_health(*a, **kw):
            return True

        async def mock_get_app_logs(*a, **kw):
            return {
                "text": "line1\nline2\nline3\n",
                "lines": ["line1", "line2", "line3"],
                "line_count": 3,
                "size": 18,
                "modified": "2026-07-21T16:58:48.537Z",
            }

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "get_app_logs", mock_get_app_logs),
        ):
            result = runner.invoke(app, ["logs", "testapp", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 0
            assert "line1" in result.stdout


class TestDeleteCommand:
    def test_delete_force(self):
        async def mock_health(*a, **kw):
            return True

        async def mock_delete(*a, **kw):
            return True

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "delete_app", mock_delete),
        ):
            result = runner.invoke(app, ["delete", "testapp", "--force", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 0
            assert "Deleted" in result.stdout


class TestInspectCommand:
    def test_inspect_success(self):
        from pko.models import AppInfo

        app_info = AppInfo(
            name="comfyui",
            path="comfyui",
            title="ComfyUI",
            description="Stable Diffusion UI",
            icon="icon.png",
            running=True,
            disk_usage="1.2GB",
        )

        async def mock_health(*a, **kw):
            return True

        async def mock_get_metadata(*a, **kw):
            return app_info

        with (
            patch.object(Client, "health", mock_health),
            patch.object(Client, "get_app_metadata", mock_get_metadata),
        ):
            result = runner.invoke(app, ["inspect", "comfyui", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 0
            assert "ComfyUI" in result.stdout
            assert "running" in result.stdout


class TestInstallCommand:
    def test_install_local_git_not_found(self):
        """Test install handles git not on PATH."""
        with (
            patch("pko.app.resolve_instance") as mock_resolve,
            patch("pko.app.subprocess.run") as mock_run,
        ):
            mock_resolve.return_value = PinokioInstance(
                host="localhost", port=42000, source="cli", is_local=True
            )
            mock_run.side_effect = FileNotFoundError("git not found")
            result = runner.invoke(app, ["install", "https://github.com/user/repo", "--host", "localhost"])
            assert result.exit_code == 1
            assert "git is not installed" in result.stdout.lower()

    def test_install_remote_prints_instructions(self):
        """Test install on remote instance prints web UI instructions."""
        with patch("pko.app.resolve_instance") as mock_resolve:
            mock_resolve.return_value = PinokioInstance(
                host="10.0.0.1", port=42000, source="cli", is_local=False
            )
            result = runner.invoke(app, ["install", "https://github.com/user/repo", "--host", "10.0.0.1"])
            assert result.exit_code == 0
            assert "not yet supported" in result.stdout.lower()


class TestStartCommand:
    def test_start_connection_refused(self):
        """Test start handles connection failure gracefully."""
        with (
            patch("pko.app.resolve_instance") as mock_resolve,
            patch.object(Client, "health", new_callable=AsyncMock, return_value=True),
            patch.object(Client, "info") as mock_info,
            patch.object(Client, "close", new_callable=AsyncMock),
            patch("pko.app.WsClient") as mock_ws_cls,
        ):
            mock_info.return_value = SystemInfo(
                home="/home/user/pinokio",
                platform="linux",
                arch="x64",
            )
            mock_ws = mock_ws_cls.return_value
            mock_ws.run_script.side_effect = Exception("Connection refused")
            mock_resolve.return_value = PinokioInstance(
                host="localhost", port=42000, source="cli", is_local=True
            )
            result = runner.invoke(app, ["start", "testapp", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 1
            assert "Failed to start" in result.stdout


class TestStopCommand:
    def test_stop_connection_refused(self):
        """Test stop handles connection failure gracefully."""
        with (
            patch("pko.app.resolve_instance") as mock_resolve,
            patch.object(Client, "health", new_callable=AsyncMock, return_value=True),
            patch.object(Client, "info") as mock_info,
            patch.object(Client, "close", new_callable=AsyncMock),
            patch("pko.app.WsClient") as mock_ws_cls,
        ):
            mock_info.return_value = SystemInfo(
                home="/home/user/pinokio",
                platform="linux",
                arch="x64",
            )
            mock_ws = mock_ws_cls.return_value
            mock_ws.stop_script.side_effect = Exception("Connection refused")
            mock_resolve.return_value = PinokioInstance(
                host="localhost", port=42000, source="cli", is_local=True
            )
            result = runner.invoke(app, ["stop", "testapp", "--host", "localhost", "--port", "42000"])
            assert result.exit_code == 1


@pytest.mark.integration
class TestLiveAppLifecycle:
    """End-to-end CLI tests against a live pinokiod instance.

    Requires pinokio-hello-world installed on the target instance.
    """

    @pytest.fixture
    def live_args(self):
        import os as _os

        host = _os.environ.get("PKO_TEST_HOST", "localhost")
        port = int(_os.environ.get("PKO_TEST_PORT", "42000"))
        args = ["--host", host, "--port", str(port)]

        # Must be reachable — integration tests fail not skip
        import httpx
        try:
            r = httpx.get(f"http://{host}:{port}/check", timeout=3)
            ok = r.status_code == 200 and r.json().get("success") is True
        except Exception:
            ok = False
        if not ok:
            pytest.fail(f"pinokiod not reachable at {host}:{port} — set PKO_TEST_HOST/PKO_TEST_PORT")

        return args

    def test_live_list(self, live_args):
        args = live_args
        result = runner.invoke(app, ["list"] + args)
        assert result.exit_code == 0
        assert "hello-world" in result.stdout.lower() or "Hello" in result.stdout

    def test_live_status_all(self, live_args):
        args = live_args
        result = runner.invoke(app, ["status", "--all"] + args)
        assert result.exit_code == 0

    def test_live_info(self, live_args):
        args = live_args
        result = runner.invoke(app, ["info"] + args)
        assert result.exit_code == 0
        assert "Platform" in result.stdout or "win32" in result.stdout or "linux" in result.stdout