"""Central Tools Registry for Ghost."""
from .tasks import add_task
from .memory_tools import save_memory, recall_memories, list_all_memories, forget_memory
from .system_tools import (
    execute_command,
    read_file,
    write_file,
    list_directory,
    search_files,
    move_or_rename,
    stage_file_deletion,
    execute_confirmed_trash,
    get_system_status,
)

TOOLS = [
    # System & Live Filesystem Operations
    execute_command,
    read_file,
    write_file,
    list_directory,
    search_files,
    move_or_rename,
    stage_file_deletion,
    get_system_status,
    # Memory
    save_memory,
    recall_memories,
    list_all_memories,
    forget_memory,
    # Tasks
    add_task,
]

__all__ = [
    "TOOLS",
    "execute_command",
    "read_file",
    "write_file",
    "list_directory",
    "search_files",
    "move_or_rename",
    "stage_file_deletion",
    "execute_confirmed_trash",
    "get_system_status",
    "add_task",
    "save_memory",
    "recall_memories",
    "list_all_memories",
    "forget_memory",
]
