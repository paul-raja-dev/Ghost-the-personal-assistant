"""Unit tests for Ghost Rate Limit Guards, Output Truncation, and System Persona."""
import json
import unittest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tools.system_tools import execute_command
from core.llm import _system_prompt


class TestRateLimitGuard(unittest.TestCase):
    def test_execute_command_truncates_giant_output(self):
        # Generate 10,000 characters of stdout
        res = execute_command("python3 -c \"print('A' * 10000)\"")
        self.assertEqual(res["status"], "ok")
        stdout = res["stdout"]
        self.assertLessEqual(len(stdout), 4200)
        self.assertIn("[... Output truncated at 4000 characters to prevent API rate limits.", stdout)

    def test_execute_command_normal_output_not_truncated(self):
        res = execute_command("echo 'short output'")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["stdout"], "short output")
        self.assertNotIn("truncated", res["stdout"])

    def test_system_prompt_contains_kratos_and_discussion_rules(self):
        prompt = _system_prompt()
        # Verify machine identity kratos is enforced
        self.assertIn("kratos", prompt)
        # Verify discussion-first philosophy is enforced
        self.assertIn("INVESTIGATIVE DISCUSSION PARTNER", prompt)
        self.assertIn("investigate_github_discussion", prompt)
        self.assertIn("DO NOT rush to write code", prompt)
        self.assertIn("ZERO EMOJIS", prompt)


if __name__ == "__main__":
    unittest.main()
