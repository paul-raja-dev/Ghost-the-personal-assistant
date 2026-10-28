"""Unit tests for Ghost System & Live Filesystem Operations."""
import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tools import system_tools


class TestSystemTools(unittest.TestCase):
    def setUp(self):
        self.test_file = Path("/tmp/ghost_test_sample.txt")
        self.renamed_file = Path("/tmp/ghost_test_renamed.txt")
        if self.test_file.exists():
            self.test_file.unlink()
        if self.renamed_file.exists():
            self.renamed_file.unlink()

    def tearDown(self):
        if self.test_file.exists():
            self.test_file.unlink()
        if self.renamed_file.exists():
            self.renamed_file.unlink()

    def test_execute_command(self):
        # 1. Standard command execution
        res = system_tools.execute_command("echo 'Ghost System Active'")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["stdout"], "Ghost System Active")

        # 2. Working directory expansion
        pwd_res = system_tools.execute_command("pwd", working_dir="~/Desktop")
        self.assertEqual(pwd_res["status"], "ok")
        self.assertTrue(pwd_res["stdout"].endswith("Desktop"))

        # 3. Guardrail against destructive command
        blocked_res = system_tools.execute_command("rm -rf /")
        self.assertEqual(blocked_res["status"], "error")
        self.assertIn("blocked", blocked_res["message"].lower())

    def test_file_operations(self):
        content = "Ghost Live System Controller\nVersion: 2.0\nStatus: Operational\n"
        
        # 1. Write file
        write_res = system_tools.write_file(str(self.test_file), content)
        self.assertEqual(write_res["status"], "ok")
        self.assertTrue(self.test_file.exists())

        # 2. Read file
        read_res = system_tools.read_file(str(self.test_file))
        self.assertEqual(read_res["status"], "ok")
        self.assertEqual(read_res["content"], content)

        # 3. List directory
        list_res = system_tools.list_directory("/tmp")
        self.assertEqual(list_res["status"], "ok")
        self.assertTrue(any(item["name"] == "ghost_test_sample.txt" for item in list_res["items"]))

        # 4. Move / rename
        move_res = system_tools.move_or_rename(str(self.test_file), str(self.renamed_file))
        self.assertEqual(move_res["status"], "ok")
        self.assertFalse(self.test_file.exists())
        self.assertTrue(self.renamed_file.exists())

        # 5. Delete file
        del_res = system_tools.delete_file_or_dir(str(self.renamed_file))
        self.assertEqual(del_res["status"], "ok")
        self.assertFalse(self.renamed_file.exists())

        # 6. Safety check: Root deletion blocked
        root_del = system_tools.delete_file_or_dir("/")
        self.assertEqual(root_del["status"], "error")
        self.assertIn("blocked", root_del["message"].lower())

    def test_get_system_status(self):
        status = system_tools.get_system_status()
        self.assertEqual(status["status"], "ok")
        sys_info = status.get("system", {})
        self.assertIn("disk_root", sys_info)
        self.assertIn("memory", sys_info)
        self.assertIn("uptime", sys_info)


if __name__ == "__main__":
    unittest.main()
