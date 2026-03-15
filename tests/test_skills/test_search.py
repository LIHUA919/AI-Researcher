"""Tests for embedding-based tool search."""

import textwrap

import pytest

from research_agent.inno.skills.base import SkillManifest
from research_agent.inno.skills.search import ToolSearchIndex, ToolSearchResult


def _make_manifest(name, description, tools, tags=None):
    return SkillManifest(
        name=name,
        description=description,
        tools=tools,
        tags=tags or [],
    )


@pytest.fixture
def manifests():
    return {
        "arxiv_search": _make_manifest(
            "arxiv_search",
            "Search and download academic papers from arXiv",
            ["search_arxiv", "download_arxiv_source"],
            tags=["research", "academic", "papers"],
        ),
        "code_search": _make_manifest(
            "code_search",
            "Search GitHub for repositories and code snippets",
            ["search_github_repos", "search_github_code"],
            tags=["code", "github"],
        ),
        "planning": _make_manifest(
            "planning",
            "Plan ML experiment components: dataset, model, training, testing",
            ["plan_dataset", "plan_model"],
            tags=["ml", "experiment"],
        ),
    }


@pytest.fixture
def index(manifests):
    """Create an index using a simple hash embedder (no network required)."""
    import chromadb
    from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
    import hashlib

    class HashEmbedding(EmbeddingFunction):
        """Deterministic hash-based embedding for offline tests."""

        def __call__(self, input: Documents) -> Embeddings:
            results = []
            for doc in input:
                h = hashlib.md5(doc.encode()).digest()
                # Create a 384-dim vector from hash bytes (repeated)
                vec = [float(b) / 255.0 for b in (h * 24)]
                results.append(vec)
            return results

    idx = ToolSearchIndex.__new__(ToolSearchIndex)
    idx._model_name = "hash"
    idx._embedder = HashEmbedding()
    idx._client = chromadb.Client()
    idx._collection = idx._client.get_or_create_collection(
        name="tool_search", embedding_function=idx._embedder
    )
    idx._built = False
    idx.build_index(manifests)
    return idx


class TestBuildIndex:
    def test_builds_from_manifests(self, index):
        assert index._collection.count() == 6  # 2 + 2 + 2 tools

    def test_empty_manifests(self, index):
        index.build_index({})
        assert index._collection.count() == 0


class TestSearch:
    def test_returns_results(self, index):
        results = index.search("find academic papers", top_k=3)
        assert len(results) > 0
        # With hash embeddings, just verify results are returned with valid fields
        for r in results:
            assert r.skill_name in ("arxiv_search", "code_search", "planning")
            assert isinstance(r.tool_name, str)

    def test_top_k_limit(self, index):
        results = index.search("search", top_k=2)
        assert len(results) <= 2

    def test_empty_index_returns_empty(self, index):
        index.build_index({})
        results = index.search("anything")
        assert results == []

    def test_result_has_score(self, index):
        results = index.search("papers")
        for r in results:
            assert isinstance(r.score, float)


class TestUpdateRemove:
    def test_update_adds_new_skill(self, index):
        before = index._collection.count()
        new = _make_manifest("web_search", "Search the web", ["search_web"])
        index.update_skill(new)
        assert index._collection.count() == before + 1

    def test_remove_skill(self, index):
        before = index._collection.count()
        index.remove_skill("planning")
        assert index._collection.count() == before - 2

    def test_remove_nonexistent_is_noop(self, index):
        before = index._collection.count()
        index.remove_skill("does_not_exist")
        assert index._collection.count() == before
