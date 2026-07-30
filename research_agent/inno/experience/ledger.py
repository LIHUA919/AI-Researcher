from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Protocol, TypeVar

from pydantic import BaseModel

from research_agent.inno.experience.intervention import (
    InterventionRecord,
    TrialProvenanceRecord,
    validate_content_derived_intervention_id,
    validate_content_derived_provenance_id,
)
from research_agent.inno.experience.models import (
    ExperienceQuery,
    ExperienceRecord,
    ExperimentAttempt,
    Hypothesis,
    KnowledgeRecord,
    Observation,
    PromotionDecision,
    RecallContext,
    VerificationRecord,
)


RecordT = TypeVar("RecordT", bound=BaseModel)


class ImmutableRecordError(ValueError):
    """Raised when an existing immutable ID is reused with different content."""


class RecordNotFoundError(KeyError):
    """Raised when a requested ledger record is not present."""


class UnsupportedLedgerSchemaError(RuntimeError):
    """Raised when a SQLite ledger schema cannot be opened safely."""


LATEST_SCHEMA_VERSION = 2


class ExperimentLedger(Protocol):
    def append_hypothesis(self, hypothesis: Hypothesis) -> None: ...
    def append_attempt(self, attempt: ExperimentAttempt) -> None: ...
    def append_observation(self, observation: Observation) -> None: ...
    def append_verification(self, verification: VerificationRecord) -> None: ...
    def append_experience(self, experience: ExperienceRecord) -> None: ...
    def append_knowledge(self, knowledge: KnowledgeRecord) -> None: ...
    def append_promotion_decision(self, decision: PromotionDecision) -> None: ...
    def append_recall_context(self, context: RecallContext) -> None: ...
    def append_intervention(self, record: InterventionRecord) -> None: ...
    def get_intervention(self, intervention_id: str) -> InterventionRecord: ...
    def list_interventions(self, run_id: str) -> list[InterventionRecord]: ...
    def append_trial_provenance(self, record: TrialProvenanceRecord) -> None: ...
    def find_trial_provenance(
        self,
        observation_id: str,
    ) -> TrialProvenanceRecord | None: ...
    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis: ...
    def get_experience(self, experience_id: str) -> ExperienceRecord: ...
    def query(self, query: ExperienceQuery) -> list[ExperienceRecord]: ...
    def list_knowledge(self) -> list[KnowledgeRecord]: ...
    def list_promotion_decisions(self) -> list[PromotionDecision]: ...
    def list_recall_contexts(self) -> list[RecallContext]: ...
    def has_valid_verification(self, run_id: str) -> bool: ...
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


def _validate_trial_lineage(
    *,
    attempt: ExperimentAttempt,
    observation: Observation,
    intervention: InterventionRecord,
    provenance: TrialProvenanceRecord,
) -> None:
    if observation.attempt_id != provenance.attempt_id:
        raise ValueError("observation does not belong to attempt")
    if attempt.run_id != intervention.run_id:
        raise ValueError("attempt and intervention run_id do not match")
    if attempt.iteration_id != intervention.iteration_id:
        raise ValueError("attempt and intervention iteration_id do not match")
    if attempt.task_id != intervention.task_id:
        raise ValueError("attempt and intervention task_id do not match")
    if attempt.hypothesis_id != intervention.hypothesis_id:
        raise ValueError("attempt and intervention hypothesis_id do not match")
    if attempt.recall_snapshot_id != intervention.recall_snapshot_id:
        raise ValueError(
            "attempt and intervention recall_snapshot_id do not match"
        )


def _validate_previous_intervention_lineage(
    *,
    current: InterventionRecord,
    previous: InterventionRecord,
) -> None:
    for field in ("run_id", "task_id"):
        if getattr(current, field) != getattr(previous, field):
            raise ValueError(
                f"current and previous intervention {field} do not match"
            )
    prefix = "iteration-"
    previous_suffix = previous.iteration_id.removeprefix(prefix)
    current_suffix = current.iteration_id.removeprefix(prefix)
    if (
        not previous.iteration_id.startswith(prefix)
        or not current.iteration_id.startswith(prefix)
        or not previous_suffix.isdigit()
        or not current_suffix.isdigit()
        or int(current_suffix) != int(previous_suffix) + 1
    ):
        raise ValueError(
            "current and previous intervention iterations must be adjacent"
        )


class InMemoryExperimentLedger:
    def __init__(self) -> None:
        self._hypotheses: dict[str, Hypothesis] = {}
        self._attempts: dict[str, ExperimentAttempt] = {}
        self._observations: dict[str, Observation] = {}
        self._verifications: dict[str, VerificationRecord] = {}
        self._experiences: dict[str, ExperienceRecord] = {}
        self._knowledge: dict[str, KnowledgeRecord] = {}
        self._promotion_decisions: dict[str, PromotionDecision] = {}
        self._recall_contexts: dict[str, RecallContext] = {}
        self._interventions: dict[str, InterventionRecord] = {}
        self._intervention_by_iteration: dict[tuple[str, str], str] = {}
        self._trial_provenance: dict[str, TrialProvenanceRecord] = {}
        self._provenance_by_observation: dict[str, str] = {}
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

    def append_recall_context(self, context: RecallContext) -> None:
        with self._lock:
            _append_immutable(
                self._recall_contexts,
                context.snapshot_id,
                context,
            )

    def append_intervention(self, record: InterventionRecord) -> None:
        with self._lock:
            validate_content_derived_intervention_id(record)
            if record.previous_intervention_id is not None:
                previous = self._interventions.get(
                    record.previous_intervention_id
                )
                if previous is None:
                    raise RecordNotFoundError(record.previous_intervention_id)
                _validate_previous_intervention_lineage(
                    current=record,
                    previous=previous,
                )
            iteration_key = (record.run_id, record.iteration_id)
            existing_id = self._intervention_by_iteration.get(iteration_key)
            if existing_id is not None and existing_id != record.intervention_id:
                raise ImmutableRecordError(
                    f"run {record.run_id!r} iteration {record.iteration_id!r} "
                    "already has an intervention"
                )
            _append_immutable(
                self._interventions,
                record.intervention_id,
                record,
            )
            self._intervention_by_iteration[iteration_key] = record.intervention_id

    def get_intervention(self, intervention_id: str) -> InterventionRecord:
        try:
            return self._interventions[intervention_id]
        except KeyError as exc:
            raise RecordNotFoundError(intervention_id) from exc

    def list_interventions(self, run_id: str) -> list[InterventionRecord]:
        return sorted(
            (
                record
                for record in self._interventions.values()
                if record.run_id == run_id
            ),
            key=lambda item: (item.created_at, item.intervention_id),
        )

    def append_trial_provenance(self, record: TrialProvenanceRecord) -> None:
        with self._lock:
            validate_content_derived_provenance_id(record)
            attempt = self._attempts.get(record.attempt_id)
            if attempt is None:
                raise RecordNotFoundError(record.attempt_id)
            observation = self._observations.get(record.observation_id)
            if observation is None:
                raise RecordNotFoundError(record.observation_id)
            intervention = self._interventions.get(record.intervention_id)
            if intervention is None:
                raise RecordNotFoundError(record.intervention_id)
            _validate_trial_lineage(
                attempt=attempt,
                observation=observation,
                intervention=intervention,
                provenance=record,
            )
            if (
                record.proposal_digest != intervention.proposal_digest
                or record.intervention_digest != intervention.intervention_digest
                or record.config_digest != intervention.config_digest
            ):
                raise ValueError("trial provenance digests do not match intervention")
            bound_id = self._provenance_by_observation.get(record.observation_id)
            if bound_id is not None and bound_id != record.provenance_id:
                raise ImmutableRecordError(
                    f"observation {record.observation_id!r} already has provenance"
                )
            _append_immutable(
                self._trial_provenance,
                record.provenance_id,
                record,
            )
            self._provenance_by_observation[record.observation_id] = (
                record.provenance_id
            )

    def find_trial_provenance(
        self,
        observation_id: str,
    ) -> TrialProvenanceRecord | None:
        provenance_id = self._provenance_by_observation.get(observation_id)
        if provenance_id is None:
            return None
        return self._trial_provenance[provenance_id]

    def get_experience(self, experience_id: str) -> ExperienceRecord:
        try:
            return self._experiences[experience_id]
        except KeyError as exc:
            raise RecordNotFoundError(experience_id) from exc

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis:
        try:
            return self._hypotheses[hypothesis_id]
        except KeyError as exc:
            raise RecordNotFoundError(hypothesis_id) from exc

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

    def list_recall_contexts(self) -> list[RecallContext]:
        return sorted(
            self._recall_contexts.values(),
            key=lambda item: (item.created_at, item.snapshot_id),
        )

    def has_valid_verification(self, run_id: str) -> bool:
        return any(
            item.attempt.run_id == run_id
            and item.verification is not None
            and item.verification.valid
            for item in self._experiences.values()
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
            self._interventions,
            self._trial_provenance,
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
    "recall_contexts": ("snapshot_id", RecallContext),
    "intervention_records": ("intervention_id", InterventionRecord),
    "trial_provenance_records": ("provenance_id", TrialProvenanceRecord),
}
_SNAPSHOT_TABLES = tuple(
    table for table in _TABLES if table != "recall_contexts"
)

_LEGACY_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE hypotheses (
        record_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE experiment_attempts (
        record_id TEXT PRIMARY KEY,
        hypothesis_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(record_id)
    )
    """,
    """
    CREATE TABLE observations (
        record_id TEXT PRIMARY KEY,
        attempt_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (attempt_id) REFERENCES experiment_attempts(record_id)
    )
    """,
    """
    CREATE TABLE verification_records (
        record_id TEXT PRIMARY KEY,
        observation_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (observation_id) REFERENCES observations(record_id)
    )
    """,
    """
    CREATE TABLE experience_records (
        record_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        outcome TEXT,
        valid INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE knowledge_records (
        record_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE knowledge_sources (
        knowledge_id TEXT NOT NULL,
        experience_id TEXT NOT NULL,
        PRIMARY KEY (knowledge_id, experience_id),
        FOREIGN KEY (knowledge_id) REFERENCES knowledge_records(record_id),
        FOREIGN KEY (experience_id) REFERENCES experience_records(record_id)
    )
    """,
    """
    CREATE TABLE promotion_decisions (
        record_id TEXT PRIMARY KEY,
        experience_id TEXT NOT NULL,
        knowledge_id TEXT,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (experience_id) REFERENCES experience_records(record_id),
        FOREIGN KEY (knowledge_id) REFERENCES knowledge_records(record_id)
    )
    """,
    """
    CREATE TABLE recall_contexts (
        record_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
)

_SIDECAR_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE intervention_records (
        record_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        iteration_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        domain TEXT NOT NULL,
        schema_id TEXT NOT NULL,
        manipulation_status TEXT NOT NULL,
        config_digest TEXT,
        previous_intervention_id TEXT,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        UNIQUE (run_id, iteration_id),
        FOREIGN KEY (previous_intervention_id)
            REFERENCES intervention_records(record_id)
    )
    """,
    """
    CREATE INDEX idx_intervention_records_run
        ON intervention_records(run_id, iteration_id)
    """,
    """
    CREATE TABLE trial_provenance_records (
        record_id TEXT PRIMARY KEY,
        attempt_id TEXT NOT NULL,
        observation_id TEXT NOT NULL UNIQUE,
        intervention_id TEXT NOT NULL,
        source_digest TEXT NOT NULL,
        config_digest TEXT NOT NULL,
        environment_digest TEXT NOT NULL,
        dataset_digest TEXT NOT NULL,
        evidence_digest TEXT NOT NULL,
        contract_digest TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY (attempt_id)
            REFERENCES experiment_attempts(record_id),
        FOREIGN KEY (observation_id)
            REFERENCES observations(record_id),
        FOREIGN KEY (intervention_id)
            REFERENCES intervention_records(record_id)
    )
    """,
    """
    CREATE INDEX idx_trial_provenance_attempt
        ON trial_provenance_records(attempt_id)
    """,
)

_LEGACY_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "hypotheses": ("record_id", "payload_json"),
    "experiment_attempts": ("record_id", "hypothesis_id", "payload_json"),
    "observations": ("record_id", "attempt_id", "payload_json"),
    "verification_records": ("record_id", "observation_id", "payload_json"),
    "experience_records": (
        "record_id",
        "task_id",
        "outcome",
        "valid",
        "created_at",
        "payload_json",
    ),
    "knowledge_records": ("record_id", "task_id", "created_at", "payload_json"),
    "knowledge_sources": ("knowledge_id", "experience_id"),
    "promotion_decisions": (
        "record_id",
        "experience_id",
        "knowledge_id",
        "created_at",
        "payload_json",
    ),
    "recall_contexts": ("record_id", "created_at", "payload_json"),
}
_SIDECAR_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "intervention_records": (
        "record_id",
        "run_id",
        "iteration_id",
        "task_id",
        "domain",
        "schema_id",
        "manipulation_status",
        "config_digest",
        "previous_intervention_id",
        "created_at",
        "payload_json",
    ),
    "trial_provenance_records": (
        "record_id",
        "attempt_id",
        "observation_id",
        "intervention_id",
        "source_digest",
        "config_digest",
        "environment_digest",
        "dataset_digest",
        "evidence_digest",
        "contract_digest",
        "created_at",
        "payload_json",
    ),
}
_SIDECAR_INDEX_COLUMNS: dict[str, tuple[str, ...]] = {
    "idx_intervention_records_run": ("run_id", "iteration_id"),
    "idx_trial_provenance_attempt": ("attempt_id",),
}
_SIDECAR_INDEX_TABLES = {
    "idx_intervention_records_run": "intervention_records",
    "idx_trial_provenance_attempt": "trial_provenance_records",
}
_SIDECAR_FOREIGN_KEYS: dict[
    str,
    set[tuple[str, str, str]],
] = {
    "intervention_records": {
        (
            "previous_intervention_id",
            "intervention_records",
            "record_id",
        ),
    },
    "trial_provenance_records": {
        ("attempt_id", "experiment_attempts", "record_id"),
        ("observation_id", "observations", "record_id"),
        ("intervention_id", "intervention_records", "record_id"),
    },
}
_SIDECAR_UNIQUE_COLUMNS: dict[str, set[tuple[str, ...]]] = {
    "intervention_records": {
        ("record_id",),
        ("run_id", "iteration_id"),
    },
    "trial_provenance_records": {
        ("record_id",),
        ("observation_id",),
    },
}
_INTEGER_COLUMNS = {("experience_records", "valid")}
_NULLABLE_COLUMNS = {
    ("hypotheses", "record_id"),
    ("experiment_attempts", "record_id"),
    ("observations", "record_id"),
    ("verification_records", "record_id"),
    ("experience_records", "record_id"),
    ("experience_records", "outcome"),
    ("knowledge_records", "record_id"),
    ("promotion_decisions", "record_id"),
    ("promotion_decisions", "knowledge_id"),
    ("recall_contexts", "record_id"),
    ("intervention_records", "record_id"),
    ("intervention_records", "config_digest"),
    ("intervention_records", "previous_intervention_id"),
    ("trial_provenance_records", "record_id"),
}
_COMPOSITE_PRIMARY_KEYS = {
    "knowledge_sources": ("knowledge_id", "experience_id"),
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
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in {0, LATEST_SCHEMA_VERSION}:
                raise UnsupportedLedgerSchemaError(
                    f"unsupported ledger schema version {version}; "
                    f"expected 0 or {LATEST_SCHEMA_VERSION}"
                )

            user_tables = self._user_tables(connection)
            if version == LATEST_SCHEMA_VERSION:
                self._validate_schema(
                    connection,
                    {**_LEGACY_TABLE_COLUMNS, **_SIDECAR_TABLE_COLUMNS},
                )
                self._validate_database_integrity(connection)
                return

            if user_tables:
                allowed_tables = set(_LEGACY_TABLE_COLUMNS) | set(
                    _SIDECAR_TABLE_COLUMNS
                )
                if not set(_LEGACY_TABLE_COLUMNS).issubset(user_tables):
                    raise UnsupportedLedgerSchemaError(
                        "schema version 0 is missing legacy ledger tables"
                    )
                if not user_tables.issubset(allowed_tables):
                    unknown = sorted(user_tables - allowed_tables)
                    raise UnsupportedLedgerSchemaError(
                        f"schema version 0 has unknown tables: {unknown}"
                    )
                self._validate_schema(connection, _LEGACY_TABLE_COLUMNS)
                sidecar_tables = user_tables & set(_SIDECAR_TABLE_COLUMNS)
                if sidecar_tables and sidecar_tables != set(
                    _SIDECAR_TABLE_COLUMNS
                ):
                    raise UnsupportedLedgerSchemaError(
                        "schema version 0 has a partial sidecar schema"
                    )
                if sidecar_tables:
                    self._validate_schema(connection, _SIDECAR_TABLE_COLUMNS)

            connection.execute("PRAGMA journal_mode = WAL")
            statements = (
                (*_LEGACY_SCHEMA_STATEMENTS, *_SIDECAR_SCHEMA_STATEMENTS)
                if not user_tables
                else (() if set(_SIDECAR_TABLE_COLUMNS) <= user_tables else _SIDECAR_SCHEMA_STATEMENTS)
            )
            try:
                connection.execute("BEGIN IMMEDIATE")
                for statement in statements:
                    connection.execute(statement)
                self._validate_schema(
                    connection,
                    {**_LEGACY_TABLE_COLUMNS, **_SIDECAR_TABLE_COLUMNS},
                )
                violations = connection.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
                if violations:
                    raise UnsupportedLedgerSchemaError(
                        "ledger contains foreign-key violations"
                    )
                connection.execute(
                    f"PRAGMA user_version = {LATEST_SCHEMA_VERSION}"
                )
                self._validate_database_integrity(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _user_tables(connection: sqlite3.Connection) -> set[str]:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        return {str(row["name"]) for row in rows}

    @classmethod
    def _validate_schema(
        cls,
        connection: sqlite3.Connection,
        expected: dict[str, tuple[str, ...]],
    ) -> None:
        user_tables = cls._user_tables(connection)
        for table, expected_columns in expected.items():
            if table not in user_tables:
                raise UnsupportedLedgerSchemaError(
                    f"ledger schema is missing table {table!r}"
                )
            rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
            actual_columns = tuple(str(row["name"]) for row in rows)
            if actual_columns != expected_columns:
                raise UnsupportedLedgerSchemaError(
                    f"ledger table {table!r} has columns {actual_columns!r}; "
                    f"expected {expected_columns!r}"
                )
            actual_types = tuple(str(row["type"]).upper() for row in rows)
            expected_types = tuple(
                "INTEGER" if (table, column) in _INTEGER_COLUMNS else "TEXT"
                for column in expected_columns
            )
            if actual_types != expected_types:
                raise UnsupportedLedgerSchemaError(
                    f"ledger table {table!r} has column type signature "
                    f"{actual_types!r}; expected {expected_types!r}"
                )
            actual_not_null = tuple(int(row["notnull"]) for row in rows)
            expected_not_null = tuple(
                0 if (table, column) in _NULLABLE_COLUMNS else 1
                for column in expected_columns
            )
            if actual_not_null != expected_not_null:
                raise UnsupportedLedgerSchemaError(
                    f"ledger table {table!r} has NOT NULL signature "
                    f"{actual_not_null!r}; expected {expected_not_null!r}"
                )
            primary_key = _COMPOSITE_PRIMARY_KEYS.get(table, ("record_id",))
            expected_primary_key = tuple(
                primary_key.index(column) + 1 if column in primary_key else 0
                for column in expected_columns
            )
            actual_primary_key = tuple(int(row["pk"]) for row in rows)
            if actual_primary_key != expected_primary_key:
                raise UnsupportedLedgerSchemaError(
                    f"ledger table {table!r} has primary-key signature "
                    f"{actual_primary_key!r}; expected {expected_primary_key!r}"
                )
        if set(_SIDECAR_TABLE_COLUMNS).issubset(expected):
            for index, expected_columns in _SIDECAR_INDEX_COLUMNS.items():
                rows = connection.execute(
                    """
                    SELECT name, tbl_name
                    FROM sqlite_master
                    WHERE type = 'index' AND name = ?
                    """,
                    (index,),
                ).fetchall()
                if not rows:
                    raise UnsupportedLedgerSchemaError(
                        f"ledger schema is missing index {index!r}"
                    )
                actual_table = str(rows[0]["tbl_name"])
                expected_table = _SIDECAR_INDEX_TABLES[index]
                if actual_table != expected_table:
                    raise UnsupportedLedgerSchemaError(
                        f"ledger index {index!r} belongs to table "
                        f"{actual_table!r}; expected {expected_table!r}"
                    )
                info = connection.execute(
                    f"PRAGMA index_info({index})"
                ).fetchall()
                actual_columns = tuple(str(row["name"]) for row in info)
                if actual_columns != expected_columns:
                    raise UnsupportedLedgerSchemaError(
                        f"ledger index {index!r} has columns "
                        f"{actual_columns!r}; expected {expected_columns!r}"
                    )
            for table, expected_foreign_keys in (
                _SIDECAR_FOREIGN_KEYS.items()
            ):
                rows = connection.execute(
                    f"PRAGMA foreign_key_list({table})"
                ).fetchall()
                actual_foreign_keys = {
                    (
                        str(row["from"]),
                        str(row["table"]),
                        str(row["to"]),
                    )
                    for row in rows
                }
                if actual_foreign_keys != expected_foreign_keys:
                    raise UnsupportedLedgerSchemaError(
                        f"ledger table {table!r} has foreign keys "
                        f"{actual_foreign_keys!r}; expected "
                        f"{expected_foreign_keys!r}"
                    )
            for table, expected_unique_columns in (
                _SIDECAR_UNIQUE_COLUMNS.items()
            ):
                indexes = connection.execute(
                    f"PRAGMA index_list({table})"
                ).fetchall()
                actual_unique_columns = set()
                for index in indexes:
                    if not bool(index["unique"]) or bool(index["partial"]):
                        continue
                    info = connection.execute(
                        f"PRAGMA index_info({index['name']})"
                    ).fetchall()
                    actual_unique_columns.add(
                        tuple(str(row["name"]) for row in info)
                    )
                if actual_unique_columns != expected_unique_columns:
                    raise UnsupportedLedgerSchemaError(
                        f"ledger table {table!r} has unique constraints "
                        f"{actual_unique_columns!r}; expected "
                        f"{expected_unique_columns!r}"
                    )

    @staticmethod
    def _validate_database_integrity(
        connection: sqlite3.Connection,
    ) -> None:
        violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if violations:
            raise UnsupportedLedgerSchemaError(
                "ledger contains foreign-key violations"
            )
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()
        if integrity is None or str(integrity[0]) != "ok":
            raise UnsupportedLedgerSchemaError(
                "ledger integrity check failed"
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

    def append_recall_context(self, context: RecallContext) -> None:
        self._append(
            "recall_contexts",
            context.snapshot_id,
            context,
            columns={"created_at": context.created_at.isoformat()},
        )

    def append_intervention(self, record: InterventionRecord) -> None:
        payload = _canonical(record)
        with self._lock, self._connect() as connection:
            validate_content_derived_intervention_id(record)
            existing = connection.execute(
                """
                SELECT payload_json
                FROM intervention_records
                WHERE record_id = ?
                """,
                (record.intervention_id,),
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != payload:
                    raise ImmutableRecordError(
                        f"record {record.intervention_id!r} already exists "
                        "with different content"
                    )
                return
            if record.previous_intervention_id is not None:
                previous_row = connection.execute(
                    """
                    SELECT payload_json
                    FROM intervention_records
                    WHERE record_id = ?
                    """,
                    (record.previous_intervention_id,),
                ).fetchone()
                if previous_row is None:
                    raise RecordNotFoundError(
                        record.previous_intervention_id
                    )
                _validate_previous_intervention_lineage(
                    current=record,
                    previous=InterventionRecord.model_validate_json(
                        previous_row["payload_json"]
                    ),
                )
            iteration_record = connection.execute(
                """
                SELECT record_id
                FROM intervention_records
                WHERE run_id = ? AND iteration_id = ?
                """,
                (record.run_id, record.iteration_id),
            ).fetchone()
            if iteration_record is not None:
                raise ImmutableRecordError(
                    f"run {record.run_id!r} iteration {record.iteration_id!r} "
                    "already has an intervention"
                )
            try:
                connection.execute(
                    """
                    INSERT INTO intervention_records (
                        record_id,
                        run_id,
                        iteration_id,
                        task_id,
                        domain,
                        schema_id,
                        manipulation_status,
                        config_digest,
                        previous_intervention_id,
                        created_at,
                        payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.intervention_id,
                        record.run_id,
                        record.iteration_id,
                        record.task_id,
                        record.proposal.domain,
                        record.proposal.schema_id,
                        record.manipulation_status,
                        record.config_digest,
                        record.previous_intervention_id,
                        record.created_at.isoformat(),
                        payload,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                message = str(exc)
                if "UNIQUE constraint failed" in message:
                    raise ImmutableRecordError(message) from exc
                raise RecordNotFoundError(message) from exc

    def get_intervention(self, intervention_id: str) -> InterventionRecord:
        return self._load_one(
            "intervention_records",
            intervention_id,
            InterventionRecord,
        )

    def list_interventions(self, run_id: str) -> list[InterventionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM intervention_records
                WHERE run_id = ?
                ORDER BY created_at, record_id
                """,
                (run_id,),
            ).fetchall()
        return [
            InterventionRecord.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def append_trial_provenance(self, record: TrialProvenanceRecord) -> None:
        payload = _canonical(record)
        with self._lock, self._connect() as connection:
            validate_content_derived_provenance_id(record)
            existing = connection.execute(
                """
                SELECT payload_json
                FROM trial_provenance_records
                WHERE record_id = ?
                """,
                (record.provenance_id,),
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != payload:
                    raise ImmutableRecordError(
                        f"record {record.provenance_id!r} already exists "
                        "with different content"
                    )
                return

            attempt = connection.execute(
                """
                SELECT payload_json
                FROM experiment_attempts
                WHERE record_id = ?
                """,
                (record.attempt_id,),
            ).fetchone()
            if attempt is None:
                raise RecordNotFoundError(record.attempt_id)
            attempt_record = ExperimentAttempt.model_validate_json(
                attempt["payload_json"]
            )
            observation = connection.execute(
                """
                SELECT payload_json
                FROM observations
                WHERE record_id = ?
                """,
                (record.observation_id,),
            ).fetchone()
            if observation is None:
                raise RecordNotFoundError(record.observation_id)
            observation_record = Observation.model_validate_json(
                observation["payload_json"]
            )
            intervention_row = connection.execute(
                """
                SELECT payload_json
                FROM intervention_records
                WHERE record_id = ?
                """,
                (record.intervention_id,),
            ).fetchone()
            if intervention_row is None:
                raise RecordNotFoundError(record.intervention_id)
            intervention = InterventionRecord.model_validate_json(
                intervention_row["payload_json"]
            )
            _validate_trial_lineage(
                attempt=attempt_record,
                observation=observation_record,
                intervention=intervention,
                provenance=record,
            )
            if (
                record.proposal_digest != intervention.proposal_digest
                or record.intervention_digest != intervention.intervention_digest
                or record.config_digest != intervention.config_digest
            ):
                raise ValueError(
                    "trial provenance digests do not match intervention"
                )
            observation_binding = connection.execute(
                """
                SELECT record_id
                FROM trial_provenance_records
                WHERE observation_id = ?
                """,
                (record.observation_id,),
            ).fetchone()
            if observation_binding is not None:
                raise ImmutableRecordError(
                    f"observation {record.observation_id!r} "
                    "already has provenance"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO trial_provenance_records (
                        record_id,
                        attempt_id,
                        observation_id,
                        intervention_id,
                        source_digest,
                        config_digest,
                        environment_digest,
                        dataset_digest,
                        evidence_digest,
                        contract_digest,
                        created_at,
                        payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.provenance_id,
                        record.attempt_id,
                        record.observation_id,
                        record.intervention_id,
                        record.source_digest,
                        record.config_digest,
                        record.environment_digest,
                        record.dataset_digest,
                        record.evidence_digest,
                        record.contract_digest,
                        record.created_at.isoformat(),
                        payload,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                message = str(exc)
                if "UNIQUE constraint failed" in message:
                    raise ImmutableRecordError(message) from exc
                raise RecordNotFoundError(message) from exc

    def find_trial_provenance(
        self,
        observation_id: str,
    ) -> TrialProvenanceRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM trial_provenance_records
                WHERE observation_id = ?
                """,
                (observation_id,),
            ).fetchone()
        if row is None:
            return None
        return TrialProvenanceRecord.model_validate_json(row["payload_json"])

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

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis:
        return self._load_one("hypotheses", hypothesis_id, Hypothesis)

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

    def list_recall_contexts(self) -> list[RecallContext]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM recall_contexts
                ORDER BY created_at, record_id
                """
            ).fetchall()
        return [RecallContext.model_validate_json(row["payload_json"]) for row in rows]

    def has_valid_verification(self, run_id: str) -> bool:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM experience_records WHERE valid = 1"
            ).fetchall()
        return any(
            ExperienceRecord.model_validate_json(row["payload_json"]).attempt.run_id
            == run_id
            for row in rows
        )

    def snapshot_id(self) -> str:
        payloads: list[str] = []
        with self._connect() as connection:
            for table in _SNAPSHOT_TABLES:
                rows = connection.execute(
                    f"SELECT payload_json FROM {table} ORDER BY record_id"
                ).fetchall()
                payloads.extend(row["payload_json"] for row in rows)
        return hashlib.sha256("\n".join(payloads).encode("utf-8")).hexdigest()
