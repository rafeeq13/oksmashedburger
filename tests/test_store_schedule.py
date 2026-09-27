"""Scheduled order slot generation per store hours."""
from datetime import date, datetime

from app.models.store import Store, StoreHours, _schedule_bounds


def _store_with_hours(open_t="11:00", close_t="17:00", tz="America/New_York"):
    s = Store(name="Test", slug="test-sched", is_active=True, accepting_scheduled=True, timezone=tz)
    s.hours = [
        StoreHours(day_of_week=i, is_closed=False, open_time=open_t, close_time=close_t)
        for i in range(7)
    ]
    return s


def test_schedule_slots_within_hours_and_before_close_buffer():
    store = _store_with_hours("11:00", "17:00")
    now = datetime(2026, 6, 2, 10, 0, 0)  # Tuesday, before open
    days = store.schedule_days(now=now)
    assert days
    slots = days[0]["slots"]
    assert slots
    assert slots[0]["value"].endswith("T11:00")
    assert slots[-1]["value"].endswith("T16:45")
    times = [s["value"].split("T")[1] for s in slots]
    assert min(times) >= "11:00"
    assert max(times) <= "16:45"


def test_schedule_bounds_last_slot_before_close():
    start, last = _schedule_bounds(date(2026, 6, 2), "11:00", "22:00", 15)
    assert start.hour == 11 and last.hour == 21 and last.minute == 45


def test_schedule_slots_respect_lead_time_today():
    store = _store_with_hours("11:00", "22:00")
    now = datetime(2026, 6, 2, 14, 10, 0)
    days = store.schedule_days(now=now)
    slots = days[0]["slots"]
    assert slots[0]["value"].endswith("T14:45")  # 30 min lead, rounded in 15 min steps from open
