"""Unit tests for Ghost Multi-Account Email Tools and confirmation workflows."""
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

from tools import email_tools
from core import llm


class TestEmailTools(unittest.TestCase):
    """Test suite covering multi-account email integration."""

    def setUp(self):
        # Setup temporary config paths
        self.orig_config_dir = email_tools.CONFIG_DIR
        self.orig_accounts_file = email_tools.ACCOUNTS_FILE
        self.orig_tickets_file = email_tools.PENDING_TICKETS_FILE

        self.test_dir = Path("/tmp/ghost_email_test")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        email_tools.CONFIG_DIR = self.test_dir
        email_tools.ACCOUNTS_FILE = self.test_dir / "email_accounts.json"
        email_tools.PENDING_TICKETS_FILE = self.test_dir / "pending_email_tickets.json"
        email_tools._pending_emails.clear()

    def tearDown(self):
        email_tools.CONFIG_DIR = self.orig_config_dir
        email_tools.ACCOUNTS_FILE = self.orig_accounts_file
        email_tools.PENDING_TICKETS_FILE = self.orig_tickets_file
        email_tools._pending_emails.clear()

        # Clean test files
        for p in self.test_dir.glob("*"):
            try:
                p.unlink()
            except Exception:
                pass
        try:
            self.test_dir.rmdir()
        except Exception:
            pass

    def test_default_accounts_and_aliases(self):
        """Verify default account creation and smart alias resolution."""
        cfg = email_tools.load_email_accounts()
        self.assertIn("accounts", cfg)
        self.assertIn("personal", cfg["accounts"])
        self.assertIn("work", cfg["accounts"])
        self.assertEqual(cfg["accounts"]["personal"]["email"], "user_personal@example.com")

        # Test alias resolution
        self.assertEqual(email_tools._resolve_account_key("personal", cfg), "personal")
        self.assertEqual(email_tools._resolve_account_key("me", cfg), "personal")
        self.assertEqual(email_tools._resolve_account_key("work", cfg), "work")
        self.assertEqual(email_tools._resolve_account_key("job", cfg), "work")
        self.assertEqual(email_tools._resolve_account_key("career", cfg), "work")
        self.assertEqual(email_tools._resolve_account_key("Professional", cfg), "work")
        # Test empty account defaults to configured default
        self.assertEqual(email_tools._resolve_account_key("", cfg), "work")

    def test_stage_email_send(self):
        """Verify staging creates safety ticket with send/copy/discard actions."""
        res = email_tools.stage_email_send(
            account="personal",
            to="friend@example.com",
            subject="Hey there",
            body="Meeting tomorrow at 5pm?",
        )
        self.assertEqual(res["status"], "staged")
        self.assertIn("ticket_id", res)
        ticket_id = res["ticket_id"]
        self.assertTrue(ticket_id.startswith("email_"))
        self.assertEqual(res["to"], "friend@example.com")
        self.assertEqual(res["subject"], "Hey there")
        self.assertEqual(len(res["actions"]), 3)
        self.assertEqual(res["actions"][0]["id"], "send")
        self.assertIn(f"confirm: send_email {ticket_id}", res["actions"][0]["payload"])

        # Check internal storage
        self.assertIn(ticket_id, email_tools._pending_emails)

    @patch("smtplib.SMTP_SSL")
    def test_execute_confirmed_send_mocked(self, mock_smtp_cls):
        """Verify confirmed send sends email and purges ticket."""
        # Set mock env var password
        with patch.dict(os.environ, {"GMAIL_PERSONAL_APP_PASSWORD": "test-password-123"}):
            stage_res = email_tools.stage_email_send(
                account="personal",
                to="colleague@example.com",
                subject="Sprint Sync",
                body="Here are the updates.",
            )
            ticket_id = stage_res["ticket_id"]

            # Mock SMTP instance
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

            send_res = email_tools.execute_confirmed_send(ticket_id)
            self.assertEqual(send_res["status"], "ok")
            self.assertIn("colleague@example.com", send_res["message"])

            # Verify SMTP login and send_message was called
            mock_smtp.login.assert_called_once_with("user_personal@example.com", "test-password-123")
            self.assertEqual(mock_smtp.send_message.call_count, 1)

            # Ticket must be deleted
            self.assertNotIn(ticket_id, email_tools._pending_emails)

    @patch("smtplib.SMTP_SSL")
    def test_execute_confirmed_send_with_overrides(self, mock_smtp_cls):
        """Verify user edits in UI card properly override the staged draft."""
        with patch.dict(os.environ, {"GMAIL_PERSONAL_APP_PASSWORD": "test-password-123"}):
            stage_res = email_tools.stage_email_send(
                account="personal",
                to="initial@example.com",
                subject="Old Subject",
                body="Old Body",
            )
            ticket_id = stage_res["ticket_id"]

            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

            # User edited fields before clicking Send
            send_res = email_tools.execute_confirmed_send(
                ticket_id=ticket_id,
                to="edited@example.com",
                subject="New Subject",
                body="New Body Text",
            )
            self.assertEqual(send_res["status"], "ok")
            self.assertIn("edited@example.com", send_res["message"])

            # Check message sent has new subject and to
            sent_msg = mock_smtp.send_message.call_args[0][0]
            self.assertEqual(sent_msg["To"], "edited@example.com")
            self.assertEqual(sent_msg["Subject"], "New Subject")
            self.assertIn("New Body Text", sent_msg.get_content())

    @patch("smtplib.SMTP_SSL")
    def test_execute_confirmed_send_direct_card_payload(self, mock_smtp_cls):
        """Verify user clicking Send Email from directly rendered composer card works without pre-staged ticket."""
        with patch.dict(os.environ, {"GMAIL_PERSONAL_APP_PASSWORD": "test-password-123"}):
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

            send_res = email_tools.execute_confirmed_send(
                ticket_id="",
                to="direct@example.com",
                subject="Direct Send",
                body="Sent from card directly",
                account="personal",
            )
            self.assertEqual(send_res["status"], "ok")
            self.assertIn("direct@example.com", send_res["message"])

            sent_msg = mock_smtp.send_message.call_args[0][0]
            self.assertEqual(sent_msg["To"], "direct@example.com")
            self.assertEqual(sent_msg["Subject"], "Direct Send")

    @patch("imaplib.IMAP4_SSL")
    def test_list_inbox_mocked(self, mock_imap_cls):
        """Verify list_inbox decodes MIME headers and snippets correctly."""
        with patch.dict(os.environ, {"GMAIL_PERSONAL_APP_PASSWORD": "test-password-123"}):
            mock_mail = MagicMock()
            mock_imap_cls.return_value = mock_mail

            # Mock search response
            mock_mail.search.return_value = ("OK", [b"1 2"])

            # Mock fetch response with sample raw email
            raw_email = (
                b"From: Alice <alice@example.com>\r\n"
                b"To: user_personal@example.com\r\n"
                b"Subject: Meeting Notes & Action Items\r\n"
                b"Date: Thu, 14 Nov 2026 18:30:00 +0000\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
                b"Hi Paul,\nHere are the notes from our discussion today.\nBest regards,\nAlice"
            )
            mock_mail.fetch.return_value = ("OK", [(b"2 (RFC822 {150}", raw_email)])

            res = email_tools.list_inbox(account="personal", limit=1, unread_only=True)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["count"], 1)
            first = res["emails"][0]
            self.assertEqual(first["subject"], "Meeting Notes & Action Items")
            self.assertIn("Alice", first["from"])
            self.assertIn("Here are the notes", first["snippet"])
            self.assertEqual(first["account"], "personal")

    @patch("imaplib.IMAP4_SSL")
    def test_read_email_details_mocked(self, mock_imap_cls):
        """Verify read_email_details extracts full body and clean text."""
        with patch.dict(os.environ, {"GMAIL_PERSONAL_APP_PASSWORD": "test-password-123"}):
            mock_mail = MagicMock()
            mock_imap_cls.return_value = mock_mail

            raw_email = (
                b"From: Recruiter <recruiter@tech.com>\r\n"
                b"To: user_personal@example.com\r\n"
                b"Subject: Interview Schedule\r\n"
                b"Date: Thu, 14 Nov 2026 19:00:00 +0000\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n\r\n"
                b"<html><body><p>Hello Paul,</p><p>We would love to invite you for an interview!</p></body></html>"
            )
            mock_mail.fetch.return_value = ("OK", [(b"10 (RFC822 {180}", raw_email)])

            res = email_tools.read_email_details(account="personal", email_id="10")
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["subject"], "Interview Schedule")
            self.assertIn("invite you for an interview", res["body"])

    @patch("smtplib.SMTP_SSL")
    def test_llm_send_email_interceptor(self, mock_smtp_cls):
        """Verify Ghost engine intercepts 'confirm: send_email <ticket_id>' and executes dispatch."""
        with patch.dict(os.environ, {"GMAIL_PERSONAL_APP_PASSWORD": "test-password-123"}):
            stage_res = email_tools.stage_email_send(
                account="personal",
                to="recipient@example.com",
                subject="Test Intercept",
                body="Testing the LLM interceptor.",
            )
            ticket_id = stage_res["ticket_id"]

            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

            # Invoke LLM run directly with the confirmation string
            response_json = llm.run(f"confirm: send_email {ticket_id}")
            data = json.loads(response_json)

            self.assertEqual(data["display"], "line")
            self.assertEqual(data["title"], "Email Sent")
            self.assertIn("[ok]", data["body"])
            self.assertIn("recipient@example.com", data["body"])


if __name__ == "__main__":
    unittest.main()
