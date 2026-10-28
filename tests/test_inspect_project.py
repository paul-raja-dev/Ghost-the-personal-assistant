"""Unit tests for Ghost High-Speed Deep Codebase Inspection Engine."""
import time
import unittest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
import sys
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tools import system_tools


class TestInspectProject(unittest.TestCase):
    def test_inspect_lowercase_ghost(self):
        t0 = time.perf_counter()
        res = system_tools.inspect_project("~/Desktop/ghost")
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["name"], "ghost")

        # Must detect Tauri / Rust
        self.assertTrue(any("Tauri" in stack or "Rust" in stack for stack in res["tech_stack"]))

        # Must extract real manifest description from Cargo.toml
        manifests = res.get("manifests", {})
        self.assertIn("Cargo.toml", manifests)
        self.assertIn("Ghost — Custom Browser Shell", manifests["Cargo.toml"].get("description", ""))

        # Must discover docs/ folder and primary doc
        docs = res.get("documentation", {})
        self.assertIn("00-PROJECT-OVERVIEW.md", docs.get("docs_folder_files", []))

        # Must extract git commits
        git_info = res.get("git", {})
        self.assertTrue(len(git_info.get("recent_commits", [])) > 0)

        # Performance requirement: Sub-50ms execution
        self.assertLess(elapsed_ms, 100.0, f"inspect_project took {elapsed_ms:.2f}ms, expected < 100ms")

    def test_inspect_uppercase_ghost(self):
        t0 = time.perf_counter()
        res = system_tools.inspect_project("~/Desktop/Ghost")
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["name"], "Ghost")

        # Must detect Electron and Python
        self.assertTrue(any("Electron" in stack for stack in res["tech_stack"]))
        self.assertTrue(any("Python" in stack for stack in res["tech_stack"]))

        # Must extract package.json description
        manifests = res.get("manifests", {})
        self.assertIn("package.json", manifests)
        self.assertIn("assistant", manifests["package.json"].get("description", "").lower())

        self.assertLess(elapsed_ms, 100.0)


if __name__ == "__main__":
    unittest.main()
