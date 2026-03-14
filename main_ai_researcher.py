import argparse
import logging
import os
import asyncio

import global_state
from dotenv import load_dotenv


logger = logging.getLogger(__name__)


def init_ai_researcher():
    """Load environment, validate required variables, and configure logging.

    Returns a dict of validated configuration values used by the research
    pipeline modes.
    """
    load_dotenv()

    # Set up basic logging (mirrors web_ai_researcher.setup_logging pattern)
    logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(logs_dir, exist_ok=True)

    import datetime

    log_file = os.path.join(
        logs_dir,
        f"log_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log",
    )
    global_state.LOG_PATH = log_file

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)

    # Validate and parse env vars with safe defaults
    config = {
        "category": os.getenv("CATEGORY", "recommendation"),
        "instance_id": os.getenv("INSTANCE_ID", "rotation_vq"),
        "task_level": os.getenv("TASK_LEVEL", "task1"),
        "container_name": os.getenv("CONTAINER_NAME", "paper_eval"),
        "workplace_name": os.getenv("WORKPLACE_NAME", "workplace"),
        "cache_path": os.getenv("CACHE_PATH", "cache"),
        "port": int(os.getenv("PORT", "12345")),
        "max_iter_times": int(os.getenv("MAX_ITER_TIMES", "0")),
    }

    logger.info("AI-Researcher initialized with config: %s", config)
    return config


def get_args_research():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance_path", type=str, default="benchmark/gnn.json")
    parser.add_argument("--container_name", type=str, default="paper_eval")
    parser.add_argument("--task_level", type=str, default="task1")
    parser.add_argument("--model", type=str, default="gpt-4o-2024-08-06")
    parser.add_argument("--workplace_name", type=str, default="workplace")
    parser.add_argument("--cache_path", type=str, default="cache")
    parser.add_argument("--port", type=int, default=12345)
    parser.add_argument("--max_iter_times", type=int, default=0)
    parser.add_argument("--category", type=str, default="recommendation")
    args = parser.parse_args()
    return args


def get_args_paper():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research_field", type=str, default="vq")
    parser.add_argument("--instance_id", type=str, default="rotation_vq")
    args = parser.parse_args()
    return args


def _prepare_research_args(config):
    """Build a research args namespace from the validated config dict.

    This consolidates the duplicated argument setup that was previously
    repeated for Mode 1 (Detailed Idea) and Mode 2 (Reference-Based Ideation).
    """
    from research_agent.constant import COMPLETION_MODEL

    args = get_args_research()
    args.instance_path = (
        f"../benchmark/final/{config['category']}/{config['instance_id']}.json"
    )
    args.task_level = config["task_level"]
    args.model = COMPLETION_MODEL
    args.container_name = config["container_name"]
    args.workplace_name = config["workplace_name"]
    args.cache_path = config["cache_path"]
    args.port = config["port"]
    args.max_iter_times = config["max_iter_times"]
    args.category = config["category"]
    return args


def main_ai_researcher(input, reference, mode):
    """Run the AI-Researcher pipeline in the specified *mode*.

    Modes:
        - 'Detailed Idea Description': run_infer_plan
        - 'Reference-Based Ideation': run_infer_idea
        - 'Paper Generation Agent': paper writing pipeline

    Returns the result produced by the selected mode, or ``None`` on error.
    """
    config = init_ai_researcher()

    result = None

    match mode:
        case "Detailed Idea Description":
            if global_state.INIT_FLAG is False:
                global_state.INIT_FLAG = True
                try:
                    current_file_path = os.path.realpath(__file__)
                    current_dir = os.path.dirname(current_file_path)
                    sub_dir = os.path.join(current_dir, "research_agent")
                    os.chdir(sub_dir)

                    from research_agent import run_infer_plan

                    args = _prepare_research_args(config)
                    result = run_infer_plan.main(args, input, reference)
                except Exception:
                    logger.exception("Error in Detailed Idea Description mode")
                finally:
                    global_state.INIT_FLAG = False

        case "Reference-Based Ideation":
            if global_state.INIT_FLAG is False:
                global_state.INIT_FLAG = True
                try:
                    current_file_path = os.path.realpath(__file__)
                    current_dir = os.path.dirname(current_file_path)
                    sub_dir = os.path.join(current_dir, "research_agent")
                    os.chdir(sub_dir)

                    from research_agent import run_infer_idea

                    args = _prepare_research_args(config)
                    result = run_infer_idea.main(args, reference)
                except Exception:
                    logger.exception("Error in Reference-Based Ideation mode")
                finally:
                    global_state.INIT_FLAG = False

        case "Paper Generation Agent":
            if global_state.INIT_FLAG is False:
                global_state.INIT_FLAG = True
                try:
                    from paper_agent import writing

                    result = asyncio.run(
                        writing.writing(
                            config["category"], config["instance_id"]
                        )
                    )
                except Exception:
                    logger.exception("Error in Paper Generation Agent mode")
                finally:
                    global_state.INIT_FLAG = False

    return result
