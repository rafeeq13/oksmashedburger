"""Skip repeat sends to email addresses that already failed permanently."""
import json
import re
from datetime import datetime, timezone

from app.extensions import db
from app.models.site import SiteSetting

BLOCK_KEY = "email_blocked_recipients"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PERMANENT = re.compile(
    r"550|551|553|554|user unknown|mailbox not found|does not exist|"
    r"recipient rejected|no such user|invalid recipient|address rejected|"
    r"undeliverable|mailbox unavailable|account disabled",
    re.I,
)


def _blocked_map():
    row = SiteSetting.query.filter_by(key=BLOCK_KEY).first()
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_valid_email(email):
    return bool(_EMAIL_RE.match((email or "").strip()))


def is_blocked(email):
    addr = (email or "").strip().lower()
    if not addr:
        return True
    return addr in _blocked_map()


def block(email, reason="delivery_failed"):
    addr = (email or "").strip().lower()
    if not addr:
        return
    data = _blocked_map()
    data[addr] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": str(reason)[:240],
    }
    row = SiteSetting.query.filter_by(key=BLOCK_KEY).first()
    if not row:
        db.session.add(SiteSetting(key=BLOCK_KEY, value=json.dumps(data)))
    else:
        row.value = json.dumps(data)
    db.session.commit()


def unblock(email):
    addr = (email or "").strip().lower()
    if not addr:
        return False
    data = _blocked_map()
    if addr not in data:
        return False
    del data[addr]
    row = SiteSetting.query.filter_by(key=BLOCK_KEY).first()
    if not row:
        return False
    row.value = json.dumps(data) if data else ""
    db.session.commit()
    return True


def should_skip(email):
    addr = (email or "").strip()
    if not is_valid_email(addr):
        return True
    return is_blocked(addr)


def note_failure(email, error_text):
    """Block the address after a permanent SMTP / delivery error."""
    if not error_text or not _PERMANENT.search(str(error_text)):
        return False
    block(email, error_text)
    return True
