from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from research_agent.inno.experience import (
    ArtifactRef,
    ExperimentAttempt,
    Hypothesis,
    Observation,
    SQLiteExperimentLedger,
    UnsupportedLedgerSchemaError,
)


NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def _append_legacy_records(ledger: SQLiteExperimentLedger) -> None:
    hypothesis = Hypothesis(
        hypothesis_id="hypothesis-legacy",
        task_id="one_layer_vq:task1",
        statement="A projection intervention improves utilization.",
        mechanism="The projection changes assignment geometry.",
        expected_metric="codebook_utilization",
        metric_direction="maximize",
        created_at=NOW,
    )
    attempt = ExperimentAttempt(
        attempt_id="attempt-legacy",
        run_id="run-legacy",
        iteration_id="iteration-1",
        task_id=hypothesis.task_id,
        hypothesis_id=hypothesis.hypothesis_id,
        code_revision="legacy-revision",
        dataset_id="cifar10",
        dataset_digest="legacy-dataset",
        model_config_digest="legacy-research-model",
        seed=401,
        budget={"seconds": 60},
        evaluation_contract_id="vq@1",
        recall_snapshot_id="empty",
        status="completed",
        created_at=NOW,
    )
    observation = Observation(
        observation_id="observation-legacy",
        attempt_id=attempt.attempt_id,
        exit_code=0,
        metrics={"codebook_utilization": 0.75},
        artifact_refs=[
            ArtifactRef(
                path="metrics.json",
                sha256="a" * 64,
                media_type="application/json",
                size_bytes=42,
            )
        ],
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        environment_fingerprint="python=3.11",
    )
    ledger.append_hypothesis(hypothesis)
    ledger.append_attempt(attempt)
    ledger.append_observation(observation)


def _legacy_payload_bytes(path) -> list[tuple[str, str, str]]:
    payloads: list[tuple[str, str, str]] = []
    with sqlite3.connect(path) as connection:
        for table in (
            "hypotheses",
            "experiment_attempts",
            "observations",
            "verification_records",
            "experience_records",
            "knowledge_records",
            "promotion_decisions",
        ):
            rows = connection.execute(
                f"""
                SELECT record_id, hex(CAST(payload_json AS BLOB))
                FROM {table}
                ORDER BY record_id
                """
            ).fetchall()
            payloads.extend((table, str(record_id), str(payload)) for record_id, payload in rows)
    return payloads


def _downgrade_to_legacy_schema(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE trial_provenance_records")
        connection.execute("DROP TABLE intervention_records")
        connection.execute("PRAGMA user_version = 0")


def _recreate_sidecars(
    path,
    *,
    include_foreign_keys: bool,
    include_unique_constraints: bool,
    intervention_task_id_type: str = "TEXT",
    intervention_task_id_not_null: bool = True,
    intervention_record_primary_key: bool = True,
    partial_intervention_unique: bool = False,
) -> None:
    intervention_unique = (
        ", UNIQUE (run_id, iteration_id)"
        if include_unique_constraints and not partial_intervention_unique
        else ""
    )
    partial_unique_index = (
        """
        CREATE UNIQUE INDEX idx_intervention_iteration_partial
            ON intervention_records(run_id, iteration_id)
            WHERE manipulation_status = 'baseline';
        """
        if include_unique_constraints and partial_intervention_unique
        else ""
    )
    intervention_foreign_key = (
        """
        , FOREIGN KEY (previous_intervention_id)
            REFERENCES intervention_records(record_id)
        """
        if include_foreign_keys
        else ""
    )
    provenance_unique = " UNIQUE" if include_unique_constraints else ""
    provenance_foreign_keys = (
        """
        , FOREIGN KEY (attempt_id)
            REFERENCES experiment_attempts(record_id)
        , FOREIGN KEY (observation_id)
            REFERENCES observations(record_id)
        , FOREIGN KEY (intervention_id)
            REFERENCES intervention_records(record_id)
        """
        if include_foreign_keys
        else ""
    )
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE trial_provenance_records")
        connection.execute("DROP TABLE intervention_records")
        connection.executescript(
            f"""
            CREATE TABLE intervention_records (
                record_id TEXT{
                    " PRIMARY KEY" if intervention_record_primary_key else " UNIQUE"
                },
                run_id TEXT NOT NULL,
                iteration_id TEXT NOT NULL,
                task_id {intervention_task_id_type}{
                    " NOT NULL" if intervention_task_id_not_null else ""
                },
                domain TEXT NOT NULL,
                schema_id TEXT NOT NULL,
                manipulation_status TEXT NOT NULL,
                config_digest TEXT,
                previous_intervention_id TEXT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
                {intervention_unique}
                {intervention_foreign_key}
            );
            {partial_unique_index}
            CREATE INDEX idx_intervention_records_run
                ON intervention_records(run_id, iteration_id);
            CREATE TABLE trial_provenance_records (
                record_id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL,
                observation_id TEXT NOT NULL{provenance_unique},
                intervention_id TEXT NOT NULL,
                source_digest TEXT NOT NULL,
                config_digest TEXT NOT NULL,
                environment_digest TEXT NOT NULL,
                dataset_digest TEXT NOT NULL,
                evidence_digest TEXT NOT NULL,
                contract_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
                {provenance_foreign_keys}
            );
            CREATE INDEX idx_trial_provenance_attempt
                ON trial_provenance_records(attempt_id);
            """
        )


def test_legacy_migration_preserves_payload_bytes_and_snapshot(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    legacy = SQLiteExperimentLedger(path)
    _append_legacy_records(legacy)
    snapshot_before = legacy.snapshot_id()
    payloads_before = _legacy_payload_bytes(path)
    _downgrade_to_legacy_schema(path)

    migrated = SQLiteExperimentLedger(path)

    assert migrated.snapshot_id() == snapshot_before
    assert _legacy_payload_bytes(path) == payloads_before
    assert migrated.list_interventions("run-legacy") == []
    assert migrated.find_trial_provenance("observation-legacy") is None
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_revision_2_missing_required_index_is_rejected(tmp_path):
    path = tmp_path / "malformed-v2.sqlite3"
    SQLiteExperimentLedger(path)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX idx_trial_provenance_attempt")

    with pytest.raises(
        UnsupportedLedgerSchemaError,
        match="idx_trial_provenance_attempt",
    ):
        SQLiteExperimentLedger(path)


def test_revision_2_rejects_required_index_attached_to_wrong_table(tmp_path):
    path = tmp_path / "misattached-index.sqlite3"
    SQLiteExperimentLedger(path)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX idx_trial_provenance_attempt")
        connection.execute(
            """
            CREATE INDEX idx_trial_provenance_attempt
            ON observations(attempt_id)
            """
        )

    with pytest.raises(
        UnsupportedLedgerSchemaError,
        match="idx_trial_provenance_attempt.*table",
    ):
        SQLiteExperimentLedger(path)


@pytest.mark.parametrize(
    ("include_foreign_keys", "include_unique_constraints", "message"),
    [
        (False, True, "foreign keys"),
        (True, False, "unique constraints"),
    ],
)
def test_revision_2_rejects_sidecars_with_weakened_constraints(
    tmp_path,
    include_foreign_keys,
    include_unique_constraints,
    message,
):
    path = tmp_path / f"weakened-{message.replace(' ', '-')}.sqlite3"
    SQLiteExperimentLedger(path)
    _recreate_sidecars(
        path,
        include_foreign_keys=include_foreign_keys,
        include_unique_constraints=include_unique_constraints,
    )

    with pytest.raises(UnsupportedLedgerSchemaError, match=message):
        SQLiteExperimentLedger(path)


def test_revision_2_rejects_sidecar_column_type_substitution(tmp_path):
    path = tmp_path / "wrong-column-type.sqlite3"
    SQLiteExperimentLedger(path)
    _recreate_sidecars(
        path,
        include_foreign_keys=True,
        include_unique_constraints=True,
        intervention_task_id_type="BLOB",
    )

    with pytest.raises(UnsupportedLedgerSchemaError, match="signature"):
        SQLiteExperimentLedger(path)


def test_revision_2_rejects_removed_not_null_constraint(tmp_path):
    path = tmp_path / "removed-not-null.sqlite3"
    SQLiteExperimentLedger(path)
    _recreate_sidecars(
        path,
        include_foreign_keys=True,
        include_unique_constraints=True,
        intervention_task_id_not_null=False,
    )

    with pytest.raises(UnsupportedLedgerSchemaError, match="signature"):
        SQLiteExperimentLedger(path)


def test_revision_2_rejects_primary_key_replaced_by_unique_constraint(tmp_path):
    path = tmp_path / "unique-not-primary-key.sqlite3"
    SQLiteExperimentLedger(path)
    _recreate_sidecars(
        path,
        include_foreign_keys=True,
        include_unique_constraints=True,
        intervention_record_primary_key=False,
    )

    with pytest.raises(UnsupportedLedgerSchemaError, match="signature"):
        SQLiteExperimentLedger(path)


def test_revision_2_rejects_partial_unique_as_full_unique_constraint(tmp_path):
    path = tmp_path / "partial-unique.sqlite3"
    SQLiteExperimentLedger(path)
    _recreate_sidecars(
        path,
        include_foreign_keys=True,
        include_unique_constraints=True,
        partial_intervention_unique=True,
    )

    with pytest.raises(UnsupportedLedgerSchemaError, match="unique constraints"):
        SQLiteExperimentLedger(path)


@pytest.mark.parametrize("version", [1, 3, 99])
def test_unknown_schema_versions_are_rejected_without_mutation(tmp_path, version):
    path = tmp_path / f"future-{version}.sqlite3"
    SQLiteExperimentLedger(path)
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {version}")
        schema_before = connection.execute(
            """
            SELECT type, name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()

    with pytest.raises(
        UnsupportedLedgerSchemaError,
        match=f"schema version {version}",
    ):
        SQLiteExperimentLedger(path)

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == version
        assert connection.execute(
            """
            SELECT type, name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall() == schema_before


def test_malformed_legacy_schema_rolls_back_without_partial_sidecars(tmp_path):
    path = tmp_path / "malformed-legacy.sqlite3"
    SQLiteExperimentLedger(path)
    _downgrade_to_legacy_schema(path)
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE hypotheses RENAME TO old_hypotheses")
        connection.execute(
            """
            CREATE TABLE hypotheses (
                record_id TEXT PRIMARY KEY
            )
            """
        )
        connection.execute("DROP TABLE old_hypotheses")

    with pytest.raises(
        UnsupportedLedgerSchemaError,
        match="hypotheses.*columns",
    ):
        SQLiteExperimentLedger(path)

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert "intervention_records" not in tables
        assert "trial_provenance_records" not in tables


def test_foreign_key_failure_rolls_back_the_entire_migration(tmp_path):
    path = tmp_path / "orphaned-legacy.sqlite3"
    SQLiteExperimentLedger(path)
    _downgrade_to_legacy_schema(path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            INSERT INTO experiment_attempts (
                record_id,
                hypothesis_id,
                payload_json
            )
            VALUES ('orphan', 'missing-hypothesis', '{}')
            """
        )

    with pytest.raises(
        UnsupportedLedgerSchemaError,
        match="foreign-key violations",
    ):
        SQLiteExperimentLedger(path)

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert "intervention_records" not in tables
        assert "trial_provenance_records" not in tables
