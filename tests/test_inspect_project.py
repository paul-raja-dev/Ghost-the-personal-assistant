"""Unit tests for Ghost High-Speed Deep Codebase Inspection Engine."""
import shutil
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
    def setUp(self):
        self.mock_dir = Path("/tmp/mock_tauri_project")
        if self.mock_dir.exists():
            shutil.rmtree(self.mock_dir)
        self.mock_dir.mkdir(parents=True, exist_ok=True)

        # Setup mock Tauri structure
        tauri_dir = self.mock_dir / "src-tauri"
        tauri_dir.mkdir(parents=True, exist_ok=True)
        (tauri_dir / "Cargo.toml").write_text(
            '[package]\nname = "mock-ghost"\nversion = "0.1.0"\ndescription = "Ghost — Custom Browser Shell"\n',
            encoding="utf-8"
        )

        docs_dir = self.mock_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "00-PROJECT-OVERVIEW.md").write_text(
            "# Ghost — Project Overview\nA custom browser shell built with Tauri v2 (Rust backend).\n",
            encoding="utf-8"
        )

    def tearDown(self):
        if self.mock_dir.exists():
            shutil.rmtree(self.mock_dir)

    def test_inspect_mock_tauri_project(self):
        t0 = time.perf_counter()
        res = system_tools.inspect_project(str(self.mock_dir))
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["name"], "mock_tauri_project")

        # Must detect Tauri / Rust
        self.assertTrue(any("Tauri" in stack or "Rust" in stack for stack in res["tech_stack"]))

        # Must extract real manifest description from Cargo.toml
        manifests = res.get("manifests", {})
        self.assertIn("Cargo.toml", manifests)
        self.assertIn("Ghost — Custom Browser Shell", manifests["Cargo.toml"].get("description", ""))

        # Must discover docs/ folder and primary doc
        docs = res.get("documentation", {})
        self.assertIn("00-PROJECT-OVERVIEW.md", docs.get("docs_folder_files", []))

        # Performance requirement: Sub-50ms execution
        self.assertLess(elapsed_ms, 100.0, f"inspect_project took {elapsed_ms:.2f}ms, expected < 100ms")

    def test_inspect_current_ghost_repo(self):
        current_repo = Path(__file__).resolve().parent.parent
        t0 = time.perf_counter()
        res = system_tools.inspect_project(str(current_repo))
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
