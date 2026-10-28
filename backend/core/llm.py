"""Ghost LLM Engine with living memory injection and structured response envelope."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import config
from core import memory, session
import tools


def _system_prompt() -> str:
    now = datetime.now(ZoneInfo(config.TZ_NAME))
    memory_ctx = memory.get_system_prompt_context()

    return (
        "You are Ghost, an autonomous personal engineering assistant running live on the user's Linux desktop (Ubuntu 24.04, user home: /home/paul).\n"
        f"Current local date/time: {now.strftime('%A, %Y-%m-%d %H:%M')} ({config.TZ_NAME}).\n"
        f"{memory_ctx}\n"
        "STRICT DESIGN & BEHAVIOR RULES:\n"
        "1. ZERO EMOJIS: Never output emojis under any circumstances. Use clean text markers like '>', '[ok]', '[info]', '[error]' instead.\n"
        "2. CONVERSATIONAL & ENGAGING: You are an autonomous Linux assistant and intelligent companion. If the user chats casually, is bored, or asks open questions, respond naturally, concisely, and insightfully in 'line' display mode with your text in 'body'.\n"
        "3. AUTONOMOUS SYSTEM & FILE CONTROL: You have direct access to the live Linux filesystem and terminal.\n"
        "   - Use execute_command to run bash commands (e.g., git status, git diff, df -h, free -m, running scripts, inspecting processes).\n"
        "   - Use read_file to view files, code, or logs.\n"
        "   - Use write_file to create, update, or append files/scripts.\n"
        "   - Use list_directory and search_files to explore the filesystem.\n"
        "   - Use get_system_status to check live RAM, disk, CPU, and uptime.\n"
        "   - Resolve '~' to /home/paul automatically.\n"
        "4. CLEAN FORMATTING & CODE BLOCKS: When outputting command output, scripts, or file content, format them cleanly. Use markdown code blocks (```python, ```bash) or bulleted summaries. Avoid ugly walls of raw text.\n"
        "5. PERSONAL INFO (NO CARDS): When the user asks what you know about them or for their profile, DO NOT return cards or lists. Instead, output neat, clean, human-readable structured text in 'body' using display: 'line' grouped into sections with bullet points (Identity & Contact, Academics & Goals, Tech Stack & Projects).\n"
        "6. LIVING MEMORY: Whenever the user mentions personal info, preferences, projects, contacts, or habits, call save_memory to remember it silently.\n"
        "7. TASKS: For reminders and to-dos, call add_task. Resolve relative dates like 'tomorrow', 'next Friday', '5pm' using the current date/time above.\n"
        "8. RESPONSE ENVELOPE: Your final response MUST be a valid JSON object matching this schema:\n"
        "{\n"
        '  "display": "line" | "compose" | "confirm",\n'
        '  "title": "Optional short header",\n'
        '  "body": "Main concise message or formatted text",\n'
        '  "items": [],\n'
        '  "actions": [ {"id": "confirm", "label": "Confirm", "type": "primary"} ],\n'
        '  "auto_close": true | false\n'
        "}\n"
        "DISPLAY RULES:\n"
        "- 'line': Default for conversation, direct answers, command results, file views, and clean text reports. Set auto_close: false if multi-line or informational; true for 1-line confirmations.\n"
        "- 'compose': When the user asks to write/draft an email or document. Put the draft in 'body'. Set auto_close: false.\n"
        "- 'confirm': When an action requires user approval (e.g. deleting important files). Set auto_close: false.\n"
        "Output ONLY the JSON object. Do not wrap in markdown code blocks like ```json."
    )


def _clean_response(raw_text: str) -> str:
    """Ensure the returned string is a valid structured JSON envelope."""
    raw = (raw_text or "").strip()

    # Strip markdown code blocks if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

    # Try to parse as JSON
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            if "display" in data:
                return json.dumps(data, ensure_ascii=False)
            # If model returned a raw dict of categories (e.g. from list_all_memories tool)
            source_dict = data.get("categories") or data.get("memories") or data.get("data")
            if isinstance(source_dict, dict):
                section_map = {
                    "identity": "Identity & Contact:",
                    "preferences": "Preferences & Communication:",
                    "projects": "Tech Stack & Projects:",
                    "contacts": "Contact & Links:",
                    "workflows": "Workflows:",
                    "notes": "Notes:"
                }
                out_sections = []
                for cat, mems in source_dict.items():
                    if isinstance(mems, list) and mems:
                        header = section_map.get(cat, f"{cat.capitalize()}:")
                        bullets = []
                        for m in mems:
                            content = m.get("content", str(m)) if isinstance(m, dict) else str(m)
                            bullets.append(f"- {content}")
                        if bullets:
                            out_sections.append(f"{header}\n" + "\n".join(bullets))
                formatted_body = "\n\n".join(out_sections) if out_sections else "No saved memories found."
                return json.dumps({
                    "display": "line",
                    "title": "",
                    "body": formatted_body,
                    "items": [],
                    "actions": [],
                    "auto_close": False,
                }, ensure_ascii=False)
    except Exception:
        pass

    # Extract JSON object from within text if wrapped
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and "display" in data:
                return json.dumps(data, ensure_ascii=False)
        except Exception:
            pass

    # Fallback envelope
    fallback = {
        "display": "line",
        "title": "",
        "body": raw or "Done.",
        "items": [],
        "actions": [],
        "auto_close": True,
    }
    return json.dumps(fallback, ensure_ascii=False)


def run(prompt: str) -> str:
    clean_p = prompt.strip().lower()
    if clean_p in ["/clear", "clear", "reset", "/reset"]:
        session.clear_session()
        return json.dumps({
            "display": "line",
            "title": "",
            "body": "[ok] Session cleared.",
            "items": [],
            "actions": [],
            "auto_close": True,
        }, ensure_ascii=False)

    if not config.GEMINI_API_KEY:
        err = {
            "display": "line",
            "title": "Configuration Error",
            "body": "Missing GEMINI_API_KEY in .env",
            "items": [],
            "actions": [],
            "auto_close": False,
        }
        return json.dumps(err)

    candidate_models = []
    for m in [config.GEMINI_MODEL, "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-latest"]:
        if m and m not in candidate_models:
            candidate_models.append(m)

    client = genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=10_000),
    )

    history = session.get_genai_history()
    last_exc = None
    for model_name in candidate_models:
        try:
            chat = client.chats.create(
                model=model_name,
                history=history,
                config=types.GenerateContentConfig(
                    system_instruction=_system_prompt(),
                    tools=tools.TOOLS,
                    temperature=0,
                ),
            )
            resp = chat.send_message(prompt)
            final_json = _clean_response(resp.text)
            session.record_turn(prompt, final_json)
            return final_json
        except Exception as exc:
            last_exc = exc
            err_msg = str(exc)
            if "503" in err_msg or "404" in err_msg or "UNAVAILABLE" in err_msg or "DEADLINE" in err_msg:
                continue
            break

    err = {
        "display": "line",
        "title": "Execution Error",
        "body": f"Error: {last_exc}",
        "items": [],
        "actions": [],
        "auto_close": False,
    }
    return json.dumps(err)
