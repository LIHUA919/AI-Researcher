"""Adapters from existing research flow outputs into eval traces."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import uuid
from typing import Any, Dict, List, Optional

from research_agent.inno.evals.evaluator import build_default_research_evaluator
from research_agent.inno.evals.evaluator import GoalDrivenEvalReport
from research_agent.inno.evals.trace import AgentStepTrace, ResearchRunTrace, RetrievalItem, ToolCallTrace


def _split_claim_block(text: str) -> List[str]:
    normalized = text.replace("\r", "").strip()
    if not normalized:
        return []

    sections = re.split(r"\n\s*\n+", normalized)
    claims: List[str] = []
    for section in sections:
        section = re.sub(r"^\s*(\d+\.\s*)", "", section.strip())
        section = re.sub(r"^\s*[-*]\s*", "", section)
        if len(section) < 8:
            continue
        claims.append(section)
    return claims or [normalized]


def _normalize_claims(claims: Optional[List[str]]) -> List[str]:
    normalized_claims: List[str] = []
    for claim in claims or []:
        claim = claim.strip()
        if not claim:
            continue
        normalized_claims.extend(_split_claim_block(claim))
    return normalized_claims


def _collect_evidence_items(
    plan: Optional[Dict[str, Any]],
    final_output: Optional[Dict[str, Any]],
) -> List[RetrievalItem]:
    items: List[RetrievalItem] = []
    for section_name, section_value in (plan or {}).items():
        if isinstance(section_value, str) and section_value.strip():
            items.append(
                RetrievalItem(
                    source_type="other",
                    identifier=f"plan:{section_name}",
                    title=section_name,
                    content=section_value,
                )
            )
        elif isinstance(section_value, dict) and section_value:
            items.append(
                RetrievalItem(
                    source_type="other",
                    identifier=f"plan:{section_name}",
                    title=section_name,
                    content=json.dumps(section_value, ensure_ascii=False),
                )
            )

    for output_name, output_value in (final_output or {}).items():
        if isinstance(output_value, str) and output_value.strip():
            items.append(
                RetrievalItem(
                    source_type="tool_output",
                    identifier=f"final:{output_name}",
                    title=output_name,
                    content=output_value,
                )
            )
        elif isinstance(output_value, dict) and output_value:
            items.append(
                RetrievalItem(
                    source_type="tool_output",
                    identifier=f"final:{output_name}",
                    title=output_name,
                    content=json.dumps(output_value, ensure_ascii=False),
                )
            )
    return items


def build_research_run_trace(
    *,
    run_id: str,
    task_id: str,
    query: str,
    goal: str = "",
    claims: Optional[List[str]] = None,
    plan: Optional[Dict[str, Any]] = None,
    final_output: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tool_calls: Optional[List[ToolCallTrace]] = None,
    agent_steps: Optional[List[AgentStepTrace]] = None,
) -> ResearchRunTrace:
    """Build a minimal eval trace from a completed research-flow result.

    This is the v1 seam from `run_infer_idea` / `run_infer_plan` outputs into
    the eval system. Upstream tracing can populate tool_calls and agent_steps
    later without changing this helper.
    """

    trace = ResearchRunTrace(
        run_id=run_id,
        task_id=task_id,
        query=query,
        goal=goal,
        claims=_normalize_claims(claims),
        plan=dict(plan or {}),
        final_output=dict(final_output or {}),
        metadata=dict(metadata or {}),
    )
    for item in _collect_evidence_items(plan, final_output):
        trace.add_retrieval(item)
    for tool_call in tool_calls or []:
        trace.add_tool_call(tool_call)
    for agent_step in agent_steps or []:
        trace.add_agent_step(agent_step)
    return trace


def _to_jsonable(value: Any) -> Any:
    """Recursively convert dataclasses and datetimes into JSON-safe values."""

    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def save_eval_artifacts(
    output_dir: str,
    trace: ResearchRunTrace,
    report: GoalDrivenEvalReport,
) -> Dict[str, str]:
    """Persist eval artifacts for a completed research flow."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    trace_path = output_path / "trace.json"
    report_path = output_path / "report.json"

    trace_path.write_text(
        json.dumps(_to_jsonable(trace), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(_to_jsonable(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "trace_path": str(trace_path),
        "report_path": str(report_path),
    }


def build_and_save_eval_result(
    flow_result: Dict[str, Any],
    cache_path: str,
) -> Dict[str, Any]:
    """Build trace/report artifacts from a completed flow result and persist them."""

    trace = build_research_run_trace(
        run_id=str(uuid.uuid4()),
        task_id=flow_result["task_id"],
        query=flow_result["query"],
        goal=flow_result.get("goal", ""),
        claims=flow_result.get("claims"),
        plan=flow_result.get("plan"),
        final_output=flow_result.get("final_output"),
        metadata=flow_result.get("metadata"),
        tool_calls=flow_result.get("tool_calls"),
        agent_steps=flow_result.get("agent_steps"),
    )
    report = build_default_research_evaluator(trace.goal).evaluate(trace)
    artifact_paths = save_eval_artifacts(
        str(Path(cache_path) / "evals"),
        trace,
        report,
    )
    return {
        "flow_result": flow_result,
        "eval_trace": trace,
        "eval_report": report,
        "artifact_paths": artifact_paths,
    }
