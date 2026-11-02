"""Unit tests for Ghost Vision and Screen Awareness Tools."""
import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tools import vision_tools
from core.llm import _system_prompt

# 1x1 base64 encoded PNG for testing
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


class TestVisionTools(unittest.TestCase):
    def test_inspect_image_missing_file(self):
        res = vision_tools.inspect_image_file("/tmp/nonexistent_image_12345.png")
        self.assertEqual(res.get("status"), "error")
        self.assertIn("not found", res.get("message", "").lower())

    def test_inspect_image_unsupported_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not an image")
            temp_path = f.name
        try:
            res = vision_tools.inspect_image_file(temp_path)
            self.assertEqual(res.get("status"), "error")
            self.assertIn("unsupported image extension", res.get("message", "").lower())
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_inspect_image_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_path = f.name
        try:
            res = vision_tools.inspect_image_file(temp_path)
            self.assertEqual(res.get("status"), "error")
            self.assertIn("empty", res.get("message", "").lower())
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_inspect_image_success(self):
        png_bytes = base64.b64decode(TINY_PNG_B64)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes)
            temp_path = f.name
        try:
            res = vision_tools.inspect_image_file(temp_path, "Describe this test image.")
            self.assertEqual(res.get("status"), "ok")
            self.assertTrue(len(res.get("analysis", "")) > 0)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch("subprocess.run")
    def test_capture_screen_gnome_screenshot_failure(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "Failed to capture"
        mock_run.return_value = mock_proc

        res = vision_tools.capture_and_inspect_screen()
        self.assertEqual(res.get("status"), "error")
        self.assertIn("failed", res.get("message", "").lower())

    def test_system_prompt_enforces_vision_rule(self):
        prompt = _system_prompt()
        self.assertIn("VISION & SCREEN AWARENESS", prompt)
        self.assertIn("capture_and_inspect_screen", prompt)
        self.assertIn("inspect_image_file", prompt)
        self.assertIn("kratos", prompt)


if __name__ == "__main__":
    unittest.main()
