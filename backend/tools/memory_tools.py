"""Memory Management Tools for Ghost.
Exposes living memory functions to Gemini via function calling.
"""
import sys
from pathlib import Path

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from core import memory


def save_memory(category: str, content: str) -> dict:
    """Save a fact, preference, contact, or workflow detail to user memory.
    Call this whenever you learn something new about the user during the conversation.

    Args:
        category: One of 'identity', 'preferences', 'projects', 'contacts', 'workflows', 'notes'.
        content: The fact to remember. Be specific and concise, e.g. 'Prefers dark mode'.

    Returns:
        A dict confirming the saved memory.
    """
    return memory.save_memory(category=category, content=content, source="conversation")


def recall_memories(query: str = "") -> dict:
    """Search or list memories relevant to a query.

    Args:
        query: Keywords to search for, or empty string to retrieve the most recent memories.

    Returns:
        A dict with the matching memories.
    """
    results = memory.recall_memories(query=query)
    return {"status": "ok", "count": len(results), "memories": results}


def list_all_memories() -> dict:
    """List all saved memories grouped by category.
    Use when the user asks 'what do you know about me?' or 'show my memories'.

    Returns:
        A dict with all memories grouped by category.
    """
    return memory.list_all_memories()


def forget_memory(memory_id: str) -> dict:
    """Delete a specific memory by its ID.
    Use when the user asks to forget or remove a specific memory.

    Args:
        memory_id: The ID of the memory, e.g. 'm_a1b2c3d4'.

    Returns:
        A dict with status ok or error.
    """
    return memory.forget_memory(memory_id=memory_id)
