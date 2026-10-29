"""Unit tests for Ghost GitHub PR and Issue Discussion Investigation Tools."""
import unittest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tools.github_tools import (
    investigate_github_discussion,
    _detect_local_repo_context,
)


class TestGitHubTools(unittest.TestCase):
    def test_investigate_explicit_zulip_pr(self):
        res = investigate_github_discussion(repo="zulip/zulip", number=39862)
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("repo"), "zulip/zulip")
        self.assertEqual(res.get("number"), 39862)
        self.assertTrue(res.get("is_pr"))
        self.assertIn("url previews", res.get("title", "").lower())
        self.assertGreater(res.get("total_comments", 0), 10)
        self.assertGreater(res.get("total_reviews", 0), 5)
        # Verify discussion comments exist
        discussion = res.get("recent_discussion", [])
        self.assertTrue(len(discussion) > 0)
        # Verify chrisbobbe's maintainer comment is captured
        authors = [c.get("author") for c in discussion]
        self.assertIn("chrisbobbe", authors)

        # Verify linked community threads capture chat.zulip.org
        czo_links = res.get("linked_community_threads", [])
        self.assertTrue(any("chat.zulip.org" in link for link in czo_links))

    def test_auto_detect_from_desktop_zulip(self):
        # /home/paul/Desktop/zulip is present on kratos
        if (Path.home() / "Desktop" / "zulip" / ".git").exists():
            ctx = _detect_local_repo_context(str(Path.home() / "Desktop" / "zulip"))
            self.assertTrue(ctx.get("detected"))
            self.assertEqual(ctx.get("repo"), "zulip/zulip")
            self.assertEqual(ctx.get("branch"), "url-preview-without-image")

            # Call investigate without repo and number
            res = investigate_github_discussion()
            self.assertEqual(res.get("status"), "ok")
            self.assertEqual(res.get("repo"), "zulip/zulip")
            self.assertEqual(res.get("number"), 39862)

    def test_invalid_repo_handling(self):
        res = investigate_github_discussion(repo="nonexistent_user_12345/nonexistent_repo_99999", number=1)
        self.assertEqual(res.get("status"), "error")


if __name__ == "__main__":
    unittest.main()
