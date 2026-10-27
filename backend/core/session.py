"""Ghost Conversation Session History Manager.
Provides multi-session persistence, session indexing with quick titles and dates,
and sliding-window chat continuation for Google GenAI.
"""
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from google.genai import types

SESSION_DIR = Path.home() / ".config" / "ghost"
SESSION_FILE = SESSION_DIR / "session.json"
SESSIONS_ARCHIVE_FILE = SESSION_DIR / "chat_sessions.json"
SESSION_TTL_SECONDS = 30 * 60  # 30 minutes active TTL
MAX_SAVED_TURNS = 12  # Retain up to 12 back-and-forth turns (24 messages) per session


def _ensure_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _load_archive() -> list[dict]:
    if not SESSIONS_ARCHIVE_FILE.exists():
        return []
    try:
        data = json.loads(SESSIONS_ARCHIVE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _save_archive(sessions: list[dict]):
    _ensure_dir()
    try:
        SESSIONS_ARCHIVE_FILE.write_text(json.dumps(sessions, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print(f"[warning] Failed to save chat sessions archive: {exc}")


def _generate_title(first_prompt: str) -> str:
    """Derive a clean, concise title from the initial user query."""
    clean = first_prompt.strip()
    if clean.startswith("/"):
        clean = clean[1:]
    # Take first sentence or up to 6 words
    words = clean.split()
    if len(words) <= 6:
        title = " ".join(words)
    else:
        title = " ".join(words[:6]) + "..."
    if len(title) > 42:
        title = title[:39] + "..."
    return title.capitalize() or "Conversation"


def load_session() -> list[dict]:
    """Load valid turns from the active session file."""
    if not SESSION_FILE.exists():
        return []

    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        updated_at = data.get("updated_at", 0)
        # If session is older than TTL, archive stays but active clears
        if time.time() - updated_at > SESSION_TTL_SECONDS:
            clear_session()
            return []
        return data.get("turns", [])
    except Exception:
        clear_session()
        return []


def record_turn(user_prompt: str, model_response: str) -> None:
    """Record a user query and the model response to the active session and multi-session archive."""
    _ensure_dir()
    current_data = {}
    if SESSION_FILE.exists():
        try:
            current_data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except Exception:
            current_data = {}

    session_id = current_data.get("id")
    turns = current_data.get("turns", [])
    created_at_str = current_data.get("date")

    now = datetime.now()
    now_ts = time.time()

    if not session_id or not created_at_str:
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        created_at_str = now.strftime("%b %d, %I:%M %p")

    # Append new turn
    turns.append({"role": "user", "text": user_prompt.strip()})
    turns.append({"role": "model", "text": model_response.strip()})

    # Keep only up to MAX_SAVED_TURNS
    max_msgs = MAX_SAVED_TURNS * 2
    if len(turns) > max_msgs:
        turns = turns[-max_msgs:]

    # Title is derived from first user turn
    first_user_turn = next((t["text"] for t in turns if t.get("role") == "user"), user_prompt)
    title = current_data.get("title") or _generate_title(first_user_turn)

    session_payload = {
        "id": session_id,
        "title": title,
        "date": created_at_str,
        "updated_at": now_ts,
        "turns": turns,
    }

    # 1. Update active session
    try:
        SESSION_FILE.write_text(json.dumps(session_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print(f"[warning] Failed to save active session: {exc}")

    # 2. Update persistent multi-session archive
    archive = _load_archive()
    idx = next((i for i, s in enumerate(archive) if s.get("id") == session_id), None)
    if idx is not None:
        archive[idx] = session_payload
    else:
        archive.insert(0, session_payload)

    # Keep last 30 saved sessions in archive
    if len(archive) > 30:
        archive = archive[:30]

    _save_archive(archive)


def clear_session() -> None:
    """Clear active conversation file (starts fresh on next prompt)."""
    try:
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
    except Exception:
        pass


def list_sessions() -> list[dict]:
    """Return all archived chat sessions sorted by recency."""
    archive = _load_archive()
    # Sort descending by updated_at
    archive.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
    summary = []
    for s in archive:
        summary.append({
            "id": s.get("id"),
            "title": s.get("title", "Untitled Chat"),
            "date": s.get("date", ""),
            "turn_count": len(s.get("turns", [])) // 2,
        })
    return summary


def load_session_by_id(session_id: str) -> Optional[dict]:
    """Switch active session to a specific archived session by ID."""
    archive = _load_archive()
    target = next((s for s in archive if s.get("id") == session_id), None)
    if not target:
        return None

    _ensure_dir()
    # Set as active session
    SESSION_FILE.write_text(json.dumps(target, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def get_genai_history() -> List[types.Content]:
    """Convert session turns into google.genai types.Content objects."""
    turns = load_session()
    contents = []
    for turn in turns:
        role = turn.get("role", "user")
        text = turn.get("text", "")
        if text:
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=text)],
                )
            )
    return contents
