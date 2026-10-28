"""Unit tests for Ghost Safety Guardrails and Staged Trash System."""
import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tools import system_tools


class TestSafetyGuardrails(unittest.TestCase):
    def setUp(self):
        self.test_file = Path("/tmp/ghost_guardrail_test.txt")
        self.test_file.write_text("Guardrail test data\n", encoding="utf-8")

    def tearDown(self):
        if self.test_file.exists():
            self.test_file.unlink()

    def test_shell_command_deletion_guardrails(self):
        # 1. Direct rm should be blocked
        res1 = system_tools.execute_command("rm /tmp/ghost_guardrail_test.txt")
        self.assertEqual(res1["status"], "error")
        self.assertIn("blocked", res1["message"].lower())
        self.assertTrue(self.test_file.exists())

        # 2. rm -rf should be blocked
        res2 = system_tools.execute_command("rm -rf /tmp/ghost_guardrail_test.txt")
        self.assertEqual(res2["status"], "error")
        self.assertIn("blocked", res2["message"].lower())
        self.assertTrue(self.test_file.exists())

        # 3. rmdir should be blocked
        res3 = system_tools.execute_command("rmdir /tmp")
        self.assertEqual(res3["status"], "error")
        self.assertIn("blocked", res3["message"].lower())

        # 4. Chained commands with rm should be blocked
        res4 = system_tools.execute_command("echo hello ; rm -f /tmp/ghost_guardrail_test.txt")
        self.assertEqual(res4["status"], "error")
        self.assertIn("blocked", res4["message"].lower())
        self.assertTrue(self.test_file.exists())

        # 5. Safe non-destructive commands should succeed
        res5 = system_tools.execute_command("echo 'Safety Verified'")
        self.assertEqual(res5["status"], "ok")
        self.assertEqual(res5["stdout"], "Safety Verified")

    def test_staged_trash_requires_explicit_confirmation(self):
        # 1. Stage deletion - file MUST NOT be deleted yet
        stage_res = system_tools.stage_file_deletion(str(self.test_file), reason="Test cleanup")
        self.assertEqual(stage_res["status"], "confirmation_required")
        ticket_id = stage_res["ticket_id"]
        self.assertTrue(ticket_id.startswith("trash_"))
        self.assertTrue(self.test_file.exists(), "File must still exist after staging")

        # 2. Forged ticket ID must fail safely
        bad_res = system_tools.execute_confirmed_trash("trash_fake_id_12345")
        self.assertEqual(bad_res["status"], "error")
        self.assertTrue(self.test_file.exists())

        # 3. Execute with valid ticket - file moves to Trash
        exec_res = system_tools.execute_confirmed_trash(ticket_id)
        self.assertEqual(exec_res["status"], "ok")
        self.assertIn("trash", exec_res["message"].lower())
        self.assertFalse(self.test_file.exists(), "File should now be moved to Trash")

        # 4. Re-executing same ticket must fail (cannot replay)
        replay_res = system_tools.execute_confirmed_trash(ticket_id)
        self.assertEqual(replay_res["status"], "error")


if __name__ == "__main__":
    unittest.main()
