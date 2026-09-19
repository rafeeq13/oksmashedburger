"""Diagnose open/closed vs hours — run on production."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app import create_app
from app.models.store import Store

app = create_app()
with app.app_context():
    now_srv = datetime.now()
    now_et = datetime.now(ZoneInfo("America/New_York"))
    print("SERVER_NOW", now_srv.strftime("%Y-%m-%d %H:%M:%S %a"))
    print("PHILLY_NOW", now_et.strftime("%Y-%m-%d %H:%M:%S %a"))
    for s in Store.query.filter_by(is_active=True).order_by(Store.name):
        ln = s.local_now()
        h = s.hours_for(ln.weekday())
        print("---", s.slug)
        print("  tz=", s.timezone, "accepting_orders=", s.accepting_orders)
        print("  open_now=", s.open_now, "scheduling_open=", s.scheduling_open)
        if h:
            print("  hours=", h.open_time, "-", h.close_time, "is_closed=", h.is_closed)
        print("  local_now=", ln.strftime("%Y-%m-%d %H:%M:%S %a"))
        print("  is_open_at(local_now)=", s.is_open_at(ln))
        if not s.open_now:
            print("  reason:", s.asap_unavailable_reason)
