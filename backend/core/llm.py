"""Ghost LLM Engine with living memory injection and structured response envelope."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAI

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import config
from core import memory, session
import tools
from tools import schemas


def _system_prompt() -> str:
    now = datetime.now(ZoneInfo(config.TZ_NAME))
    memory_ctx = memory.get_system_prompt_context()

    return (
        "You are Ghost, an autonomous personal engineering assistant running live on the user's Linux machine named 'kratos' (Ubuntu 24.04, user home: /home/paul). Always refer to this system as kratos, never generic 'Ubuntu system'.\n"
        f"Current local date/time: {now.strftime('%A, %Y-%m-%d %H:%M')} ({config.TZ_NAME}).\n"
        f"{memory_ctx}\n"
        "STRICT DESIGN & BEHAVIOR RULES:\n"
        "1. ZERO EMOJIS: Never output emojis under any circumstances. Use clean text markers like '>', '[ok]', '[info]', '[error]' instead.\n"
        "2. CONVERSATIONAL & ENGAGING: You are an autonomous Linux assistant and intelligent companion. If the user chats casually, is bored, or asks open questions, respond naturally, concisely, and insightfully in 'line' display mode with your text in 'body'.\n"
        "3. AUTONOMOUS SYSTEM & FILE CONTROL: You have direct access to the live Linux filesystem, GitHub, and terminal.\n"
        "   - Use capture_and_inspect_screen to take a live screenshot and analyze what is visible on the user's screen on kratos.\n"
        "   - Use inspect_image_file to inspect and analyze local images, diagrams, or screenshots.\n"
        "   - Use investigate_github_discussion to deeply inspect PR discussions, reviews, maintainer feedback, and community debate.\n"
        "   - Use execute_command to run bash commands (e.g., git status, git diff, df -h, free -m, running scripts, inspecting processes).\n"
        "   - Use read_file to view files, code, or logs.\n"
        "   - Use write_file to create, update, or append files/scripts.\n"
        "   - Use list_directory and search_files to explore the filesystem.\n"
        "   - Use inspect_project to deeply inspect any project or repository in one fast (<30ms) pass.\n"
        "   - Use get_system_status to check live RAM, disk, CPU, and uptime.\n"
        "   - Resolve '~' to /home/paul automatically.\n"
        "4. MANDATORY FILE DELETION CONFIRMATION: You CANNOT delete or trash files directly. Permanent deletion (unlink/rmtree/rm) is STRICTLY PROHIBITED.\n"
        "   - When the user asks to delete or remove a file or directory, you MUST call stage_file_deletion(path).\n"
        "   - After calling stage_file_deletion, you MUST return a response with display: 'confirm':\n"
        "     {\n"
        '       "display": "confirm",\n'
        '       "title": "Confirm Move to Trash",\n'
        '       "body": "Are you sure you want to move <path> to Trash? (ticket: <ticket_id>)",\n'
        '       "items": [],\n'
        '       "actions": [ {"id": "confirm", "label": "Move to Trash", "type": "danger", "payload": "confirm: trash <ticket_id>"} ],\n'
        '       "auto_close": false\n'
        "     }\n"
        "   - STRICT INFORMATIONAL INQUIRIES: If the user asks 'how about X', 'what about Y', 'check Z', or asks about file sizes/storage, DO NOT stage or delete anything! Treat it strictly as an informational query: inspect the file, check its size with read_file/list_directory/execute_command, or explain what it is. NEVER call stage_file_deletion unless the user explicitly uses the words 'delete', 'remove', or 'trash'.\n"
        "5. DEEP CODEBASE & PROJECT INSPECTION (NO VAGUE GUESSING):\n"
        "   - When asked to inspect, analyze, explore, or compare projects, folders, or codebases, ALWAYS call inspect_project(path).\n"
        "   - CONTEXTUAL REPO AWARENESS: When the user asks about names that match folders on their desktop (e.g. 'ghost and Ghost', 'zulip', 'gatekeeper', 'AssetFlow'), check their local projects first using inspect_project rather than talking about generic third-party internet software.\n"
        "   - NEVER make vague generalizations or guess what a codebase does based on directory names or boilerplate template READMEs.\n"
        "   - Deliver concrete, evidence-based technical facts on the VERY FIRST TURN: cite exact framework & language (e.g. Tauri v2 + Rust 2021 + WebKitGTK vs Electron + Python 3.12), real project descriptions from Cargo.toml/package.json, architecture documentation from docs/, and recent git commit messages.\n"
        "   - SPEED & DEPTH: inspect_project gathers all manifests, docs, and git logs in one pass so you can provide deep, accurate analysis in a single sub-2-second turn.\n"
        "6. INVESTIGATIVE DISCUSSION PARTNER & PR INTELLIGENCE (NO PREMATURE CODE RUSH):\n"
        "   - When the user asks about PRs, issues, code reviews, maintainer feedback, or open source contributions (e.g. Zulip, GitHub repos), DO NOT rush to write code or modify files!\n"
        "   - Always use investigate_github_discussion to thoroughly inspect the actual PR comments, review statuses, and community threads first.\n"
        "   - Deliver DEEP SYNTHESIS: extract maintainers' exact stances (e.g. chrisbobbe, pratik-pc, emilysutherlin), highlight requirements (e.g. API changes requiring discussion in #api design on CZO, mobile screenshots, test guidelines), and analyze architectural trade-offs.\n"
        "   - Act as an investigative partner: discuss the problem with the user, brainstorm solutions, draft responses or discussion posts for the user to send on GitHub or chat.zulip.org, and align on decisions.\n"
        "   - DO NOT modify or rewrite local code unless the user explicitly tells you that the discussion has concluded and instructs you to proceed with coding.\n"
        "7. VISION & SCREEN AWARENESS (LIVE DESKTOP EYES ON KRATOS):\n"
        "   - When the user asks 'look at my screen', 'what is on my screen', 'check my display', 'what error is showing', 'what am I looking at', or refers to an open window or visual bug, YOU MUST AUTONOMOUSLY CALL capture_and_inspect_screen(focus_instruction).\n"
        "   - When the user mentions an image file or screenshot path (e.g. 'check the screenshot on my desktop', 'inspect image.png'), CALL inspect_image_file(image_path, instruction).\n"
        "   - Use the visual facts returned (open windows, terminal errors, visible code, browser views) to immediately diagnose issues, explain errors, and advise the user directly.\n"
        "8. CLEAN FORMATTING & CODE BLOCKS: When outputting command output, scripts, or file content, format them cleanly. Use markdown code blocks (```python, ```bash) or bulleted summaries. Avoid ugly walls of raw text.\n"
        "9. PERSONAL INFO (NO CARDS): When the user asks what you know about them or for their profile, DO NOT return cards or lists. Instead, output neat, clean, human-readable structured text in 'body' using display: 'line' grouped into sections with bullet points (Identity & Contact, Academics & Goals, Tech Stack & Projects).\n"
        "10. LIVING MEMORY: Whenever the user mentions personal info, preferences, projects, contacts, or habits, call save_memory to remember it silently.\n"
        "11. TASKS: For reminders and to-dos, call add_task. Resolve relative dates like 'tomorrow', 'next Friday', '5pm' using the current date/time above.\n"
        "12. RESPONSE ENVELOPE: Your final response MUST be a valid JSON object matching this schema:\n"
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
        "- 'confirm': When an action requires user approval (e.g. moving files to Trash). Set auto_close: false.\n"
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

    def _unwrap_json(candidate):
        """Recursively unwrap stringified or unicode-escaped JSON."""
        if isinstance(candidate, str):
            candidate = candidate.strip()
            try:
                parsed = json.loads(candidate)
                return _unwrap_json(parsed)
            except Exception:
                if "\\\"" in candidate or "\\n" in candidate:
                    try:
                        parsed = json.loads(candidate.encode().decode("unicode_escape"))
                        return _unwrap_json(parsed)
                    except Exception:
                        pass
                return candidate
        return candidate

    # Try direct parse
    try:
        data = _unwrap_json(raw)
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
            data = _unwrap_json(match.group(0))
            if isinstance(data, dict) and "display" in data:
                return json.dumps(data, ensure_ascii=False)
        except Exception:
            pass

    # Fallback envelope: unwrap if fallback_body itself is stringified JSON
    fallback_body = raw or "Done."
    try:
        data = _unwrap_json(fallback_body)
        if isinstance(data, dict) and "display" in data:
            return json.dumps(data, ensure_ascii=False)
    except Exception:
        pass

    fallback = {
        "display": "line",
        "title": "",
        "body": fallback_body,
        "items": [],
        "actions": [],
        "auto_close": True,
    }
    return json.dumps(fallback, ensure_ascii=False)


def run(prompt: str) -> str:
    clean_p = prompt.strip()
    lower_p = clean_p.lower()

    if lower_p in ["/clear", "clear", "reset", "/reset"]:
        session.clear_session()
        return json.dumps({
            "display": "line",
            "title": "",
            "body": "[ok] Session cleared.",
            "items": [],
            "actions": [],
            "auto_close": True,
        }, ensure_ascii=False)

    # Intercept confirmed trash actions directly
    if lower_p.startswith("confirm: trash "):
        ticket_id = clean_p[len("confirm: trash "):].strip()
        from tools import system_tools
        res = system_tools.execute_confirmed_trash(ticket_id)
        if res.get("status") == "ok":
            return json.dumps({
                "display": "line",
                "title": "Moved to Trash",
                "body": f"[ok] {res.get('message')}",
                "items": [],
                "actions": [],
                "auto_close": False,
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "display": "line",
                "title": "Trash Notice",
                "body": f"[error] {res.get('message')}",
                "items": [],
                "actions": [],
                "auto_close": False,
            }, ensure_ascii=False)

    if not config.LLM_API_KEY and not config.GEMINI_API_KEY:
        err = {
            "display": "line",
            "title": "Configuration Error",
            "body": "Missing API key (GEMINI_API_KEY or LLM_API_KEY) in .env",
            "items": [],
            "actions": [],
            "auto_close": False,
        }
        return json.dumps(err)

    # Build standard OpenAI messages list
    messages = [{"role": "system", "content": _system_prompt()}]
    summary = session.get_session_summary()
    if summary:
        messages.append({
            "role": "user",
            "content": f"[Context Summary of earlier conversation turns:\n{summary}]",
        })
        messages.append({
            "role": "assistant",
            "content": "[ok] Context acknowledged. I have full context of our earlier discussion.",
        })

    for turn in session.load_session():
        role = "assistant" if turn.get("role") == "model" else turn.get("role", "user")
        text = turn.get("text", "")
        if text:
            messages.append({"role": role, "content": text})

    messages.append({"role": "user", "content": prompt})

    openai_tools = schemas.get_openai_tools()

    # Configure provider candidates (primary configured provider + Gemini fallback)
    providers_to_try = []

    # 1. Primary provider
    if config.LLM_API_KEY:
        providers_to_try.append({
            "name": config.LLM_PROVIDER,
            "client": OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=25.0),
            "model": config.LLM_MODEL,
        })

    # 2. Seamless Gemini Fallback if primary is a different provider
    if config.GEMINI_API_KEY:
        is_already_primary = (
            config.LLM_BASE_URL == config.GEMINI_BASE_URL
            and config.LLM_MODEL == config.GEMINI_MODEL
        )
        if not is_already_primary:
            providers_to_try.append({
                "name": "gemini-fallback",
                "client": OpenAI(base_url=config.GEMINI_BASE_URL, api_key=config.GEMINI_API_KEY, timeout=25.0),
                "model": config.GEMINI_MODEL or "gemini-3.5-flash-lite",
            })

    last_exc = None
    for p_cfg in providers_to_try:
        try:
            curr_messages = list(messages)
            client = p_cfg["client"]
            model_name = p_cfg["model"]

            # Tool execution loop (up to 10 iterations)
            for _ in range(10):
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=curr_messages,
                    tools=openai_tools,
                    temperature=0,
                )
                choice = resp.choices[0]
                msg = choice.message

                # If no tool calls, return final response
                if not msg.tool_calls:
                    final_json = _clean_response(msg.content or "")
                    session.record_turn(prompt, final_json)
                    return final_json

                # Execute requested tools locally on kratos
                curr_messages.append(msg)
                for tc in msg.tool_calls:
                    res_data = schemas.dispatch_tool_call(tc.function.name, tc.function.arguments)
                    curr_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(res_data, ensure_ascii=False),
                    })

        except Exception as exc:
            last_exc = exc
            err_msg = str(exc)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                return json.dumps({
                    "display": "line",
                    "title": "Rate Limit Notice",
                    "body": "[error] Free Tier API quota / rate limit reached. Please wait a moment before sending your next request.",
                    "items": [],
                    "actions": [],
                    "auto_close": False,
                }, ensure_ascii=False)
            continue

    err = {
        "display": "line",
        "title": "Execution Error",
        "body": f"Error: {last_exc}",
        "items": [],
        "actions": [],
        "auto_close": False,
    }
    return json.dumps(err)
