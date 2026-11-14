"""Ghost Multi-Account Email Tools for Kratos.
Supports IMAP inbox inspection and SMTP email sending across multiple accounts
(e.g. personal and professional/work) using secure Gmail App Passwords.
"""
import email
from email.header import decode_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime, formatdate
import imaplib
import json
import os
from pathlib import Path
import re
import smtplib
import time
from typing import Any, Dict, List, Optional
import uuid

# Configuration path for email accounts
CONFIG_DIR = Path.home() / ".config" / "ghost"
ACCOUNTS_FILE = CONFIG_DIR / "email_accounts.json"
PENDING_TICKETS_FILE = CONFIG_DIR / "pending_email_tickets.json"

# In-memory ticket storage for email staging
_pending_emails: Dict[str, Dict[str, Any]] = {}

DEFAULT_ACCOUNTS_CONFIG = {
    "accounts": {
        "personal": {
            "display_name": "Personal",
            "email": "paulraja.creator@gmail.com",
            "provider": "gmail_imap",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 465,
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "username": "paulraja.creator@gmail.com",
            "secret_env_var": "GMAIL_PERSONAL_APP_PASSWORD",
        },
        "work": {
            "display_name": "Professional",
            "email": "paul.work@example.com",
            "provider": "gmail_imap",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 465,
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "username": "paul.work@example.com",
            "secret_env_var": "GMAIL_WORK_APP_PASSWORD",
        },
    },
    "default_account": "personal",
}


def _ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_email_accounts() -> Dict[str, Any]:
    """Load email accounts from configuration file, creating default if missing."""
    _ensure_config_dir()
    if not ACCOUNTS_FILE.exists():
        try:
            with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_ACCOUNTS_CONFIG, f, indent=2)
            return DEFAULT_ACCOUNTS_CONFIG
        except Exception:
            return DEFAULT_ACCOUNTS_CONFIG

    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "accounts" not in data:
                return DEFAULT_ACCOUNTS_CONFIG
            return data
    except Exception:
        return DEFAULT_ACCOUNTS_CONFIG


def save_email_accounts(config_data: Dict[str, Any]) -> bool:
    """Save email accounts configuration."""
    _ensure_config_dir()
    try:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception:
        return False


def _resolve_account_key(account_str: str, config_data: Dict[str, Any]) -> Optional[str]:
    """Resolve an account key or alias to an actual configured account identifier."""
    if not account_str:
        return config_data.get("default_account", "personal")

    key = account_str.strip().lower()
    accounts = config_data.get("accounts", {})

    if key in accounts:
        return key

    # Smart alias matching
    if key in ("personal", "p", "me", "private"):
        if "personal" in accounts:
            return "personal"
    if key in ("work", "pro", "professional", "office", "job", "career"):
        if "work" in accounts:
            return "work"
        for k in accounts:
            if "work" in k or "pro" in k:
                return k

    # Check display name matches
    for k, v in accounts.items():
        disp = v.get("display_name", "").lower()
        email_addr = v.get("email", "").lower()
        if key in disp or key in email_addr:
            return k

    return None


def _get_account_password(account_info: Dict[str, Any]) -> Optional[str]:
    """Retrieve account password from environment variable."""
    env_var = account_info.get("secret_env_var", "")
    if not env_var:
        return None
    # Check os.environ
    pw = os.getenv(env_var)
    if pw:
        return pw.strip().replace(" ", "")  # App passwords often have spaces

    # Check .env directly if not loaded in os.environ
    env_file = Path("/home/paul/Desktop/Ghost/.env")
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{env_var}="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        return val.replace(" ", "")
        except Exception:
            pass
    return None


def _decode_mime_header(header_value: Optional[str]) -> str:
    """Safely decode RFC2047 MIME encoded headers."""
    if not header_value:
        return ""
    try:
        decoded_slices = decode_header(header_value)
        out = []
        for content, encoding in decoded_slices:
            if isinstance(content, bytes):
                encoding = encoding or "utf-8"
                try:
                    out.append(content.decode(encoding, errors="replace"))
                except Exception:
                    out.append(content.decode("latin1", errors="replace"))
            else:
                out.append(str(content))
        return "".join(out).strip()
    except Exception:
        return str(header_value).strip()


def _strip_html(html_text: str) -> str:
    """Convert HTML content to plain readable text snippet."""
    if not html_text:
        return ""
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_body_and_snippet(msg: email.message.Message) -> (str, str):
    """Extract plain text body and clean 1-line snippet from MIME message."""
    plain_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get("Content-Disposition", ""))
            if "attachment" in cdispo:
                continue

            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded_text = payload.decode(charset, errors="replace")

                if ctype == "text/plain" and not plain_body:
                    plain_body = decoded_text
                elif ctype == "text/html" and not html_body:
                    html_body = decoded_text
            except Exception:
                continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                plain_body = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    html_body = plain_body
                    plain_body = ""
        except Exception:
            pass

    final_body = plain_body if plain_body else _strip_html(html_body)
    cleaned_body = re.sub(r"\r\n", "\n", final_body).strip()

    # Create 1-line snippet
    first_few_lines = [line.strip() for line in cleaned_body.split("\n") if line.strip() and not line.strip().startswith(">")]
    snippet_candidate = " ".join(first_few_lines)
    snippet = re.sub(r"\s+", " ", snippet_candidate)[:140]

    return cleaned_body, snippet


def list_inbox(account: str = "all", limit: int = 5, unread_only: bool = True) -> Dict[str, Any]:
    """Fetch and list recent emails from personal, work, or all configured accounts on kratos.

    Args:
        account: Account identifier ('personal', 'work', 'all', or account name). Defaults to 'all'.
        limit: Maximum number of emails to retrieve per account (default 5).
        unread_only: If True, only fetches unread emails; if False, fetches latest emails.
    """
    config_data = load_email_accounts()
    accounts = config_data.get("accounts", {})

    target_keys = []
    if account.lower() == "all":
        target_keys = list(accounts.keys())
    else:
        resolved = _resolve_account_key(account, config_data)
        if not resolved:
            return {
                "status": "error",
                "message": f"Account '{account}' not found. Configured accounts: {', '.join(accounts.keys())}",
                "emails": [],
            }
        target_keys = [resolved]

    all_emails: List[Dict[str, Any]] = []
    account_statuses = {}

    for acc_key in target_keys:
        acc_info = accounts[acc_key]
        display_name = acc_info.get("display_name", acc_key.capitalize())
        imap_host = acc_info.get("imap_host", "imap.gmail.com")
        imap_port = int(acc_info.get("imap_port", 993))
        username = acc_info.get("username", acc_info.get("email", ""))
        password = _get_account_password(acc_info)
        secret_var = acc_info.get("secret_env_var", "")

        if not password:
            account_statuses[acc_key] = f"Credentials not found (Missing {secret_var} in .env)"
            continue

        try:
            # Connect via IMAP SSL
            mail = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=12)
            mail.login(username, password)
            mail.select("INBOX", readonly=True)

            search_criterion = "UNSEEN" if unread_only else "ALL"
            res_code, data = mail.search(None, search_criterion)

            if res_code != "OK":
                mail.logout()
                account_statuses[acc_key] = f"IMAP search error: {res_code}"
                continue

            msg_ids = data[0].split()
            # If unread_only was requested but no unread messages exist, fall back to ALL if limit allows
            if not msg_ids and unread_only:
                account_statuses[acc_key] = "Inbox clean (0 unread emails)"
                mail.logout()
                continue

            # Fetch the newest 'limit' messages
            selected_ids = msg_ids[-limit:]
            selected_ids.reverse()  # Newest first

            for msg_id in selected_ids:
                fetch_status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if fetch_status != "OK" or not msg_data:
                    continue

                raw_email = None
                for part in msg_data:
                    if isinstance(part, tuple) and len(part) > 1:
                        raw_email = part[1]
                        break

                if not raw_email:
                    continue

                msg = email.message_from_bytes(raw_email)
                subject = _decode_mime_header(msg.get("Subject", "(No Subject)"))
                sender = _decode_mime_header(msg.get("From", "Unknown"))
                date_str = msg.get("Date", "")
                formatted_date = date_str
                try:
                    dt = parsedate_to_datetime(date_str)
                    formatted_date = dt.strftime("%b %d, %I:%M %p")
                except Exception:
                    pass

                _, snippet = _extract_body_and_snippet(msg)

                all_emails.append({
                    "id": msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id),
                    "account": acc_key,
                    "account_name": display_name,
                    "from": sender,
                    "subject": subject,
                    "date": formatted_date,
                    "snippet": snippet or "(Empty preview)",
                    "unread": bool(unread_only),
                })

            account_statuses[acc_key] = f"Retrieved {len(selected_ids)} emails"
            try:
                mail.close()
            except Exception:
                pass
            mail.logout()

        except Exception as e:
            account_statuses[acc_key] = f"Connection error: {str(e)}"

    return {
        "status": "ok",
        "account_statuses": account_statuses,
        "count": len(all_emails),
        "emails": all_emails,
    }


def read_email_details(account: str, email_id: str) -> Dict[str, Any]:
    """Retrieve full email body and metadata for a specific email message.

    Args:
        account: Account identifier ('personal', 'work', or configured name).
        email_id: ID of the email message to retrieve.
    """
    config_data = load_email_accounts()
    resolved_key = _resolve_account_key(account, config_data)
    if not resolved_key:
        return {"status": "error", "message": f"Account '{account}' not recognized."}

    acc_info = config_data["accounts"][resolved_key]
    imap_host = acc_info.get("imap_host", "imap.gmail.com")
    imap_port = int(acc_info.get("imap_port", 993))
    username = acc_info.get("username", acc_info.get("email", ""))
    password = _get_account_password(acc_info)

    if not password:
        return {"status": "error", "message": f"Missing password for account '{resolved_key}' in .env."}

    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=15)
        mail.login(username, password)
        mail.select("INBOX", readonly=True)

        res_code, msg_data = mail.fetch(str(email_id).encode("utf-8"), "(RFC822)")
        if res_code != "OK" or not msg_data:
            mail.logout()
            return {"status": "error", "message": f"Failed to fetch email ID {email_id}."}

        raw_email = None
        for part in msg_data:
            if isinstance(part, tuple) and len(part) > 1:
                raw_email = part[1]
                break

        if not raw_email:
            mail.logout()
            return {"status": "error", "message": "Email payload empty or unreadable."}

        msg = email.message_from_bytes(raw_email)
        subject = _decode_mime_header(msg.get("Subject", "(No Subject)"))
        sender = _decode_mime_header(msg.get("From", "Unknown"))
        recipient = _decode_mime_header(msg.get("To", ""))
        date_str = msg.get("Date", "")
        formatted_date = date_str
        try:
            dt = parsedate_to_datetime(date_str)
            formatted_date = dt.strftime("%A, %b %d, %Y at %I:%M %p")
        except Exception:
            pass

        body, snippet = _extract_body_and_snippet(msg)

        try:
            mail.close()
        except Exception:
            pass
        mail.logout()

        return {
            "status": "ok",
            "account": resolved_key,
            "account_name": acc_info.get("display_name", resolved_key.capitalize()),
            "id": email_id,
            "from": sender,
            "to": recipient,
            "subject": subject,
            "date": formatted_date,
            "snippet": snippet,
            "body": body,
        }
    except Exception as e:
        return {"status": "error", "message": f"Error reading email: {str(e)}"}


def stage_email_send(account: str, to: str, subject: str, body: str) -> Dict[str, Any]:
    """Prepare and stage an email draft for sending, generating a safety confirmation ticket.
    Ghost NEVER sends an email without explicit user verification.

    Args:
        account: Account identifier ('personal' or 'work').
        to: Destination email address.
        subject: Email subject line.
        body: Text content of the email.
    """
    config_data = load_email_accounts()
    resolved_key = _resolve_account_key(account, config_data) or config_data.get("default_account", "personal")
    acc_info = config_data.get("accounts", {}).get(resolved_key, {})

    ticket_id = f"email_{uuid.uuid4().hex[:8]}"

    ticket_data = {
        "ticket_id": ticket_id,
        "account": resolved_key,
        "account_name": acc_info.get("display_name", resolved_key.capitalize()),
        "from_email": acc_info.get("email", ""),
        "to": to.strip(),
        "subject": subject.strip(),
        "body": body.strip(),
        "timestamp": time.time(),
    }

    _pending_emails[ticket_id] = ticket_data
    _persist_pending_tickets()

    return {
        "status": "staged",
        "ticket_id": ticket_id,
        "account": resolved_key,
        "account_name": acc_info.get("display_name", resolved_key.capitalize()),
        "from_email": acc_info.get("email", ""),
        "to": to.strip(),
        "subject": subject.strip(),
        "body": body.strip(),
        "message": f"Draft staged for {to.strip()} from {resolved_key}. Ready for review.",
        "actions": [
            {
                "id": "send",
                "label": "Send Email",
                "type": "primary",
                "payload": f"confirm: send_email {ticket_id}",
            },
            {
                "id": "copy",
                "label": "Copy Draft",
                "type": "secondary",
            },
            {
                "id": "discard",
                "label": "Discard",
                "type": "danger",
            },
        ],
    }


def _persist_pending_tickets():
    """Save pending tickets to disk so confirmation survives restarts."""
    _ensure_config_dir()
    try:
        with open(PENDING_TICKETS_FILE, "w", encoding="utf-8") as f:
            json.dump(_pending_emails, f)
    except Exception:
        pass


def _load_persisted_tickets():
    """Load pending tickets from disk."""
    if not PENDING_TICKETS_FILE.exists():
        return
    try:
        with open(PENDING_TICKETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                _pending_emails.update(data)
    except Exception:
        pass


def execute_confirmed_send(
    ticket_id: str,
    to: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    account: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute confirmed email dispatch via SMTP after user approval.

    Args:
        ticket_id: Safety ticket ID returned by stage_email_send.
        to: Optional overridden destination address.
        subject: Optional overridden subject line.
        body: Optional overridden body text.
        account: Optional overridden account key.
    """
    _load_persisted_tickets()
    config_data = load_email_accounts()
    ticket = _pending_emails.get(ticket_id) if ticket_id else None

    if not ticket:
        if to and body:
            resolved_key = _resolve_account_key(account or "personal", config_data) or config_data.get("default_account", "personal")
            acc_info = config_data.get("accounts", {}).get(resolved_key, {})
            ticket = {
                "account": resolved_key,
                "account_name": acc_info.get("display_name", resolved_key.capitalize()),
                "from_email": acc_info.get("email", ""),
                "to": to.strip(),
                "subject": (subject or "(No Subject)").strip(),
                "body": body.strip(),
                "timestamp": time.time(),
            }
        else:
            return {
                "status": "error",
                "message": f"Invalid or expired email send ticket '{ticket_id}'.",
            }

    # Apply overrides if provided by user edits in the UI card
    if to:
        ticket["to"] = to.strip()
    if subject:
        ticket["subject"] = subject.strip()
    if body:
        ticket["body"] = body.strip()
    if account:
        ticket["account"] = account.strip()

    # Ticket expiry after 2 hours
    if time.time() - ticket.get("timestamp", 0) > 7200:
        if ticket_id:
            _pending_emails.pop(ticket_id, None)
            _persist_pending_tickets()
        return {
            "status": "error",
            "message": f"Email ticket '{ticket_id}' has expired. Please draft again.",
        }

    acc_key = ticket.get("account", "personal")
    acc_info = config_data.get("accounts", {}).get(acc_key, {})

    smtp_host = acc_info.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(acc_info.get("smtp_port", 465))
    from_email = acc_info.get("email", "")
    username = acc_info.get("username", from_email)
    password = _get_account_password(acc_info)

    if not password:
        return {
            "status": "error",
            "message": f"Missing secret password for account '{acc_key}' in .env ({acc_info.get('secret_env_var')}).",
        }

    to_email = ticket.get("to", "")
    subject = ticket.get("subject", "")
    body = ticket.get("body", "")

    try:
        msg = EmailMessage()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg.set_content(body)

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)

        # Successfully sent: clean up ticket
        _pending_emails.pop(ticket_id, None)
        _persist_pending_tickets()

        return {
            "status": "ok",
            "ticket_id": ticket_id,
            "message": f"Email successfully sent to {to_email} via {acc_key} ({from_email}).",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"SMTP dispatch failed: {str(e)}",
        }


def configure_email_account(
    account_key: str,
    email_address: str,
    display_name: str = "",
    secret_env_var: str = "",
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 465,
    imap_host: str = "imap.gmail.com",
    imap_port: int = 993,
) -> Dict[str, Any]:
    """Configure or update an email profile in Ghost's account registry.

    Args:
        account_key: Short identifier (e.g. 'personal', 'work', 'client_xyz').
        email_address: The email address.
        display_name: Human readable label (e.g. 'Personal Gmail', 'Zulip Work').
        secret_env_var: Name of the environment variable storing the App Password.
        smtp_host: SMTP server hostname (default 'smtp.gmail.com').
        smtp_port: SMTP server port (default 465 SSL).
        imap_host: IMAP server hostname (default 'imap.gmail.com').
        imap_port: IMAP server port (default 993 SSL).
    """
    config_data = load_email_accounts()
    key = account_key.strip().lower()

    if not secret_env_var:
        secret_env_var = f"GMAIL_{key.upper()}_APP_PASSWORD"

    config_data.setdefault("accounts", {})[key] = {
        "display_name": display_name or key.capitalize(),
        "email": email_address.strip(),
        "provider": "gmail_imap",
        "smtp_host": smtp_host.strip(),
        "smtp_port": smtp_port,
        "imap_host": imap_host.strip(),
        "imap_port": imap_port,
        "username": email_address.strip(),
        "secret_env_var": secret_env_var.strip(),
    }

    if save_email_accounts(config_data):
        return {
            "status": "ok",
            "account": key,
            "message": f"Account '{key}' ({email_address}) configured. Ensure {secret_env_var} is defined in .env.",
        }
    return {"status": "error", "message": "Failed to save configuration."}
