import json
from research_agent.inno.workflow.flowcache import FlowModule, ToolModule, AgentModule
from research_agent.inno.tools.inno_tools.paper_search import get_arxiv_paper_meta
from research_agent.inno.tools.inno_tools.code_search import search_github_repos, search_github_code
from research_agent.inno.agents.inno_agent.plan_agent import get_coding_plan_agent
from research_agent.inno.agents.inno_agent.prepare_agent import get_prepare_agent
from research_agent.inno.agents.inno_agent.ml_agent import get_ml_agent
from research_agent.inno.agents.inno_agent.judge_agent import get_judge_agent
from research_agent.inno.agents.inno_agent.survey_agent import get_survey_agent
from research_agent.inno.agents.inno_agent.exp_analyser import get_exp_analyser_agent
from research_agent.inno.agents.inno_agent.idea_agent import get_idea_agent, get_code_survey_agent
from research_agent.inno.tools.arxiv_source import download_arxiv_source_by_title
from research_agent.inno import MetaChain
from tqdm import tqdm
from pydantic import BaseModel, Field
from research_agent.constant import DOCKER_WORKPLACE_NAME, COMPLETION_MODEL, CHEEP_MODEL
from research_agent.inno.util import single_select_menu
from research_agent.inno.environment.docker_env import DockerEnv, DockerConfig
from research_agent.inno.environment.browser_env import BrowserEnv
from research_agent.inno.environment.markdown_browser import RequestsMarkdownBrowser
import asyncio
import argparse
import os
from typing import List, Dict, Any, Union
from research_agent.inno.logger import MetaChainLogger
import importlib
from research_agent.inno.environment.utils import (
    setup_dataset,
    ensure_legacy_workspace_aliases,
    normalize_workplace_layout,
)
from research_agent.runtime import MasterRuntime
from research_agent.inno.evals import (
    build_and_save_eval_result,
)
from research_agent.inno_common import (
    build_project_manifest,
    build_plan_result,
    build_survey_result,
    ensure_plan_artifacts,
    load_cached_stage_result,
    load_cached_plan_result,
    warp_source_papers,
    extract_json_from_output,
    load_cached_survey_result,
    load_cached_prepare_result,
    persist_stage_result,
    resolve_experiment_analysis,
    resolve_prepare_result,
    persist_survey_result,
    get_args,
    EvalMetadata,
    load_instance,
    github_search,
)

def _persist_stage_output(cache_path: str, stage_name: str, payload: Dict[str, Any]) -> str:
    stage_dir = os.path.join(cache_path, "plan_stages")
    os.makedirs(stage_dir, exist_ok=True)
    stage_path = os.path.join(stage_dir, f"{stage_name}.json")
    with open(stage_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)
    return stage_path


def _update_runtime_progress(runtime: MasterRuntime, run_id: str, task_level: str) -> None:
    runtime.write_runtime_status(
        run_id=run_id,
        status="running",
        metadata={"entrypoint": "run_infer_idea", "task_level": task_level},
    )

class InnoFlow(FlowModule):
    def __init__(self, cache_path: str, log_path: Union[str, None, MetaChainLogger] = None, model: str = "gpt-4o-2024-08-06", code_env: DockerEnv = None, web_env: BrowserEnv = None, file_env: RequestsMarkdownBrowser = None):
        super().__init__(cache_path, log_path, model)
        self.load_ins = ToolModule(load_instance, cache_path, trace_recorder=self.record_tool_call)
        self.git_search = ToolModule(github_search, cache_path, trace_recorder=self.record_tool_call)
        self.prepare_agent = AgentModule(get_prepare_agent(model=CHEEP_MODEL, code_env=code_env), self.client, cache_path, trace_recorder=self.record_agent_step)
        self.download_papaer = ToolModule(download_arxiv_source_by_title, cache_path, trace_recorder=self.record_tool_call)
        self.coding_plan_agent = AgentModule(get_coding_plan_agent(model=CHEEP_MODEL, code_env=code_env), self.client, cache_path, trace_recorder=self.record_agent_step)
        self.ml_agent = AgentModule(get_ml_agent(model=COMPLETION_MODEL, code_env=code_env), self.client, cache_path, trace_recorder=self.record_agent_step)
        self.judge_agent = AgentModule(get_judge_agent(model=CHEEP_MODEL, code_env=code_env, web_env=web_env, file_env=file_env), self.client, cache_path, trace_recorder=self.record_agent_step)
        self.idea_agent = AgentModule(get_idea_agent(model=CHEEP_MODEL, file_env=file_env, code_env=code_env), self.client, cache_path, trace_recorder=self.record_agent_step)
        # self.survey_agent = AgentModule(get_survey_agent(model=CHEEP_MODEL, file_env=file_env, code_env=code_env), self.client, cache_path)
        self.code_survey_agent = AgentModule(get_code_survey_agent(model=CHEEP_MODEL, file_env=file_env, code_env=code_env), self.client, cache_path, trace_recorder=self.record_agent_step)
        self.exp_analyser = AgentModule(get_exp_analyser_agent(model=CHEEP_MODEL, file_env=file_env, code_env=code_env), self.client, cache_path, trace_recorder=self.record_agent_step)
    async def forward(self, instance_path: str, task_level: str, local_root: str, workplace_name: str, max_iter_times: int, category: str, references: str, *args, **kwargs):
        metadata = self.load_ins({"instance_path": instance_path, "task_level": task_level})
        runtime = MasterRuntime(self.cache_path)
        runtime.sync_stage_state()
        run_id = metadata.get("instance_id", task_level)
        runtime.write_runtime_status(
            run_id=run_id,
            status="running",
            metadata={"entrypoint": "run_infer_idea", "task_level": task_level},
        )
        stage_state = runtime.load_state()
        context_variables = {
            "working_dir": f"/{workplace_name}", # TODO: change to the codebase path
            "date_limit": metadata["date_limit"],
            "prepare_artifact_dir": os.path.join(self.cache_path, "prepare_stage"),
            "plan_artifact_dir": os.path.join(self.cache_path, "plan_stages"),
            "stage_state": stage_state,
        }

        github_result = self.git_search({"metadata": metadata})
        data_module = importlib.import_module(f"benchmark.process.dataset_candidate.{category}.metaprompt")

        dataset_description = f"""\
You should select SEVERAL datasets as experimental datasets from the following description:
{data_module.DATASET}

We have already selected the following baselines for these datasets:
{data_module.BASELINE}

The performance comparison of these datasets:
{data_module.COMPARISON}

And the evaluation metrics are:
{data_module.EVALUATION}

{data_module.REF}
"""
        
        query = f"""\
You are given a list of papers, searching results of the papers on GitHub. 
List of papers:
{references}

Searching results of the papers on GitHub:
{github_result}

Your task is to choose at least 5 repositories as the reference codebases. Note that this time there is no innovative ideas, you should choose the most valuable repositories as the reference codebases.
"""
        prepare_dict = load_cached_prepare_result(self.cache_path)
        if prepare_dict:
            context_variables["prepare_result"] = prepare_dict
            prepare_res = json.dumps(prepare_dict, ensure_ascii=False, indent=4)
            runtime.record_stage_completion(
                "prepare",
                artifacts={"prepare_result": os.path.join(self.cache_path, "prepare_stage", "prepare_result.json")},
            )
        else:
            messages = [{"role": "user", "content": query}]
            prepare_messages, context_variables = await self.prepare_agent(messages, context_variables)
            prepare_res = prepare_messages[-1]["content"]
            prepare_dict = resolve_prepare_result(
                prepare_res=prepare_res,
                context_variables=context_variables,
                local_root=local_root,
                workplace_name=workplace_name,
                category=category,
                cache_path=self.cache_path,
            )
            if not prepare_dict:
                raise ValueError("Prepare Agent did not produce a usable prepare_result and no fallback could be derived.")
            prepare_res = json.dumps(prepare_dict, ensure_ascii=False, indent=4)
            runtime.record_stage_completion(
                "prepare",
                artifacts={"prepare_result": os.path.join(self.cache_path, "prepare_stage", "prepare_result.json")},
            )
        context_variables["stage_state"] = runtime.load_state()
        _update_runtime_progress(runtime, run_id, task_level)
        paper_list = prepare_dict["reference_papers"]
        download_res = self.download_papaer({"paper_list": paper_list, "local_root": local_root, "workplace_name": workplace_name})

        
        idea_query = f"""\
I have a task related to machine learning:
{data_module.TASK}
And a list of papers for your reference:
{references}

I have carefully gone through these papers' github repositories and found download some of them in my local machine, with the following information:
{prepare_res}
And I have also downloaded the corresponding paper in the Tex format, with the following information:
{download_res}

Your task is to thoroughly review research papers and generate innovative ideas for the given task.

Note that the math formula should be as complete as possible.
"""
        messages = [{"role": "user", "content": idea_query}]
        context_variables["notes"] = []
        survey_messages, context_variables = await self.idea_agent(messages, context_variables)
        survey_res = survey_messages[-1]["content"]
        ideas = [survey_res]
        IDEA_NUM = 5
        for i in range(IDEA_NUM - 1):
            messages.extend(survey_messages)
            messages.append({"role": "user", "content": "please survey again and give me another idea"})
            survey_messages, context_variables = await self.idea_agent(messages, context_variables, iter_times=i+1)
            survey_res = survey_messages[-1]["content"]
            ideas.append(survey_res)
        # messages.extend(survey_messages)
        messages = [{"role": "user", "content": """\
You have generated {} innovative ideas for the given task:
{}

Your task is to analyze multiple existing ideas, select the most novel one, enhance the idea if any key information is missing, finally give me the most novel idea with refined math formula and code implementation. Directly output the selected refined idea report.
""".format(IDEA_NUM, '\n===================\n==================='.join(ideas))}]
        survey_messages, context_variables = await self.idea_agent(messages, context_variables, iter_times="select")
        survey_res = survey_messages[-1]["content"]
        # print(survey_res)

        code_survey_query = f"""\
I have an innovative idea related to machine learning:
{survey_res}

I have carefully gone through these papers' github repositories and found download some of them in my local machine, in the directory `/workplace`, use the `list_files` tool to navigate the directory.
And I have also downloaded the corresponding paper in the Tex format, with the following information:
{download_res}

Your task is to carefully understand the innovative idea, and thoroughly review codebases and generate a comprehensive implementation report for the innovative idea. You can NOT stop to review the codebases until you have get all academic concepts in the innovative idea.

Note that the code implementation should be as complete as possible.
"""
        cached_survey = load_cached_survey_result(self.cache_path)
        if cached_survey.get("survey_report"):
            code_survey_res = cached_survey["survey_report"]
            context_variables["model_survey"] = code_survey_res
            runtime.record_stage_completion(
                "survey",
                artifacts={"survey_result": os.path.join(self.cache_path, "survey_stage", "survey_result.json")},
            )
        else:
            messages = [{"role": "user", "content": code_survey_query}]
            code_survey_messages, context_variables = await self.code_survey_agent(messages, context_variables)
            code_survey_res = build_survey_result(code_survey_messages[-1]["content"], context_variables)
            context_variables["model_survey"] = code_survey_res
            survey_result_path = persist_survey_result(
                self.cache_path,
                metadata.get("instance_id", task_level),
                code_survey_query,
                code_survey_res,
            )
            runtime.record_stage_completion(
                "survey",
                artifacts={"survey_result": survey_result_path},
            )
        context_variables["stage_state"] = runtime.load_state()
        _update_runtime_progress(runtime, run_id, task_level)

        plan_query = f"""\
I have an innovative ideas related to machine learning:
{survey_res}
And a list of papers for your reference:
{references}

I have carefully gone through these papers' github repositories and found download some of them in my local machine, with the following information:
{prepare_res}

I have also understood the innovative idea, comprehensively reviewed the codebases, and generated a comprehensive implementation report:
{code_survey_res}

We have already selected the following datasets as experimental datasets:
{dataset_description}

Your task is to carefully review the existing resources and understand the task, and give me a detailed plan for the implementation.
"""
        cached_plan = load_cached_plan_result(self.cache_path)
        if cached_plan.get("plan_report"):
            context_variables["dataset_plan"] = cached_plan.get("dataset_plan", context_variables.get("dataset_plan"))
            context_variables["training_plan"] = cached_plan.get("training_plan", context_variables.get("training_plan"))
            context_variables["testing_plan"] = cached_plan.get("testing_plan", context_variables.get("testing_plan"))
            context_variables["plan_artifacts"] = cached_plan.get("plan_artifacts", context_variables.get("plan_artifacts", {}))
            plan_res = cached_plan["plan_report"]
            runtime.record_stage_completion(
                "plan",
                artifacts=context_variables.get("plan_artifacts", {}),
            )
        else:
            messages = [{"role": "user", "content": plan_query}]
            plan_messages, context_variables = await self.coding_plan_agent(messages, context_variables)
            context_variables = ensure_plan_artifacts(
                context_variables=context_variables,
                dataset_description=dataset_description,
                idea_text=survey_res,
                workplace_name=workplace_name,
            )
            plan_res = build_plan_result(plan_messages[-1]["content"], context_variables)
            _persist_stage_output(
                self.cache_path,
                "plan_report",
                {
                    "task_id": metadata.get("instance_id", task_level),
                    "query": plan_query,
                    "plan_report": plan_res,
                    "plan_artifacts": context_variables.get("plan_artifacts", {}),
                },
            )
            runtime.record_stage_completion(
                "plan",
                artifacts=context_variables.get("plan_artifacts", {}),
            )
        context_variables["stage_state"] = runtime.load_state()
        _update_runtime_progress(runtime, run_id, task_level)

        if not runtime.can_run_stage("implement"):
            raise RuntimeError("Implement stage cannot start before required prior stages are completed.")

        # write the model based on the model survey notes
        ml_dev_query = f"""\
INPUT:
You are given an innovative idea:
{survey_res}. 
and the reference codebases chosen by the `Prepare Agent`:
{prepare_res}
And I have conducted the comprehensive survey on the innovative idea and the papers, and give you the model survey notes:
{survey_res}
You should carefully go through the math formula and the code implementation, and implement the innovative idea according to the plan and existing resources.

We have already selected the following datasets as experimental datasets:
{dataset_description}
Your task is to implement the innovative idea after carefully reviewing the math formula and the code implementation in the paper notes and existing resources in the directory `/{workplace_name}`. You should select ONE most appropriate and lightweight dataset from the given datasets, and implement the idea by creating new model, and EXACTLY run TWO epochs of training and testing on the ACTUAL dataset on the GPU device. Note that EVERY atomic academic concept in model survey notes should be implemented in the project.

PROJECT STRUCTURE REQUIREMENTS:
1. Directory Organization
- Data: `/{workplace_name}/project/data/`
     * Use the dataset selected by the `Plan Agent`
     * NO toy or random datasets
- Model Components: `/{workplace_name}/project/model/`
    * All model architecture files
    * All model components as specified in survey notes
    * Dataset processing scripts and utilities

- Training: `/{workplace_name}/project/training/`
    * Training loop implementation
    * Loss functions
    * Optimization logic

- Testing: `/{workplace_name}/project/testing/`
    * Evaluation metrics
    * Testing procedures

- Data processing: `/{workplace_name}/project/data_processing/`
    * Implement the data processing pipeline

- Main Script: `/{workplace_name}/project/run_training_testing.py`
    * Complete training and testing pipeline
    * Configuration management
    * Results logging

2. Complete Implementation Requirements
   - MUST implement EVERY component from model survey notes
   - NO placeholder code (no `pass`, `...`, `raise NotImplementedError`)
   - MUST include complete logic and mathematical operations
   - Each component MUST be fully functional and tested

3. Dataset and Training Requirements
   - Select and download ONE actual dataset from references
   - Implement full data processing pipeline
   - Train for exactly 2 epochs
   - Test model performance after training
   - Log all metrics and results

4. Integration Requirements
   - All components must work together seamlessly
   - Clear dependencies between modules
   - Consistent coding style and documentation
   - Proper error handling and GPU support

EXECUTION WORKFLOW:
1. Dataset Setup
   - Choose appropriate dataset from references (You MUST use the actual dataset, not the toy or random datasets) [IMPORTANT!!!]
   - Download to data directory `/{workplace_name}/project/data`
   - Implement processing pipeline in `/{workplace_name}/project/data_processing/`
   - Verify data loading

2. Model Implementation
   - Study model survey notes thoroughly
   - Implement each component completely
   - Document mathematical operations
   - Add comprehensive docstrings

3. Training Implementation
   - Complete training loop
   - Loss function implementation
   - Optimization setup
   - Progress monitoring

4. Testing Setup
   - Implement evaluation metrics
   - Create testing procedures
   - Set up results logging
   - Error handling

5. Integration
   - Create run_training_testing.py
   - Configure for 2 epoch training
   - Add GPU support and OOM handling
   - Implement full pipeline execution

VERIFICATION CHECKLIST:
1. Project Structure
   - All directories exist and are properly organized
   - Each component is in correct location
   - Clear separation of concerns

2. Implementation Completeness
   - Every function is fully implemented
   - No placeholder code exists
   - All mathematical operations are coded
   - Documentation is complete

3. Functionality
   - Dataset downloads and loads correctly
   - Training runs for 2 epochs
   - Testing produces valid metrics
   - GPU support is implemented

Remember: 
- MUST use actual dataset (no toy data, download according to the reference codebases) [IMPORTANT!!!]
- Implementation MUST strictly follow model survey notes
- ALL components MUST be fully implemented
- Project MUST run end-to-end without placeholders
- MUST complete 2 epochs of training and testing
"""
        messages = [{"role": "user", "content": ml_dev_query}]
        cached_implement = load_cached_stage_result(self.cache_path, "implement", "project_manifest.json")
        if not runtime.should_run_stage("implement") and cached_implement:
            ml_dev_res = cached_implement.get("implementation_report", "")
        else:
            ml_dev_messages, context_variables = await self.ml_agent(messages, context_variables)
            ml_dev_res = ml_dev_messages[-1]["content"]
            project_manifest = build_project_manifest(local_root, workplace_name)
            implement_path = persist_stage_result(
                self.cache_path,
                "implement",
                "project_manifest.json",
                {
                    "task_id": metadata.get("instance_id", task_level),
                    "implementation_report": ml_dev_res,
                    "project_manifest": project_manifest,
                },
            )
            runtime.record_stage_completion(
                "implement",
                artifacts={"project_manifest": implement_path},
            )
        context_variables["stage_state"] = runtime.load_state()
        _update_runtime_progress(runtime, run_id, task_level)

        if not runtime.can_run_stage("judge"):
            raise RuntimeError("Judge stage cannot start before implement stage is completed.")

        query = f"""\
INPUT:
You are given an innovative idea:
{survey_res}
and the reference codebases chosen by the `Prepare Agent`:
{prepare_res}
and the detailed coding plan:
{plan_res}
The implementation of the project:
{ml_dev_res}
Your task is to evaluate the implementation, and give a suggestion about the implementation. Note that you should carefully check whether the implementation meets the idea, especially the atomic academic concepts in the model survey notes one by one! If not, give comprehensive suggestions about the implementation.

[IMPORTANT] You should fully utilize the existing resources in the reference codebases as much as possible, including using the existing datasets, model components, and training process, but you should also implement the idea by creating new model components!

[IMPORTANT] You should recognize every key point in the innovative idea, and carefully check whether the implementation meets the idea one by one!

[IMPORTANT] Some tips about the evaluation:
1. The implementation should carefully follow the plan. Please check every component in the plan step by step.
2. The implementation should have the test process. All in all, you should train ONE dataset with TWO epochs, and finally test the model on the test dataset within one script. The test metrics should follow the plan.
3. The model should be train on GPU device. If you meet Out of Memory problem, you should try another specific GPU device.
"""
        input_messages = [{
            "role": "user",
            "content": query
        }]
        cached_judge = load_cached_stage_result(self.cache_path, "judge", "judge_report.json")
        if not runtime.should_run_stage("judge") and cached_judge:
            judge_res = cached_judge.get("judge_report", "")
            judge_messages = [{"role": "assistant", "content": judge_res}]
        else:
            judge_messages, context_variables = await self.judge_agent(input_messages, context_variables)
            judge_res = judge_messages[-1]["content"]
            judge_path = persist_stage_result(
                self.cache_path,
                "judge",
                "judge_report.json",
                {
                    "task_id": metadata.get("instance_id", task_level),
                    "judge_query": query,
                    "judge_report": judge_res,
                },
            )
            runtime.record_stage_completion(
                "judge",
                artifacts={"judge_report": judge_path},
            )
        context_variables["stage_state"] = runtime.load_state()
        _update_runtime_progress(runtime, run_id, task_level)

        MAX_ITER_TIMES = max_iter_times
        for i in range(MAX_ITER_TIMES):
            query = f"""\
You are given an innovative idea:
{survey_res}
and the reference codebases chosen by the `Prepare Agent`:
{prepare_res}
and the detailed coding plan:
{plan_res}
And your last implementation of the project:
{ml_dev_res}
The suggestion about your last implementation:
{judge_res}
Your task is to modify the project according to the suggestion. Note that you should MODIFY rather than create a new project! Take full advantage of the existing resources! Still use the SAME DATASET!

[IMPORTANT] You should modify the project in the directory `/{workplace_name}/project`, rather than create a new project!

[IMPORTANT] If you meet dataset missing problem, you should download the dataset from the reference codebases, and put the dataset in the directory `/{workplace_name}/project/data`. 

[IMPORTANT] You CANNOT stop util you 2 epochs of training and testing on your model with the ACTUAL dataset.

[IMPORTANT] You encounter ImportError while using `run_python()`, you should check whether every `__init__.py` file is correctly implemented in the directories in the `/{workplace_name}/project`!

[IMPORTANT] Carefully check whether model and its components are correctly implemented according to the model survey notes!

Remember: 
- Implementation MUST strictly follow model survey notes
- ALL components MUST be fully implemented
- Project MUST run end-to-end without placeholders
- MUST use actual dataset (no toy data)
- MUST complete 2 epochs of training and testing
"""
            judge_messages.append({"role": "user", "content": query})
            judge_messages, context_variables = await self.ml_agent(judge_messages, context_variables, iter_times=i+1)
            ml_dev_res = judge_messages[-1]["content"]
            query = f"""\
You are given an innovative idea:
{survey_res}
and the reference codebases chosen by the `Prepare Agent`:
{prepare_res}
and the detailed coding plan:
{plan_res}
The implementation of the project:
{ml_dev_res}
Please evaluate the implementation, and give a suggestion about the implementation.
"""
            judge_messages.append({"role": "user", "content": query})
            judge_messages, context_variables = await self.judge_agent(judge_messages, context_variables, iter_times=i+1)
            judge_res = judge_messages[-1]["content"]
            if '"fully_correct": true' in judge_messages[-1]["content"]:
                break   

        # return judge_messages[-1]["content"]
        # submit the code to the environment -> get the result


        
        ml_submit_query = f"""\
You are given an innovative idea:
{survey_res}
And your last implementation of the project:
{ml_dev_res}
The suggestion about your last implementation:
{judge_res}
You have run out the maximum iteration times to implement the idea by running the script `run_training_testing.py` with TWO epochs of training and testing on ONE ACTUAL dataset.
Your task is to submit the code to the environment by running the script `run_training_testing.py` with APPROPRIATE epochs of training and testing on THIS ACTUAL dataset in order to get some stastical results. You must MODIFY the epochs in the script `run_training_testing.py` rather than use the 2 epochs.

[IMPORTANT] In this stage, you are NOT allowed to modify the existing code in the script `run_training_testing.py` except for the epochs!

Note that if your last implementation is not runable, you should finalize the submission with `case_not_resolved` function. But you can temporarily ignore the judgement of the `Judge Agent` which contains the suggestions about the implementation.
After you get the result, you should return the result with your analysis and suggestions about the implementation with `case_resolved` function.
"""
        cached_submit = load_cached_stage_result(self.cache_path, "submit", "submit_result.json")
        if not runtime.should_run_stage("submit") and cached_submit:
            submit_res = cached_submit.get("submission_report", "")
        else:
            judge_messages.append({"role": "user", "content": ml_submit_query})
            judge_messages, context_variables = await self.ml_agent(judge_messages, context_variables, iter_times="submit")
            submit_res = judge_messages[-1]["content"]
            submit_path = persist_stage_result(
                self.cache_path,
                "submit",
                "submit_result.json",
                {
                    "task_id": metadata.get("instance_id", task_level),
                    "submission_query": ml_submit_query,
                    "submission_report": submit_res,
                },
            )
            runtime.record_stage_completion(
                "submit",
                artifacts={"submit_result": submit_path},
            )
        context_variables["stage_state"] = runtime.load_state()
        _update_runtime_progress(runtime, run_id, task_level)

        EXP_ITER_TIMES = 2
        analysis_report = ""
        for i in range(EXP_ITER_TIMES):
            exp_planner_query = f"""\
You are given an innovative idea:
{survey_res}
And the reference codebases chosen by the `Prepare Agent`:
{prepare_res}
And the detailed coding plan:
{plan_res}
You have conducted the experiments and get the experimental results:
{submit_res}
Your task is to: 
1. Analyze the experimental results and give a detailed analysis report about the results.
2. Analyze the reference codebases and papers, and give a further plan to let `Machine Learning Agent` to do more experiments based on the innovative idea. The further experiments could include but not limited to:
    - Modify the implementation to better fit the idea.
    - Add more experiments to prove the effectiveness and superiority of the idea. 
    - Visualize the experimental results and give a detailed analysis report about the results.
    - ANY other experiments that exsiting concurrent reference papers and codebases have done.
DO NOT use the `case_resolved` function before you have carefully and comprehensively analyzed the experimental results and the reference codebases and papers.
"""
            judge_messages.append({"role": "user", "content": exp_planner_query})
            judge_messages, context_variables = await self.exp_analyser(judge_messages, context_variables, iter_times=f"refine_{i+1}")
            analysis_report = judge_messages[-1]["content"]
            analysis_report, further_plan = resolve_experiment_analysis(
                context_variables,
                analysis_report,
            )
            # print(analysis_report)
            refine_query = f"""\
You are given an innovative idea:
{survey_res}
And the reference codebases chosen by the `Prepare Agent`:
{prepare_res}
And the detailed coding plan:
{plan_res}
You have conducted the experiments and get the experimental results:
{submit_res}
And a detailed analysis report about the results are given by the `Experiment Planner Agent`:
{analysis_report}
Your task is to refine the experimental results according to the analysis report by modifying existing code in the directory `/{workplace_name}/project`. You should NOT stop util every experiment is done with ACTUAL results. If you encounter Out of Memory problem, you should try another specific GPU device. If you encounter ANY other problems, you should try your best to solve the problem by yourself.

Note that you should fully utilize the existing code in the directory `/{workplace_name}/project` as much as possible. If you want to add more experiments, you should add the python script in the directory `/{workplace_name}/project/`, like `run_training_testing.py`. Select and output the important results during the experiments into the log files, do NOT output them all in the terminal.
"""
            judge_messages.append({"role": "user", "content": refine_query})
            judge_messages, context_variables = await self.ml_agent(judge_messages, context_variables, iter_times=f"refine_{i+1}")
            refine_res = judge_messages[-1]["content"]

        analysis_path = persist_stage_result(
            self.cache_path,
            "analyze",
            "analysis_report.json",
            {
                "task_id": metadata.get("instance_id", task_level),
                "analysis_report": analysis_report,
                "further_plan": further_plan if "further_plan" in locals() else {},
                "latest_refine_report": refine_res if "refine_res" in locals() else "",
            },
        )
        runtime.record_stage_completion(
            "analyze",
            artifacts={"analysis_report": analysis_path},
        )
        _update_runtime_progress(runtime, run_id, task_level)

        print(refine_res)
        runtime.sync_stage_state()
        goal_evaluation = runtime.evaluate_goal()
        runtime.write_runtime_status(
            run_id=run_id,
            status="completed" if goal_evaluation.all_criteria_met else "running",
            metadata={"entrypoint": "run_infer_idea", "task_level": task_level},
        )
        return {
            "task_id": metadata.get("instance_id", task_level),
            "query": idea_query,
            "goal": "discover and refine a novel research idea",
            "claims": [survey_res] if survey_res else [],
            "plan": {
                "dataset": context_variables.get("dataset_plan", ""),
                "model": context_variables.get("model_survey", ""),
                "training": context_variables.get("training_plan", ""),
                "testing": context_variables.get("testing_plan", ""),
            },
            "final_output": {
                "idea_report": survey_res,
                "code_survey_report": code_survey_res,
                "plan_report": plan_res,
                "judge_report": judge_res,
                "submission_report": submit_res,
            },
            "metadata": {
                "instance_path": instance_path,
                "task_level": task_level,
                "category": category,
                "workplace_name": workplace_name,
                "stage_state": runtime.load_state(),
                "goal_evaluation": {
                    "current_stage": goal_evaluation.current_stage,
                    "completed_stages": goal_evaluation.completed_stages,
                    "incomplete_stages": goal_evaluation.incomplete_stages,
                    "all_criteria_met": goal_evaluation.all_criteria_met,
                    "next_stage": runtime.next_stage(),
                },
            },
            "tool_calls": self.export_runtime_trace()["tool_calls"],
            "agent_steps": self.export_runtime_trace()["agent_steps"],
        }
        
def main(args, references):
    """
    MAX_ATTEMPTS

    # load the eval instance

    # choose the code base

    # generate the detailed coding plan

    # coding and debuging -> fail to implement the plan

    -> success to implement the plan

    # submit the code to the environment -> get the result

    for attempt in range(MAX_ATTEMPTS): 
        # evaluate the result

        # coding and debuging

        # submit the code to the environment -> get the result
        if done:
            break
    """
    # load the eval instance
    with open(args.instance_path, "r", encoding="utf-8") as f:
        eval_instance = json.load(f)
    instance_id = eval_instance["instance_id"] + "_idea"
    model_suffix = args.model.replace("/", "__")
    cache_path = args.cache_path + "_" + instance_id + "_" + model_suffix
    local_root = os.path.join(
        os.getcwd(),
        "workplace_paper",
        f"task_{instance_id}" + "_" + model_suffix,
    )
    container_name = args.container_name + "_" + instance_id + "_" + model_suffix
    os.makedirs(local_root, exist_ok=True)
    env_config = DockerConfig(container_name = container_name, 
                              workplace_name = args.workplace_name, 
                              communication_port = args.port, 
                              local_root = local_root,
                              )
    
    code_env = DockerEnv(env_config)
    normalize_workplace_layout(code_env.local_workplace)
    code_env.init_container()
    setup_dataset(args.category, code_env.local_workplace)
    ensure_legacy_workspace_aliases(code_env.local_workplace)
    web_env = BrowserEnv(browsergym_eval_env = None, local_root=env_config.local_root, workplace_name=env_config.workplace_name)
    file_env = RequestsMarkdownBrowser(viewport_size=1024 * 4, local_root=env_config.local_root, workplace_name=env_config.workplace_name, downloads_folder=os.path.join(env_config.local_root, env_config.workplace_name, "downloads"))
    flow = InnoFlow(cache_path=cache_path, log_path="log_" + instance_id, code_env=code_env, web_env=web_env, file_env=file_env, model=args.model)
    runtime = MasterRuntime(cache_path)
    try:
        result = asyncio.run(flow(instance_path=args.instance_path, task_level=args.task_level, local_root=local_root, workplace_name=args.workplace_name, max_iter_times=args.max_iter_times, category=args.category, references = references))
        return build_and_save_eval_result(result, cache_path)
    except Exception as exc:
        runtime.write_failure_status(
            run_id=instance_id,
            error_message=str(exc),
            stage_name=runtime.next_stage(),
            metadata={"entrypoint": "run_infer_idea", "task_level": args.task_level},
        )
        raise
    # print(judge_result)




if __name__ == "__main__":
    args = get_args()
    with open(args.instance_path, "r", encoding="utf-8") as f:
        eval_instance = json.load(f)
    references = warp_source_papers(eval_instance["source_papers"])
    main(args, references)





"""\
INPUT:
You are given an innovative idea:
Combine DDPM model with transformer model to generate the image.
And `Prepare Agent` has chosen the reference codebases:
{prepare_res}
And `Survey Agent` has given the model survey notes:
{survey_res}

REQUIREMENTS:
1. Model Organization
   - Break down the model into smaller, logical modules based on academic definitions
   - Each module should correspond to one or more academic concepts from the papers
   - Create a clear hierarchy of modules that can be assembled into the final model
   - Example structure:
     * Base modules (fundamental building blocks)
     * Intermediate modules (combining base modules)
     * Main model class (assembling all modules)

2. Module Implementation Guidelines
   - Each module should be in a separate file under `/{workplace_name}/project/model/`
   - Modules should have clear input/output interfaces
   - Include docstrings with academic references and mathematical formulations
   - Implement forward pass with complete mathematical operations

3. Complete Implementation Requirements
   - MUST implement EVERY component from model survey notes
   - NO placeholder code (no `pass`, `...`, `raise NotImplementedError`)
   - MUST include complete logic and mathematical operations
   - Each module MUST be fully functional and tested
   - Final model should inherit from nn.Module and combine all sub-modules

Remember: 
- Break down complex models into smaller, reusable modules
- Each module should map to specific academic concepts
- Implementation MUST strictly follow model survey notes
- ALL components MUST be fully implemented
- Project MUST run end-to-end without placeholders

Task: 
Carefully go through the model survey notes, break down the model into logical modules based on academic definitions, and implement each module in a realistic way. NO placeholder code. 
In this stage, you only care about the model implementation, and don't care about the dataset, training, testing.
"""
