from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

from research_agent.run_infer_plan import (
    FROZEN_VQ_TEMPLATES,
    InnoFlow,
    build_frozen_submission_report,
    run_frozen_vq_protocol,
)


def test_frozen_vq_protocol_runs_project_entrypoint(monkeypatch, tmp_path):
    project_dir = tmp_path / "workplace" / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "protocol.py").write_text("corrupted", encoding="utf-8")
    (project_dir / "run_training_testing.py").write_text(
        "anny",
        encoding="utf-8",
    )
    invocations = []

    def fake_run(command, **kwargs):
        assert (project_dir / "protocol.py").read_bytes() == (
            FROZEN_VQ_TEMPLATES["protocol.py"]
        ).read_bytes()
        assert (project_dir / "run_training_testing.py").read_bytes() == (
            FROZEN_VQ_TEMPLATES["run_training_testing.py"]
        ).read_bytes()
        invocations.append((command, kwargs))
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="completed",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    code_env = SimpleNamespace(
        local_workplace=str(tmp_path / "workplace"),
    )

    result = run_frozen_vq_protocol(code_env, "workplace")

    assert result == "completed"
    assert invocations[0][0][-1] == "run_training_testing.py"
    assert invocations[0][1]["cwd"] == project_dir
    assert Path(invocations[0][0][0]).name == "python"
    assert invocations[0][1]["env"]["HF_HUB_OFFLINE"] == "1"


def test_frozen_vq_protocol_rejects_failed_training(monkeypatch, tmp_path):
    project_dir = tmp_path / "workplace" / "project"
    project_dir.mkdir(parents=True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="training failed",
        ),
    )
    code_env = SimpleNamespace(
        local_workplace=str(tmp_path / "workplace"),
    )

    with pytest.raises(RuntimeError, match="training failed"):
        run_frozen_vq_protocol(code_env, "workplace")


def test_inno_flow_retains_code_environment_for_frozen_protocol(tmp_path):
    code_env = SimpleNamespace()

    flow = InnoFlow(
        cache_path=str(tmp_path),
        code_env=code_env,
        web_env=SimpleNamespace(),
        file_env=SimpleNamespace(),
    )

    assert flow.code_env is code_env


def test_frozen_submission_report_is_nonempty_and_claim_limited():
    report = build_frozen_submission_report(
        '{"event": "run_completed", "evidence_digest": "abc"}'
    )

    assert "independent evaluator" in report
    assert "no scientific improvement is claimed" in report
    assert '"evidence_digest": "abc"' in report
