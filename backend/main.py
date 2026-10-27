"""Entry point for Ghost backend logic."""
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core import llm


def run_prompt(prompt: str) -> str:
    return llm.run(prompt)


def main() -> None:
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        result = run_prompt(prompt)
        print(result)
    else:
        print("Error: No prompt provided to Ghost backend.")


if __name__ == "__main__":
    main()
