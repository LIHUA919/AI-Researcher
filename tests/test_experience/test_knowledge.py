from research_agent.inno.experience import (
    InMemoryExperimentLedger,
    KnowledgeGate,
    SQLiteExperimentLedger,
)
from tests.test_experience.test_ledger import append_complete_record, build_records


def gate() -> KnowledgeGate:
    return KnowledgeGate(domain="vision", model_family="vq", policy_version="1")


def test_gate_promotes_verified_positive_experience_with_provenance():
    experience = build_records(outcome="positive")[4]

    decision, knowledge = gate().decide(experience, related=[])

    assert decision.accepted is True
    assert knowledge is not None
    assert knowledge.outcome == "positive"
    assert knowledge.source_experience_ids == [experience.experience_id]
    assert knowledge.promotion_policy_version == "1"
    assert decision.knowledge_id == knowledge.knowledge_id


def test_gate_promotes_reproducible_negative_lesson():
    experience = build_records(outcome="negative")[4]
    verification = experience.verification.model_copy(
        update={
            "public_feedback": [
                "The candidate repeats a globally suboptimal assignment."
            ]
        }
    )
    experience = experience.model_copy(update={"verification": verification})

    decision, knowledge = gate().decide(experience, related=[])

    assert decision.accepted is True
    assert knowledge is not None
    assert knowledge.outcome == "negative"
    assert knowledge.lesson.startswith("Verified evaluator feedback:")
    assert "Failed candidate rationale (do not repeat):" in knowledge.lesson
    assert "globally suboptimal assignment" in knowledge.lesson


def test_gate_rejects_missing_invalid_or_neutral_verification():
    verified = build_records()[4]
    missing = verified.model_copy(update={"verification": None})
    invalid_verification = verified.verification.model_copy(
        update={"valid": False, "outcome": "invalid", "passed": False}
    )
    invalid = verified.model_copy(update={"verification": invalid_verification})
    neutral_verification = verified.verification.model_copy(
        update={"outcome": "neutral", "passed": False}
    )
    neutral = verified.model_copy(update={"verification": neutral_verification})

    missing_decision, _ = gate().decide(missing, [])
    invalid_decision, _ = gate().decide(invalid, [])
    neutral_decision, _ = gate().decide(neutral, [])

    assert missing_decision.reasons == ["missing_verification"]
    assert "invalid_verification" in invalid_decision.reasons
    assert "non_reusable_outcome" in neutral_decision.reasons


def test_gate_rejects_contradictory_verified_experience():
    positive = build_records(suffix="1", outcome="positive")[4]
    negative = build_records(suffix="2", outcome="negative")[4]

    decision, knowledge = gate().decide(positive, [negative])

    assert decision.accepted is False
    assert knowledge is None
    assert "contradictory_verified_experience" in decision.reasons


def test_gate_is_deterministic_and_aggregates_consistent_sources():
    first = build_records(suffix="1", outcome="positive")[4]
    second = build_records(suffix="2", outcome="positive")[4]

    decision_a, knowledge_a = gate().decide(first, [second])
    decision_b, knowledge_b = gate().decide(first, [second])

    assert decision_a == decision_b
    assert knowledge_a == knowledge_b
    assert knowledge_a is not None
    assert knowledge_a.source_experience_ids == ["experience-1", "experience-2"]
    assert knowledge_a.confidence == 0.8


def test_ledger_persists_acceptance_and_rejection_decisions(tmp_path):
    ledgers = [
        InMemoryExperimentLedger(),
        SQLiteExperimentLedger(tmp_path / "experience.sqlite3"),
    ]
    for ledger in ledgers:
        records = append_complete_record(ledger)
        experience = records[4]
        accepted, knowledge = gate().decide(experience, [])
        assert knowledge is not None
        ledger.append_knowledge(knowledge)
        ledger.append_promotion_decision(accepted)

        missing_verification = experience.model_copy(update={"verification": None})
        rejected, _ = gate().decide(missing_verification, [])
        ledger.append_promotion_decision(rejected)

        assert {
            item.decision_id for item in ledger.list_promotion_decisions()
        } == {accepted.decision_id, rejected.decision_id}
