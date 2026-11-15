"""Central Tools Registry for Ghost."""
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
from .email_tools import (
    list_inbox,
    read_email_details,
    stage_email_send,
    configure_email_account,
    execute_confirmed_send,
)
from .keep_tools import (
    list_keep_notes,
    read_keep_note,
    create_keep_note,
    update_keep_note,
    stage_keep_note_deletion,
    execute_confirmed_keep_deletion,
)

TOOLS = [
    # Google Keep Notes & Mobile Sync
    list_keep_notes,
    read_keep_note,
    create_keep_note,
    update_keep_note,
    stage_keep_note_deletion,
    # Multi-Account Email
    list_inbox,
    read_email_details,
    stage_email_send,
    configure_email_account,
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
]

__all__ = [
    "TOOLS",
    "list_keep_notes",
    "read_keep_note",
    "create_keep_note",
    "update_keep_note",
    "stage_keep_note_deletion",
    "execute_confirmed_keep_deletion",
    "list_inbox",
    "read_email_details",
    "stage_email_send",
    "configure_email_account",
    "execute_confirmed_send",
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
    "save_memory",
    "recall_memories",
    "list_all_memories",
    "forget_memory",
]
