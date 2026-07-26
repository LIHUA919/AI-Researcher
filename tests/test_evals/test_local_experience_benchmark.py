from benchmark.run_local_experience_benchmark import run


def test_local_behavioral_benchmark_measures_verified_recall_gain(tmp_path):
    report = run(tmp_path, seeds=[1, 2])

    assert report.metadata["synthetic"] is False
    assert report.baseline.valid_rate == 1.0
    assert report.closed_loop.valid_rate == 1.0
    assert report.baseline.repeated_failure_rate == 0.5
    assert report.closed_loop.repeated_failure_rate == 0.0
    assert report.experience_gain > 0.9
    assert report.closed_loop.mean == 1.0

    baseline_transitions = (
        tmp_path
        / "operator-selection"
        / "off"
        / "seed-1"
        / "experience.sqlite3"
    )
    closed_loop_transitions = (
        tmp_path
        / "operator-selection"
        / "closed-loop"
        / "seed-1"
        / "experience.sqlite3"
    )
    assert baseline_transitions.is_file()
    assert closed_loop_transitions.is_file()
