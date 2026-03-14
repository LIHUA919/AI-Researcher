"""Tests for the memory subsystem (Memory, Reranker base class).

These tests avoid API calls by using the local SentenceTransformer backend.
"""

import os
import tempfile

import pytest

from research_agent.inno.memory.rag_memory import Memory, Reranker


@pytest.fixture
def memory_instance(tmp_dir):
    """Create a Memory instance backed by SentenceTransformer (no API key needed)."""
    return Memory(project_path=tmp_dir, db_name=".test_db", platform="local")


class TestMemory:
    def test_init(self, memory_instance):
        assert memory_instance.collection_name == "memory"
        assert memory_instance.client is not None

    def test_add_and_query(self, memory_instance):
        queries = [
            {"query": "How does backprop work?", "response": "Chain rule."},
            {"query": "What is attention?", "response": "Weighted sum."},
        ]
        ids = memory_instance.add_query(queries)
        assert len(ids) == 2
        assert memory_instance.count() == 2

    def test_count_empty(self, memory_instance):
        assert memory_instance.count() == 0

    def test_peek(self, memory_instance):
        queries = [{"query": "test", "response": "test_resp"}]
        memory_instance.add_query(queries)
        results = memory_instance.peek()
        assert len(results["ids"]) >= 1


class TestReranker:
    def test_reranker_is_abstract(self):
        """Reranker should inherit from ABC and cannot be instantiated if
        rerank is not implemented."""
        with pytest.raises(TypeError):
            Reranker(model="test")  # type: ignore
