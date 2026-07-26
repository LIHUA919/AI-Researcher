import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from research_agent.inno.evals import (
    CandidateGeneration,
    CandidateRequest,
    ExperienceBenchmarkRunner,
    OpenAICompatibleSolutionGenerator,
    ScientistBenchTrialAdapter,
    TrialConfiguration,
    load_scientist_bench_task,
)
from research_agent.inno.experience import (
    CommandVerifier,
    RecallContext,
    RecallRequest,
)


ROOT = Path(__file__).resolve().parents[2]
EVALUATOR_ROOT = ROOT / "benchmark" / "evaluators" / "scientist_bench"
TASK_PATH = ROOT / "benchmark" / "final" / "diffu_flow" / "immiscible_diffusion.json"
CONTRACT_PATH = (
    EVALUATOR_ROOT / "immiscible_diffusion_task1" / "contract.yaml"
)
INTERFACE_PATH = (
    EVALUATOR_ROOT / "immiscible_diffusion_task1" / "interface.md"
)

CORRECT_SOLUTION = """
import itertools
import struct

def _half(value):
    return struct.unpack("e", struct.pack("e", value))[0]

def assign_noise(images, noises, use_fp16=False):
    cast = _half if use_fp16 else float
    def cost(permutation):
        return sum(
            sum(
                (cast(x) - cast(y)) ** 2
                for x, y in zip(images[row], noises[column])
            )
            for row, column in enumerate(permutation)
        )
    return list(min(itertools.permutations(range(len(noises))), key=cost))
""".strip()

NAIVE_SOLUTION = """
def assign_noise(images, noises, use_fp16=False):
    return list(range(len(noises)))
""".strip()

PARTIAL_SOLUTION = """
import itertools

def assign_noise(images, noises, use_fp16=False):
    if use_fp16:
        return list(range(len(noises)))
    def cost(permutation):
        return sum(
            sum(
                (x - y) ** 2
                for x, y in zip(images[row], noises[column])
            )
            for row, column in enumerate(permutation)
        )
    return list(min(itertools.permutations(range(len(noises))), key=cost))
""".strip()


class FeedbackAwareGenerator:
    configuration_digest = "generator@" + "1" * 64

    def generate(self, request):
        return CandidateGeneration(
            solution_code=(
                CORRECT_SOLUTION if request.recall.items else NAIVE_SOLUTION
            ),
            analysis=(
                "Use a globally optimal permutation."
                if request.recall.items
                else "Try the input order before feedback is available."
            ),
            tokens=10,
        )


class RegressingGenerator:
    configuration_digest = "generator@" + "2" * 64

    def __init__(self):
        self.calls = {}

    def generate(self, request):
        key = (request.configuration.mode, request.configuration.seed)
        self.calls[key] = self.calls.get(key, 0) + 1
        return CandidateGeneration(
            solution_code=(
                PARTIAL_SOLUTION if self.calls[key] == 1 else NAIVE_SOLUTION
            ),
            analysis="The second candidate intentionally regresses.",
        )


def _run(tmp_path):
    task = load_scientist_bench_task(
        TASK_PATH,
        task_level="task1",
        primary_metric="implementation_score",
    )
    trial = ScientistBenchTrialAdapter(
        tmp_path,
        task=task,
        evaluator_root=EVALUATOR_ROOT,
        contract_path=CONTRACT_PATH,
        interface_path=INTERFACE_PATH,
        generator=FeedbackAwareGenerator(),
        domain="scientist-bench-diffusion",
        verifier=CommandVerifier(contract_dir=EVALUATOR_ROOT),
    )
    return ExperienceBenchmarkRunner(
        trial,
        require_verified_trials=True,
    ).run(
        task,
        seeds=[11, 12],
        model="feedback-aware-test-generator",
        budget={"iterations": 2, "recall_items": 4, "recall_tokens": 1000},
        evaluator_version="scientist-bench-immiscible-diffusion-task1@1",
        dataset_digest="scientist-bench-immiscible-hidden-cases@1",
        code_revision="test-revision",
    )


def test_verified_scientist_bench_trial_closes_the_experience_loop(tmp_path):
    report = _run(tmp_path)

    assert report.baseline.scores == pytest.approx([0.275, 0.275])
    assert report.closed_loop.scores == pytest.approx([1.0, 1.0])
    assert report.experience_gain == pytest.approx(0.725)
    assert report.closed_loop.valid_rate == 1
    assert report.baseline.repeated_failure_rate == 0.5
    for pair in report.trial_pairs:
        assert pair.baseline.score_source == "verification_record"
        assert pair.closed_loop.score_source == "verification_record"
        assert pair.baseline.comparison_digest == pair.closed_loop.comparison_digest
        assert pair.baseline.manifest_digest != pair.closed_loop.manifest_digest
        assert pair.closed_loop.verification_id
        assert pair.closed_loop.evaluator_digest
        assert pair.closed_loop.artifact_digests["verification_result.json"]

    closed_log = (
        tmp_path
        / "immiscible_diffusion:task1"
        / "closed-loop"
        / "seed-11"
        / "attempt-2"
        / "run.log"
    )
    off_log = (
        tmp_path
        / "immiscible_diffusion:task1"
        / "off"
        / "seed-11"
        / "attempt-2"
        / "run.log"
    )
    assert json.loads(closed_log.read_text())["citations"]
    assert json.loads(off_log.read_text())["citations"] == []


def test_candidate_generation_cannot_supply_a_score():
    with pytest.raises(ValidationError):
        CandidateGeneration(
            solution_code=NAIVE_SOLUTION,
            analysis="self-scored",
            score=1.0,
        )


def test_trial_selects_best_verified_attempt_within_fixed_budget(tmp_path):
    task = load_scientist_bench_task(
        TASK_PATH,
        task_level="task1",
        primary_metric="implementation_score",
    )
    trial = ScientistBenchTrialAdapter(
        tmp_path,
        task=task,
        evaluator_root=EVALUATOR_ROOT,
        contract_path=CONTRACT_PATH,
        interface_path=INTERFACE_PATH,
        generator=RegressingGenerator(),
        domain="scientist-bench-diffusion",
        verifier=CommandVerifier(contract_dir=EVALUATOR_ROOT),
    )
    report = ExperienceBenchmarkRunner(
        trial,
        require_verified_trials=True,
    ).run(
        task,
        seeds=[21],
        model="regressing-test-generator",
        budget={"iterations": 2},
        evaluator_version="scientist-bench-immiscible-diffusion-task1@1",
        dataset_digest="scientist-bench-immiscible-hidden-cases@1",
        code_revision="test-revision",
    )

    for result in (
        report.trial_pairs[0].baseline,
        report.trial_pairs[0].closed_loop,
    ):
        assert result.score > 0.275
        assert result.selected_iteration == 1
        assert len(result.attempt_ids) == len(result.verification_ids) == 2


def test_candidate_normalization_tolerates_unclosed_provider_fence():
    normalized = ScientistBenchTrialAdapter._normalize_solution(
        "```python\ndef quantize(values, levels, eps=1e-3):\n    return values"
    )

    assert normalized.startswith("def quantize")
    compile(normalized, "solution.py", "exec")


def test_identical_model_request_is_reused_across_paired_modes():
    task = load_scientist_bench_task(
        TASK_PATH,
        task_level="task1",
        primary_metric="implementation_score",
    )
    generator = OpenAICompatibleSolutionGenerator(
        model="paired-model",
        base_url="https://example.invalid/v1",
        api_key="not-a-real-key",
    )

    class FakeCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                "<analysis>same request</analysis>"
                                f"<solution>{NAIVE_SOLUTION}</solution>"
                            )
                        )
                    )
                ],
                usage=None,
            )

    completions = FakeCompletions()
    generator.client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    recall_request = RecallRequest(
        query=task.query,
        task_id=task.task_id,
        domain="test",
        dataset_id="dataset",
        model_family="paired-model",
    )
    recall = RecallContext(
        snapshot_id="snapshot",
        memory_snapshot_id="memory",
        request=recall_request,
        items=[],
        token_count=0,
    )
    common = {
        "task_id": task.task_id,
        "seed": 1,
        "model": "paired-model",
        "budget": {"iterations": 2, "generation_tokens": 1000},
        "evaluator_version": "evaluator@1",
        "dataset_digest": "dataset",
        "code_revision": "revision",
    }
    first = generator.generate(
        CandidateRequest(
            task=task,
            configuration=TrialConfiguration(mode="off", **common),
            interface_text="interface",
            recall=recall,
            iteration=1,
        )
    )
    paired = generator.generate(
        CandidateRequest(
            task=task,
            configuration=TrialConfiguration(mode="closed-loop", **common),
            interface_text="interface",
            recall=recall,
            iteration=1,
        )
    )

    assert completions.calls == 1
    assert first.solution_code == paired.solution_code
    assert first.cache_hit is False
    assert paired.cache_hit is True
