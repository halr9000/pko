"""Tests for pko config module (profiles)."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pko.config import (
    load_config,
    save_config,
    get_profile,
    set_profile,
    list_profiles,
    remove_profile,
    get_default_instance,
)
from pko.models import PinokioInstance


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
        assert cfg == {"profiles": {}, "default_profile": "default"}

    def test_save_and_load(self):
        cfg = {"profiles": {"test": {"host": "10.0.0.1", "port": 42000}}, "default_profile": "test"}
        save_config(cfg)
        loaded = load_config()
        assert loaded["profiles"]["test"]["host"] == "10.0.0.1"
        assert loaded["default_profile"] == "test"


class TestProfileCRUD:
    def test_set_and_get_profile(self):
        inst = PinokioInstance(host="192.168.1.50", port=42000, name="myserver")
        set_profile("myserver", inst)
        profile = get_profile("myserver")
        assert profile["host"] == "192.168.1.50"
        assert profile["port"] == 42000

    def test_get_nonexistent(self):
        assert get_profile("nope") is None

    def test_list_profiles(self):
        set_profile("a", PinokioInstance(host="10.0.0.1", port=42000))
        set_profile("b", PinokioInstance(host="10.0.0.2", port=42001))
        profiles = list_profiles()
        assert len(profiles) == 2
        names = [p["name"] for p in profiles]
        assert "a" in names
        assert "b" in names

    def test_remove_profile(self):
        set_profile("x", PinokioInstance(host="10.0.0.1", port=42000))
        assert remove_profile("x") is True
        assert get_profile("x") is None

    def test_remove_nonexistent(self):
        assert remove_profile("ghost") is False


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