import json
import os
import time
from research_agent.inno.core import MetaChain, MetaChainLogger
from typing import Union, Dict, List, Callable, Any
from research_agent.inno import Agent
from abc import ABC, abstractmethod
from research_agent.inno.evals.trace import AgentStepTrace, ToolCallTrace
from research_agent.inno.workflow.cache_identity import CacheIdentity, CachePolicy


def _summarize_text(value: Any, limit: int = 240) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."

def _runtime_cache_identity(
    *,
    stage: str,
    normalized_input: Any,
    context_variables: Dict | None = None,
    model_configuration: Dict | None = None,
    tool_configuration: Dict | None = None,
) -> CacheIdentity:
    context = context_variables or {}
    runtime_context = context.get("runtime_context") or {}
    recall_context = context.get("recall_context") or {}
    return CacheIdentity(
        task_id=str(
            context.get("task_id")
            or runtime_context.get("task_id")
            or runtime_context.get("task_level")
            or "unknown"
        ),
        stage=stage,
        normalized_input=normalized_input,
        model_configuration=dict(model_configuration or {}),
        tool_configuration=dict(tool_configuration or {}),
        recall_snapshot_id=str(
            context.get("recall_snapshot_id")
            or recall_context.get("snapshot_id")
            or "off"
        ),
        code_revision=str(context.get("code_revision") or ""),
        dataset_digest=str(context.get("dataset_digest") or ""),
        evaluation_contract_version=str(
            context.get("evaluation_contract_version") or ""
        ),
    )


class AgentModule:
    def __init__(
        self,
        agent: Agent,
        client: MetaChain,
        cache_path: str,
        trace_recorder: Callable[[AgentStepTrace], None] | None = None,
        cache_policy: CachePolicy = "reuse",
    ):
        self.agent = agent
        self.client = client
        self.cache_path = cache_path
        self.trace_recorder = trace_recorder
        self.cache_policy = cache_policy
    async def __call__(self, messages: List[Dict], context_variables: Dict, iter_times: int = None, *args, **kwargs):
        # messages = [{"role": "user", "content": query}]
        input_summary = _summarize_text(messages[-1].get("content", "")) if messages else ""
        max_turns = getattr(self.agent, "max_turns", None) or float("inf")
        transferred_to = None
        output_summary = ""
        cache_key = _runtime_cache_identity(
            stage=self.agent.name,
            normalized_input=messages,
            context_variables=context_variables,
            model_configuration={"model": getattr(self.agent, "model", "")},
        ).digest()
        agent_cache, escape_running = self.check_cache(
            self.agent.name,
            iter_times,
            cache_key=cache_key,
        )
        if agent_cache and escape_running:
            messages.extend(agent_cache["messages"])
            context_variables.update(agent_cache["context_variables"])
            output_summary = _summarize_text(agent_cache["messages"][-1].get("content", "")) if agent_cache["messages"] else ""
        elif agent_cache and not escape_running:
            messages.extend(agent_cache["messages"])
            context_variables.update(agent_cache["context_variables"])
            response = await self.client.run_async(
                self.agent,
                messages,
                context_variables=context_variables,
                debug=True,
                max_turns=max_turns,
            )
            ret_messages = response.messages
            ret_context_variables = response.context_variables
            transferred_to = getattr(response.agent, "name", None)
            output_summary = _summarize_text(ret_messages[-1].get("content", "")) if ret_messages else ""
            if ret_messages[-1]["role"] != "error":
                ret_messages.append({"role": "success", "content": "The agent successfully generated a response."})
            self.save_cache(
                self.agent.name,
                agent_cache["messages"] + ret_messages[:-1],
                iter_times,
                ret_context_variables,
                cache_key=cache_key,
            )
            messages.extend(ret_messages[:-1])
            context_variables.update(ret_context_variables)
            if ret_messages[-1]["role"] == "error":
                raise Exception(ret_messages[-1]["content"])
        else:
            response = await self.client.run_async(
                self.agent,
                messages,
                context_variables=context_variables,
                debug=True,
                max_turns=max_turns,
            )
            ret_messages = response.messages
            ret_context_variables = response.context_variables
            transferred_to = getattr(response.agent, "name", None)
            output_summary = _summarize_text(ret_messages[-1].get("content", "")) if ret_messages else ""
            if ret_messages[-1]["role"] != "error":
                ret_messages.append({"role": "success", "content": "The agent successfully generated a response."})
            self.save_cache(
                self.agent.name,
                ret_messages[:-1],
                iter_times,
                ret_context_variables,
                cache_key=cache_key,
            )
            messages.extend(ret_messages[:-1])
            context_variables.update(ret_context_variables)
            if ret_messages[-1]["role"] == "error":
                raise Exception(ret_messages[-1]["content"])
        if self.trace_recorder is not None:
            self.trace_recorder(
                AgentStepTrace(
                    agent_name=self.agent.name,
                    input_summary=input_summary,
                    output_summary=output_summary,
                    transferred_to=transferred_to if transferred_to and transferred_to != self.agent.name else None,
                )
            )
        return messages, context_variables
    def save_cache(
        self,
        agent_name,
        messages,
        iter_times: int = None,
        context_variables: Dict = None,
        *,
        cache_key: str,
    ):
        if self.cache_policy == "disabled":
            return
        agent_name = agent_name.replace(" ", "_").lower()
        if iter_times is not None:
            agent_name = agent_name + f"_iter_{iter_times}"
        agent_cache_file = f"{self.cache_path}/agents/{agent_name}-{cache_key}.json"
        os.makedirs(os.path.dirname(agent_cache_file), exist_ok=True)
        with open(agent_cache_file, "w", encoding="utf-8") as f:
            json.dump({"messages": messages, "context_variables": context_variables}, f, ensure_ascii=False, indent=4)
    def check_cache(self, agent_name, iter_times: int = None, *, cache_key: str):
        if self.cache_policy != "reuse":
            return None, False
        agent_name_norm = agent_name.replace(" ", "_").lower()
        if iter_times is not None:
            agent_name_norm = agent_name_norm + f"_iter_{iter_times}"
        cache_file = f"{self.cache_path}/agents/{agent_name_norm}-{cache_key}.json"
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f), True
        return None, False
    
class ToolModule:
    def __init__(
        self,
        tool: Callable[[Any], Union[str, Dict]],
        cache_path: str,
        trace_recorder: Callable[[ToolCallTrace], None] | None = None,
        trace_owner: str = "Flow",
        cache_policy: CachePolicy = "reuse",
        context_variables: Dict | None = None,
    ):
        self.tool = tool
        self.cache_path = cache_path
        self.trace_recorder = trace_recorder
        self.trace_owner = trace_owner
        self.cache_policy = cache_policy
        self.context_variables = context_variables or {}
    def __call__(self, tool_args: Dict, *args, **kwargs):
        start_time = time.perf_counter()
        cache_key = _runtime_cache_identity(
            stage=self.tool.__name__,
            normalized_input=tool_args,
            context_variables=self.context_variables,
            tool_configuration={"tool": self.tool.__name__},
        ).digest()
        tool_cache = self.check_cache(self.tool.__name__, cache_key=cache_key)
        if tool_cache:
            result = tool_cache
        else:
            result = self.tool(**tool_args)
            self.save_cache(self.tool, tool_args, result, cache_key=cache_key)
        if self.trace_recorder is not None:
            self.trace_recorder(
                ToolCallTrace(
                    agent_name=self.trace_owner,
                    tool_name=self.tool.__name__,
                    args=dict(tool_args),
                    success=True,
                    latency_ms=int((time.perf_counter() - start_time) * 1000),
                    output_summary=_summarize_text(result),
                )
            )
        return result
    def save_cache(
        self,
        tool: Callable,
        tool_args: Dict,
        tool_result: Union[str, Dict],
        *,
        cache_key: str,
    ):
        if self.cache_policy == "disabled":
            return
        tool_name = tool.__name__

        tool_cache_file = f"{self.cache_path}/tools/{tool_name}-{cache_key}.json"
        os.makedirs(os.path.dirname(tool_cache_file), exist_ok=True)
        tool_cache_dict = {
            "name": tool_name,
            "args": tool_args,
            "result": tool_result
        }
        with open(tool_cache_file, "w", encoding="utf-8") as f:
            json.dump(tool_cache_dict, f, ensure_ascii=False, indent=4)
    def check_cache(self, tool_name: str, *, cache_key: str):
        if self.cache_policy != "reuse":
            return None
        cache_file = f"{self.cache_path}/tools/{tool_name}-{cache_key}.json"
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                tool_cache_dict = json.load(f)
                return tool_cache_dict["result"]
        return None

class FlowModule(ABC):
    def __init__(self, cache_path: str, log_path: Union[str, None, MetaChainLogger] = None, model: str = "gpt-4o-2024-08-06"):
        self.cache_path = cache_path
        self.client = MetaChain(log_path=log_path)
        self.model = model
        self._agent_steps: List[AgentStepTrace] = []
        self._tool_calls: List[ToolCallTrace] = []

    def record_agent_step(self, step: AgentStepTrace) -> None:
        self._agent_steps.append(step)

    def record_tool_call(self, tool_call: ToolCallTrace) -> None:
        self._tool_calls.append(tool_call)

    def export_runtime_trace(self) -> Dict[str, List]:
        return {
            "agent_steps": list(self._agent_steps),
            "tool_calls": list(self._tool_calls),
        }
    @abstractmethod
    async def forward(self, *args, **kwargs):
        raise NotImplementedError("subclass should implement this method")
    
    async def __call__(self, *args, **kwargs):
        return await self.forward(*args, **kwargs)

    
