"""Legacy wrapper redirecting to backend.tools package."""
from tools import (
    TOOLS,
    add_task,
    save_memory,
    recall_memories,
    list_all_memories,
    forget_memory,
)

__all__ = [
    "TOOLS",
    "add_task",
    "save_memory",
    "recall_memories",
    "list_all_memories",
    "forget_memory",
]
