"""Maintenance window planner. Picks the latest planned stop (break or shift change) that still comes before the forecast
ISO damage zone, with a safety margin. Pure code: BigQuery ML forecast hours + the shop's shift timetable. No AI."""
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
WINDOWS = [(dtime(6, 0), "shift start (6:00)"), (dtime(10, 0), "tea break (10:00)"), (dtime(13, 0), "lunch break (13:00)"),
           (dtime(14, 0), "shift change (14:00)"), (dtime(17, 30), "tea break (17:30)"), (dtime(19, 30), "dinner break (19:30)"), (dtime(22, 0), "shift change (22:00)")]
MARGIN_H = 0.5   # stop at least 30 minutes before the forecast damage zone


def plan_stop(hours_to_zone_d, now=None) -> dict:
    if hours_to_zone_d is None:
        return {"needed": False, "short": "", "message": "No damage zone forecast in the next 24 hours: no stop needed."}
    now = now or datetime.now(IST)
    deadline = now + timedelta(hours=float(hours_to_zone_d))
    latest_ok = deadline - timedelta(hours=MARGIN_H)
    cands = [(datetime.combine((now + timedelta(days=d)).date(), t, IST), name)
             for d in (0, 1) for t, name in WINDOWS]
    cands = [(at, n) for at, n in cands if now + timedelta(minutes=10) <= at <= latest_ok]
    if not cands:
        return {"needed": True, "stop_now": True, "damage_zone_at": deadline.strftime("%H:%M"), "short": "Plan: stop as soon as possible",
                "message": f"Stop as soon as possible: no planned break comes early enough before the damage zone (~{deadline:%H:%M})."}
    at, name = cands[-1]
    lead = (deadline - at).total_seconds() / 3600
    return {"needed": True, "stop_now": False, "stop_at": at.strftime("%H:%M"), "window": name, "damage_zone_at": deadline.strftime("%H:%M"),
            "margin_hours": round(lead, 1), "short": f"Plan: stop at the {name}",
            "message": (f"Plan the repair at the {name}, about {lead:.1f} h before the forecast damage zone (~{deadline:%H:%M}): "
                        "a planned stop in a break instead of a breakdown mid-shift.")}
