"""
ai_service.py — Extract structured event data from Instagram captions
using Google Gemini API, with regex fallback.

KEY FIX: image_url is NEVER sent to Gemini and NEVER overwritten by Gemini's
response. It is always carried from the scraper untouched.
"""

import os
import json
import re
import requests
from utils.logger import setup_logger

logger = setup_logger()

GEMINI_MODEL   = "gemini-2.0-flash"
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models"
    f"/{GEMINI_MODEL}:generateContent"
)

EVENT_KEYWORDS = [
    "party", "event", "night", "club", "doors open", "entry", "ticket",
    "reservation", "reservations", "lineup", "dj ", " dj", "live act",
    "concert", "gig", "rave", "festival", "dress code", "mkd", "eur",
    "free entry", "vip", "table", "booking", "book now", "tonight",
    "this friday", "this saturday", "this sunday", "this week",
    "večer", "zabava", "nastap", "ulaz", "rezervacija",
]

# Fields Gemini is allowed to set — image_url is NOT in this list
GEMINI_ALLOWED_FIELDS = {
    "is_event", "title", "venue", "location", "date", "start_time",
    "entry_price", "phone", "description", "genre", "dress_code", "age_limit",
}


def _api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def _looks_like_event(caption: str) -> bool:
    lower = caption.lower()
    return any(kw in lower for kw in EVENT_KEYWORDS)


PROMPT_TEMPLATE = """\
You are an expert at analysing Instagram posts from nightclubs and event promoters.

Read this caption and determine if it announces a REAL UPCOMING party or event
(NOT a throwback, NOT a general photo, NOT a "thanks for last night" post).

Caption:
\"\"\"
{caption}
\"\"\"

Return ONLY valid JSON — no markdown, no extra keys:
{{
  "is_event":    true or false,
  "title":       "Event name or null",
  "venue":       "Club/venue name or null",
  "location":    "Address or area or null",
  "date":        "Event date e.g. Saturday 18 January 2025 or null",
  "start_time":  "Door time e.g. 22:00 or null",
  "entry_price": "Price with currency e.g. 500 MKD or null",
  "phone":       "Contact phone or null",
  "description": "1-2 sentence event summary or null",
  "genre":       "Music genre e.g. Techno, House, R&B or null",
  "dress_code":  "Dress code or null",
  "age_limit":   "Age restriction e.g. 18+ or null"
}}\
"""


def extract_event_info(caption: str, username: str = "", image_url: str = "") -> dict | None:
    """
    Analyse one caption. Returns a structured dict if it's an event, None if not.
    image_url is passed in from the scraper and is NEVER touched by Gemini.
    """
    if not _looks_like_event(caption):
        logger.info(f"[AI] skipped (no event keywords) @{username}")
        return None

    key = _api_key()
    if not key:
        logger.warning("[AI] no GEMINI_API_KEY — regex fallback")
        return _regex_extract(caption, username, image_url)

    prompt  = PROMPT_TEMPLATE.format(caption=caption[:3000])
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":      0.05,
            "maxOutputTokens":  800,
            "responseMimeType": "application/json",
        },
    }

    try:
        resp = requests.post(
            GEMINI_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            params={"key": key},
            timeout=25,
        )
        resp.raise_for_status()

        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        gemini_data = json.loads(text)

        if not gemini_data.get("is_event"):
            logger.info(f"[AI] Gemini: not an event @{username}")
            return None

        # ── CRITICAL: only take Gemini-allowed fields, never image_url ──
        result = {k: v for k, v in gemini_data.items() if k in GEMINI_ALLOWED_FIELDS}

        # Always set these from our own data, not from Gemini
        result["image_url"]         = image_url   # from scraper, not Gemini
        result["instagram_profile"] = username
        result["raw_caption"]       = caption

        logger.info(
            f"[AI] extracted '{result.get('title', '—')}' | "
            f"image={'YES (' + image_url[:60] + ')' if image_url else 'NO'}"
        )
        return result

    except requests.HTTPError as e:
        logger.error(f"[AI] Gemini HTTP {e.response.status_code}: {e.response.text[:300]}")
        return _regex_extract(caption, username, image_url)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error(f"[AI] parse error: {e}")
        return _regex_extract(caption, username, image_url)
    except Exception as e:
        logger.error(f"[AI] {e}")
        return _regex_extract(caption, username, image_url)


def batch_extract_events(posts: list) -> list:
    """
    Process posts. image_url is taken from the scraper post, never from Gemini.
    """
    events = []
    for post in posts:
        caption   = (post.get("caption") or "").strip()
        image_url = (post.get("image_url") or "").strip()

        if len(caption) < 15:
            continue

        logger.info(f"[batch] processing post | image={'YES' if image_url else 'NO'} | caption={caption[:60]}")

        result = extract_event_info(
            caption   = caption,
            username  = post.get("username", ""),
            image_url = image_url,
        )

        if result is None:
            continue

        # Sanity check — make sure image_url survived
        if not result.get("image_url") and image_url:
            logger.warning("[batch] image_url was lost — restoring from post")
            result["image_url"] = image_url

        result["instagram_post_url"] = post.get("post_url", "")
        logger.info(
            f"[batch] event saved: '{result.get('title','—')}' | "
            f"image={'YES' if result.get('image_url') else 'NO'}"
        )
        events.append(result)

    logger.info(f"[batch] {len(events)} events from {len(posts)} posts")
    return events


# ── Regex fallback ────────────────────────────────────────────────
def _regex_extract(caption: str, username: str, image_url: str) -> dict | None:
    if not _looks_like_event(caption):
        return None

    lines     = caption.splitlines()
    raw_title = re.sub(r"[^\w\s\-&!]", "", lines[0]).strip() if lines else ""
    title     = raw_title[:80] or "Nightlife Event"

    phone_m = re.search(r"(\+?[\d][\d\s\-\(\)]{7,18})", caption)
    phone   = phone_m.group(1).strip() if phone_m else None

    price_m = re.search(r"(\d[\d.,]*)\s*(MKD|EUR|USD|GBP|ден|€|\$)", caption, re.I)
    price   = f"{price_m.group(1)} {price_m.group(2).upper()}" if price_m else None
    if not price and re.search(r"\bfree\s*entry\b|\bfree\b", caption, re.I):
        price = "Free"

    time_m = re.search(r"\b(\d{1,2}[:.]\d{2})\b", caption)
    start  = time_m.group(1).replace(".", ":") if time_m else None

    date_m = re.search(
        r"\b(\d{1,2}[\s./]\w+[\s./]\d{2,4}|\w+day,?\s+\w+\s+\d{1,2}|\d{1,2}\s+\w{3,})",
        caption, re.I
    )
    date = date_m.group(0).strip() if date_m else None

    genres = ["Techno", "House", "R&B", "Hip-Hop", "Reggaeton",
              "Pop", "EDM", "Trance", "Afrobeats", "Latin", "Disco",
              "Drum and Bass", "Commercial"]
    genre = next((g for g in genres if g.lower() in caption.lower()), None)
    age   = "18+" if "18+" in caption else ("21+" if "21+" in caption else None)

    return {
        "is_event":          True,
        "title":             title,
        "venue":             username.replace("_", " ").title() if username else None,
        "location":          None,
        "date":              date,
        "start_time":        start,
        "entry_price":       price,
        "phone":             phone,
        "description":       caption[:250] + ("…" if len(caption) > 250 else ""),
        "genre":             genre,
        "dress_code":        None,
        "age_limit":         age,
        "image_url":         image_url,   # always from scraper
        "instagram_profile": username,
        "raw_caption":       caption,
    }