"""Loads settings from .env """
import os
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env", override=True)

# Provider Presets for Universal OpenAI-compatible API
PROVIDER_PRESETS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-3.5-flash-lite",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5-coder:7b",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
}

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
_preset = PROVIDER_PRESETS.get(LLM_PROVIDER, PROVIDER_PRESETS["gemini"])

LLM_BASE_URL = os.getenv("LLM_BASE_URL") or _preset["base_url"]
LLM_API_KEY = (
    os.getenv("LLM_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or ("ollama" if LLM_PROVIDER == "ollama" else "")
)
LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("GEMINI_MODEL") or _preset["default_model"]

# Dedicated Fallback Configuration (Gemini)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_BASE_URL = PROVIDER_PRESETS["gemini"]["base_url"]

TZ_NAME = os.getenv("TIMEZONE", "Asia/Kolkata")

# Either a TickTick personal API token / OAuth access token pasted here,
# or leave empty and run auth.py to create token.json.
TICKTICK_TOKEN = os.getenv("TICKTICK_TOKEN", "")
TICKTICK_CLIENT_ID = os.getenv("TICKTICK_CLIENT_ID", "")
TICKTICK_CLIENT_SECRET = os.getenv("TICKTICK_CLIENT_SECRET", "")
# Optional. Empty = tasks go to your Inbox.
TICKTICK_PROJECT_ID = os.getenv("TICKTICK_PROJECT_ID", "")

TOKEN_FILE = BASE / "token.json"
