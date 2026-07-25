from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Protocol

from research_agent.inno.experience.ledger import ExperimentLedger
from research_agent.inno.experience.models import (
    KnowledgeRecord,
    RecallContext,
    RecallItem,
    RecallRequest,
)


class ExperienceRetriever(Protocol):
    def recall(self, request: RecallRequest) -> RecallContext: ...


class CandidateIndex(Protocol):
    def rebuild(self, records: list[KnowledgeRecord]) -> None: ...
    def query_ids(self, query: str, limit: int) -> list[str]: ...


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w-]+", value.lower(), flags=re.UNICODE)
        if len(token) > 1
    }


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _token_count(value: str) -> int:
    return max(1, math.ceil(len(value.encode("utf-8")) / 4))


class KeywordExperienceRetriever:
    def __init__(self, ledger: ExperimentLedger) -> None:
        self.ledger = ledger

    def _candidates(self, request: RecallRequest) -> list[KnowledgeRecord]:
        return self.ledger.list_knowledge()

    def recall(self, request: RecallRequest) -> RecallContext:
        memory_snapshot_id = self.ledger.snapshot_id()
        candidates = [
            item
            for item in self._candidates(request)
            if self._in_scope(item, request)
        ]
        selected = self._rank_and_budget(candidates, request)
        snapshot_payload = {
            "memory_snapshot_id": memory_snapshot_id,
            "request": request.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in selected],
        }
        snapshot_id = hashlib.sha256(
            json.dumps(
                snapshot_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        for existing in self.ledger.list_recall_contexts():
            if existing.snapshot_id == snapshot_id:
                return existing
        context = RecallContext(
            snapshot_id=snapshot_id,
            memory_snapshot_id=memory_snapshot_id,
            request=request,
            items=selected,
            token_count=sum(item.token_count for item in selected),
        )
        self.ledger.append_recall_context(context)
        return context

    @staticmethod
    def _in_scope(record: KnowledgeRecord, request: RecallRequest) -> bool:
        if not request.cross_task and record.task_id != request.task_id:
            return False
        if record.domain != request.domain:
            return False
        if record.dataset_id != request.dataset_id:
            return False
        if record.model_family != request.model_family:
            return False
        if not request.include_negative and record.outcome == "negative":
            return False
        return True

    def _rank_and_budget(
        self,
        candidates: list[KnowledgeRecord],
        request: RecallRequest,
    ) -> list[RecallItem]:
        if request.max_items == 0 or request.token_budget == 0:
            return []
        query_tokens = _tokens(request.query)
        remaining = list(candidates)
        selected: list[RecallItem] = []
        selected_tokens: list[set[str]] = []
        used_tokens = 0

        while remaining and len(selected) < request.max_items:
            scored: list[tuple[float, str, KnowledgeRecord, dict[str, float]]] = []
            for record in remaining:
                lesson_tokens = _tokens(
                    " ".join([record.lesson, *record.conditions])
                )
                relevance = _overlap(query_tokens, lesson_tokens)
                outcome_utility = 1.0 if record.outcome == "positive" else 0.9
                provenance_quality = min(
                    1.0,
                    0.7 * record.confidence
                    + 0.3 * min(1.0, len(record.source_experience_ids) / 3),
                )
                recency = min(1.0, record.created_at.timestamp() / 2_000_000_000)
                redundancy = max(
                    (_overlap(lesson_tokens, used) for used in selected_tokens),
                    default=0.0,
                )
                breakdown = {
                    "relevance": relevance,
                    "outcome_utility": outcome_utility,
                    "provenance_quality": provenance_quality,
                    "recency": recency,
                    "redundancy": -redundancy,
                }
                score = (
                    0.5 * relevance
                    + 0.15 * outcome_utility
                    + 0.2 * provenance_quality
                    + 0.05 * recency
                    - 0.1 * redundancy
                )
                scored.append((score, record.knowledge_id, record, breakdown))
            scored.sort(key=lambda item: (-item[0], item[1]))
            score, _, record, breakdown = scored[0]
            remaining.remove(record)
            item_tokens = _token_count(record.lesson)
            if used_tokens + item_tokens > request.token_budget:
                continue
            selected.append(
                RecallItem(
                    citation_id=f"knowledge:{record.knowledge_id}",
                    knowledge_id=record.knowledge_id,
                    lesson=record.lesson,
                    outcome=record.outcome,
                    source_experience_ids=record.source_experience_ids,
                    score=round(score, 8),
                    score_breakdown={
                        key: round(value, 8) for key, value in breakdown.items()
                    },
                    token_count=item_tokens,
                )
            )
            selected_tokens.append(_tokens(record.lesson))
            used_tokens += item_tokens
        return selected


class ChromaKnowledgeIndex:
    def __init__(self, path: str | Path, collection_name: str = "verified_experience") -> None:
        import chromadb

        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(collection_name)

    @staticmethod
    def _embedding(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [byte / 255.0 for byte in digest]

    def rebuild(self, records: list[KnowledgeRecord]) -> None:
        existing = self.collection.get()
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])
        if not records:
            return
        self.collection.add(
            ids=[record.knowledge_id for record in records],
            documents=[record.lesson for record in records],
            metadatas=[
                {
                    "task_id": record.task_id,
                    "domain": record.domain,
                    "dataset_id": record.dataset_id,
                    "model_family": record.model_family,
                }
                for record in records
            ],
            embeddings=[self._embedding(record.lesson) for record in records],
        )

    def query_ids(self, query: str, limit: int) -> list[str]:
        if self.collection.count() == 0 or limit <= 0:
            return []
        result = self.collection.query(
            query_embeddings=[self._embedding(query)],
            n_results=min(limit, self.collection.count()),
        )
        return list((result.get("ids") or [[]])[0])


class ChromaExperienceRetriever(KeywordExperienceRetriever):
    def __init__(
        self,
        ledger: ExperimentLedger,
        index: CandidateIndex,
        *,
        candidate_multiplier: int = 4,
    ) -> None:
        super().__init__(ledger)
        self.index = index
        self.candidate_multiplier = max(1, candidate_multiplier)

    def rebuild_index(self) -> None:
        self.index.rebuild(self.ledger.list_knowledge())

    def _candidates(self, request: RecallRequest) -> list[KnowledgeRecord]:
        records = {item.knowledge_id: item for item in self.ledger.list_knowledge()}
        ids = self.index.query_ids(
            request.query,
            max(request.max_items * self.candidate_multiplier, request.max_items),
        )
        return [records[item_id] for item_id in ids if item_id in records]
