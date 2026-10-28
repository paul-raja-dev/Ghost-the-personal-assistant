"""System and Live Filesystem Operations for Ghost."""
import glob
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def _resolve_path(path_str: str) -> Path:
    """Safely expand and resolve a path string."""
    expanded = os.path.expanduser(os.path.expandvars(path_str.strip()))
    return Path(expanded).resolve()


def execute_command(command: str, working_dir: str = "~") -> dict:
    """Execute a bash shell command on the user's Linux system and return the output.

    Args:
        command: The shell command line to run, e.g. "git status", "ls -la", "df -h".
        working_dir: The directory to run the command in. Defaults to the user's home directory "~".

    Returns:
        A dict containing status, exit_code, stdout, stderr, and working_dir.
    """
    cmd = command.strip()
    if not cmd:
        return {"status": "error", "message": "Command is empty."}

    # Guardrail against catastrophic root destruction
    lower_cmd = cmd.lower()
    destructive_patterns = [
        "rm -rf /", "rm -rf /*", "mkfs", ":(){ :|:& };:", "dd if=/dev/zero of=/dev/sd", "dd if=/dev/urandom of=/dev/sd"
    ]
    for pattern in destructive_patterns:
        if pattern in lower_cmd:
            return {"status": "error", "message": f"Execution blocked: Command matches destructive pattern '{pattern}'."}

    cwd_path = _resolve_path(working_dir)
    if not cwd_path.exists() or not cwd_path.is_dir():
        cwd_path = Path.home()

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            timeout=15,  # 15s timeout to prevent hanging on interactive prompts
            stdin=subprocess.DEVNULL,
        )
        return {
            "status": "ok" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "working_dir": str(cwd_path),
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "exit_code": 124,
            "stdout": "",
            "stderr": "Command timed out after 15 seconds.",
            "working_dir": str(cwd_path),
        }
    except Exception as exc:
        return {
            "status": "error",
            "exit_code": 1,
            "stdout": "",
            "stderr": str(exc),
            "working_dir": str(cwd_path),
        }


def read_file(path: str, max_lines: int = 300) -> dict:
    """Read contents of a text file from the local filesystem.

    Args:
        path: Absolute or relative file path (supports '~' expansion).
        max_lines: Maximum number of lines to read (default 300).

    Returns:
        A dict containing status, path, line_count, and content or error.
    """
    file_path = _resolve_path(path)
    if not file_path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}
    if not file_path.is_file():
        return {"status": "error", "message": f"Path is a directory, not a file: {file_path}"}

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [f.readline() for _ in range(max_lines)]
            truncated = f.readline() != ""

        content = "".join(lines)
        return {
            "status": "ok",
            "path": str(file_path),
            "lines_read": len(lines),
            "truncated": truncated,
            "content": content,
        }
    except Exception as exc:
        return {"status": "error", "message": f"Failed to read file: {exc}"}


def write_file(path: str, content: str, append: bool = False) -> dict:
    """Write or append text content to a file, creating parent directories if needed.

    Args:
        path: Absolute or relative file path (supports '~' expansion).
        content: The text content to write.
        append: If True, appends to the file instead of overwriting.

    Returns:
        A dict containing status, path, and bytes_written.
    """
    file_path = _resolve_path(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(file_path, mode, encoding="utf-8") as f:
            f.write(content)

        return {
            "status": "ok",
            "path": str(file_path),
            "action": "appended" if append else "written",
            "bytes_written": len(content.encode("utf-8")),
        }
    except Exception as exc:
        return {"status": "error", "message": f"Failed to write file: {exc}"}


def list_directory(path: str = "~/Desktop", show_hidden: bool = False) -> dict:
    """List files and subdirectories in a directory with their sizes and types.

    Args:
        path: Path to list (supports '~' expansion). Defaults to '~/Desktop'.
        show_hidden: Whether to include hidden files (starting with '.').

    Returns:
        A dict containing status, path, items count, and list of file summaries.
    """
    dir_path = _resolve_path(path)
    if not dir_path.exists():
        return {"status": "error", "message": f"Directory not found: {dir_path}"}
    if not dir_path.is_dir():
        return {"status": "error", "message": f"Path is not a directory: {dir_path}"}

    try:
        items = []
        for entry in os.scandir(dir_path):
            if not show_hidden and entry.name.startswith("."):
                continue
            is_dir = entry.is_dir()
            size = 0
            if not is_dir:
                try:
                    size = entry.stat().st_size
                except Exception:
                    size = 0

            mod_time = ""
            try:
                mod_time = datetime.fromtimestamp(entry.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

            items.append({
                "name": entry.name,
                "type": "directory" if is_dir else "file",
                "size_bytes": size,
                "modified": mod_time,
            })

        items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
        return {
            "status": "ok",
            "path": str(dir_path),
            "count": len(items),
            "items": items,
        }
    except Exception as exc:
        return {"status": "error", "message": f"Failed to list directory: {exc}"}


def search_files(query: str, search_dir: str = "~", file_pattern: str = "*", max_results: int = 30) -> dict:
    """Search for files by filename pattern or text content within a directory.

    Args:
        query: Search string or filename query.
        search_dir: Root directory to search from. Defaults to '~'.
        file_pattern: Filename glob pattern, e.g. '*.py', '*.txt', '*'.
        max_results: Max results to return (default 30).

    Returns:
        A dict with status, results list, and total count.
    """
    root_path = _resolve_path(search_dir)
    if not root_path.exists():
        return {"status": "error", "message": f"Search directory not found: {root_path}"}

    results = []
    # Try using fast grep/find if query is content search
    try:
        # 1. Filename matching
        for path in root_path.rglob(file_pattern):
            if query.lower() in path.name.lower():
                results.append({
                    "path": str(path),
                    "type": "directory" if path.is_dir() else "file",
                    "match_type": "filename",
                })
                if len(results) >= max_results:
                    break

        return {
            "status": "ok",
            "query": query,
            "search_dir": str(root_path),
            "count": len(results),
            "results": results,
        }
    except Exception as exc:
        return {"status": "error", "message": f"Search failed: {exc}"}


def move_or_rename(source: str, destination: str) -> dict:
    """Move or rename a file or directory.

    Args:
        source: Source file or directory path.
        destination: Destination file or directory path.

    Returns:
        A dict with status, source, destination, and message.
    """
    src_path = _resolve_path(source)
    dst_path = _resolve_path(destination)

    if not src_path.exists():
        return {"status": "error", "message": f"Source does not exist: {src_path}"}

    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))
        return {
            "status": "ok",
            "source": str(src_path),
            "destination": str(dst_path),
            "message": f"Moved '{src_path.name}' to '{dst_path}'",
        }
    except Exception as exc:
        return {"status": "error", "message": f"Move failed: {exc}"}


def delete_file_or_dir(path: str) -> dict:
    """Delete a file or directory from the filesystem.

    Args:
        path: File or directory path to delete.

    Returns:
        A dict with status, path, and message.
    """
    target_path = _resolve_path(path)
    if not target_path.exists():
        return {"status": "error", "message": f"Target not found: {target_path}"}

    # Guardrails against deleting root or home root
    if str(target_path) in ["/", str(Path.home()), "/home"]:
        return {"status": "error", "message": "Deletion blocked: Cannot delete root or home directory."}

    try:
        if target_path.is_dir():
            shutil.rmtree(str(target_path))
        else:
            target_path.unlink()

        return {
            "status": "ok",
            "path": str(target_path),
            "message": f"Deleted '{target_path.name}'",
        }
    except Exception as exc:
        return {"status": "error", "message": f"Failed to delete: {exc}"}


def get_system_status() -> dict:
    """Retrieve quick system status telemetry including CPU, RAM, disk space, and uptime.

    Returns:
        A dict with CPU, RAM, disk, and uptime metrics.
    """
    stats = {}

    # 1. Disk usage
    try:
        disk_res = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=3)
        stats["disk_root"] = disk_res.stdout.strip().split("\n")[-1]
    except Exception:
        stats["disk_root"] = "Unavailable"

    # 2. RAM usage
    try:
        mem_res = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=3)
        stats["memory"] = mem_res.stdout.strip()
    except Exception:
        stats["memory"] = "Unavailable"

    # 3. Uptime
    try:
        up_res = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=3)
        stats["uptime"] = up_res.stdout.strip()
    except Exception:
        stats["uptime"] = "Unavailable"

    # 4. CPU load
    try:
        with open("/proc/loadavg", "r") as f:
            stats["load_average"] = f.read().strip()
    except Exception:
        stats["load_average"] = "Unavailable"

    return {
        "status": "ok",
        "system": stats,
    }
