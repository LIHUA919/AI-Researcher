"""Embedding-based semantic search for skill tools."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Dict, List, Optional

import chromadb
from chromadb.utils import embedding_functions

from research_agent.inno.skills.base import SkillManifest


@dataclass
class ToolSearchResult:
    """A single tool search result with relevance score."""

    skill_name: str
    tool_name: str
    description: str
    score: float


class ToolSearchIndex:
    """Builds and queries an in-memory embedding index over skill tools.

    Uses the same SentenceTransformer model as the existing Memory class
    in rag_memory.py for consistency.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        try:
            self._embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=model_name
            )
        except Exception:
            self._embedder = self._hash_embed
        self._client = chromadb.Client()  # in-memory, not persistent
        self._collection = self._client.get_or_create_collection(
            name="tool_search",
            embedding_function=self._embedder,
        )
        self._built = False

    @staticmethod
    def _hash_embed(input: List[str]) -> List[List[float]]:
        """Offline-safe deterministic embedder used as a last-resort fallback."""
        results: List[List[float]] = []
        for doc in input:
            digest = hashlib.md5(doc.encode("utf-8")).digest()
            vec = [float(b) / 255.0 for b in (digest * 24)]
            results.append(vec)
        return results

    def build_index(self, manifests: Dict[str, SkillManifest]) -> None:
        """Embed all tool descriptions from scanned manifests."""
        # Reset collection
        self._client.delete_collection("tool_search")
        self._collection = self._client.get_or_create_collection(
            name="tool_search",
            embedding_function=self._embedder,
        )
        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[dict] = []

        for skill_name, manifest in manifests.items():
            tags_str = ", ".join(manifest.tags) if manifest.tags else ""
            for tool_name in manifest.tools:
                doc_id = f"{skill_name}::{tool_name}"
                doc_text = (
                    f"{tool_name}: {manifest.description}"
                    + (f" -- Tags: {tags_str}" if tags_str else "")
                )
                ids.append(doc_id)
                documents.append(doc_text)
                metadatas.append(
                    {"skill_name": skill_name, "tool_name": tool_name}
                )

        if ids:
            self._collection.add(ids=ids, documents=documents, metadatas=metadatas)
        self._built = True

    def search(self, query: str, top_k: int = 5) -> List[ToolSearchResult]:
        """Search for tools by natural language query."""
        if not self._built or self._collection.count() == 0:
            return []
        n = min(top_k, self._collection.count())
        results = self._collection.query(query_texts=[query], n_results=n)
        out: List[ToolSearchResult] = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i]
                distance = results["distances"][0][i] if results["distances"] else 0.0
                score = max(0.0, 1.0 - distance)  # convert distance to similarity
                out.append(
                    ToolSearchResult(
                        skill_name=meta["skill_name"],
                        tool_name=meta["tool_name"],
                        description=results["documents"][0][i],
                        score=score,
                    )
                )
        return out

    def update_skill(self, manifest: SkillManifest) -> None:
        """Add or update a single skill's tools in the index."""
        self.remove_skill(manifest.name)
        tags_str = ", ".join(manifest.tags) if manifest.tags else ""
        ids, documents, metadatas = [], [], []
        for tool_name in manifest.tools:
            doc_id = f"{manifest.name}::{tool_name}"
            doc_text = (
                f"{tool_name}: {manifest.description}"
                + (f" -- Tags: {tags_str}" if tags_str else "")
            )
            ids.append(doc_id)
            documents.append(doc_text)
            metadatas.append(
                {"skill_name": manifest.name, "tool_name": tool_name}
            )
        if ids:
            self._collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def remove_skill(self, skill_name: str) -> None:
        """Remove all tools for a skill from the index."""
        try:
            existing = self._collection.get(where={"skill_name": skill_name})
            if existing["ids"]:
                self._collection.delete(ids=existing["ids"])
        except Exception:
            pass
