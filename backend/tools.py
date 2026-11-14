"""Legacy wrapper redirecting to backend.tools package."""
from tools import (
    TOOLS,
    list_inbox,
    read_email_details,
    stage_email_send,
    configure_email_account,
    execute_confirmed_send,
    capture_and_inspect_screen,
    inspect_image_file,
    investigate_github_discussion,
    add_task,
    save_memory,
    recall_memories,
    list_all_memories,
    forget_memory,
)

__all__ = [
    "TOOLS",
    "list_inbox",
    "read_email_details",
    "stage_email_send",
    "configure_email_account",
    "execute_confirmed_send",
    "capture_and_inspect_screen",
    "inspect_image_file",
    "investigate_github_discussion",
    "add_task",
    "save_memory",
    "recall_memories",
    "list_all_memories",
    "forget_memory",
]
