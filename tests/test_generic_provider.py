"""Unit tests for Generic Multi-Provider Architecture and Tool Schemas."""
import json
import os
import sys
import unittest
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import config
from tools import schemas
from core import llm


class TestGenericProvider(unittest.TestCase):
    def test_provider_presets(self):
        self.assertIn("gemini", config.PROVIDER_PRESETS)
        self.assertIn("ollama", config.PROVIDER_PRESETS)
        self.assertIn("deepseek", config.PROVIDER_PRESETS)
        self.assertIn("groq", config.PROVIDER_PRESETS)
        self.assertIn("openai", config.PROVIDER_PRESETS)

        # Gemini preset uses OpenAI-compatible endpoint
        gemini_preset = config.PROVIDER_PRESETS["gemini"]
        self.assertTrue(gemini_preset["base_url"].endswith("/openai/"))

    def test_openai_tool_schemas_structure(self):
        tools = schemas.get_openai_tools()
        self.assertIsInstance(tools, list)
        self.assertGreaterEqual(len(tools), 10)

        names = [t["function"]["name"] for t in tools]
        self.assertIn("execute_command", names)
        self.assertIn("read_file", names)
        self.assertIn("capture_and_inspect_screen", names)
        self.assertIn("inspect_project", names)
        self.assertIn("get_system_status", names)

        for t in tools:
            self.assertEqual(t.get("type"), "function")
            func = t.get("function", {})
            self.assertIn("name", func)
            self.assertIn("description", func)
            params = func.get("parameters", {})
            self.assertEqual(params.get("type"), "object")
            self.assertIn("properties", params)

    def test_dispatch_tool_call_known(self):
        res = schemas.dispatch_tool_call("execute_command", {"command": "echo 'ghost generic test'"})
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("stdout"), "ghost generic test")

    def test_dispatch_tool_call_stringified_json_args(self):
        res = schemas.dispatch_tool_call("execute_command", '{"command": "echo stringified"}')
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("stdout"), "stringified")

    def test_dispatch_tool_call_unknown(self):
        res = schemas.dispatch_tool_call("nonexistent_ghost_tool", {})
        self.assertEqual(res.get("status"), "error")
        self.assertIn("Unknown tool", res.get("message"))

    def test_llm_run_generic_simple_prompt(self):
        raw = llm.run("Say hello briefly.")
        self.assertIsInstance(raw, str)
        data = json.loads(raw)
        self.assertIn("display", data)
        self.assertIn("body", data)
        self.assertTrue(len(data["body"]) > 0)

    def test_llm_run_generic_tool_calling(self):
        raw = llm.run("What is my current system status and free RAM on kratos?")
        data = json.loads(raw)
        self.assertEqual(data.get("display"), "line")
        body = data.get("body", "").lower()
        # Verify it executed get_system_status
        self.assertTrue("ram" in body or "memory" in body or "status" in body)


if __name__ == "__main__":
    unittest.main()
