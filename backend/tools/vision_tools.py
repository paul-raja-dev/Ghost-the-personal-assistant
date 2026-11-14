"""Ghost Vision & Screen Awareness Tools for Linux (kratos).
Enables Ghost to autonomously capture and inspect the user's screen via gnome-screenshot
and analyze local image files using Gemini Multimodal Vision.
"""
import base64
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import config
from openai import OpenAI


def capture_and_inspect_screen(focus_instruction: str = "") -> dict:
    """Capture a live screenshot of the user's desktop on kratos and analyze it using Gemini Vision.

    Use this tool whenever the user asks to look at their screen, check what is open, diagnose
    an error dialog, inspect visual UI, or review what they are currently working on.

    Args:
        focus_instruction: Optional specific instruction on what to look for (e.g. 'check terminal error',
                          'read the code in VSCode', 'what is in the browser').

    Returns:
        Structured visual observations detailing active windows, visible code/errors, and UI layout.
    """
    if not config.GEMINI_API_KEY:
        return {
            "status": "error",
            "message": "Missing GEMINI_API_KEY in configuration.",
        }

    temp_path = Path("/tmp/ghost_screen.png")
    img_bytes = b""

    try:
        # Capture screenshot via native gnome-screenshot on GNOME Wayland/X11
        proc = subprocess.run(
            ["gnome-screenshot", "-f", str(temp_path)],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if proc.returncode != 0 or not temp_path.exists():
            return {
                "status": "error",
                "message": f"Screen capture failed (code {proc.returncode}): {proc.stderr.strip() or 'Screenshot file not generated'}",
            }
        img_bytes = temp_path.read_bytes()
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": "Screen capture timed out after 8 seconds.",
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "message": "gnome-screenshot command not found on kratos.",
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to capture screen: {exc}",
        }
    finally:
        # Immediate ephemeral purge for privacy
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

    if not img_bytes:
        return {
            "status": "error",
            "message": "Captured screen image was empty.",
        }

    # Universal Vision analysis using Base64 Data URL (OpenAI standard)
    vision_instruction = (
        "You are Ghost's Vision System on the user's Linux machine 'kratos'.\n"
        "Analyze this live screen capture accurately. Provide a technical, structured summary with clean bullet points and ZERO EMOJIS:\n"
        "- Active Applications & Windows: List main apps open (e.g. VS Code, terminal, browser, system dialogs) and their window titles.\n"
        "- Visible Text, Code & Errors: Transcribe any critical error traces, terminal logs, code snippets, or UI messages visible on screen.\n"
        f"- Specific Focus: {focus_instruction or 'Identify what the user is working on and diagnose any visible issues or anomalies.'}\n"
        "Be precise and direct."
    )

    b64_image = base64.b64encode(img_bytes).decode("utf-8")
    vision_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": vision_instruction},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
            ],
        }
    ]

    # Try primary provider, fallback to Gemini
    providers_to_try = []
    if config.LLM_API_KEY:
        providers_to_try.append({
            "client": OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=25.0),
            "model": config.LLM_MODEL,
        })
    if config.GEMINI_API_KEY and (config.LLM_BASE_URL != config.GEMINI_BASE_URL or config.LLM_MODEL != config.GEMINI_MODEL):
        providers_to_try.append({
            "client": OpenAI(base_url=config.GEMINI_BASE_URL, api_key=config.GEMINI_API_KEY, timeout=25.0),
            "model": config.GEMINI_MODEL or "gemini-3.5-flash-lite",
        })

    last_exc = None
    for p in providers_to_try:
        try:
            resp = p["client"].chat.completions.create(
                model=p["model"],
                messages=vision_messages,
                temperature=0,
            )
            analysis = (resp.choices[0].message.content or "").strip()
            return {
                "status": "ok",
                "focus": focus_instruction or "general screen inspection",
                "visual_observations": analysis,
            }
        except Exception as exc:
            last_exc = exc
            continue

    return {
        "status": "error",
        "message": f"Vision analysis failed: {last_exc}",
    }


def inspect_image_file(image_path: str, instruction: str = "") -> dict:
    """Inspect and analyze any local image file on kratos using Vision.

    Args:
        image_path: Path to the image file (supports '~' expansion, e.g. '~/Desktop/screenshot.png').
        instruction: Optional query or instruction regarding the image.

    Returns:
        Structured visual analysis, OCR transcription, and answers to the query.
    """
    if not config.LLM_API_KEY and not config.GEMINI_API_KEY:
        return {
            "status": "error",
            "message": "Missing API key in configuration.",
        }

    clean_path = image_path.strip().strip("'\"")
    path_obj = Path(clean_path).expanduser().resolve()

    if not path_obj.exists() or not path_obj.is_file():
        return {
            "status": "error",
            "message": f"Image file not found: {clean_path}",
        }

    ext = path_obj.suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    mime = mime_types.get(ext)
    if not mime:
        return {
            "status": "error",
            "message": f"Unsupported image extension '{ext}'. Supported formats: png, jpg, jpeg, webp, gif, bmp.",
        }

    try:
        img_bytes = path_obj.read_bytes()
        if not img_bytes:
            return {"status": "error", "message": "Image file is empty (0 bytes)."}

        b64_image = base64.b64encode(img_bytes).decode("utf-8")
        vision_instruction = (
            "You are Ghost's Vision System on Linux machine 'kratos'.\n"
            f"Analyze this image file ('{path_obj.name}') in detail. Zero emojis.\n"
            f"Instruction: {instruction or 'Describe the image, extract any visible text/code, and summarize key elements.'}\n"
        )
        vision_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": vision_instruction},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64_image}"}},
                ],
            }
        ]

        providers_to_try = []
        if config.LLM_API_KEY:
            providers_to_try.append({
                "client": OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=25.0),
                "model": config.LLM_MODEL,
            })
        if config.GEMINI_API_KEY and (config.LLM_BASE_URL != config.GEMINI_BASE_URL or config.LLM_MODEL != config.GEMINI_MODEL):
            providers_to_try.append({
                "client": OpenAI(base_url=config.GEMINI_BASE_URL, api_key=config.GEMINI_API_KEY, timeout=25.0),
                "model": config.GEMINI_MODEL or "gemini-3.5-flash-lite",
            })

        last_exc = None
        for p in providers_to_try:
            try:
                resp = p["client"].chat.completions.create(
                    model=p["model"],
                    messages=vision_messages,
                    temperature=0,
                )
                return {
                    "status": "ok",
                    "file_name": path_obj.name,
                    "file_path": str(path_obj),
                    "analysis": (resp.choices[0].message.content or "").strip(),
                }
            except Exception as exc:
                last_exc = exc
                continue

        return {
            "status": "error",
            "message": f"Failed to analyze image file: {last_exc}",
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to read image file: {exc}",
        }
