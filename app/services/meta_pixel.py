"""Queue one-shot Meta Pixel events across redirects (session flash)."""
from flask import session


def queue_fbq_event(event, params=None):
    if not event:
        return
    payload = {"event": str(event), "params": params or {}}
    session.setdefault("_fbq_events", []).append(payload)
    session.modified = True


def pop_fbq_events():
    events = session.pop("_fbq_events", None) or []
    return events
