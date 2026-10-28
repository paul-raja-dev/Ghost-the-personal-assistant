"""Entry point for Ghost backend logic."""
import json
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core import llm, session


def run_prompt(prompt: str) -> str:
    return llm.run(prompt)


def main() -> None:
    if len(sys.argv) > 1:
        first_arg = sys.argv[1].strip()

        if first_arg == "--list-sessions":
            sessions = session.list_sessions()
            print(json.dumps(sessions, ensure_ascii=False))
            return

        if first_arg == "--load-session" and len(sys.argv) > 2:
            sess_id = sys.argv[2].strip()
            loaded = session.load_session_by_id(sess_id)
            print(json.dumps(loaded or {}, ensure_ascii=False))
            return

        if first_arg == "--delete-session" and len(sys.argv) > 2:
            sess_id = sys.argv[2].strip()
            ok = session.delete_session(sess_id)
            print(json.dumps({"success": ok}, ensure_ascii=False))
            return

        prompt = " ".join(sys.argv[1:])
        result = run_prompt(prompt)
        print(result)
    else:
        print("Error: No prompt provided to Ghost backend.")


if __name__ == "__main__":
    main()
