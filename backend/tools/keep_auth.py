"""Google Keep Onboarding & Master Token Exchange Utility for Kratos.
Allows exchanging an oauth_token cookie from accounts.google.com/EmbeddedSetup
into a Google Master Token, saving it to .env, and creating the cached session.
"""
import json
import os
from pathlib import Path
import sys

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from tools import keep_tools


def setup_keep_token(oauth_token_cookie: str, email: str = ""):
    """Exchange browser oauth_token cookie for Master Token and cache session state."""
    try:
        import gpsoauth
        import gkeepapi
    except ImportError:
        print("[error] Required packages missing. Run: pip install gkeepapi gpsoauth")
        return False

    if not email:
        email = keep_tools.get_keep_email()

    cookie = oauth_token_cookie.strip()
    if not cookie:
        print("[error] No oauth_token provided.")
        return False

    print(f"[info] Exchanging token for Google account: {email}...")
    try:
        # A dummy android ID is accepted by Google's OAuth endpoint
        res = gpsoauth.exchange_token(email, cookie, "0123456789abcdef")
        if not res:
            print("[error] Token exchange failed: empty response from Google.")
            return False

        if isinstance(res, dict):
            if "Error" in res:
                print(f"[error] Token exchange failed: {res['Error']}")
                return False
            master_token = res.get("Token") or res.get("Auth")
        else:
            master_token = str(res)

        if not master_token or "Error=" in str(master_token):
            print(f"[error] Token exchange failed: {master_token}")
            return False

        print("[ok] Master token successfully obtained.")

        # Save to .env
        env_file = Path("/home/paul/Desktop/Ghost/.env")
        lines = []
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

        new_lines = [l for l in lines if not l.strip().startswith("GOOGLE_KEEP_MASTER_TOKEN=")]
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f'GOOGLE_KEEP_MASTER_TOKEN="{master_token}"\n')

        with open(env_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print("[ok] GOOGLE_KEEP_MASTER_TOKEN saved to .env")

        # Set environment variable for current process
        os.environ["GOOGLE_KEEP_MASTER_TOKEN"] = master_token

        # Initial keep sync and session state cache
        print("[info] Performing initial Google Keep sync...")
        keep = gkeepapi.Keep()
        keep.authenticate(email, master_token)

        keep_tools._ensure_config_dir()
        with open(keep_tools.KEEP_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(keep.dump(), f)

        note_count = len(list(keep.all()))
        print(f"[ok] Connected to Google Keep! Synced {note_count} existing notes to kratos.")
        return True
    except Exception as exc:
        print(f"[error] Failed during setup: {exc}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        token_input = sys.argv[1]
    else:
        print("=== Google Keep Onboarding for Kratos ===")
        print("1. Open browser: https://accounts.google.com/EmbeddedSetup")
        print("2. Sign in with your work email (paulraja.creator@gmail.com)")
        print("3. Press F12 -> Application/Storage -> Cookies -> accounts.google.com")
        print("4. Copy the value of cookie 'oauth_token' (starts with oauth2_4/)")
        print("=========================================")
        token_input = input("Paste oauth_token here: ").strip()

    setup_keep_token(token_input)
