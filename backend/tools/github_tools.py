"""GitHub PR & Issue Discussion Investigation Tools for Ghost.
Enables Ghost to deeply inspect online discussions, reviewer feedback, maintainer stances,
and community debates on GitHub without bloating prompt tokens or rushing into code edits.
"""
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


def _get_headers() -> Dict[str, str]:
    headers = {
        "User-Agent": "Ghost-Assistant/1.0 (kratos)",
        "Accept": "application/vnd.github.v3+json",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _http_get_json(url: str, timeout: int = 10) -> Optional[Any]:
    req = urllib.request.Request(url, headers=_get_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        return {"error": f"HTTP {exc.code}: {exc.reason}"}
    except Exception as exc:
        return {"error": str(exc)}


def _detect_local_repo_context(local_dir: Optional[str] = None) -> Dict[str, Any]:
    """Attempt to detect GitHub repository and branch from a local git folder."""
    candidate_paths = []
    if local_dir:
        candidate_paths.append(Path(local_dir).expanduser())
    # Common desktop projects
    candidate_paths.extend([
        Path.home() / "Desktop" / "zulip",
        Path.home() / "Desktop" / "Ghost",
        Path.cwd(),
    ])

    for p in candidate_paths:
        if not p.exists() or not (p / ".git").exists():
            continue
        try:
            # Check remotes
            res_remote = subprocess.run(
                ["git", "remote", "-v"],
                cwd=str(p),
                capture_output=True,
                text=True,
                timeout=3,
            )
            # Check current branch
            res_branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(p),
                capture_output=True,
                text=True,
                timeout=3,
            )
            branch = res_branch.stdout.strip()
            remotes = res_remote.stdout

            # Prefer upstream repo if present, otherwise origin
            upstream_repo = None
            origin_repo = None
            origin_user = None

            for line in remotes.splitlines():
                # e.g. upstream  https://github.com/zulip/zulip.git (fetch)
                # or origin  git@github.com:paul-raja-dev/zulip.git (fetch)
                match = re.search(r"github\.com[:/]([\w\-]+)/([\w\-]+?)(?:\.git)?\s+\(fetch\)", line)
                if match:
                    owner, repo_name = match.group(1), match.group(2)
                    if line.startswith("upstream"):
                        upstream_repo = f"{owner}/{repo_name}"
                    elif line.startswith("origin"):
                        origin_repo = f"{owner}/{repo_name}"
                        origin_user = owner

            target_repo = upstream_repo or origin_repo
            if target_repo:
                return {
                    "detected": True,
                    "local_path": str(p),
                    "repo": target_repo,
                    "branch": branch,
                    "fork_user": origin_user,
                    "upstream_repo": upstream_repo,
                    "origin_repo": origin_repo,
                }
        except Exception:
            continue

    return {"detected": False}


def _find_pr_for_branch(repo: str, branch: str, fork_user: Optional[str] = None) -> Optional[int]:
    """Look up active or recent PR number for a given branch / fork user."""
    # 1. Search with fork_user:branch
    queries = []
    if fork_user:
        queries.append(f"{fork_user}:{branch}")
    queries.append(branch)

    for head_query in queries:
        url = f"https://api.github.com/repos/{repo}/pulls?head={urllib.parse.quote(head_query)}&state=all"
        data = _http_get_json(url)
        if isinstance(data, list) and data:
            return data[0].get("number")

    return None


def investigate_github_discussion(
    repo: str = "",
    number: int = 0,
    state: str = "open",
    max_comments: int = 8,
) -> dict:
    """Investigate discussions, review feedback, maintainer stances, and community debate for a GitHub PR or issue.

    Args:
        repo: Repository in 'owner/repo' format (e.g. 'zulip/zulip'). If blank, auto-detected from local repos.
        number: PR or issue number (e.g. 39862). If 0, auto-detected from local branch.
        state: 'open', 'closed', or 'all' (default: 'open').
        max_comments: Maximum number of recent discussion comments to return (default: 8).

    Returns:
        Structured analysis containing discussion summary, reviewer feedback, maintainer stances,
        timeline events, and external community discussion links (e.g., CZO threads).
    """
    repo = (repo or "").strip()
    detected_info = {}

    if not repo or not number:
        local_ctx = _detect_local_repo_context()
        if local_ctx.get("detected"):
            detected_info = local_ctx
            if not repo:
                repo = local_ctx["repo"]
            if not number and local_ctx.get("branch"):
                found_num = _find_pr_for_branch(
                    repo=repo,
                    branch=local_ctx["branch"],
                    fork_user=local_ctx.get("fork_user"),
                )
                if found_num:
                    number = found_num

    if not repo:
        return {
            "status": "error",
            "message": "Repository not specified and could not be auto-detected. Example: 'zulip/zulip'.",
        }

    # If number is still not known, try finding the latest open PR or recent issues
    if not number:
        list_url = f"https://api.github.com/repos/{repo}/pulls?state={state}&per_page=5"
        prs = _http_get_json(list_url)
        if isinstance(prs, list) and prs:
            summary_list = [
                f"#{p.get('number')}: {p.get('title')} (by @{p.get('user', {}).get('login', 'unknown')})"
                for p in prs
            ]
            return {
                "status": "ok",
                "message": f"Multiple open PRs found in {repo}. Specify a PR number to inspect discussions.",
                "open_prs": summary_list,
            }
        return {
            "status": "error",
            "message": f"No active PRs found or PR number required for {repo}.",
        }

    # 1. Fetch Pull Request / Issue details
    pr_url = f"https://api.github.com/repos/{repo}/pulls/{number}"
    pr_data = _http_get_json(pr_url)
    is_pr = True
    if not pr_data or (isinstance(pr_data, dict) and "error" in pr_data):
        # Fall back to issue endpoint
        issue_url = f"https://api.github.com/repos/{repo}/issues/{number}"
        pr_data = _http_get_json(issue_url)
        is_pr = False

    if not pr_data or (isinstance(pr_data, dict) and "error" in pr_data):
        return {
            "status": "error",
            "message": f"Failed to retrieve #{number} from {repo}: {pr_data.get('error') if isinstance(pr_data, dict) else 'Not found'}",
        }

    title = pr_data.get("title", "")
    author = pr_data.get("user", {}).get("login", "")
    state_val = pr_data.get("state", "")
    is_draft = pr_data.get("draft", False)
    created_at = pr_data.get("created_at", "")
    updated_at = pr_data.get("updated_at", "")
    html_url = pr_data.get("html_url", "")
    head_branch = pr_data.get("head", {}).get("ref", "") if is_pr else ""
    base_branch = pr_data.get("base", {}).get("ref", "") if is_pr else ""

    # Truncate main description to 500 chars
    body_text = (pr_data.get("body") or "").strip()
    if len(body_text) > 500:
        body_text = body_text[:497] + "..."

    # 2. Fetch issue / PR comments
    comments_url = f"https://api.github.com/repos/{repo}/issues/{number}/comments?per_page=50"
    all_comments = _http_get_json(comments_url) or []
    if isinstance(all_comments, dict) and "error" in all_comments:
        all_comments = []

    # 3. Fetch reviews if it's a PR
    all_reviews = []
    review_comments = []
    if is_pr:
        reviews_url = f"https://api.github.com/repos/{repo}/pulls/{number}/reviews"
        all_reviews = _http_get_json(reviews_url) or []
        if isinstance(all_reviews, dict) and "error" in all_reviews:
            all_reviews = []

        rev_comments_url = f"https://api.github.com/repos/{repo}/pulls/{number}/comments?per_page=30"
        review_comments = _http_get_json(rev_comments_url) or []
        if isinstance(review_comments, dict) and "error" in review_comments:
            review_comments = []

    # Extract external community references (e.g. Zulip CZO links, RFCs)
    community_links = set()
    link_pattern = re.compile(r"https?://(?:chat\.zulip\.org|github\.com/[^\s)]+/issues/\d+|github\.com/[^\s)]+/pull/\d+)[^\s)]*")
    for text_sample in [body_text] + [c.get("body", "") for c in all_comments] + [r.get("body", "") for r in all_reviews]:
        if text_sample:
            for match in link_pattern.findall(text_sample):
                community_links.add(match)

    # Format discussion timeline (retain the most recent comments up to max_comments)
    comments_summary = []
    recent_comments = all_comments[-max_comments:] if len(all_comments) > max_comments else all_comments
    for c in recent_comments:
        user = c.get("user", {}).get("login", "unknown")
        c_body = (c.get("body") or "").strip()
        # Truncate long comments to 400 chars to protect token budget
        if len(c_body) > 400:
            c_body = c_body[:397] + "..."
        comments_summary.append({
            "author": user,
            "created_at": c.get("created_at", "")[:10],
            "body": c_body,
        })

    # Format reviews
    reviews_summary = []
    for r in all_reviews:
        r_state = r.get("state", "COMMENTED")
        r_body = (r.get("body") or "").strip()
        if len(r_body) > 300:
            r_body = r_body[:297] + "..."
        user = r.get("user", {}).get("login", "unknown")
        # Only record if review has a body or definitive state like APPROVED / CHANGES_REQUESTED
        if r_body or r_state in ["APPROVED", "CHANGES_REQUESTED"]:
            reviews_summary.append({
                "reviewer": user,
                "state": r_state,
                "body": r_body,
            })

    # Format inline code comments
    inline_summary = []
    recent_review_comments = review_comments[-5:] if len(review_comments) > 5 else review_comments
    for rc in recent_review_comments:
        rc_body = (rc.get("body") or "").strip()
        if len(rc_body) > 250:
            rc_body = rc_body[:247] + "..."
        inline_summary.append({
            "author": rc.get("user", {}).get("login", "unknown"),
            "path": rc.get("path", ""),
            "body": rc_body,
        })

    return {
        "status": "ok",
        "repo": repo,
        "number": number,
        "is_pr": is_pr,
        "title": title,
        "author": author,
        "state": state_val,
        "draft": is_draft,
        "head_branch": head_branch,
        "base_branch": base_branch,
        "html_url": html_url,
        "total_comments": len(all_comments),
        "total_reviews": len(all_reviews),
        "recent_discussion": comments_summary,
        "reviews": reviews_summary,
        "inline_feedback": inline_summary,
        "linked_community_threads": list(community_links)[:5],
        "auto_detected": detected_info.get("detected", False),
    }
