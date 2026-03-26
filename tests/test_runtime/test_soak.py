from argparse import Namespace

from research_agent.runtime.soak import build_run_command, build_soak_env, compute_cache_path


def test_compute_cache_path_uses_requested_model_suffix():
    cache_path = compute_cache_path("cache_soak", "one_layer_vq", "openai/gpt-4o-2024-08-06")

    assert cache_path == "cache_soak_one_layer_vq_openai__gpt-4o-2024-08-06"


def test_build_run_command_includes_required_arguments():
    args = Namespace(
        python_bin=".venv/bin/python",
        entry_script="research_agent/run_infer_plan.py",
        instance_path="benchmark/final/vq/one_layer_vq.json",
        task_level="task1",
        model="gpt-4o-2024-08-06",
        workplace_name="workplace",
        cache_prefix="cache_soak",
        port=12345,
        max_iter_times=0,
        category="vq",
        container_name="paper_eval",
    )

    command = build_run_command(args)

    assert command[0] == ".venv/bin/python"
    assert "--instance_path" in command
    assert "benchmark/final/vq/one_layer_vq.json" in command
    assert "--category" in command
    assert "vq" in command


def test_build_soak_env_defaults_model_fallbacks_to_primary_model():
    args = Namespace(
        llm_timeout=180,
        llm_retry_attempts=3,
        llm_retry_backoff_seconds=5,
        model_fallbacks="",
        model="gpt-4o-2024-08-06",
    )

    env = build_soak_env(args)

    assert env["AUTO_SELECT_FIRST_OPTION"] == "1"
    assert env["MODEL_FALLBACKS"] == "gpt-4o-2024-08-06"
