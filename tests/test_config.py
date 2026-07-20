"""Tests for pko config module (host:port storage, no profile names)."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pko.config import (
    load_config,
    save_config,
    add_host,
    set_default_host,
    forget_host,
    list_hosts,
    get_default_instance,
)


@pytest.fixture(autouse=True)
def temp_config():
    """Use a temp config dir for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "pko"
        config_dir.mkdir(parents=True)
        with (
            patch("pko.config.CONFIG_DIR", config_dir),
            patch("pko.config.CONFIG_FILE", config_dir / "config.json"),
        ):
            yield


class TestConfigLoadSave:
    def test_load_empty(self):
        cfg = load_config()
        assert cfg == {"hosts": [], "default": None}

    def test_save_and_load(self):
        cfg = {"hosts": [{"host": "10.0.0.1", "port": 42000}], "default": {"host": "10.0.0.1", "port": 42000}}
        save_config(cfg)
        loaded = load_config()
        assert loaded["hosts"][0]["host"] == "10.0.0.1"
        assert loaded["default"]["host"] == "10.0.0.1"


class TestAddHost:
    def test_add_sets_default(self):
        add_host("192.168.1.50", 42000)
        hosts = list_hosts()
        assert len(hosts) == 1
        assert hosts[0]["host"] == "192.168.1.50"
        assert hosts[0]["default"] is True

    def test_add_duplicate_no_dupe_entry(self):
        add_host("10.0.0.1", 42000)
        add_host("10.0.0.1", 42000)
        assert len(list_hosts()) == 1

    def test_second_add_without_default_keeps_first_default(self):
        add_host("10.0.0.1", 42000, set_default=True)
        add_host("10.0.0.2", 42000, set_default=False)
        hosts = {h["host"]: h["default"] for h in list_hosts()}
        assert hosts["10.0.0.1"] is True
        assert hosts["10.0.0.2"] is False


class TestSetDefaultHost:
    def test_set_known_host(self):
        add_host("10.0.0.1", 42000)
        add_host("10.0.0.2", 42000, set_default=False)
        assert set_default_host("10.0.0.2", 42000) is True
        hosts = {h["host"]: h["default"] for h in list_hosts()}
        assert hosts["10.0.0.2"] is True
        assert hosts["10.0.0.1"] is False

    def test_set_unknown_host_fails(self):
        assert set_default_host("nope", 42000) is False


class TestForgetHost:
    def test_forget_removes_entry(self):
        add_host("10.0.0.1", 42000)
        assert forget_host("10.0.0.1", 42000) is True
        assert list_hosts() == []

    def test_forget_unknown_fails(self):
        assert forget_host("ghost", 42000) is False

    def test_forgetting_default_promotes_next(self):
        add_host("10.0.0.1", 42000)
        add_host("10.0.0.2", 42000, set_default=False)
        forget_host("10.0.0.1", 42000)
        hosts = list_hosts()
        assert len(hosts) == 1
        assert hosts[0]["default"] is True


class TestDefaultInstance:
    @patch.dict(os.environ, {}, clear=True)
    def test_fallback_to_localhost(self):
        inst = get_default_instance()
        assert inst.host == "localhost"
        assert inst.port == 42000
        assert inst.source == "default"
        assert inst.is_local is True

    @patch.dict(os.environ, {"PKO_HOST": "10.0.0.5", "PKO_PORT": "43000"}, clear=True)
    def test_env_var_overrides(self):
        inst = get_default_instance()
        assert inst.host == "10.0.0.5"
        assert inst.port == 43000
        assert inst.source == "env"

    @patch.dict(os.environ, {"PINOKIO_HOST": "10.0.0.6", "PINOKIO_PORT": "42001"}, clear=True)
    def test_pinokio_env_var_fallback(self):
        inst = get_default_instance()
        assert inst.host == "10.0.0.6"
        assert inst.port == 42001

    @patch.dict(os.environ, {}, clear=True)
    def test_uses_saved_default(self):
        add_host("10.0.0.7", 42000)
        inst = get_default_instance()
        assert inst.host == "10.0.0.7"
        assert inst.source == "config"

    @patch.dict(os.environ, {"PKO_HOST": "10.0.0.8", "PKO_PORT": "42000"}, clear=True)
    def test_env_overrides_saved_default(self):
        add_host("10.0.0.7", 42000)
        inst = get_default_instance()
        assert inst.host == "10.0.0.8"
