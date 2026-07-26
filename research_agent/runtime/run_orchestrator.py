from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Protocol

from research_agent.inno.evals import build_and_save_eval_result
from research_agent.inno.environment.browser_env import BrowserEnv
from research_agent.inno.environment.docker_env import DockerConfig, DockerEnv
from research_agent.inno.environment.markdown_browser import RequestsMarkdownBrowser
from research_agent.inno.environment.utils import (
    ensure_legacy_workspace_aliases,
    normalize_workplace_layout,
    setup_dataset,
)
from research_agent.runtime.experience_adapter import ExperienceRunAdapter
from research_agent.runtime.master import MasterRuntime


class FlowFactory(Protocol):
    def __call__(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class ResearchRunLaunch:
    run_id: str
    task_id: str
    query: str
    entrypoint: str
    task_level: str
    model: str
    domain: str
    dataset_id: str


class ResearchExecutionAdapter(Protocol):
    cache_path: Path
    project_dir: Path

    def execute(self, *, recall_context: Any, verification_check: Any) -> dict[str, Any]:
        """Execute one Experiment Attempt and return the flow result."""

    def build_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Build the caller-facing result bundle for a completed Research Run."""


@dataclass
class DockerFlowExecutionAdapter:
    """Prepare and execute the existing Docker-backed research Flow."""

    cache_path: Path
    project_dir: Path
    flow: Any
    flow_arguments: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_args(
        cls,
        args: Any,
        *,
        run_id: str,
        flow_factory: FlowFactory,
        flow_arguments: dict[str, Any],
    ) -> "DockerFlowExecutionAdapter":
        model_suffix = args.model.replace("/", "__")
        cache_path = Path(f"{args.cache_path}_{run_id}_{model_suffix}")
        local_root = (
            Path.cwd()
            / "workplace_paper"
            / f"task_{run_id}_{model_suffix}"
        )
        local_root.mkdir(parents=True, exist_ok=True)
        container_name = f"{args.container_name}_{run_id}_{model_suffix}"
        env_config = DockerConfig(
            container_name=container_name,
            workplace_name=args.workplace_name,
            communication_port=args.port,
            local_root=str(local_root),
        )
        code_env = DockerEnv(env_config)
        normalize_workplace_layout(code_env.local_workplace)
        code_env.init_container()
        setup_dataset(args.category, code_env.local_workplace)
        ensure_legacy_workspace_aliases(code_env.local_workplace)
        web_env = BrowserEnv(
            browsergym_eval_env=None,
            local_root=env_config.local_root,
            workplace_name=env_config.workplace_name,
        )
        file_env = RequestsMarkdownBrowser(
            viewport_size=1024 * 4,
            local_root=env_config.local_root,
            workplace_name=env_config.workplace_name,
            downloads_folder=os.path.join(
                env_config.local_root,
                env_config.workplace_name,
                "downloads",
            ),
        )
        flow = flow_factory(
            cache_path=str(cache_path),
            log_path=f"log_{run_id}",
            code_env=code_env,
            web_env=web_env,
            file_env=file_env,
            model=args.model,
            cache_policy=getattr(args, "cache_policy", "reuse"),
        )
        return cls(
            cache_path=cache_path,
            project_dir=local_root / args.workplace_name / "project",
            flow=flow,
            flow_arguments={
                "instance_path": args.instance_path,
                "task_level": args.task_level,
                "local_root": str(local_root),
                "workplace_name": args.workplace_name,
                "max_iter_times": args.max_iter_times,
                "category": args.category,
                **flow_arguments,
            },
        )

    def execute(self, *, recall_context: Any, verification_check: Any) -> dict[str, Any]:
        return asyncio.run(
            self.flow(
                **self.flow_arguments,
                recall_context=recall_context,
                verification_check=verification_check,
            )
        )

    def build_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return build_and_save_eval_result(result, str(self.cache_path))


class ResearchRunOrchestrator:
    """Own the common Recall → execute → verify → iterate lifecycle."""

    def __init__(
        self,
        *,
        experience: ExperienceRunAdapter,
        execution: ResearchExecutionAdapter,
    ) -> None:
        self.experience = experience
        self.execution = execution

    def run(self, launch: ResearchRunLaunch) -> dict[str, Any]:
        runtime = MasterRuntime(str(self.execution.cache_path))
        recall_context = None
        iteration_number = 1
        attempt_recorded = False
        try:
            recall_context = self._recall(launch)
            outcome = None
            iteration_limit = (
                self.experience.max_iterations
                if self.experience.runs_closed_loop
                else 1
            )
            result: dict[str, Any] = {}
            for iteration_number in range(1, iteration_limit + 1):
                attempt_recorded = False
                result = self.execution.execute(
                    recall_context=recall_context,
                    verification_check=self.experience.pending_verification_check(),
                )
                outcome = self.experience.after_flow(
                    result,
                    project_dir=self.execution.project_dir,
                    run_id=launch.run_id,
                    model=launch.model,
                    domain=launch.domain,
                    dataset_id=launch.dataset_id,
                    model_family=launch.model,
                    recall_context=recall_context,
                    iteration_number=iteration_number,
                )
                attempt_recorded = self.experience.records_experience
                self.experience.finalize_runtime(
                    run_id=launch.run_id,
                    outcome=outcome,
                )
                if (
                    not self.experience.runs_closed_loop
                    or outcome is None
                    or outcome.action != "continue"
                ):
                    break
                recall_context = self._recall(launch)

            bundle = self.execution.build_result(result)
            bundle["experience_outcome"] = (
                outcome.model_dump(mode="json") if outcome is not None else None
            )
            return bundle
        except Exception as exc:
            experience_recording_error = self._record_failure(
                launch=launch,
                recall_context=recall_context,
                iteration_number=iteration_number,
                attempt_recorded=attempt_recorded,
                error=exc,
            )
            runtime.write_failure_status(
                run_id=launch.run_id,
                error_message=str(exc),
                stage_name=runtime.next_stage(),
                metadata={
                    "entrypoint": launch.entrypoint,
                    "task_level": launch.task_level,
                    "experience_recording_error": experience_recording_error,
                },
            )
            raise

    def _recall(self, launch: ResearchRunLaunch):
        return self.experience.before_run(
            task_id=launch.task_id,
            query=launch.query,
            domain=launch.domain,
            dataset_id=launch.dataset_id,
            model_family=launch.model,
        )

    def _record_failure(
        self,
        *,
        launch: ResearchRunLaunch,
        recall_context: Any,
        iteration_number: int,
        attempt_recorded: bool,
        error: Exception,
    ) -> str | None:
        if not self.experience.records_experience or attempt_recorded:
            return None
        try:
            failed_outcome = self.experience.after_failure(
                project_dir=self.execution.project_dir,
                run_id=launch.run_id,
                task_id=launch.task_id,
                query=launch.query,
                model=launch.model,
                domain=launch.domain,
                dataset_id=launch.dataset_id,
                model_family=launch.model,
                recall_context=recall_context,
                iteration_number=iteration_number,
                error=error,
            )
            self.experience.finalize_runtime(
                run_id=launch.run_id,
                outcome=failed_outcome,
            )
        except Exception as record_exc:
            return f"{type(record_exc).__name__}: {record_exc}"
        return None
