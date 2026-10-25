# Ghost

Minimal AI personal assistant command palette.

Hotkey -> Modern Spotlight Command Palette -> Gemini decides -> Task lands in TickTick (or other tools).

---

## Architecture

- **`ui/`**: Electron frontend matching the command palette design (HTML/CSS/JS).
- **`backend/`**: 100% Python AI logic (`llm.py`, `tools.py`, `ticktick.py`).

```
Ghost/
├── ui/                 # Frontend: Electron window, styles, HTML
├── backend/            # Backend: Python tools & LLM logic
│   ├── tools.py        # <--- Add all your custom tools here!
│   ├── llm.py          # Gemini AI runner
│   └── ticktick.py     # TickTick integration
├── run.sh              # Hotkey launcher
└── .env                # API keys and settings
```

---

## Setup (Ubuntu)

```bash
cd Ghost
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
chmod +x run.sh
cp .env.example .env     # then edit .env with your keys
```

### 1. Launching Ghost
- Run `./run.sh` or `npm start` to open the command palette.
- Press `Enter` to create a task, or `Esc` to close.

### 2. Hotkey Shortcut
Go to **Settings -> Keyboard -> Keyboard Shortcuts -> Custom Shortcuts -> Add**:
- **Name**: `Ghost`
- **Command**: `/full/path/to/Ghost/run.sh`
- **Shortcut**: `Super+Space` or `Super+G`

---

## Adding More Tools

Gemini never sees your function body. It only sees the **name**, the **type-hinted signature**, and the **docstring**. The docstring is effectively the prompt for the tool, so write it for the model, not for humans.

### Steps
1. Write a plain Python function in `backend/tools.py`.
2. Add it to `TOOLS`. The SDK runs the call loop automatically.

### Rules
- **Name**: verb-first and specific (`add_task`, `check_unread_emails`). The model uses it to decide *when* to call.
- **Type hints on every param**: they become the schema. Stick to `str`, `int`, `float`, `bool`, `list[str]`. No custom classes.
- **Defaults = optional**: a param with no default is required, so the model must supply it. Use `""` as the "not given" sentinel.
- **Docstring, first line**: what the tool does and when to use it.
- **`Args:` block**: for every param, give the exact format and allowed values, plus an example. This is where the model learns `"YYYY-MM-DDTHH:MM"` or `"none" | "low" | "medium" | "high"`. Vague args produce malformed calls.
- **Constraints between params**: state them (e.g. "a repeating task must also have a due date").
- **Return a dict** with `status` (`"ok"` / `"error"`) and a `message`. Never raise; return the error so the model can explain it to the user.
- **Validate inputs yourself**: the model can still send bad values. Return a descriptive error and the model will usually retry with a corrected call.

### Example
```python
def add_task(
    title: str,
    due: str = "",
    priority: str = "none",
) -> dict:
    """Create a task or reminder in TickTick.

    Args:
        title: Short task title, e.g. "Call the vendor".
        due: "YYYY-MM-DDTHH:MM" (24h) if a time is given, "YYYY-MM-DD" if only
            a day is given, empty string if no date was mentioned.
        priority: One of "none", "low", "medium", "high".

    Returns:
        A dict with status "ok" or "error" and a message.
    """
    ...

TOOLS = [add_task]
```
