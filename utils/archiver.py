"""
archiver.py — Parse event date strings and auto-archive past events.

Called at app startup and after every scrape.
"""

import re
from datetime import date, datetime, timedelta
from utils.logger import setup_logger

logger = setup_logger()

# Month name → number, covers English + Macedonian/Serbian
MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10,
    'november': 11, 'december': 12,
    # Macedonian
    'јануари': 1, 'февруари': 2, 'март': 3, 'април': 4, 'мај': 5,
    'јуни': 6, 'јули': 7, 'август': 8, 'септември': 9,
    'октомври': 10, 'ноември': 11, 'декември': 12,
    # Short Macedonian
    'јан': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'јун': 6,
    'јул': 7, 'авг': 8, 'сеп': 9, 'окт': 10, 'ное': 11, 'дек': 12,
}

# Day-of-week words to ignore in parsing
DOW = {'monday','tuesday','wednesday','thursday','friday','saturday','sunday',
       'понеделник','вторник','среда','четврток','петок','сабота','недела'}


def parse_event_date(date_str: str) -> date | None:
    """
    Try to extract a calendar date from the AI-generated date string.
    Returns a date object or None if parsing fails.
    """
    if not date_str:
        return None

    s = date_str.strip().lower()
    today = datetime.utcnow().date()
    year  = today.year

    # Remove day-of-week words
    for dow in DOW:
        s = s.replace(dow, ' ')

    s = re.sub(r'[,.]', ' ', s).strip()

    # ── ISO format: 2025-01-18 ────────────────────────────────────
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # ── DD/MM/YYYY or DD.MM.YYYY ──────────────────────────────────
    m = re.search(r'(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})', s)
    if m:
        try:
            y = int(m.group(3))
            if y < 100:
                y += 2000
            return date(y, int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # ── DD MonthName YYYY  or  MonthName DD YYYY ──────────────────
    m = re.search(r'(\d{1,2})\s+([a-zа-ш]+)\s+(\d{4})', s)
    if not m:
        m = re.search(r'([a-zа-ш]+)\s+(\d{1,2})\s+(\d{4})', s)
        if m:
            # swap to day month year
            m = type('M', (), {
                'group': lambda self, n: [None, m.group(2), m.group(1), m.group(3)][n]
            })()
    if m:
        mon = MONTHS.get(m.group(2)[:3] if len(m.group(2)) > 3 else m.group(2))
        if not mon:
            mon = MONTHS.get(m.group(2))
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(1)))
            except ValueError:
                pass

    # ── DD MonthName (no year — assume current or next year) ──────
    m = re.search(r'(\d{1,2})\s+([a-zа-ш]+)', s)
    if not m:
        m = re.search(r'([a-zа-ш]+)\s+(\d{1,2})', s)
        if m:
            m = type('M', (), {
                'group': lambda self, n: [None, m.group(2), m.group(1)][n]
            })()
    if m:
        key = m.group(2)
        mon = MONTHS.get(key[:3]) or MONTHS.get(key)
        if mon:
            try:
                day = int(m.group(1))
                candidate = date(year, mon, day)
                # if this date already passed, try next year
                if candidate < today - timedelta(days=1):
                    candidate = date(year + 1, mon, day)
                return candidate
            except ValueError:
                pass

    logger.debug(f"[archiver] could not parse date: '{date_str}'")
    return None


def auto_archive_past_events(db) -> int:
    """
    Find all non-archived events whose event_date has passed and archive them.
    Returns number of events archived.
    """
    from models import Event
    today = datetime.utcnow().date()

    # Events with a known parsed date that has passed
    past = Event.query.filter(
        Event.is_archived == False,
        Event.event_date != None,
        Event.event_date < today,
    ).all()

    count = 0
    for ev in past:
        ev.archive()
        count += 1
        logger.info(f"[archiver] archived past event: '{ev.title}' (date: {ev.event_date})")

    if count:
        try:
            db.session.commit()
            logger.info(f"[archiver] archived {count} past events")
        except Exception as e:
            logger.error(f"[archiver] commit failed: {e}")
            db.session.rollback()
            count = 0

    return count


def parse_and_set_event_date(ev_dict: dict) -> date | None:
    """Parse the 'date' string from an extracted event dict and return a date object."""
    return parse_event_date(ev_dict.get('date') or '')