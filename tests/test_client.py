"""Tests for pko HTTP client (mocked and integration)."""
from unittest.mock import patch

import httpx
import pytest

from pko.client import Client
from pko.models import PinokioInstance

LOCAL = PinokioInstance(host="localhost", port=42000, is_local=True)


#
# ── Mocked unit tests ───────────────────────────────────────────────
#


@pytest.fixture
async def client():
    """Create a client pointing at localhost:42000 but with mock transport."""
    c = Client(LOCAL)
    yield c
    await c.close()


class TestClientHealth:
    async def test_healthy(self):
        async def mock_get(*a, **kw):
            return httpx.Response(200, json={"success": True})

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            ok = await c.health()
            assert ok is True
            await c.close()

    async def test_unhealthy(self):
        async def mock_get(*a, **kw):
            raise httpx.ConnectError("refused")

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            ok = await c.health()
            assert ok is False
            await c.close()


class TestClientInfo:
    async def test_returns_system_info(self):
        mock_data = {
            "platform": "linux",
            "arch": "x64",
            "version": {"pinokiod": "8.0.36"},
            "mem": {"total": 16000000, "free": 8000000},
            "gpu": {"model": "Intel"},
            "scripts": [{"app": "comfyui", "local": {"url": "http://localhost:7860"}}],
            "home": "/home/user/pinokio",
        }
        req = httpx.Request("GET", "http://localhost:42000/pinokio/info")

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_data, request=req)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            info = await c.info()
            assert info.platform == "linux"
            assert info.version == {"pinokiod": "8.0.36"}
            assert info.memory["total"] == 16000000
            assert info.home == "/home/user/pinokio"
            assert not hasattr(info, "running_scripts")
            assert not hasattr(info, "apps")
            await c.close()


class TestClientListRunningScripts:
    async def test_returns_scripts(self):
        mock_data = {
            "scripts": [{"app": "comfyui", "local": {"url": "http://localhost:7860"}}],
        }

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_data)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            scripts = await c.list_running_scripts()
            assert len(scripts) == 1
            assert scripts[0]["app"] == "comfyui"
            await c.close()

    async def test_empty_on_error(self):
        async def mock_get(*a, **kw):
            return httpx.Response(500)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            scripts = await c.list_running_scripts()
            assert scripts == []
            await c.close()


class TestClientListApps:
    async def test_empty(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404, json={"error": "not found"})

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            apps = await c.list_apps()
            assert apps == []
            await c.close()

    async def test_with_apps(self):
        mock_data = [{"name": "comfyui", "title": "ComfyUI"}, {"name": "foo"}]
        req = httpx.Request("GET", "http://localhost:42000/pinokio/fs")

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_data, request=req)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            apps = await c.list_apps()
            assert len(apps) == 2
            assert apps[0]["name"] == "comfyui"
            await c.close()


class TestClientReadPinokioJs:
    async def test_found(self):
        mock_meta = {"title": "Test App", "description": "A test"}

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_meta)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.read_pinokio_js("testapp")
            assert meta["title"] == "Test App"
            await c.close()

    async def test_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.read_pinokio_js("nonexistent")
            assert meta is None
            await c.close()


class TestClientDelete:
    async def test_success(self):
        async def mock_post(*a, **kw):
            return httpx.Response(200, json={"success": True})

        with patch.object(httpx.AsyncClient, "post", mock_post):
            c = Client(LOCAL)
            assert await c.delete_app("testapp") is True
            await c.close()

    async def test_failure(self):
        async def mock_post(*a, **kw):
            return httpx.Response(500, json={"error": "fail"})

        with patch.object(httpx.AsyncClient, "post", mock_post):
            c = Client(LOCAL)
            assert await c.delete_app("testapp") is False
            await c.close()


class TestClientConfig:
    async def test_parses_environment_file(self):
        env_content = "KEY1=value1\nKEY2=value2\n# comment\nKEY3=value3\n"

        async def mock_get(*a, **kw):
            return httpx.Response(200, text=env_content)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            env = await c.get_config()
            assert env["KEY1"] == "value1"
            assert env["KEY2"] == "value2"
            assert env["KEY3"] == "value3"
            assert "# comment" not in env
            await c.close()

    async def test_empty_when_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            assert await c.get_config() == {}
            await c.close()


class TestClientGetAppStatus:
    async def test_running(self):
        mock_data = {
            "app_id": "testapp",
            "running": True,
            "ready_url": "http://127.0.0.1:7860",
            "title": "Test App",
        }

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_data)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            status = await c.get_app_status("testapp")
            assert status is not None
            assert status.app_id == "testapp"
            assert status.running is True
            assert status.ready_url == "http://127.0.0.1:7860"
            await c.close()

    async def test_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            status = await c.get_app_status("nonexistent")
            assert status is None
            await c.close()


class TestClientGetLogs:
    async def test_success(self):
        async def mock_get(*a, **kw):
            return httpx.Response(200, text="line1\nline2\nline3\n")

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            logs = await c.get_logs("stdout.txt")
            assert logs == "line1\nline2\nline3\n"
            await c.close()

    async def test_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(500)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            logs = await c.get_logs("nonexistent.txt")
            assert logs is None
            await c.close()


class TestClientRestart:
    async def test_success(self):
        async def mock_post(*a, **kw):
            return httpx.Response(200)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            c = Client(LOCAL)
            assert await c.restart() is True
            await c.close()

    async def test_failure(self):
        async def mock_post(*a, **kw):
            return httpx.Response(500)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            c = Client(LOCAL)
            assert await c.restart() is False
            await c.close()


class TestClientDiskUsage:
    async def test_success(self):
        async def mock_get(*a, **kw):
            return httpx.Response(200, text="1.2GB")

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            du = await c.disk_usage("testapp")
            assert du == "1.2GB"
            await c.close()

    async def test_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            du = await c.disk_usage("nonexistent")
            assert du is None
            await c.close()

    async def test_json_bytes(self):
        """Raw JSON response like {\"du\": 218911011} is parsed and formatted."""
        async def mock_get(*a, **kw):
            return httpx.Response(200, json={"du": 218911011})

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            du = await c.disk_usage("testapp")
            assert du == "208.8 MB"
            await c.close()

    async def test_json_bytes_string(self):
        """Raw JSON with du as a string of digits."""
        async def mock_get(*a, **kw):
            return httpx.Response(200, json={"du": "6638810876"})

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            du = await c.disk_usage("testapp")
            assert du == "6.2 GB"
            await c.close()


class TestFormatBytes:
    def test_zero(self):
        from pko.client import _format_bytes
        assert _format_bytes(0) == "0 B"

    def test_bytes(self):
        from pko.client import _format_bytes
        assert _format_bytes(500) == "500 B"

    def test_kilobytes(self):
        from pko.client import _format_bytes
        assert _format_bytes(2048) == "2.0 KB"

    def test_megabytes(self):
        from pko.client import _format_bytes
        assert _format_bytes(218911011) == "208.8 MB"

    def test_gigabytes(self):
        from pko.client import _format_bytes
        assert _format_bytes(6638810876) == "6.2 GB"

    def test_terabytes(self):
        from pko.client import _format_bytes
        assert _format_bytes(2_199_023_255_552) == "2.0 TB"


class TestExtractJsModuleFields:
    def test_extracts_fields(self):
        from pko.client import _extract_js_module_fields
        source = '''
module.exports = {
    title: "Test App",
    description: "A test app for pko",
    icon: "icon.png",
    version: "1.0.0",
    menu: async function() {}
};
'''
        result = _extract_js_module_fields(source)
        assert result is not None
        assert result["title"] == "Test App"
        assert result["description"] == "A test app for pko"
        assert result["icon"] == "icon.png"
        assert result["version"] == "1.0.0"

    def test_not_a_module(self):
        from pko.client import _extract_js_module_fields
        result = _extract_js_module_fields('{"title": "JSON"}')
        assert result is None

    def test_no_matching_fields(self):
        from pko.client import _extract_js_module_fields
        source = '''
module.exports = {
    menu: async function() { return []; }
};
'''
        result = _extract_js_module_fields(source)
        assert result is None


class TestClientListAppsStringItems:
    async def test_string_items(self):
        mock_data = [{"name": "comfyui"}, "bare-string-item"]
        req = httpx.Request("GET", "http://localhost:42000/pinokio/fs")

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_data, request=req)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            apps = await c.list_apps()
            assert len(apps) == 2
            assert apps[0]["name"] == "comfyui"
            assert apps[1]["name"] == "bare-string-item"
            await c.close()


class TestClientGetAppMetadata:

    async def test_status_and_du_both_fail(self):
        async def mock_get(*a, **kw):
            url = str(a[1]) if len(a) > 1 else ""
            if "/apps/status/" in url:
                return httpx.Response(404)
            if "/du/" in url:
                return httpx.Response(404)
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.get_app_metadata("nonexistent")
            assert meta is None
            await c.close()

    async def test_found_via_status_endpoint(self):
        mock_status = {
            "app_id": "testapp",
            "title": "Test App",
            "description": "A test",
            "icon": "icon.png",
            "path": "/pinokio/api/testapp",
            "running": True,
        }

        async def mock_get(*a, **kw):
            url = str(a[1]) if len(a) > 1 else ""
            if "/du/" in url:
                return httpx.Response(200, text="1.2GB")
            return httpx.Response(200, json=mock_status)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.get_app_metadata("testapp")
            assert meta is not None
            assert meta.name == "testapp"
            assert meta.title == "Test App"
            assert meta.description == "A test"
            assert meta.running is True
            await c.close()

    async def test_falls_back_to_pinokio_js(self):
        mock_meta = {"title": "Test App", "description": "A test", "icon": "icon.png"}

        async def mock_get(*a, **kw):
            url = str(a[1]) if len(a) > 1 else ""
            if "/apps/status/" in url:
                return httpx.Response(404)
            if "/du/" in url:
                return httpx.Response(200, text="1.2GB")
            return httpx.Response(200, json=mock_meta)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.get_app_metadata("testapp")
            assert meta is not None
            assert meta.name == "testapp"
            assert meta.title == "Test App"
            assert meta.running is False
            await c.close()

    async def test_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.get_app_metadata("nonexistent")
            assert meta is None
            await c.close()


#
# ── Integration tests (live pinokiod) ───────────────────────────────
#
# Target instance set via PKO_TEST_HOST / PKO_TEST_PORT env vars.
# Defaults to localhost:42000. Skip if unreachable — set env vars to point
# at any reachable pinokiod instance for remote testing.
#


def _test_instance() -> PinokioInstance:
    import os as _os
    host = _os.environ.get("PKO_TEST_HOST", "localhost")
    port = int(_os.environ.get("PKO_TEST_PORT", "42000"))
    return PinokioInstance(host=host, port=port, is_local=host in ("localhost", "127.0.0.1", "::1"))


@pytest.mark.integration
class TestLiveClient:
    """These tests require pinokiod running on a reachable host:port."""

    @pytest.fixture
    async def live_client(self):
        inst = _test_instance()
        c = Client(inst)
        ok = await c.health()
        if not ok:
            pytest.fail(f"pinokiod not reachable at {inst.host}:{inst.port} — set PKO_TEST_HOST/PKO_TEST_PORT")
        yield c
        await c.close()

    async def test_health(self, live_client):
        ok = await live_client.health()
        assert ok is True

    async def test_info(self, live_client):
        info = await live_client.info()
        assert info.platform in ("linux", "win32", "darwin")
        assert isinstance(info.version, dict)
        assert isinstance(info.home, str)

    async def test_port(self, live_client):
        port = await live_client.get_port()
        assert isinstance(port, int)
        assert port > 0

    async def test_list_apps(self, live_client):
        apps = await live_client.list_apps()
        assert isinstance(apps, list)

    async def test_get_config(self, live_client):
        env = await live_client.get_config()
        assert isinstance(env, dict)

    async def test_get_app_status_for_nonexistent(self, live_client):
        status = await live_client.get_app_status("definitely-not-a-real-app-xyz")
        assert status is None

    async def test_disk_usage_formatted(self, live_client):
        """Disk usage returns a human-readable string for a real app."""
        apps = await live_client.list_apps_from_info()
        assert len(apps) > 0
        app_name = apps[0]["path"]
        du = await live_client.disk_usage(app_name)
        assert du is not None
        # Should be formatted like "209 MB" or "6.6 GB" or "1234 B"
        assert any(c.isdigit() for c in du)
        assert any(unit in du for unit in ("B", "KB", "MB", "GB", "TB"))

    async def test_logs(self, live_client):
        """Logs endpoint returns None for non-existent files."""
        logs = await live_client.get_logs("definitely-not-a-real-log-file-xyz.txt")
        assert logs is None

    async def test_restart(self, live_client):
        """Restart signal is accepted by the server."""
        ok = await live_client.restart()
        assert ok is True

    async def test_app_lifecycle(self, live_client):
        """Start an app, verify it's running, stop it, verify it's stopped.

        Uses pinokio-hello-world which must be installed on the target instance.
        """
        import asyncio

        from pko.client import WsClient

        inst = _test_instance()
        apps = await live_client.list_apps_from_info()
        hello_apps = [a for a in apps if "hello-world" in str(a.get("path", ""))]
        if not hello_apps:
            pytest.fail("pinokio-hello-world not installed on target instance — install it first via pko install")

        app_name = hello_apps[0]["path"]

        # Resolve the script path
        script_uri = await live_client.resolve_script_path(app_name, "start.js")

        # If the app is already running, stop it first
        status = await live_client.get_app_status(app_name)
        if status and status.running:
            ws = WsClient(inst)
            try:
                async with asyncio.timeout(10):
                    await ws.stop_script(script_uri)
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(1)

        # Start the app
        ws = WsClient(inst)
        try:
            async with asyncio.timeout(30):
                result_text = await ws.start_script_and_wait(script_uri)
            assert isinstance(result_text, str)
        except asyncio.TimeoutError:
            pytest.fail("Timed out waiting for app to start — check that the app is installed and pinokiod is responsive")
        finally:
            pass  # keep ws alive for now

        # Verify it's now running
        status = await live_client.get_app_status(app_name)
        assert status is not None, f"App {app_name} should be found"
        assert status.running, f"App {app_name} should be running"

        # Stop the app
        try:
            async with asyncio.timeout(15):
                await ws.stop_script(script_uri)
        except asyncio.TimeoutError:
            pytest.fail("Timed out stopping app")

        # Give the server a moment to process the stop
        await asyncio.sleep(1)

        # Verify it's stopped
        # Note: get_app_status may still show running briefly after stop
        # We check that the running_scripts list is empty
        scripts = await live_client.list_running_scripts()
        hello_scripts = [s for s in scripts if app_name in str(s.get("app", ""))]
        assert len(hello_scripts) == 0, f"App {app_name} should not have running scripts"


@pytest.mark.integration
class TestLiveWsClient:
    """WebSocket integration tests against a live pinokiod instance."""

    @pytest.fixture
    async def live_ws(self):
        inst = _test_instance()
        from pko.client import WsClient
        ws = WsClient(inst)
        yield ws

    async def test_ws_connection(self, live_ws):
        """WebSocket connection to pinokiod can be established."""
        import asyncio
        import json

        import websockets

        inst = _test_instance()
        # Retry health check in case a restart test ran before this
        for attempt in range(5):
            c = Client(inst)
            ok = await c.health()
            await c.close()
            if ok:
                break
            if attempt < 4:
                await asyncio.sleep(2)
        else:
            pytest.fail(f"pinokiod not reachable at {inst.host}:{inst.port} — set PKO_TEST_HOST/PKO_TEST_PORT")

        # Verify the WebSocket handshake succeeds — the connection itself
        # proves the server accepts WebSocket upgrades on the same port.
        try:
            async with asyncio.timeout(10):
                async with websockets.connect(inst.ws_url) as _:
                    pass  # Connection established = handshake succeeded
        except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as e:
            pytest.fail(f"WebSocket handshake failed: {e}")

    async def test_ws_stop_nonexistent(self, live_ws):
        """Stopping a nonexistent script should not raise an error."""
        import asyncio

        inst = _test_instance()
        # Retry health check in case a restart test ran before this
        for attempt in range(5):
            c = Client(inst)
            ok = await c.health()
            await c.close()
            if ok:
                break
            if attempt < 4:
                await asyncio.sleep(2)
        else:
            pytest.fail(f"pinokiod not reachable at {inst.host}:{inst.port} — set PKO_TEST_HOST/PKO_TEST_PORT")

        from pko.client import WsClient
        ws = WsClient(inst)
        # Should not raise — stopping a script that isn't running is a no-op
        try:
            async with asyncio.timeout(10):
                await ws.stop_script("/api/nonexistent-app/start.js")
        except asyncio.TimeoutError:
            pytest.fail("WebSocket stop_script timed out")
