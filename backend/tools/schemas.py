"""Universal OpenAI-compatible Tool Schemas and Dispatcher for Ghost.
Converts Ghost's registered Python functions into standardized OpenAI tool schemas
and executes tool calls dynamically on kratos.
"""
import inspect
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional, Union, get_origin, get_args

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


def _resolve_json_type(py_type: Any) -> Dict[str, Any]:
    """Resolve a Python type or typing annotation to an OpenAPI/JSON schema property dict."""
    if py_type == inspect.Parameter.empty:
        return {"type": "string"}

    origin = get_origin(py_type)
    args = get_args(py_type)

    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _resolve_json_type(non_none[0])

    if py_type in _TYPE_MAP:
        t = _TYPE_MAP[py_type]
        if t == "array":
            return {"type": "array", "items": {"type": "string"}}
        return {"type": t}

    if origin in (list, List):
        item_type = "string"
        if args:
            item_schema = _resolve_json_type(args[0])
            item_type = item_schema.get("type", "string")
        return {"type": "array", "items": {"type": item_type}}

    if origin in (dict, Dict):
        return {"type": "object"}

    return {"type": "string"}


def _extract_doc_param_descriptions(doc: str) -> Dict[str, str]:
    """Extract parameter descriptions from function docstring Args section."""
    descriptions: Dict[str, str] = {}
    if not doc or "Args:" not in doc:
        return descriptions

    args_section = doc.split("Args:", 1)[1]
    for section_break in ("Returns:", "Raises:", "Yields:"):
        if section_break in args_section:
            args_section = args_section.split(section_break, 1)[0]

    current_param = None
    current_desc: List[str] = []
    for line in args_section.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if ":" in line_stripped:
            parts = line_stripped.split(":", 1)
            candidate = parts[0].strip()
            if candidate.isidentifier():
                if current_param:
                    descriptions[current_param] = " ".join(current_desc).strip()
                current_param = candidate
                current_desc = [parts[1].strip()]
                continue
        if current_param:
            current_desc.append(line_stripped)

    if current_param:
        descriptions[current_param] = " ".join(current_desc).strip()

    return descriptions


def function_to_openai_schema(func: Callable) -> Dict[str, Any]:
    """Convert a Python function with docstrings and type annotations into an OpenAI tool schema."""
    name = func.__name__
    doc = inspect.getdoc(func) or ""
    # Use first section of docstring for clear description
    description = doc.split("\n\n")[0].replace("\n", " ").strip() if doc else f"Execute {name}"
    param_docs = _extract_doc_param_descriptions(doc)

    sig = inspect.signature(func)
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        py_type = param.annotation if param.annotation != inspect.Parameter.empty else str
        prop_schema = _resolve_json_type(py_type)
        prop_schema["description"] = param_docs.get(param_name, f"Parameter: {param_name}")
        properties[param_name] = prop_schema

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
