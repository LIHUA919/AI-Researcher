import inspect
from datetime import datetime
import json
from typing import List, Dict, Optional, Union, get_args, get_origin
from dataclasses import is_dataclass, fields, MISSING
from pydantic import BaseModel
from rich.console import Console


def print_in_box(text: str, console: Optional[Console] = None, title: str = "", color: str = "white") -> None:
    """
    Print the text in a box.
    :param text: the text to print.
    :param console: the console to print the text.
    :param title: the title of the box.
    :param color: the border color.
    :return:
    """
    console = console or Console()

    # panel = Panel(text, title=title, border_style=color, expand=True, highlight=True)
    # console.print(panel)
    console.print('_'*20 + title + '_'*20, style=f"bold {color}")
    console.print(text, highlight=True, emoji=True)
    


def debug_print(debug: bool, *args: str, **kwargs: dict) -> None:
    if not debug:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = "\n".join(map(str, args))
    color = kwargs.get("color", "white")
    title = kwargs.get("title", "")
    log_str = f"[{timestamp}]\n{message}"
    print_in_box(log_str, color=color, title=title)
    log_path = kwargs.get("log_path", None)
    if log_path:
        with open(log_path, 'a') as f:
            f.write(log_str + '\n')

def get_type_info(annotation, base_type_map):
    # 处理基本类型
    if annotation in base_type_map:
        return {"type": base_type_map[annotation]}
    
    # 处理typing类型
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        
        # 处理List类型
        if origin is list or origin is List:
            item_type = args[0]
            return {
                "type": "array",
                "items": get_type_info(item_type, base_type_map)
            }
        
        # 处理Dict类型
        elif origin is dict or origin is Dict:
            key_type, value_type = args
            if key_type is not str:
                raise ValueError("Dictionary keys must be strings")
            
            # 如果value_type是TypedDict或Pydantic模型
            if (hasattr(value_type, "__annotations__") or 
                (isinstance(value_type, type) and issubclass(value_type, BaseModel))):
                return get_type_info(value_type, base_type_map)
            
            # 普通Dict类型
            return {
                "type": "object",
                "additionalProperties": get_type_info(value_type, base_type_map)
            }
        
        # 处理Union类型
        elif origin is Union:
            types = [get_type_info(arg, base_type_map) for arg in args if arg is not type(None)]
            if len(types) == 1:
                return types[0]
            return {"oneOf": types}
    
    # 处理Pydantic模型
    if isinstance(annotation, type):  # 先检查是否是类型
        try:
            if issubclass(annotation, BaseModel):
                schema = annotation.model_json_schema()
                # 提取主要schema部分
                properties = schema.get("properties", {})
                required = schema.get("required", [])
                
                return {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False
                }
        except TypeError:
            pass
    
    # 处理dataclass
    if is_dataclass(annotation):
        properties = {}
        required = []
        for field in fields(annotation):
            properties[field.name] = get_type_info(field.type, base_type_map)
            if field.default == field.default_factory == MISSING:
                required.append(field.name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False
        }

    # 处理TypedDict
    if hasattr(annotation, "__annotations__"):
        properties = {}
        required = getattr(annotation, "__required_keys__", annotation.__annotations__.keys())
        
        for key, field_type in annotation.__annotations__.items():
            properties[key] = get_type_info(field_type, base_type_map)
        
        return {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False
        }

    # 默认返回string类型
    return {"type": "string"}


def function_to_json(func) -> dict:
    """
    Converts a Python function into a JSON-serializable dictionary
    that describes the function's signature, including its name,
    description, and parameters.

    Args:
        func: The function to be converted.

    Returns:
        A dictionary representing the function's signature in JSON format.
    """
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        # list: "array",
        # dict: "object",
        type(None): "null",
    }
    # def get_type_info(annotation):
    #     if hasattr(annotation, "__origin__"):  # 处理typing类型
    #         origin = annotation.__origin__
    #         if origin is list:  # 处理List类型
    #             item_type = annotation.__args__[0]
    #             return {
    #                 "type": "array",
    #                 "items": {
    #                     "type": type_map.get(item_type, "string")
    #                 }
    #             }
    #         elif origin is dict:  # 处理Dict类型
    #             return {"type": "object"}
    #     return {"type": type_map.get(annotation, "string")}

    try:
        signature = inspect.signature(func)
    except ValueError as e:
        raise ValueError(
            f"Failed to get signature for function {func.__name__}: {str(e)}"
        )

    parameters = {}
    # for param in signature.parameters.values():
    #     try:
    #         param_type = type_map.get(param.annotation, "string")
    #     except KeyError as e:
    #         raise KeyError(
    #             f"Unknown type annotation {param.annotation} for parameter {param.name}: {str(e)}"
    #         )
    #     parameters[param.name] = {"type": param_type}
    for param in signature.parameters.values():
        try:
            parameters[param.name] = get_type_info(param.annotation, type_map)
        except KeyError as e:
            raise KeyError(f"Unknown type annotation {param.annotation} for parameter {param.name}: {str(e)}")

    required = [
        param.name
        for param in signature.parameters.values()
        if param.default == inspect._empty
    ]

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": func.__doc__ or "",
            "parameters": {
                "type": "object",
                "properties": parameters,
                "required": required,
            },
        },
    }

def pretty_print_messages(message, **kwargs) -> None:
    # for message in messages:
    if message["role"] != "assistant" and message["role"] != "tool":
        return
    console = Console()
    if message["role"] == "tool":
        console.print("[bold blue]tool execution:[/bold blue]", end=" ")
        console.print(f"[bold purple]{message['name']}[/bold purple], result: {message['content']}")
        log_path = kwargs.get("log_path", None)
        if log_path:
            with open(log_path, 'a') as file:
                file.write(f"tool execution: {message['name']}, result: {message['content']}\n")
        return
                
    # print agent name in blue
    console.print(f"[bold blue]{message['sender']}[/bold blue]:", end=" ")

    # print response, if any
    if message["content"]:
        console.print(message["content"], highlight=True, emoji=True)

    # print tool calls in purple, if any
    tool_calls = message.get("tool_calls") or []
    if len(tool_calls) > 1:
        console.print()
    for tool_call in tool_calls:
        f = tool_call["function"]
        name, args = f["name"], f["arguments"]
        arg_str = json.dumps(json.loads(args)).replace(":", "=")
        console.print(f"[bold purple]{name}[/bold purple]({arg_str[1:-1]})")
    log_path = kwargs.get("log_path", None)
    if log_path:
        with open(log_path, 'a') as file:
            file.write(f"{message['sender']}: {message['content']}\n")
            for tool_call in tool_calls:
                f = tool_call["function"]
                name, args = f["name"], f["arguments"]
                arg_str = json.dumps(json.loads(args)).replace(":", "=")
                file.write(f"{name}({arg_str[1:-1]})\n")
