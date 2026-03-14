import os
import tempfile

import pytest


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def mock_env(monkeypatch):
    """Set up minimal env vars needed by the research agent config."""
    monkeypatch.setenv("CATEGORY", "vq")
    monkeypatch.setenv("INSTANCE_ID", "rotation_vq")
    monkeypatch.setenv("TASK_LEVEL", "task1")
    monkeypatch.setenv("CONTAINER_NAME", "paper_eval")
    monkeypatch.setenv("WORKPLACE_NAME", "workplace")
    monkeypatch.setenv("CACHE_PATH", "cache")
    monkeypatch.setenv("PORT", "12345")
    monkeypatch.setenv("MAX_ITER_TIMES", "0")
    monkeypatch.setenv("DEBUG", "False")
    monkeypatch.setenv("DEFAULT_LOG", "False")
