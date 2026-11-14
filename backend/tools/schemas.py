"""Universal OpenAI-compatible Tool Schemas and Dispatcher for Ghost.
Converts Ghost's registered Python functions into standardized OpenAI tool schemas
and executes tool calls dynamically on kratos.
"""
import inspect
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional

backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import tools

_TYPE_MAP = {
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    str: "string",
}


def function_to_openai_schema(func: Callable) -> Dict[str, Any]:
    """Convert a Python function with docstrings and type annotations into an OpenAI tool schema."""
    name = func.__name__
    doc = inspect.getdoc(func) or ""
    # Use first section of docstring for clear description
    description = doc.split("\n\n")[0].replace("\n", " ").strip() if doc else f"Execute {name}"

    sig = inspect.signature(func)
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        py_type = param.annotation if param.annotation != inspect.Parameter.empty else str
        json_type = _TYPE_MAP.get(py_type, "string")

        properties[param_name] = {
            "type": json_type,
            "description": f"Parameter: {param_name}",
        }
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def get_openai_tools() -> List[Dict[str, Any]]:
    """Return all registered Ghost tools formatted as standard OpenAI function definitions."""
    return [function_to_openai_schema(t) for t in tools.TOOLS]


def dispatch_tool_call(name: str, arguments: Any) -> Dict[str, Any]:
    """Dynamically execute a tool call by name with parsed arguments."""
    tool_map = {t.__name__: t for t in tools.TOOLS}
    func = tool_map.get(name)

    if not func:
        return {"status": "error", "message": f"Unknown tool: '{name}'"}

    # Ensure arguments is a dict
    kwargs = arguments
    if isinstance(arguments, str):
        try:
            kwargs = json.loads(arguments)
        except Exception:
            kwargs = {}
    if not isinstance(kwargs, dict):
        kwargs = {}

    try:
        res = func(**kwargs)
        if isinstance(res, dict):
            return res
        return {"status": "ok", "result": res}
    except Exception as exc:
        return {"status": "error", "message": f"Error executing tool '{name}': {exc}"}
