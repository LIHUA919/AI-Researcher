from types import SimpleNamespace

from research_agent.inno.agents.inno_agent.judge_agent import get_judge_agent


def test_judge_and_code_review_agents_have_bounded_turns():
    judge_agent = get_judge_agent(
        model="test-model",
        code_env=SimpleNamespace(),
    )

    assert judge_agent.max_turns == 16
    code_review_transfer = next(
        function
        for function in judge_agent.functions
        if function.__name__ == "transfer_to_code_review_agent"
    )
    code_review_agent = code_review_transfer("test idea")
    assert code_review_agent.max_turns == 16
