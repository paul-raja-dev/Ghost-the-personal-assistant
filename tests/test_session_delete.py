"""Unit tests for Ghost chat session deletion."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core import session


class TestSessionDelete(unittest.TestCase):
    def setUp(self):
        # Clear active session before each test
        session.clear_session()

    def tearDown(self):
        # Clean up active session
        session.clear_session()

    def test_delete_session_removes_from_archive_and_active(self):
        # 1. Record a turn to create a session in archive
        session.record_turn("What is the distance to the moon?", "About 384,400 km.")
        
        # Get active session ID
        active_turns = session.load_session()
        self.assertTrue(len(active_turns) >= 2)

        sessions = session.list_sessions()
        self.assertTrue(len(sessions) > 0)
        target_id = sessions[0]["id"]
        initial_count = len(sessions)

        # 2. Delete the session
        success = session.delete_session(target_id)
        self.assertTrue(success)

        # 3. Verify it is removed from list_sessions
        remaining_sessions = session.list_sessions()
        self.assertEqual(len(remaining_sessions), initial_count - 1)
        self.assertFalse(any(s["id"] == target_id for s in remaining_sessions))

        # 4. Verify active session file is cleared if it matched
        if session.SESSION_FILE.exists():
            active_data = json.loads(session.SESSION_FILE.read_text(encoding="utf-8"))
            self.assertNotEqual(active_data.get("id"), target_id)

    def test_delete_session_cli(self):
        # Record a test session
        session.record_turn("Testing CLI session deletion", "CLI test confirmed.")
        sessions = session.list_sessions()
        self.assertTrue(len(sessions) > 0)
        target_id = sessions[0]["id"]

        # Run backend/main.py --delete-session <id>
        root_dir = Path(__file__).resolve().parent.parent
        main_py = root_dir / "backend" / "main.py"
        res = subprocess.run(
            [sys.executable, str(main_py), "--delete-session", target_id],
            capture_output=True,
            text=True,
            check=True
        )
        output = json.loads(res.stdout.strip())
        self.assertTrue(output.get("success"))

        # Verify target is no longer in list_sessions
        remaining_ids = [s["id"] for s in session.list_sessions()]
        self.assertNotIn(target_id, remaining_ids)


if __name__ == "__main__":
    unittest.main()
