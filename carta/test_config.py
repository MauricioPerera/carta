"""Tests for carta.config — global config store."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from carta.config import get, inject_env, load, save, set_value, unset


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Redirect the config dir to a temp path for every test."""
    import carta.config as _cfg_mod
    monkeypatch.setattr(_cfg_mod, "_CONFIG_DIR", tmp_path / ".carta")
    monkeypatch.setattr(_cfg_mod, "_CONFIG_FILE", tmp_path / ".carta" / "config.yaml")


def test_load_empty_when_no_file():
    assert load() == {}


def test_set_and_get():
    set_value("api_key", "sk-abc")
    assert get("api_key") == "sk-abc"


def test_get_default_when_missing():
    assert get("api_key", "fallback") == "fallback"


def test_set_overwrites():
    set_value("api_key", "first")
    set_value("api_key", "second")
    assert get("api_key") == "second"


def test_unset_existing():
    set_value("api_key", "sk-xyz")
    removed = unset("api_key")
    assert removed is True
    assert get("api_key") == ""


def test_unset_missing():
    removed = unset("api_key")
    assert removed is False


def test_multiple_keys():
    set_value("api_key", "sk-1")
    set_value("preset", "ollama-cloud")
    cfg = load()
    assert cfg["api_key"] == "sk-1"
    assert cfg["preset"] == "ollama-cloud"


def test_inject_env_sets_ollama_api_key(monkeypatch):
    set_value("api_key", "sk-injected")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    inject_env()
    assert os.environ.get("OLLAMA_API_KEY") == "sk-injected"


def test_inject_env_does_not_overwrite_existing(monkeypatch):
    set_value("api_key", "sk-from-config")
    monkeypatch.setenv("OLLAMA_API_KEY", "sk-from-shell")
    inject_env()
    assert os.environ.get("OLLAMA_API_KEY") == "sk-from-shell"


def test_inject_env_noop_when_no_config(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    inject_env()
    assert os.environ.get("OLLAMA_API_KEY") is None


def test_config_dir_created_on_save(tmp_path, monkeypatch):
    import carta.config as _cfg_mod
    new_dir = tmp_path / "nested" / ".carta"
    monkeypatch.setattr(_cfg_mod, "_CONFIG_DIR", new_dir)
    monkeypatch.setattr(_cfg_mod, "_CONFIG_FILE", new_dir / "config.yaml")
    set_value("api_key", "sk-abc")
    assert (new_dir / "config.yaml").exists()
