from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from research_agent.runtime.master import MasterRuntime


@dataclass(frozen=True)
class SupervisorResult:
    status: str
    restart_count: int
    returncode: int | None
    last_error: str | None


class GoalDrivenSupervisor:
    def __init__(
        self,
        *,
        runtime: MasterRuntime,
        run_id: str,
        command: Sequence[str],
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        max_restarts: int = 2,
        poll_interval_seconds: float = 30.0,
        stale_timeout_seconds: int = 900,
        termination_grace_seconds: float = 5.0,
        process_factory: Callable[[], subprocess.Popen] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ):
        self.runtime = runtime
        self.run_id = run_id
        self.command = list(command)
        self.cwd = cwd
        self.env = dict(env) if env is not None else None
        self.max_restarts = max_restarts
        self.poll_interval_seconds = poll_interval_seconds
        self.stale_timeout_seconds = stale_timeout_seconds
        self.termination_grace_seconds = termination_grace_seconds
        self.process_factory = process_factory
        self.sleep_fn = sleep_fn or time.sleep

    def _spawn_process(self):
        if self.process_factory is not None:
            return self.process_factory()
        return subprocess.Popen(
            self.command,
            cwd=self.cwd or os.getcwd(),
            env=self.env,
        )

    def _terminate_process(self, process) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=self.termination_grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=self.termination_grace_seconds)

    def _mark_running(self) -> None:
        self.runtime.sync_stage_state()
        self.runtime.write_runtime_status(
            run_id=self.run_id,
            status="running",
            metadata={"supervisor": "goal-driven"},
        )

    def _final_result(
        self,
        *,
        status: str,
        restart_count: int,
        returncode: int | None,
        last_error: str | None,
    ) -> SupervisorResult:
        if status == "completed":
            self.runtime.write_runtime_status(
                run_id=self.run_id,
                status="completed",
                last_error=None,
                metadata={"supervisor": "goal-driven"},
            )
        elif status == "stalled":
            self.runtime.write_stalled_status(
                run_id=self.run_id,
                reason=last_error or "stalled",
                stage_name=self.runtime.next_stage(),
                metadata={"supervisor": "goal-driven"},
            )
        else:
            self.runtime.write_failure_status(
                run_id=self.run_id,
                error_message=last_error or "failed",
                stage_name=self.runtime.next_stage(),
                metadata={"supervisor": "goal-driven"},
            )
        return SupervisorResult(
            status=status,
            restart_count=restart_count,
            returncode=returncode,
            last_error=last_error,
        )

    def run(self) -> SupervisorResult:
        restart_count = 0

        while True:
            self._mark_running()
            process = self._spawn_process()

            while True:
                self.runtime.sync_stage_state()
                goal = self.runtime.evaluate_goal()
                if goal.all_criteria_met:
                    self._terminate_process(process)
                    return self._final_result(
                        status="completed",
                        restart_count=restart_count,
                        returncode=process.poll(),
                        last_error=None,
                    )

                returncode = process.poll()
                if returncode is not None:
                    last_error = (
                        "process_exited_before_completion"
                        if returncode == 0
                        else f"process_exit_{returncode}"
                    )
                    break

                stall = self.runtime.evaluate_stall(
                    max_stale_seconds=self.stale_timeout_seconds,
                )
                if stall.stalled:
                    self._terminate_process(process)
                    last_error = stall.reason
                    break

                self.sleep_fn(self.poll_interval_seconds)

            if restart_count >= self.max_restarts:
                final_status = "stalled" if last_error == "heartbeat_stale" else "failed"
                return self._final_result(
                    status=final_status,
                    restart_count=restart_count,
                    returncode=process.poll(),
                    last_error=last_error,
                )

            restart_count += 1
