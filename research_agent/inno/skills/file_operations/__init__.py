"""file_operations skill: File and directory operations in Docker env."""

from inspect import signature
from typing import Callable, List

from research_agent.inno.tools.terminal_tools import (
    create_directory,
    create_file,
    gen_code_tree_structure,
    list_files,
    read_file,
    write_file,
)


def get_tools(**kwargs) -> List[Callable]:
    tools = [
        read_file,
        create_file,
        write_file,
        list_files,
        create_directory,
        gen_code_tree_structure,
    ]

    code_env = kwargs.get("code_env")
    if code_env is not None:
        from functools import wraps

        def _with_env(env, tool):
            @wraps(tool)
            def wrapper(*args, **kw):
                kw["env"] = env
                return tool(*args, **kw)
            return wrapper

        tools = [
            _with_env(code_env, t)
            if "env" in signature(t).parameters
            else t
            for t in tools
        ]

    return tools
