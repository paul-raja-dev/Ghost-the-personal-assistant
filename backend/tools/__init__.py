"""Central Tools Registry for Ghost."""
from .tasks import add_task
from .memory_tools import save_memory, recall_memories, list_all_memories, forget_memory

TOOLS = [
    add_task,
    save_memory,
    recall_memories,
    list_all_memories,
    forget_memory,
]

__all__ = [
    "TOOLS",
    "add_task",
    "save_memory",
    "recall_memories",
    "list_all_memories",
    "forget_memory",
]
