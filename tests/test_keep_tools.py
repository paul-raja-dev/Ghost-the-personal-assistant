"""Unit tests for Ghost Google Keep tools and mobile sync lifecycle."""
import json
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tools import keep_tools
from core import llm


class TestKeepTools(unittest.TestCase):
    """Test suite covering Google Keep tools with mocked gkeepapi."""

    def setUp(self):
        self.orig_config_dir = keep_tools.CONFIG_DIR
        self.orig_state_file = keep_tools.KEEP_STATE_FILE
        self.orig_pending_file = keep_tools.PENDING_TICKETS_FILE

        self.test_dir = Path("/tmp/ghost_keep_test")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        keep_tools.CONFIG_DIR = self.test_dir
        keep_tools.KEEP_STATE_FILE = self.test_dir / "keep_state.json"
        keep_tools.PENDING_TICKETS_FILE = self.test_dir / "pending_keep_tickets.json"
        keep_tools._keep_client = None
        keep_tools._pending_deletions.clear()

    def tearDown(self):
        keep_tools.CONFIG_DIR = self.orig_config_dir
        keep_tools.KEEP_STATE_FILE = self.orig_state_file
        keep_tools.PENDING_TICKETS_FILE = self.orig_pending_file
        keep_tools._keep_client = None
        keep_tools._pending_deletions.clear()

        for p in self.test_dir.glob("*"):
            try:
                p.unlink()
            except Exception:
                pass
        try:
            self.test_dir.rmdir()
        except Exception:
            pass

    def test_get_keep_email(self):
        """Verify work account email is resolved by default."""
        email = keep_tools.get_keep_email()
        self.assertEqual(email, "paulraja.creator@gmail.com")

    def test_missing_token_setup_guidance(self):
        """Verify clean setup guidance when master token is not configured."""
        with patch.dict(os.environ, {}, clear=True):
            res = keep_tools.list_keep_notes()
            self.assertEqual(res["status"], "setup_required")
            self.assertIn("GOOGLE_KEEP_MASTER_TOKEN", res["message"])

    @patch("tools.keep_tools.get_keep_client")
    def test_list_keep_notes_mocked(self, mock_get_client):
        """Verify note search, color parsing, and checklist extraction."""
        import gkeepapi

        mock_keep = MagicMock()
        mock_get_client.return_value = (mock_keep, None)

        # Mock standard text note
        mock_note1 = MagicMock(spec=gkeepapi.node.TopLevelNode)
        mock_note1.id = "note_101"
        mock_note1.title = "Architecture Ideas"
        mock_note1.text = "1. Sync with Google Keep\n2. Mobile notifications"
        mock_note1.pinned = True
        mock_note1.trashed = False
        mock_note1.archived = False
        mock_note1.color = MagicMock()
        mock_note1.color.name = "Yellow"
        mock_note1.labels.all.return_value = []

        # Mock checklist note
        mock_note2 = MagicMock(spec=gkeepapi.node.List)
        mock_note2.id = "list_102"
        mock_note2.title = "Groceries"
        mock_note2.text = "Milk\nEggs"
        mock_note2.pinned = False
        mock_note2.trashed = False
        mock_note2.archived = False
        mock_note2.color = MagicMock()
        mock_note2.color.name = "Green"
        mock_note2.labels.all.return_value = []

        item1 = MagicMock()
        item1.text = "Milk"
        item1.checked = True
        item2 = MagicMock()
        item2.text = "Eggs"
        item2.checked = False
        mock_note2.items = [item1, item2]

        mock_keep.all.return_value = [mock_note1, mock_note2]

        # Query all
        res = keep_tools.list_keep_notes()
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["count"], 2)

        first = res["notes"][0]
        self.assertEqual(first["title"], "Architecture Ideas")
        self.assertEqual(first["color"], "yellow")
        self.assertTrue(first["pinned"])
        self.assertFalse(first["is_checklist"])

        second = res["notes"][1]
        self.assertEqual(second["title"], "Groceries")
        self.assertEqual(second["color"], "green")
        self.assertTrue(second["is_checklist"])
        self.assertEqual(len(second["checklist_items"]), 2)
        self.assertTrue(second["checklist_items"][0]["checked"])

        # Filter by search term
        res_search = keep_tools.list_keep_notes(query="groceries")
        self.assertEqual(res_search["count"], 1)
        self.assertEqual(res_search["notes"][0]["title"], "Groceries")

    @patch("tools.keep_tools.get_keep_client")
    def test_read_keep_note_mocked(self, mock_get_client):
        """Verify reading a specific note by ID."""
        import gkeepapi

        mock_keep = MagicMock()
        mock_get_client.return_value = (mock_keep, None)

        mock_note = MagicMock(spec=gkeepapi.node.Node)
        mock_note.id = "note_abc"
        mock_note.title = "Sprint Retrospective"
        mock_note.text = "Completed multi-account email and screen capture."
        mock_note.pinned = False
        mock_note.archived = False
        mock_note.color = None

        mock_keep.get.return_value = mock_note

        res = keep_tools.read_keep_note("note_abc")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["title"], "Sprint Retrospective")
        self.assertIn("multi-account email", res["text"])

    @patch("tools.keep_tools.get_keep_client")
    def test_create_keep_note_text(self, mock_get_client):
        """Verify creating a text note invokes keep.sync()."""
        mock_keep = MagicMock()
        mock_get_client.return_value = (mock_keep, None)

        mock_created = MagicMock()
        mock_created.id = "new_note_1"
        mock_created.text = "Note content here"
        mock_created.pinned = True
        mock_keep.createNote.return_value = mock_created

        res = keep_tools.create_keep_note(
            title="Meeting Notes",
            text="Note content here",
            pinned=True,
            color="blue",
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["note_id"], "new_note_1")
        mock_keep.createNote.assert_called_once_with("Meeting Notes", "Note content here")
        mock_keep.sync.assert_called_once()

    @patch("tools.keep_tools.get_keep_client")
    def test_create_keep_note_checklist(self, mock_get_client):
        """Verify creating a checklist note with items."""
        mock_keep = MagicMock()
        mock_get_client.return_value = (mock_keep, None)

        mock_list = MagicMock()
        mock_list.id = "new_list_2"
        mock_list.text = "Task 1\nTask 2"
        mock_list.pinned = False
        mock_keep.createList.return_value = mock_list

        res = keep_tools.create_keep_note(
            title="Sprint Checklist",
            checklist_items=["Task 1", "Task 2"],
        )
        self.assertEqual(res["status"], "ok")
        self.assertTrue(res["is_checklist"])
        mock_keep.createList.assert_called_once_with("Sprint Checklist", [("Task 1", False), ("Task 2", False)])
        mock_keep.sync.assert_called_once()

    @patch("tools.keep_tools.get_keep_client")
    def test_stage_and_execute_delete_keep_note(self, mock_get_client):
        """Verify 2-step safety confirmation ticket for note deletion."""
        mock_keep = MagicMock()
        mock_get_client.return_value = (mock_keep, None)

        mock_note = MagicMock()
        mock_note.id = "del_note_id"
        mock_note.title = "Old Draft"
        mock_keep.get.return_value = mock_note

        # 1. Stage deletion
        stage_res = keep_tools.stage_keep_note_deletion("del_note_id")
        self.assertEqual(stage_res["status"], "staged")
        self.assertIn("ticket_id", stage_res)
        ticket_id = stage_res["ticket_id"]

        # 2. Execute deletion
        del_res = keep_tools.execute_confirmed_keep_deletion(ticket_id)
        self.assertEqual(del_res["status"], "ok")
        self.assertIn("Old Draft", del_res["message"])
        mock_note.trash.assert_called_once()
        mock_keep.sync.assert_called_once()

    @patch("tools.keep_tools.get_keep_client")
    def test_llm_keep_delete_interceptor(self, mock_get_client):
        """Verify Ghost engine intercepts 'confirm: delete_keep_note <ticket_id>' cleanly."""
        mock_keep = MagicMock()
        mock_get_client.return_value = (mock_keep, None)

        mock_note = MagicMock()
        mock_note.id = "intercept_note"
        mock_note.title = "Obsolete Idea"
        mock_keep.get.return_value = mock_note

        stage_res = keep_tools.stage_keep_note_deletion("intercept_note")
        ticket_id = stage_res["ticket_id"]

        resp_json = llm.run(f"confirm: delete_keep_note {ticket_id}")
        data = json.loads(resp_json)
        self.assertEqual(data["display"], "line")
        self.assertEqual(data["title"], "Note Deleted")
        self.assertIn("[ok]", data["body"])
        self.assertIn("Obsolete Idea", data["body"])


if __name__ == "__main__":
    unittest.main()
