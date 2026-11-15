"""Ghost Google Keep Integration Tools for Linux (kratos).
Provides seamless two-way synchronization of notes, brainstorms, thoughts,
and checklists with the user's mobile Google Keep app via gkeepapi.
"""
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional
import uuid

# Configuration paths
CONFIG_DIR = Path.home() / ".config" / "ghost"
KEEP_STATE_FILE = CONFIG_DIR / "keep_state.json"
PENDING_TICKETS_FILE = CONFIG_DIR / "pending_keep_tickets.json"
ACCOUNTS_FILE = CONFIG_DIR / "email_accounts.json"

_keep_client = None
_pending_deletions: Dict[str, Dict[str, Any]] = {}

COLOR_MAP = {
    "white": "White",
    "red": "Red",
    "orange": "Orange",
    "yellow": "Yellow",
    "green": "Green",
    "teal": "Teal",
    "blue": "Blue",
    "darkblue": "DarkBlue",
    "purple": "Purple",
    "pink": "Pink",
    "brown": "Brown",
    "gray": "Gray",
    "grey": "Gray",
}


def _ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_keep_email() -> str:
    """Resolve the Google account email configured for Google Keep (defaults to work)."""
    if ACCOUNTS_FILE.exists():
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                accounts = data.get("accounts", {})
                if "work" in accounts and accounts["work"].get("email"):
                    return accounts["work"]["email"]
                if "personal" in accounts and accounts["personal"].get("email"):
                    return accounts["personal"]["email"]
        except Exception:
            pass
    return "paulraja.creator@gmail.com"


def get_master_token() -> Optional[str]:
    """Retrieve Google Keep Master Token from environment or .env file."""
    token = os.getenv("GOOGLE_KEEP_MASTER_TOKEN")
    if token:
        return token.strip()

    env_file = Path("/home/paul/Desktop/Ghost/.env")
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GOOGLE_KEEP_MASTER_TOKEN="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        return val.strip()
        except Exception:
            pass
    return None


def get_keep_client():
    """Get or initialize the authenticated gkeepapi.Keep client.
    Uses cached session state from ~/.config/ghost/keep_state.json for instant sub-60ms connections.
    """
    global _keep_client
    if _keep_client is not None:
        return _keep_client, None

    try:
        import gkeepapi
    except ImportError:
        return None, "gkeepapi package not installed in environment."

    email = get_keep_email()
    master_token = get_master_token()

    if not master_token:
        return None, (
            "Google Keep Master Token not configured. "
            "Please set GOOGLE_KEEP_MASTER_TOKEN in your .env file on kratos."
        )

    _ensure_config_dir()
    keep = gkeepapi.Keep()

    # 1. Try resuming from cached local state
    if KEEP_STATE_FILE.exists():
        try:
            with open(KEEP_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            keep.resume(email, master_token, state=state, sync=True)
            _keep_client = keep
            return keep, None
        except Exception:
            # Fall back to fresh authenticate if cached state invalid or expired
            pass

    # 2. Authenticate fresh using master token
    try:
        keep.authenticate(email, master_token)
        # Cache state to disk for future runs
        try:
            with open(KEEP_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(keep.dump(), f)
        except Exception:
            pass
        _keep_client = keep
        return keep, None
    except Exception as exc:
        return None, f"Google Keep authentication failed: {str(exc)}"


def list_keep_notes(
    query: str = "",
    limit: int = 10,
    pinned_only: bool = False,
    label: str = "",
) -> Dict[str, Any]:
    """Search and retrieve notes and checklists from Google Keep on kratos.

    Args:
        query: Optional search keyword to filter notes by title or content.
        limit: Maximum number of notes to return (default 10).
        pinned_only: If True, only returns pinned notes.
        label: Optional label/tag name to filter by.
    """
    keep, err = get_keep_client()
    if err or not keep:
        return {
            "status": "setup_required" if "not configured" in (err or "") else "error",
            "message": err or "Google Keep client unavailable.",
            "notes": [],
            "count": 0,
        }

    try:
        import gkeepapi

        notes_iter = keep.all()
        results: List[Dict[str, Any]] = []

        q_lower = query.strip().lower() if query else ""

        for note in notes_iter:
            if note.trashed or note.archived:
                continue
            if pinned_only and not note.pinned:
                continue

            # Check label
            if label:
                note_labels = [l.name.lower() for l in note.labels.all()]
                if label.lower() not in note_labels:
                    continue

            # Check query
            title = note.title or ""
            text = note.text or ""

            if q_lower:
                if q_lower not in title.lower() and q_lower not in text.lower():
                    continue

            is_checklist = isinstance(note, gkeepapi.node.List)
            checklist_items = []
            if is_checklist:
                for item in note.items:
                    checklist_items.append({"text": item.text, "checked": bool(item.checked)})

            # Extract 1-line snippet
            snippet_raw = " ".join([l.strip() for l in text.split("\n") if l.strip()])
            snippet = re.sub(r"\s+", " ", snippet_raw)[:140]

            color_name = "default"
            if note.color:
                color_name = str(note.color.name).lower()

            results.append({
                "id": str(note.id),
                "title": title or "(Untitled Note)",
                "text": text,
                "snippet": snippet or "(Empty note)",
                "pinned": bool(note.pinned),
                "color": color_name,
                "is_checklist": is_checklist,
                "checklist_items": checklist_items,
            })

            if len(results) >= limit:
                break

        return {
            "status": "ok",
            "count": len(results),
            "notes": results,
        }
    except Exception as exc:
        return {"status": "error", "message": f"Error querying Google Keep: {str(exc)}", "notes": []}


def read_keep_note(note_id: str) -> Dict[str, Any]:
    """Retrieve full details of a specific Google Keep note or checklist.

    Args:
        note_id: The unique ID of the Google Keep note.
    """
    keep, err = get_keep_client()
    if err or not keep:
        return {"status": "error", "message": err or "Google Keep client unavailable."}

    try:
        import gkeepapi

        note = keep.get(str(note_id).strip())
        if not note:
            return {"status": "error", "message": f"Note '{note_id}' not found in Google Keep."}

        is_checklist = isinstance(note, gkeepapi.node.List)
        checklist_items = []
        if is_checklist:
            for item in note.items:
                checklist_items.append({"text": item.text, "checked": bool(item.checked)})

        color_name = "default"
        if note.color:
            color_name = str(note.color.name).lower()

        return {
            "status": "ok",
            "note_id": str(note.id),
            "title": note.title or "(Untitled Note)",
            "text": note.text or "",
            "pinned": bool(note.pinned),
            "color": color_name,
            "is_checklist": is_checklist,
            "checklist_items": checklist_items,
            "archived": bool(note.archived),
        }
    except Exception as exc:
        return {"status": "error", "message": f"Failed to read note {note_id}: {str(exc)}"}


def create_keep_note(
    title: str,
    text: str = "",
    checklist_items: Optional[List[str]] = None,
    pinned: bool = False,
    color: str = "",
) -> Dict[str, Any]:
    """Create a new note or checklist in Google Keep, syncing immediately with mobile.

    Args:
        title: The title of the note or list.
        text: Plain text content (for standard notes).
        checklist_items: Optional list of strings to create a to-do checklist.
        pinned: Whether to pin the note to the top of Google Keep.
        color: Optional note color (white, red, orange, yellow, green, teal, blue, darkblue, purple, pink, brown, gray).
    """
    keep, err = get_keep_client()
    if err or not keep:
        return {
            "status": "setup_required" if "not configured" in (err or "") else "error",
            "message": err or "Google Keep client unavailable.",
        }

    try:
        import gkeepapi

        clean_title = (title or "").strip()
        is_checklist = bool(checklist_items and len(checklist_items) > 0)

        if is_checklist:
            items_tuples = [(str(it).strip(), False) for it in checklist_items if str(it).strip()]
            note = keep.createList(clean_title, items_tuples)
        else:
            note = keep.createNote(clean_title, (text or "").strip())

        note.pinned = bool(pinned)

        # Set color if valid
        if color:
            color_key = color.strip().lower()
            if color_key in COLOR_MAP:
                enum_name = COLOR_MAP[color_key]
                if hasattr(gkeepapi.node.ColorValue, enum_name):
                    note.color = getattr(gkeepapi.node.ColorValue, enum_name)

        keep.sync()

        # Update cached state
        try:
            with open(KEEP_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(keep.dump(), f)
        except Exception:
            pass

        return {
            "status": "ok",
            "note_id": str(note.id),
            "title": clean_title,
            "text": note.text,
            "pinned": bool(note.pinned),
            "is_checklist": is_checklist,
            "message": f"Note '{clean_title}' saved to Google Keep and synced to mobile.",
        }
    except Exception as exc:
        return {"status": "error", "message": f"Failed to create Google Keep note: {str(exc)}"}


def update_keep_note(
    note_id: str,
    text: str = "",
    append: bool = True,
    add_items: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Update an existing note in Google Keep by appending or adding checklist items.

    Args:
        note_id: The ID of the note to update.
        text: Text to append or set.
        append: If True, appends text to existing content; if False, overwrites text.
        add_items: Optional list of new items to add to a checklist.
    """
    keep, err = get_keep_client()
    if err or not keep:
        return {"status": "error", "message": err or "Google Keep client unavailable."}

    try:
        import gkeepapi

        note = keep.get(str(note_id).strip())
        if not note:
            return {"status": "error", "message": f"Note '{note_id}' not found."}

        is_checklist = isinstance(note, gkeepapi.node.List)

        if is_checklist and add_items:
            for it in add_items:
                if str(it).strip():
                    note.add(str(it).strip(), False)
        elif text:
            if append and note.text:
                note.text = f"{note.text}\n{text.strip()}"
            else:
                note.text = text.strip()

        keep.sync()

        # Update cache
        try:
            with open(KEEP_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(keep.dump(), f)
        except Exception:
            pass

        return {
            "status": "ok",
            "note_id": str(note.id),
            "title": note.title or "(Untitled Note)",
            "message": f"Note '{note.title}' updated successfully.",
        }
    except Exception as exc:
        return {"status": "error", "message": f"Failed to update note {note_id}: {str(exc)}"}


def stage_keep_note_deletion(note_id: str) -> Dict[str, Any]:
    """Prepare and stage note deletion with user confirmation ticket.
    Ghost NEVER deletes a Google Keep note without explicit user approval.

    Args:
        note_id: The ID of the Google Keep note to delete.
    """
    keep, err = get_keep_client()
    if err or not keep:
        return {"status": "error", "message": err or "Google Keep client unavailable."}

    try:
        note = keep.get(str(note_id).strip())
        if not note:
            return {"status": "error", "message": f"Note '{note_id}' not found."}

        ticket_id = f"keep_del_{uuid.uuid4().hex[:8]}"
        title = note.title or "(Untitled Note)"

        _pending_deletions[ticket_id] = {
            "note_id": str(note.id),
            "title": title,
            "timestamp": time.time(),
        }

        # Persist pending tickets
        _ensure_config_dir()
        try:
            with open(PENDING_TICKETS_FILE, "w", encoding="utf-8") as f:
                json.dump(_pending_deletions, f)
        except Exception:
            pass

        return {
            "status": "staged",
            "ticket_id": ticket_id,
            "note_id": str(note.id),
            "title": title,
            "message": f"Are you sure you want to delete note '{title}' from Google Keep?",
            "actions": [
                {
                    "id": "confirm",
                    "label": "Delete Note",
                    "type": "danger",
                    "payload": f"confirm: delete_keep_note {ticket_id}",
                },
                {
                    "id": "cancel",
                    "label": "Cancel",
                    "type": "secondary",
                },
            ],
        }
    except Exception as exc:
        return {"status": "error", "message": f"Failed to stage note deletion: {str(exc)}"}


def execute_confirmed_keep_deletion(ticket_id: str) -> Dict[str, Any]:
    """Execute confirmed note deletion from Google Keep after user approval.

    Args:
        ticket_id: Safety ticket ID returned by stage_keep_note_deletion.
    """
    # Load persisted tickets if memory empty
    if not _pending_deletions and PENDING_TICKETS_FILE.exists():
        try:
            with open(PENDING_TICKETS_FILE, "r", encoding="utf-8") as f:
                _pending_deletions.update(json.load(f))
        except Exception:
            pass

    ticket = _pending_deletions.get(ticket_id)
    if not ticket:
        return {"status": "error", "message": f"Invalid or expired deletion ticket '{ticket_id}'."}

    note_id = ticket.get("note_id")
    title = ticket.get("title", "")

    keep, err = get_keep_client()
    if err or not keep:
        return {"status": "error", "message": err or "Google Keep client unavailable."}

    try:
        note = keep.get(str(note_id).strip())
        if not note:
            _pending_deletions.pop(ticket_id, None)
            return {"status": "error", "message": f"Note '{note_id}' no longer exists in Google Keep."}

        # note.trash() moves to Keep Trash (restorable for 7 days)
        note.trash()
        keep.sync()

        # Clean up ticket
        _pending_deletions.pop(ticket_id, None)
        try:
            with open(PENDING_TICKETS_FILE, "w", encoding="utf-8") as f:
                json.dump(_pending_deletions, f)
        except Exception:
            pass

        return {
            "status": "ok",
            "ticket_id": ticket_id,
            "message": f"Note '{title}' moved to Google Keep Trash.",
        }
    except Exception as exc:
        return {"status": "error", "message": f"Failed to delete note from Google Keep: {str(exc)}"}
