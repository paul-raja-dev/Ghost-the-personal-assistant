"""Loads settings from .env """
import os
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env", override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Model names change often on the free tier. If you get a "model not found" error,
# open Google AI Studio, pick a current Flash model, and put its name in .env.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

TZ_NAME = os.getenv("TIMEZONE", "Asia/Kolkata")

# Either a TickTick personal API token / OAuth access token pasted here,
# or leave empty and run auth.py to create token.json.
TICKTICK_TOKEN = os.getenv("TICKTICK_TOKEN", "")
TICKTICK_CLIENT_ID = os.getenv("TICKTICK_CLIENT_ID", "")
TICKTICK_CLIENT_SECRET = os.getenv("TICKTICK_CLIENT_SECRET", "")
# Optional. Empty = tasks go to your Inbox.
TICKTICK_PROJECT_ID = os.getenv("TICKTICK_PROJECT_ID", "")

TOKEN_FILE = BASE / "token.json"
