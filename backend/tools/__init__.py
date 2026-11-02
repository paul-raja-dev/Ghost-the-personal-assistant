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
    inspect_project,
)
from .github_tools import investigate_github_discussion
from .vision_tools import capture_and_inspect_screen, inspect_image_file

TOOLS = [
    # Vision & Screen Awareness
    capture_and_inspect_screen,
    inspect_image_file,
    # GitHub PR & Issue Discussion Investigation
    investigate_github_discussion,
    # System & Live Filesystem Operations
    execute_command,
    read_file,
    write_file,
    list_directory,
    search_files,
    move_or_rename,
    stage_file_deletion,
    inspect_project,
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
    "capture_and_inspect_screen",
    "inspect_image_file",
    "investigate_github_discussion",
    "execute_command",
    "read_file",
    "write_file",
    "list_directory",
    "search_files",
    "move_or_rename",
    "stage_file_deletion",
    "execute_confirmed_trash",
    "inspect_project",
    "get_system_status",
    "add_task",
    "save_memory",
    "recall_memories",
    "list_all_memories",
    "forget_memory",
]
