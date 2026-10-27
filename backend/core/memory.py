"""Living Memory Engine for Ghost.
Stores and retrieves persistent user facts, preferences, contacts, and workflows in JSONL.
"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

# Primary path is user config directory so memories survive git operations
CONFIG_DIR = Path.home() / ".config" / "ghost"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_FILE = CONFIG_DIR / "memories.jsonl"


def _load_all() -> list[dict]:
    """Load all active (non-deleted) memories from disk."""
    if not MEMORY_FILE.exists():
        return []
    memories = []
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if not data.get("deleted", False):
                        memories.append(data)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    return memories


def _append_memory(record: dict) -> None:
    """Append a new memory record to disk."""
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def save_memory(category: str, content: str, source: str = "conversation") -> dict:
    """Save a fact, preference, contact, or workflow detail to memory.
    
    Args:
        category: One of 'identity', 'preferences', 'projects', 'contacts', 'workflows', 'notes'.
        content: The fact to remember. Be specific and concise.
        source: Origin of fact, e.g. 'conversation', 'github', 'gmail', 'system'.
    """
    category = (category or "notes").strip().lower()
    content = content.strip()
    if not content:
        return {"status": "error", "message": "Memory content cannot be empty."}

    existing = _load_all()
    # Check for near-identical duplicate
    for m in existing:
        if m.get("category") == category and m.get("content", "").lower() == content.lower():
            return {
                "status": "ok",
                "message": f"Already remembered: {content}",
                "memory_id": m.get("id"),
            }

    memory_id = f"m_{uuid.uuid4().hex[:8]}"
    record = {
        "id": memory_id,
        "ts": datetime.now().isoformat(),
        "category": category,
        "content": content,
        "source": source,
        "deleted": False,
    }
    _append_memory(record)
    return {
        "status": "ok",
        "message": f"Remembered [{category}]: {content}",
        "memory_id": memory_id,
    }


def recall_memories(query: str = "", limit: int = 15) -> list[dict]:
    """Search active memories by keyword or return most recent.
    
    Args:
        query: Optional keywords to search for.
        limit: Max number of memories to return.
    """
    memories = _load_all()
    if not query.strip():
        # Return most recent
        return memories[-limit:]

    tokens = [t.lower() for t in query.strip().split() if len(t) > 1]
    scored = []
    for m in memories:
        text = f"{m.get('category', '')} {m.get('content', '')}".lower()
        score = sum(1 for t in tokens if t in text)
        if score > 0:
            scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:limit]]


def list_all_memories() -> dict:
    """Return all memories grouped by category."""
    memories = _load_all()
    grouped = {}
    for m in memories:
        cat = m.get("category", "notes")
        grouped.setdefault(cat, []).append({
            "id": m.get("id"),
            "content": m.get("content"),
            "ts": m.get("ts"),
        })
    return {"status": "ok", "total": len(memories), "categories": grouped}


def forget_memory(memory_id: str) -> dict:
    """Soft-delete a specific memory by ID."""
    memory_id = memory_id.strip()
    memories = _load_all()
    found = False
    new_records = []
    
    if not MEMORY_FILE.exists():
        return {"status": "error", "message": "No memories found."}

    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if data.get("id") == memory_id:
                    data["deleted"] = True
                    found = True
                new_records.append(data)
            except Exception:
                continue

    if found:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            for r in new_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return {"status": "ok", "message": f"Deleted memory {memory_id}."}
    return {"status": "error", "message": f"Memory {memory_id} not found."}


def get_system_prompt_context(max_memories: int = 25) -> str:
    """Format active user memories into a concise context block for the system prompt."""
    memories = _load_all()
    if not memories:
        return ""
    # Take most recent memories
    selected = memories[-max_memories:]
    lines = ["\nWhat you know about your user (learned from past interactions):"]
    for m in selected:
        cat = m.get("category", "general")
        content = m.get("content", "").strip()
        if content:
            lines.append(f"- [{cat}] {content}")
    return "\n".join(lines) + "\n"
