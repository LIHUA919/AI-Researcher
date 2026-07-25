from datetime import timedelta

from research_agent.inno.experience import (
    ChromaExperienceRetriever,
    ChromaKnowledgeIndex,
    InMemoryExperimentLedger,
    KeywordExperienceRetriever,
    RecallRequest,
    SQLiteExperimentLedger,
)
from tests.test_experience.test_ledger import build_records


def append_knowledge(
    ledger,
    *,
    suffix: str,
    lesson: str,
    outcome: str = "positive",
    task_id: str = "task-vq",
    domain: str = "vision",
    dataset_id: str = "cifar10",
    model_family: str = "vq",
):
    hypothesis, attempt, observation, verification, experience, knowledge = build_records(
        suffix=suffix,
        outcome=outcome,
    )
    if task_id != experience.task_id:
        hypothesis = hypothesis.model_copy(update={"task_id": task_id})
        attempt = attempt.model_copy(update={"task_id": task_id, "hypothesis_id": hypothesis.hypothesis_id})
        experience = experience.model_copy(
            update={
                "task_id": task_id,
                "hypothesis": hypothesis,
                "attempt": attempt,
            }
        )
    knowledge = knowledge.model_copy(
        update={
            "knowledge_id": f"knowledge-{suffix}-{task_id}-{domain}-{dataset_id}-{model_family}",
            "task_id": task_id,
            "domain": domain,
            "dataset_id": dataset_id,
            "model_family": model_family,
            "lesson": lesson,
            "outcome": outcome,
            "source_experience_ids": [experience.experience_id],
            "created_at": knowledge.created_at + timedelta(seconds=int(suffix)),
        }
    )
    ledger.append_hypothesis(hypothesis)
    ledger.append_attempt(attempt)
    ledger.append_observation(observation)
    ledger.append_verification(verification)
    ledger.append_experience(experience)
    ledger.append_knowledge(knowledge)
    return knowledge


def request(**updates):
    values = {
        "query": "improve codebook utilization",
        "task_id": "task-vq",
        "domain": "vision",
        "dataset_id": "cifar10",
        "model_family": "vq",
        "max_items": 8,
        "token_budget": 3000,
    }
    values.update(updates)
    return RecallRequest(**values)


def test_keyword_retrieval_enforces_scope_and_negative_policy():
    ledger = InMemoryExperimentLedger()
    positive = append_knowledge(
        ledger,
        suffix="1",
        lesson="Improve codebook utilization with a learned transform.",
    )
    negative = append_knowledge(
        ledger,
        suffix="2",
        lesson="Avoid an unstable transform for codebook utilization.",
        outcome="negative",
    )
    append_knowledge(
        ledger,
        suffix="3",
        lesson="Wrong task",
        task_id="other-task",
    )
    append_knowledge(
        ledger,
        suffix="4",
        lesson="Wrong dataset",
        dataset_id="imagenet",
    )

    included = KeywordExperienceRetriever(ledger).recall(request())
    positive_only = KeywordExperienceRetriever(ledger).recall(
        request(include_negative=False)
    )

    assert {item.knowledge_id for item in included.items} == {
        positive.knowledge_id,
        negative.knowledge_id,
    }
    assert [item.knowledge_id for item in positive_only.items] == [
        positive.knowledge_id
    ]
    assert all(item.citation_id.startswith("knowledge:") for item in included.items)


def test_retrieval_is_deterministic_persisted_and_does_not_change_memory_snapshot():
    ledger = InMemoryExperimentLedger()
    append_knowledge(
        ledger,
        suffix="1",
        lesson="Improve codebook utilization with a learned transform.",
    )
    retriever = KeywordExperienceRetriever(ledger)
    before = ledger.snapshot_id()

    first = retriever.recall(request())
    after_first = ledger.snapshot_id()
    second = retriever.recall(request())

    assert first == second
    assert first.memory_snapshot_id == before
    assert after_first == before
    assert ledger.list_recall_contexts() == [first]


def test_retrieval_enforces_item_and_token_budgets():
    ledger = InMemoryExperimentLedger()
    append_knowledge(ledger, suffix="1", lesson="short useful lesson")
    append_knowledge(
        ledger,
        suffix="2",
        lesson="a much longer lesson that cannot fit inside a tiny token budget",
    )

    context = KeywordExperienceRetriever(ledger).recall(
        request(max_items=1, token_budget=5)
    )
    empty = KeywordExperienceRetriever(ledger).recall(
        request(max_items=0, token_budget=0)
    )

    assert len(context.items) <= 1
    assert context.token_count <= 5
    assert empty.items == []


class FakeIndex:
    def __init__(self):
        self.records = []

    def rebuild(self, records):
        self.records = list(records)

    def query_ids(self, query, limit):
        return [record.knowledge_id for record in reversed(self.records[:limit])]


def test_chroma_retriever_uses_semantic_candidates_then_shared_scope_ranker():
    ledger = InMemoryExperimentLedger()
    scoped = append_knowledge(
        ledger,
        suffix="1",
        lesson="Improve codebook utilization.",
    )
    append_knowledge(
        ledger,
        suffix="2",
        lesson="Out of scope candidate.",
        dataset_id="imagenet",
    )
    index = FakeIndex()
    retriever = ChromaExperienceRetriever(ledger, index)
    retriever.rebuild_index()

    context = retriever.recall(request())

    assert [item.knowledge_id for item in context.items] == [scoped.knowledge_id]


def test_chroma_index_can_be_rebuilt_from_canonical_knowledge(tmp_path):
    ledger = InMemoryExperimentLedger()
    knowledge = append_knowledge(
        ledger,
        suffix="1",
        lesson="Improve codebook utilization with a learned transform.",
    )
    index = ChromaKnowledgeIndex(tmp_path / "semantic-index")

    index.rebuild(ledger.list_knowledge())
    ids = index.query_ids("codebook utilization", 3)

    assert ids == [knowledge.knowledge_id]


def test_sqlite_recall_snapshot_survives_reopen(tmp_path):
    path = tmp_path / "experience.sqlite3"
    ledger = SQLiteExperimentLedger(path)
    append_knowledge(
        ledger,
        suffix="1",
        lesson="Improve codebook utilization with a learned transform.",
    )
    context = KeywordExperienceRetriever(ledger).recall(request())

    reopened = SQLiteExperimentLedger(path)

    assert reopened.list_recall_contexts() == [context]
    assert KeywordExperienceRetriever(reopened).recall(request()) == context
