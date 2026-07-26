from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from openai import OpenAI

from benchmark.run_local_experience_benchmark import (
    LocalVerifiedExperienceTrial,
    OperatorSelection,
)
from research_agent.inno.evals.experience_benchmark import (
    ExperienceBenchmarkRunner,
    ExperienceBenchmarkTask,
    TrialConfiguration,
    save_experience_gain_report,
)
from research_agent.inno.experience import RecallContext


EVALUATOR_DIR = (
    Path(__file__).parent / "evaluators" / "operator_selection_identity"
)


class OpenAICompatibleOperatorSelector:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
    ) -> None:
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def __call__(
        self,
        config: TrialConfiguration,
        recall: RecallContext,
    ) -> OperatorSelection:
        evidence = "\n".join(
            f"- {item.citation_id}: {item.lesson} (outcome={item.outcome})"
            for item in recall.items
        )
        if not evidence:
            evidence = "- No prior verified evidence is available."
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You select one candidate for a black-box experiment. "
                        "Use cited verified evidence when present. Never claim "
                        "that an unverified guess is correct."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Paired seed: {config.seed}\n"
                        "Goal: maximize a hidden transformation score.\n"
                        "Candidates: identity or square.\n"
                        f"Verified evidence:\n{evidence}\n"
                        "Select exactly one candidate."
                    ),
                },
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "select_operator",
                        "description": "Select the next black-box candidate.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "operator": {
                                    "type": "string",
                                    "enum": ["identity", "square"],
                                },
                                "reason": {"type": "string"},
                            },
                            "required": ["operator", "reason"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            tool_choice="required",
            temperature=0,
            max_tokens=128,
        )
        message = response.choices[0].message
        if not message.tool_calls:
            raise RuntimeError("model did not return the required selection tool")
        arguments = json.loads(message.tool_calls[0].function.arguments)
        usage = response.usage
        return OperatorSelection(
            operator=arguments["operator"],
            tokens=(
                (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)
                if usage is not None
                else 0
            ),
        )


def run(
    output_root: Path,
    *,
    seeds: list[int],
    model: str,
    base_url: str,
    api_key: str,
):
    selector = OpenAICompatibleOperatorSelector(
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
    task = ExperienceBenchmarkTask(
        task_id="operator-selection-model-smoke",
        query="Select a black-box operator using only verified prior outcomes.",
        goal="Verify that a real model can act on cited negative experience.",
        primary_metric="score",
        direction="maximize",
        metadata={
            "synthetic": False,
            "scope": "external-model behavioral smoke benchmark",
        },
    )
    trial = LocalVerifiedExperienceTrial(
        output_root,
        evaluator_dir=EVALUATOR_DIR,
        selector=selector,
        domain="external-model-behavioral-smoke",
    )
    return ExperienceBenchmarkRunner(trial).run(
        task,
        seeds=seeds,
        model=model,
        budget={"iterations": 2},
        evaluator_version="operator-selection-identity@1",
        dataset_digest="hidden-identity-transform@1",
        code_revision="external-model-behavioral-smoke@1",
        metadata={
            "synthetic": False,
            "claim_scope": (
                "Validates model response to verified recall in a controlled "
                "task; not evidence of Scientist-Bench improvement."
            ),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument(
        "--output-root",
        default=".ai_researcher/benchmarks/model-experience-smoke",
    )
    args = parser.parse_args()
    api_key = os.getenv(args.api_key_env)
    if not api_key:
        parser.error(f"environment variable {args.api_key_env!r} is not set")
    seeds = [int(value) for value in args.seeds.split(",") if value]
    output_root = Path(args.output_root)
    report_path = output_root / "experience_gain.json"
    if report_path.exists():
        parser.error(
            f"report already exists at {report_path}; use a fresh --output-root"
        )
    report = run(
        output_root,
        seeds=seeds,
        model=args.model,
        base_url=args.base_url,
        api_key=api_key,
    )
    print(save_experience_gain_report(report, report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
