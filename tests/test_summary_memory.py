"""Unit test for Ghost Rolling Conversation Summary Memory."""
import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core import session


class TestRollingSummaryMemory(unittest.TestCase):
    def setUp(self):
        # Clear active session before each test
        session.clear_session()

    def tearDown(self):
        # Clean up active session
        session.clear_session()

    def test_rolling_summary_triggers_and_preserves_context(self):
        # Simulate 13 turns (26 messages)
        # Turn 1 includes critical early information
        session.record_turn(
            "My secret project codename is Project Chimera.",
            "Understood, I will remember that Project Chimera is your secret project codename."
        )

        for i in range(2, 14):
            session.record_turn(
                f"Question {i}: Tell me a short fact about Linux subsystem {i}.",
                f"Answer {i}: Here is fact number {i} regarding Linux kernel and memory architecture."
            )

        # 1. Summary should now be generated
        summary = session.get_session_summary()
        self.assertTrue(len(summary) > 0, "Summary should be populated after exceeding trigger turns")

        # 2. Verbatim turns should be kept between VERBATIM_TURNS_KEEP and SUMMARY_TRIGGER_TURNS
        turns = session.load_session()
        self.assertTrue(len(turns) <= session.SUMMARY_TRIGGER_TURNS * 2)
        self.assertTrue(len(turns) >= session.VERBATIM_TURNS_KEEP * 2)

        # 3. get_genai_history() should contain the summary header + recent turns
        history = session.get_genai_history()
        self.assertTrue(len(history) > len(turns), "History should include summary block at the beginning")
        self.assertEqual(history[0].role, "user")
        self.assertIn("Context Summary", history[0].parts[0].text)
        self.assertEqual(history[1].role, "model")

        print("\n[OK] Rolling summary unit test verified successfully!")
        print(f"Generated Summary preview:\n{summary}\n")


if __name__ == "__main__":
    unittest.main()
