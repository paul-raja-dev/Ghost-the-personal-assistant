"""System and Live Filesystem Operations for Ghost with Safe Trash and Mandatory Confirmation."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

PENDING_ACTIONS_FILE = Path.home() / ".config" / "ghost" / "pending_actions.json"


def _resolve_path(path_str: str) -> Path:
    """Safely expand and resolve a path string."""
    expanded = os.path.expanduser(os.path.expandvars(path_str.strip()))
    return Path(expanded).resolve()


def _load_pending_actions() -> dict:
    if not PENDING_ACTIONS_FILE.exists():
        return {}
    try:
        return json.loads(PENDING_ACTIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_pending_actions(actions: dict):
    PENDING_ACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_ACTIONS_FILE.write_text(json.dumps(actions, indent=2, ensure_ascii=False), encoding="utf-8")


def _move_to_trash_bin(target_path: Path) -> bool:
    """Move a file or directory safely to Linux desktop Trash (never permanently delete)."""
    # 1. Try native Linux gio trash
    try:
        res = subprocess.run(["gio", "trash", str(target_path)], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    # 2. Fallback: Move directly to user's GNOME Trash directory
    try:
        trash_dir = Path.home() / ".local" / "share" / "Trash" / "files"
        trash_dir.mkdir(parents=True, exist_ok=True)
        destination = trash_dir / target_path.name
        if destination.exists():
            destination = trash_dir / f"{target_path.stem}_{int(datetime.now().timestamp())}{target_path.suffix}"
        shutil.move(str(target_path), str(destination))
        return True
    except Exception:
        return False


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

    lower_cmd = cmd.lower()

    # Guardrails against catastrophic root destruction
    destructive_patterns = [
        "rm -rf /", "rm -rf /*", "mkfs", ":(){ :|:& };:", "dd if=/dev/zero", "dd if=/dev/urandom"
    ]
    for pattern in destructive_patterns:
        if pattern in lower_cmd:
            return {"status": "error", "message": f"Execution blocked: Command matches destructive pattern '{pattern}'."}

    # Strict file deletion guardrails: Block direct rm / rmdir / unlink / shred in shell
    tokens = re.split(r"[;&|]\s*", lower_cmd)
    for tok in tokens:
        sub = tok.strip()
        if sub == "rm" or sub.startswith("rm ") or sub.startswith("rmdir") or sub.startswith("unlink ") or sub.startswith("shred "):
            return {
                "status": "error",
                "message": "Execution blocked: Direct file deletion via shell ('rm'/'rmdir'/'unlink'/'shred') is strictly prohibited. You must use the confirmed trash staging system instead.",
            }

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
        out = proc.stdout.strip()
        if len(out) > 4000:
            out = out[:3900] + "\n\n[... Output truncated at 4000 characters to prevent API rate limits. Use grep/head/tail if specific lines are needed ...]"

        err = proc.stderr.strip()
        if len(err) > 2000:
            err = err[:1900] + "\n\n[... Stderr truncated to prevent API rate limits ...]"

        return {
            "status": "ok" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": out,
            "stderr": err,
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
    try:
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


def stage_file_deletion(path: str, reason: str = "") -> dict:
    """Stage a file or directory for deletion to Trash. DOES NOT delete the file.
    Always requires explicit confirmation from the user before executing.

    Args:
        path: File or directory path the user wants to remove.
        reason: Optional user reason or explanation.

    Returns:
        A dict containing confirmation_required status, ticket_id, path, and display instructions.
    """
    target_path = _resolve_path(path)
    if not target_path.exists():
        return {"status": "error", "message": f"Target not found: {target_path}"}

    # Guardrails against deleting root or home root
    if str(target_path) in ["/", str(Path.home()), "/home"]:
        return {"status": "error", "message": "Deletion blocked: Cannot delete root or home directory."}

    ticket_id = f"trash_{uuid.uuid4().hex[:8]}"
    actions = _load_pending_actions()
    actions[ticket_id] = {
        "ticket_id": ticket_id,
        "path": str(target_path),
        "name": target_path.name,
        "is_dir": target_path.is_dir(),
        "reason": reason,
        "staged_at": datetime.now().isoformat(),
    }
    _save_pending_actions(actions)

    return {
        "status": "confirmation_required",
        "ticket_id": ticket_id,
        "path": str(target_path),
        "name": target_path.name,
        "is_directory": target_path.is_dir(),
        "message": f"Action staged: Moving '{target_path.name}' to Trash. YOU MUST NOT DELETE IT DIRECTLY. Return a JSON response with display: 'confirm' asking the user for explicit approval with ticket_id '{ticket_id}'.",
    }


def execute_confirmed_trash(ticket_id: str) -> dict:
    """Execute a confirmed deletion by moving the file safely to Linux desktop Trash (gio trash).
    Can only be called after explicit user confirmation of the ticket_id.

    Args:
        ticket_id: The confirmation ticket ID generated by stage_file_deletion.

    Returns:
        A dict with status, path, and recovery message.
    """
    actions = _load_pending_actions()
    ticket = actions.get(ticket_id)
    if not ticket:
        return {
            "status": "error",
            "message": f"No pending deletion ticket found with ID '{ticket_id}'. Staged action may have expired or already executed.",
        }

    target_path = Path(ticket["path"])
    if not target_path.exists():
        actions.pop(ticket_id, None)
        _save_pending_actions(actions)
        return {"status": "error", "message": f"Target no longer exists: {target_path}"}

    success = _move_to_trash_bin(target_path)
    if success:
        actions.pop(ticket_id, None)
        _save_pending_actions(actions)
        return {
            "status": "ok",
            "ticket_id": ticket_id,
            "path": str(target_path),
            "message": f"Moved '{target_path.name}' safely to Trash. Recoverable in ~/.local/share/Trash.",
        }
    else:
        return {"status": "error", "message": f"Failed to move '{target_path.name}' to Trash."}


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


def inspect_project(path: str) -> dict:
    """Perform a deep, high-speed (<30ms) inspection of a software project or repository.
    Extracts package manifests, tech stack, architecture documentation, git history, and directory layout.

    Args:
        path: Path to the project or repository directory (supports '~' expansion).

    Returns:
        A rich dict containing project name, detected tech stack, manifest summaries,
        architecture docs excerpts, git branch and recent commits, and directory structure.
    """
    root_path = _resolve_path(path)
    if not root_path.exists():
        return {"status": "error", "message": f"Path not found: {root_path}"}
    if not root_path.is_dir():
        return {"status": "error", "message": f"Path is not a directory: {root_path}"}

    info = {
        "status": "ok",
        "name": root_path.name,
        "path": str(root_path),
        "tech_stack": [],
        "manifests": {},
        "documentation": {},
        "git": {},
        "structure": {},
    }

    # 1. Directory Structure
    try:
        entries = list(os.scandir(root_path))
        dirs = [e.name for e in entries if e.is_dir() and not e.name.startswith(".")]
        files = [e.name for e in entries if e.is_file() and not e.name.startswith(".")]
        info["structure"] = {
            "directories": sorted(dirs),
            "files": sorted(files),
        }
    except Exception:
        pass

    # 2. Manifest & Tech Stack Detection
    # Rust / Tauri
    cargo_paths = [root_path / "src-tauri" / "Cargo.toml", root_path / "Cargo.toml"]
    for cp in cargo_paths:
        if cp.exists():
            try:
                content = cp.read_text(encoding="utf-8", errors="replace")
                info["tech_stack"].append("Rust / Cargo" if "src-tauri" not in str(cp) else "Tauri (Rust)")
                manifest_data = {}
                for line in content.splitlines()[:25]:
                    line_s = line.strip()
                    if line_s.startswith("name ="):
                        manifest_data["name"] = line_s.split("=", 1)[1].strip().strip('"')
                    elif line_s.startswith("description ="):
                        manifest_data["description"] = line_s.split("=", 1)[1].strip().strip('"')
                    elif line_s.startswith("version ="):
                        manifest_data["version"] = line_s.split("=", 1)[1].strip().strip('"')
                info["manifests"]["Cargo.toml"] = manifest_data
                break
            except Exception:
                pass

    # Node / JS / Electron
    pkg_json = root_path / "package.json"
    if pkg_json.exists():
        try:
            pj = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            is_electron = "electron" in pj.get("dependencies", {}) or "electron" in pj.get("devDependencies", {})
            info["tech_stack"].append("Electron" if is_electron else "Node.js")
            info["manifests"]["package.json"] = {
                "name": pj.get("name"),
                "version": pj.get("version"),
                "description": pj.get("description"),
                "main": pj.get("main"),
                "scripts": list(pj.get("scripts", {}).keys()),
            }
        except Exception:
            pass

    # Python
    pyproject = root_path / "pyproject.toml"
    reqs = root_path / "requirements.txt"
    if pyproject.exists() or reqs.exists() or (root_path / "setup.py").exists():
        info["tech_stack"].append("Python")
        if reqs.exists():
            try:
                lines = [l.strip() for l in reqs.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip() and not l.startswith("#")]
                info["manifests"]["requirements.txt"] = lines[:10]
            except Exception:
                pass

    # Go / C / C++ / Docker
    if (root_path / "go.mod").exists():
        info["tech_stack"].append("Go")
    if (root_path / "CMakeLists.txt").exists() or (root_path / "Makefile").exists():
        info["tech_stack"].append("C/C++ Build")
    if (root_path / "Dockerfile").exists() or (root_path / "docker-compose.yml").exists():
        info["tech_stack"].append("Docker")

    # 3. Documentation Discovery
    docs_dir = root_path / "docs"
    if docs_dir.exists() and docs_dir.is_dir():
        try:
            doc_files = [f.name for f in docs_dir.iterdir() if f.is_file() and f.suffix in [".md", ".txt", ".rst"]]
            info["documentation"]["docs_folder_files"] = sorted(doc_files)
            if doc_files:
                top_doc = docs_dir / sorted(doc_files)[0]
                lines = top_doc.read_text(encoding="utf-8", errors="replace").splitlines()[:25]
                info["documentation"]["primary_doc_excerpt"] = {
                    "filename": top_doc.name,
                    "excerpt": "\n".join(lines).strip(),
                }
        except Exception:
            pass

    readme = root_path / "README.md"
    if readme.exists():
        try:
            lines = readme.read_text(encoding="utf-8", errors="replace").splitlines()[:25]
            info["documentation"]["readme_excerpt"] = "\n".join(lines).strip()
        except Exception:
            pass

    # 4. Git Metadata & Recent Commit DNA
    git_dir = root_path / ".git"
    if git_dir.exists():
        try:
            c_proc = subprocess.run(
                ["git", "log", "-n", "5", "--oneline"],
                cwd=str(root_path),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if c_proc.returncode == 0:
                info["git"]["recent_commits"] = c_proc.stdout.strip().splitlines()

            b_proc = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(root_path),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if b_proc.returncode == 0:
                info["git"]["branch"] = b_proc.stdout.strip()

            r_proc = subprocess.run(
                ["git", "remote", "-v"],
                cwd=str(root_path),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if r_proc.returncode == 0:
                remotes = set()
                for line in r_proc.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        remotes.add(f"{parts[0]}: {parts[1]}")
                info["git"]["remotes"] = sorted(list(remotes))
        except Exception:
            pass

    return info
