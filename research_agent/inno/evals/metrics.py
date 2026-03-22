"""Goal-driven evaluation metrics for research runs."""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

from research_agent.inno.evals.trace import ResearchRunTrace


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _contains_any(haystack: str, needles: Iterable[str]) -> bool:
    normalized_haystack = _normalize(haystack)
    return any(_normalize(needle) in normalized_haystack for needle in needles if needle)


def evidence_coverage(trace: ResearchRunTrace) -> Dict[str, object]:
    """Score how many claims are backed by retrieved evidence or tool outputs."""

    claims = trace.claims or []
    if not claims:
        return {"score": 1.0, "supported_claims": [], "unsupported_claims": []}

    evidence_texts: List[str] = []
    evidence_texts.extend(
        f"{item.title} {item.content}".strip() for item in trace.retrieved_items
    )
    evidence_texts.extend(
        f"{call.tool_name} {call.output_summary}".strip() for call in trace.tool_calls
    )

    supported, unsupported = [], []
    for claim in claims:
        if _contains_any(" ".join(evidence_texts), [claim]):
            supported.append(claim)
        else:
            unsupported.append(claim)

    score = len(supported) / len(claims)
    return {
        "score": score,
        "supported_claims": supported,
        "unsupported_claims": unsupported,
    }


def plan_executability(
    plan: Dict[str, object],
    required_sections: Sequence[str] = ("dataset", "model", "training", "testing"),
) -> Dict[str, object]:
    """Score whether a plan contains the minimal executable structure."""

    section_scores: Dict[str, float] = {}
    missing_sections: List[str] = []

    for section in required_sections:
        value = plan.get(section)
        if isinstance(value, str):
            section_scores[section] = 1.0 if value.strip() else 0.0
        elif isinstance(value, dict):
            section_scores[section] = 1.0 if any(
                isinstance(v, str) and v.strip() or isinstance(v, (list, dict)) and len(v) > 0
                for v in value.values()
            ) else 0.0
        elif isinstance(value, list):
            section_scores[section] = 1.0 if len(value) > 0 else 0.0
        else:
            section_scores[section] = 0.0

        if section_scores[section] == 0.0:
            missing_sections.append(section)

    score = sum(section_scores.values()) / len(required_sections)
    return {
        "score": score,
        "section_scores": section_scores,
        "missing_sections": missing_sections,
    }
