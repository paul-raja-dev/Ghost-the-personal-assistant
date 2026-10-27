"""Ghost Conversation Session History Manager.
Provides sliding-window conversation turns with auto-expiry (15 mins) for multi-turn chat continuation.
"""
import json
import time
from pathlib import Path
from typing import List

from google.genai import types

SESSION_DIR = Path.home() / ".config" / "ghost"
SESSION_FILE = SESSION_DIR / "session.json"
SESSION_TTL_SECONDS = 15 * 60  # 15 minutes
MAX_SAVED_TURNS = 8  # Retain up to 8 back-and-forth turns (16 messages)


def _ensure_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def load_session() -> list[dict]:
    """Load valid turns from session file if within TTL."""
    if not SESSION_FILE.exists():
        return []

    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        updated_at = data.get("updated_at", 0)
        # Check if session has expired
        if time.time() - updated_at > SESSION_TTL_SECONDS:
            clear_session()
            return []
        return data.get("turns", [])
    except Exception:
        clear_session()
        return []


def record_turn(user_prompt: str, model_response: str) -> None:
    """Record a user query and the model response to the active session."""
    _ensure_dir()
    turns = load_session()

    # Append new turn
    turns.append({"role": "user", "text": user_prompt.strip()})
    turns.append({"role": "model", "text": model_response.strip()})

    # Keep only the last MAX_SAVED_TURNS (each turn is 2 messages: user + model)
    max_msgs = MAX_SAVED_TURNS * 2
    if len(turns) > max_msgs:
        turns = turns[-max_msgs:]

    session_data = {
        "updated_at": time.time(),
        "turns": turns,
    }

    try:
        SESSION_FILE.write_text(json.dumps(session_data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print(f"[warning] Failed to save session: {exc}")


def clear_session() -> None:
    """Clear conversation history."""
    try:
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
    except Exception:
        pass


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
