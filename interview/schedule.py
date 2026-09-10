"""Interview date/time extraction and approval-only calendar proposals.

This module never creates a calendar event. It extracts a best-effort datetime
from invite text and builds a proposal dict. Actual creation happens only after
explicit user approval, via the Google Calendar connector - not from this code.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
    )
}

_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})\b")
_DMY_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b.*?\b(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", re.IGNORECASE | re.DOTALL)
_MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?"
    r".*?\b(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)",
    re.IGNORECASE | re.DOTALL,
)


def _to_24h(hour: int, ampm: str | None) -> int:
    if not ampm:
        return hour
    ampm = ampm.lower().replace(".", "")
    if ampm == "pm" and hour != 12:
        return hour + 12
    if ampm == "am" and hour == 12:
        return 0
    return hour


def extract_interview_datetime(text: str, now: datetime | None = None) -> datetime | None:
    """Best-effort. Returns a timezone-aware UTC datetime or None if unsure."""
    if not text:
        return None
    now = now or datetime.now(timezone.utc)

    m = _ISO_RE.search(text)
    if m:
        y, mo, d, h, mi = (int(x) for x in m.groups())
        return _safe(y, mo, d, h, mi)

    m = _MONTH_RE.search(text)
    if m:
        mon = _MONTHS[m.group(1).lower()[:3]]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        hour = _to_24h(int(m.group(4)), m.group(6))
        minute = int(m.group(5) or 0)
        dt = _safe(year, mon, day, hour, minute)
        if dt and not m.group(3) and dt < now - timedelta(days=1):
            dt = _safe(year + 1, mon, day, hour, minute)
        return dt

    m = _DMY_RE.search(text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hour = _to_24h(int(m.group(4)), m.group(6))
        minute = int(m.group(5) or 0)
        return _safe(y, mo, d, hour, minute)

    return None


def _safe(y: int, mo: int, d: int, h: int, mi: int) -> datetime | None:
    try:
        return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)
    except ValueError:
        return None


def propose_calendar_event(
    company: str,
    role: str,
    when: datetime | None,
    duration_minutes: int = 45,
    notes: str = "",
) -> dict:
    """Build a calendar-event proposal. Creation is approval-only and happens
    via the Google Calendar connector, never from this function."""
    start = when.isoformat() if when else None
    end = (when + timedelta(minutes=duration_minutes)).isoformat() if when else None
    return {
        "requires_approval": True,
        "action": "create_calendar_event",
        "summary": f"Interview — {company} ({role})",
        "start": start,
        "end": end,
        "timezone_note": "times parsed as UTC unless the invite stated one — confirm before approving",
        "description": (notes or "Interview. Prep pack generated separately.").strip(),
        "confirmed_datetime": start is not None,
    }
