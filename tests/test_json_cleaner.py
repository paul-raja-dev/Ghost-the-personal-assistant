"""Unit tests for Ghost JSON Response Cleaner and Double-Parse Defense."""
import json
import unittest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.llm import _clean_response


class TestJsonCleaner(unittest.TestCase):
    def test_standard_envelope(self):
        envelope = {
            "display": "line",
            "title": "Status",
            "body": "All systems operational.",
            "items": [],
            "actions": [],
            "auto_close": False,
        }
        raw = json.dumps(envelope)
        cleaned = _clean_response(raw)
        data = json.loads(cleaned)
        self.assertEqual(data["display"], "line")
        self.assertEqual(data["body"], "All systems operational.")

    def test_double_encoded_json(self):
        envelope = {
            "display": "line",
            "title": "PR Status",
            "body": "PR #39862 is open.",
            "items": [],
            "actions": [],
            "auto_close": False,
        }
        # Double JSON encode: json string inside json string
        double_encoded = json.dumps(json.dumps(envelope))
        cleaned = _clean_response(double_encoded)
        data = json.loads(cleaned)
        self.assertEqual(data["display"], "line")
        self.assertEqual(data["body"], "PR #39862 is open.")

    def test_escaped_string_envelope(self):
        # Raw string matching what was observed in user incident:
        # {\n \"display\": \"line\",\n \"title\": \"Zulip PR Status\" ... }
        escaped_str = '{\\n \\"display\\": \\"line\\",\\n \\"title\\": \\"Zulip PR Status\\",\\n \\"body\\": \\"Checked Zulip PR\\",\\n \\"items\\": [],\\n \\"actions\\": [],\\n \\"auto_close\\": false\\n}'
        cleaned = _clean_response(escaped_str)
        data = json.loads(cleaned)
        self.assertEqual(data["display"], "line")
        self.assertEqual(data["body"], "Checked Zulip PR")

    def test_markdown_wrapped_envelope(self):
        envelope = {
            "display": "compose",
            "title": "Draft",
            "body": "Hello maintainer",
            "items": [],
            "actions": [],
            "auto_close": False,
        }
        raw = f"```json\n{json.dumps(envelope)}\n```"
        cleaned = _clean_response(raw)
        data = json.loads(cleaned)
        self.assertEqual(data["display"], "compose")
        self.assertEqual(data["body"], "Hello maintainer")

    def test_plain_text_fallback(self):
        cleaned = _clean_response("I checked the PR and everything looks good.")
        data = json.loads(cleaned)
        self.assertEqual(data["display"], "line")
        self.assertEqual(data["body"], "I checked the PR and everything looks good.")


if __name__ == "__main__":
    unittest.main()
