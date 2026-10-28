"""Ghost Conversation Session History Manager.
Provides multi-session persistence, session indexing with quick titles and dates,
sliding-window chat continuation, and autonomous rolling conversation summaries for Google GenAI.
"""
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from google import genai
from google.genai import types

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import config

SESSION_DIR = Path.home() / ".config" / "ghost"
SESSION_FILE = SESSION_DIR / "session.json"
SESSIONS_ARCHIVE_FILE = SESSION_DIR / "chat_sessions.json"
SESSION_TTL_SECONDS = 30 * 60  # 30 minutes active TTL
VERBATIM_TURNS_KEEP = 8  # Retain up to 8 back-and-forth turns (16 messages) verbatim
SUMMARY_TRIGGER_TURNS = 12  # Trigger consolidation when reaching 12 turns (24 messages)


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


def _summarize_turns(turns_to_summarize: list[dict], existing_summary: str = "") -> str:
    """Summarize a segment of conversation turns and merge with existing running summary."""
    if not turns_to_summarize:
        return existing_summary

    lines = []
    for t in turns_to_summarize:
        role = "User" if t.get("role") == "user" else "Ghost"
        text = t.get("text", "").strip()
        if text.startswith("{") and "body" in text:
            try:
                data = json.loads(text)
                text = data.get("body", text)
            except Exception:
                pass
        lines.append(f"{role}: {text}")

    conversation_text = "\n".join(lines)
    prompt = (
        "You are a concise conversation summarizer. Strict zero emojis.\n"
        "Condense the following conversation segment into 2 to 4 bullet points capturing key topics, decisions, instructions, and facts.\n"
    )
    if existing_summary:
        prompt += f"\nPrevious Running Summary so far:\n{existing_summary}\n\nUpdate and consolidate the summary to include this new segment:\n"
    else:
        prompt += "\nConversation Segment:\n"
    prompt += conversation_text + "\n\nUpdated Concise Summary (clean bullet points):"

    try:
        client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=10_000),
        )
        resp = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=300,
                temperature=0,
            )
        )
        summary_text = (resp.text or "").strip()
        if summary_text:
            return summary_text
    except Exception as exc:
        print(f"[warning] Failed to summarize turns via Gemini: {exc}")

    # Fallback deterministic summary
    user_topics = [t.get("text", "")[:40] for t in turns_to_summarize if t.get("role") == "user"]
    fallback = "- Topics discussed: " + "; ".join(user_topics[:4])
    if existing_summary:
        return existing_summary + "\n" + fallback
    return fallback


def get_session_summary() -> str:
    """Load running summary from the active session file if within TTL."""
    if not SESSION_FILE.exists():
        return ""
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        if time.time() - data.get("updated_at", 0) > SESSION_TTL_SECONDS:
            return ""
        return data.get("summary", "")
    except Exception:
        return ""


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
    summary = current_data.get("summary", "")
    created_at_str = current_data.get("date")

    now = datetime.now()
    now_ts = time.time()

    if not session_id or not created_at_str:
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        created_at_str = now.strftime("%b %d, %I:%M %p")

    # Append new turn
    turns.append({"role": "user", "text": user_prompt.strip()})
    turns.append({"role": "model", "text": model_response.strip()})

    # Rolling summary consolidation:
    # When turns reach SUMMARY_TRIGGER_TURNS * 2 (24 messages / 12 turns),
    # slice off the oldest turns that exceed VERBATIM_TURNS_KEEP * 2,
    # summarize them into running summary, and retain recent turns verbatim.
    trigger_limit = SUMMARY_TRIGGER_TURNS * 2
    verbatim_limit = VERBATIM_TURNS_KEEP * 2

    if len(turns) >= trigger_limit:
        cutoff = len(turns) - verbatim_limit
        old_turns = turns[:cutoff]
        turns = turns[cutoff:]
        summary = _summarize_turns(old_turns, summary)

    # Title is derived from first user turn
    first_user_turn = next((t["text"] for t in turns if t.get("role") == "user"), user_prompt)
    title = current_data.get("title") or _generate_title(first_user_turn)

    session_payload = {
        "id": session_id,
        "title": title,
        "date": created_at_str,
        "updated_at": now_ts,
        "summary": summary,
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


def delete_session(session_id: str) -> bool:
    """Delete a session from the persistent archive. If active, clear active session."""
    archive = _load_archive()
    new_archive = [s for s in archive if s.get("id") != session_id]
    _save_archive(new_archive)

    # If currently active session matches deleted session, remove active session file
    if SESSION_FILE.exists():
        try:
            active_data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            if active_data.get("id") == session_id:
                SESSION_FILE.unlink()
        except Exception:
            pass
    return True


def get_genai_history() -> List[types.Content]:
    """Convert session turns and rolling summary into google.genai types.Content objects."""
    summary = get_session_summary()
    turns = load_session()
    contents = []

    # If a rolling summary of earlier turns exists, inject as the opening context block
    if summary:
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"[Context Summary of earlier conversation turns:\n{summary}]")]
            )
        )
        contents.append(
            types.Content(
                role="model",
                parts=[types.Part.from_text(text="[ok] Context acknowledged. I have full context of our earlier discussion.")]
            )
        )

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
