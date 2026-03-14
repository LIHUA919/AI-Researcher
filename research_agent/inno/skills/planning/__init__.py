"""planning skill: ML experiment planning tools."""

from typing import Callable, List

from research_agent.inno.tools.inno_tools.planning_tools import (
    plan_dataset,
    plan_model,
    plan_testing,
    plan_training,
)


def get_tools(**kwargs) -> List[Callable]:
    return [plan_dataset, plan_model, plan_training, plan_testing]
