"""Safety Guardrails & Command Classifier for Ghost.
Enforces the 3-tier safety valve for all system actions.
"""
import re

BLOCKED_PATTERNS = [
    r"\bsudo\b",
    r"\bsu\b",
    r"\bpkill\b",
    r"\bkill\s+-9\b",
    r"\bpasswd\b",
    r"\b(dd|mkfs|fdisk|parted)\b",
    r"\b(iptables|ufw|nftables)\b",
    r"\b(systemctl|service)\b",
    r"/(etc|boot|sys|proc|dev)/",
    r"\brm\s+-[rf]*\s+/(?:\s|$)",  # rm -rf /
]

CONFIRM_PATTERNS = [
    r"\brm\b",
    r"\bmv\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\b(pip|npm|yarn|cargo)\s+install\b",
    r">\s*[^>]+",  # file overwrite redirection
]


def classify_shell_command(command: str) -> dict:
    """Classify a shell command into one of 3 safety tiers:
    - blocked: strictly forbidden, never runs
    - confirm: requires explicit user confirmation
    - safe: read-only or harmless, runs immediately
    """
    cmd = command.strip()

    # Check Tier 1: Blocked
    for pat in BLOCKED_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return {
                "tier": "blocked",
                "reason": f"Command matches restricted pattern: {pat}",
            }

    # Check Tier 2: Confirmation required
    for pat in CONFIRM_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return {
                "tier": "confirm",
                "reason": "Operation modifies or removes files/packages and requires confirmation.",
            }

    # Tier 3: Safe
    return {
        "tier": "safe",
        "reason": "Read-only or non-destructive command.",
    }
