"""Tests for main_ai_researcher module."""

import os
import sys

import pytest


class TestInitAiResearcher:
    def test_init_returns_config(self, mock_env):
        from main_ai_researcher import init_ai_researcher

        config = init_ai_researcher()
        assert isinstance(config, dict)
        assert config["category"] == "vq"
        assert config["port"] == 12345
        assert config["max_iter_times"] == 0

    def test_init_default_port(self, monkeypatch):
        """PORT defaults to 12345 when unset."""
        monkeypatch.delenv("PORT", raising=False)
        monkeypatch.setenv("DEBUG", "False")
        monkeypatch.setenv("DEFAULT_LOG", "False")
        from main_ai_researcher import init_ai_researcher

        config = init_ai_researcher()
        assert config["port"] == 12345


class TestPrepareResearchArgs:
    def test_args_from_config(self, mock_env, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["test"])
        from main_ai_researcher import _prepare_research_args

        config = {
            "category": "gnn",
            "instance_id": "test_id",
            "task_level": "task2",
            "container_name": "ct",
            "workplace_name": "wp",
            "cache_path": "cp",
            "port": 9999,
            "max_iter_times": 3,
        }
        args = _prepare_research_args(config)
        assert args.port == 9999
        assert "gnn" in args.instance_path
        assert args.category == "gnn"
