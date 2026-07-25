from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Protocol, TypeVar

from pydantic import BaseModel

from research_agent.inno.experience.models import (
    ExperienceQuery,
    ExperienceRecord,
    ExperimentAttempt,
    Hypothesis,
    KnowledgeRecord,
    Observation,
    PromotionDecision,
    VerificationRecord,
)


RecordT = TypeVar("RecordT", bound=BaseModel)


class ImmutableRecordError(ValueError):
    """Raised when an existing immutable ID is reused with different content."""


class RecordNotFoundError(KeyError):
    """Raised when a requested ledger record is not present."""


class ExperimentLedger(Protocol):
    def append_hypothesis(self, hypothesis: Hypothesis) -> None: ...
    def append_attempt(self, attempt: ExperimentAttempt) -> None: ...
    def append_observation(self, observation: Observation) -> None: ...
    def append_verification(self, verification: VerificationRecord) -> None: ...
    def append_experience(self, experience: ExperienceRecord) -> None: ...
    def append_knowledge(self, knowledge: KnowledgeRecord) -> None: ...
    def append_promotion_decision(self, decision: PromotionDecision) -> None: ...
    def get_experience(self, experience_id: str) -> ExperienceRecord: ...
    def query(self, query: ExperienceQuery) -> list[ExperienceRecord]: ...
    def list_knowledge(self) -> list[KnowledgeRecord]: ...
    def list_promotion_decisions(self) -> list[PromotionDecision]: ...
    def snapshot_id(self) -> str: ...


def _canonical(record: BaseModel) -> str:
    return json.dumps(
        record.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _append_immutable(store: dict[str, RecordT], record_id: str, record: RecordT) -> None:
    existing = store.get(record_id)
    if existing is None:
        store[record_id] = record
        return
    if _canonical(existing) != _canonical(record):
        raise ImmutableRecordError(f"record {record_id!r} already exists with different content")


class InMemoryExperimentLedger:
    def __init__(self) -> None:
        self._hypotheses: dict[str, Hypothesis] = {}
        self._attempts: dict[str, ExperimentAttempt] = {}
        self._observations: dict[str, Observation] = {}
        self._verifications: dict[str, VerificationRecord] = {}
        self._experiences: dict[str, ExperienceRecord] = {}
        self._knowledge: dict[str, KnowledgeRecord] = {}
        self._promotion_decisions: dict[str, PromotionDecision] = {}
        self._lock = RLock()

    def append_hypothesis(self, hypothesis: Hypothesis) -> None:
        with self._lock:
            _append_immutable(self._hypotheses, hypothesis.hypothesis_id, hypothesis)

    def append_attempt(self, attempt: ExperimentAttempt) -> None:
        with self._lock:
            if attempt.hypothesis_id not in self._hypotheses:
                raise RecordNotFoundError(attempt.hypothesis_id)
            _append_immutable(self._attempts, attempt.attempt_id, attempt)

    def append_observation(self, observation: Observation) -> None:
        with self._lock:
            if observation.attempt_id not in self._attempts:
                raise RecordNotFoundError(observation.attempt_id)
            _append_immutable(self._observations, observation.observation_id, observation)

    def append_verification(self, verification: VerificationRecord) -> None:
        with self._lock:
            if verification.observation_id not in self._observations:
                raise RecordNotFoundError(verification.observation_id)
            _append_immutable(
                self._verifications,
                verification.verification_id,
                verification,
            )

    def append_experience(self, experience: ExperienceRecord) -> None:
        with self._lock:
            if experience.hypothesis.hypothesis_id not in self._hypotheses:
                raise RecordNotFoundError(experience.hypothesis.hypothesis_id)
            if experience.attempt.attempt_id not in self._attempts:
                raise RecordNotFoundError(experience.attempt.attempt_id)
            if experience.observation.observation_id not in self._observations:
                raise RecordNotFoundError(experience.observation.observation_id)
            if (
                experience.verification is not None
                and experience.verification.verification_id not in self._verifications
            ):
                raise RecordNotFoundError(experience.verification.verification_id)
            _append_immutable(self._experiences, experience.experience_id, experience)

    def append_knowledge(self, knowledge: KnowledgeRecord) -> None:
        with self._lock:
            missing = [
                source_id
                for source_id in knowledge.source_experience_ids
                if source_id not in self._experiences
            ]
            if missing:
                raise RecordNotFoundError(missing[0])
            _append_immutable(self._knowledge, knowledge.knowledge_id, knowledge)

    def append_promotion_decision(self, decision: PromotionDecision) -> None:
        with self._lock:
            if decision.experience_id not in self._experiences:
                raise RecordNotFoundError(decision.experience_id)
            if decision.knowledge_id and decision.knowledge_id not in self._knowledge:
                raise RecordNotFoundError(decision.knowledge_id)
            _append_immutable(
                self._promotion_decisions,
                decision.decision_id,
                decision,
            )

    def get_experience(self, experience_id: str) -> ExperienceRecord:
        try:
            return self._experiences[experience_id]
        except KeyError as exc:
            raise RecordNotFoundError(experience_id) from exc

    def query(self, query: ExperienceQuery) -> list[ExperienceRecord]:
        records = sorted(
            self._experiences.values(),
            key=lambda item: (item.created_at, item.experience_id),
            reverse=True,
        )
        if query.task_id is not None:
            records = [item for item in records if item.task_id == query.task_id]
        if query.outcome is not None:
            records = [
                item
                for item in records
                if item.verification is not None and item.verification.outcome == query.outcome
            ]
        if query.valid_only:
            records = [
                item
                for item in records
                if item.verification is not None and item.verification.valid
            ]
        return records[: query.limit]

    def list_knowledge(self) -> list[KnowledgeRecord]:
        return sorted(
            self._knowledge.values(),
            key=lambda item: (item.created_at, item.knowledge_id),
        )

    def list_promotion_decisions(self) -> list[PromotionDecision]:
        return sorted(
            self._promotion_decisions.values(),
            key=lambda item: (item.created_at, item.decision_id),
        )

    def snapshot_id(self) -> str:
        records: list[BaseModel] = []
        for store in (
            self._hypotheses,
            self._attempts,
            self._observations,
            self._verifications,
            self._experiences,
            self._knowledge,
            self._promotion_decisions,
        ):
            records.extend(store[key] for key in sorted(store))
        payload = "\n".join(_canonical(record) for record in records)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_TABLES: dict[str, tuple[str, type[BaseModel]]] = {
    "hypotheses": ("hypothesis_id", Hypothesis),
    "experiment_attempts": ("attempt_id", ExperimentAttempt),
    "observations": ("observation_id", Observation),
    "verification_records": ("verification_id", VerificationRecord),
    "experience_records": ("experience_id", ExperienceRecord),
    "knowledge_records": ("knowledge_id", KnowledgeRecord),
    "promotion_decisions": ("decision_id", PromotionDecision),
}


class SQLiteExperimentLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS hypotheses (
                    record_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiment_attempts (
                    record_id TEXT PRIMARY KEY,
                    hypothesis_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(record_id)
                );
                CREATE TABLE IF NOT EXISTS observations (
                    record_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY (attempt_id) REFERENCES experiment_attempts(record_id)
                );
                CREATE TABLE IF NOT EXISTS verification_records (
                    record_id TEXT PRIMARY KEY,
                    observation_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY (observation_id) REFERENCES observations(record_id)
                );
                CREATE TABLE IF NOT EXISTS experience_records (
                    record_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    outcome TEXT,
                    valid INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_records (
                    record_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    knowledge_id TEXT NOT NULL,
                    experience_id TEXT NOT NULL,
                    PRIMARY KEY (knowledge_id, experience_id),
                    FOREIGN KEY (knowledge_id) REFERENCES knowledge_records(record_id),
                    FOREIGN KEY (experience_id) REFERENCES experience_records(record_id)
                );
                CREATE TABLE IF NOT EXISTS promotion_decisions (
                    record_id TEXT PRIMARY KEY,
                    experience_id TEXT NOT NULL,
                    knowledge_id TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY (experience_id) REFERENCES experience_records(record_id),
                    FOREIGN KEY (knowledge_id) REFERENCES knowledge_records(record_id)
                );
                """
            )

    def _append(
        self,
        table: str,
        record_id: str,
        record: BaseModel,
        *,
        columns: dict[str, str | int] | None = None,
    ) -> None:
        payload = _canonical(record)
        values = {"record_id": record_id, "payload_json": payload, **(columns or {})}
        names = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                f"SELECT payload_json FROM {table} WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != payload:
                    raise ImmutableRecordError(
                        f"record {record_id!r} already exists with different content"
                    )
                return
            try:
                connection.execute(
                    f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
                    tuple(values.values()),
                )
            except sqlite3.IntegrityError as exc:
                raise RecordNotFoundError(str(exc)) from exc

    def append_hypothesis(self, hypothesis: Hypothesis) -> None:
        self._append("hypotheses", hypothesis.hypothesis_id, hypothesis)

    def append_attempt(self, attempt: ExperimentAttempt) -> None:
        self._append(
            "experiment_attempts",
            attempt.attempt_id,
            attempt,
            columns={"hypothesis_id": attempt.hypothesis_id},
        )

    def append_observation(self, observation: Observation) -> None:
        self._append(
            "observations",
            observation.observation_id,
            observation,
            columns={"attempt_id": observation.attempt_id},
        )

    def append_verification(self, verification: VerificationRecord) -> None:
        self._append(
            "verification_records",
            verification.verification_id,
            verification,
            columns={"observation_id": verification.observation_id},
        )

    def append_experience(self, experience: ExperienceRecord) -> None:
        with self._connect() as connection:
            required = (
                ("hypotheses", experience.hypothesis.hypothesis_id),
                ("experiment_attempts", experience.attempt.attempt_id),
                ("observations", experience.observation.observation_id),
            )
            if experience.verification is not None:
                required += (
                    ("verification_records", experience.verification.verification_id),
                )
            for table, record_id in required:
                exists = connection.execute(
                    f"SELECT 1 FROM {table} WHERE record_id = ?",
                    (record_id,),
                ).fetchone()
                if exists is None:
                    raise RecordNotFoundError(record_id)
        verification = experience.verification
        self._append(
            "experience_records",
            experience.experience_id,
            experience,
            columns={
                "task_id": experience.task_id,
                "outcome": verification.outcome if verification else None,
                "valid": int(bool(verification and verification.valid)),
                "created_at": experience.created_at.isoformat(),
            },
        )

    def append_knowledge(self, knowledge: KnowledgeRecord) -> None:
        payload = _canonical(knowledge)
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM knowledge_records WHERE record_id = ?",
                (knowledge.knowledge_id,),
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != payload:
                    raise ImmutableRecordError(
                        f"record {knowledge.knowledge_id!r} already exists with different content"
                    )
                return
            try:
                connection.execute(
                    """
                    INSERT INTO knowledge_records
                        (record_id, task_id, created_at, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        knowledge.knowledge_id,
                        knowledge.task_id,
                        knowledge.created_at.isoformat(),
                        payload,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO knowledge_sources (knowledge_id, experience_id)
                    VALUES (?, ?)
                    """,
                    [
                        (knowledge.knowledge_id, source_id)
                        for source_id in knowledge.source_experience_ids
                    ],
                )
            except sqlite3.IntegrityError as exc:
                raise RecordNotFoundError(str(exc)) from exc

    def append_promotion_decision(self, decision: PromotionDecision) -> None:
        self._append(
            "promotion_decisions",
            decision.decision_id,
            decision,
            columns={
                "experience_id": decision.experience_id,
                "knowledge_id": decision.knowledge_id,
                "created_at": decision.created_at.isoformat(),
            },
        )

    def _load_one(self, table: str, record_id: str, model: type[RecordT]) -> RecordT:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT payload_json FROM {table} WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFoundError(record_id)
        return model.model_validate_json(row["payload_json"])

    def get_experience(self, experience_id: str) -> ExperienceRecord:
        return self._load_one("experience_records", experience_id, ExperienceRecord)

    def query(self, query: ExperienceQuery) -> list[ExperienceRecord]:
        clauses: list[str] = []
        values: list[str | int] = []
        if query.task_id is not None:
            clauses.append("task_id = ?")
            values.append(query.task_id)
        if query.outcome is not None:
            clauses.append("outcome = ?")
            values.append(query.outcome)
        if query.valid_only:
            clauses.append("valid = 1")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(query.limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT payload_json FROM experience_records
                {where}
                ORDER BY created_at DESC, record_id DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        return [ExperienceRecord.model_validate_json(row["payload_json"]) for row in rows]

    def list_knowledge(self) -> list[KnowledgeRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM knowledge_records
                ORDER BY created_at, record_id
                """
            ).fetchall()
        return [KnowledgeRecord.model_validate_json(row["payload_json"]) for row in rows]

    def list_promotion_decisions(self) -> list[PromotionDecision]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM promotion_decisions
                ORDER BY created_at, record_id
                """
            ).fetchall()
        return [PromotionDecision.model_validate_json(row["payload_json"]) for row in rows]

    def snapshot_id(self) -> str:
        payloads: list[str] = []
        with self._connect() as connection:
            for table in _TABLES:
                rows = connection.execute(
                    f"SELECT payload_json FROM {table} ORDER BY record_id"
                ).fetchall()
                payloads.extend(row["payload_json"] for row in rows)
        return hashlib.sha256("\n".join(payloads).encode("utf-8")).hexdigest()
