"""Shared fixtures for quickrun-mcp tests."""

import os
import pytest

from quickrun_mcp.config import Config
from quickrun_mcp.executor import PersistentWorker, StatelessExecutor


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "artifacts").mkdir()
    (ws / "tmp").mkdir()
    return ws


@pytest.fixture
def allowed_folder(tmp_path):
    folder = tmp_path / "allowed"
    folder.mkdir()
    return folder


@pytest.fixture
def config(workspace, allowed_folder, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("ALLOWED_FOLDERS", str(allowed_folder))
    monkeypatch.setenv("DEFAULT_TIMEOUT", "30")
    monkeypatch.setenv("MAX_OUTPUT_CHARS", str(60 * 1024))
    monkeypatch.setenv("ALLOW_NETWORK", "true")
    return Config()


@pytest.fixture
async def basic_worker(config):
    w = PersistentWorker(config, with_write=False)
    yield w
    await w.cleanup()


@pytest.fixture
async def write_worker(config):
    w = PersistentWorker(config, with_write=True)
    yield w
    await w.cleanup()


@pytest.fixture
def stateless_ro(config):
    return StatelessExecutor(config, with_write=False)


@pytest.fixture
def stateless_rw(config):
    return StatelessExecutor(config, with_write=True)
