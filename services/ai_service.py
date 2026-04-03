import os
import json
import re
import requests
from utils.logger import setup_logger

from dotenv import load_dotenv
load_dotenv()

logger = setup_logger()

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


def extract_event_info(caption: str, username: str = "", image_url: str = "") -> dict:
    """
    Send an Instagram caption to Gemini API and extract structured event info.
    Returns a dict with event fields.
    """
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set, using demo extraction")
        return _demo_extract(caption, username, image_url)

    prompt = f"""You are an expert at extracting nightlife event information from Instagram posts.

Analyze this Instagram post caption and extract ALL relevant event details.

Caption:
\"\"\"
{caption}
\"\"\"

Extract and return ONLY a valid JSON object with these fields (use null if information is not found):
{{
  "title": "Event or party name/title",
  "venue": "Venue/club name",
  "location": "Full address or location description",
  "date": "Event date (try to standardize to DD Month YYYY or day of week)",
  "start_time": "When doors open or event starts (e.g. 22:00)",
  "entry_price": "Entry fee / ticket price (include currency if mentioned)",
  "phone": "Reservation or contact phone number",
  "description": "Brief description of the event vibe, performers, music genre",
  "genre": "Music genre (e.g. Techno, House, R&B, Hip-Hop, Pop, etc.)",
  "dress_code": "Dress code if mentioned",
  "age_limit": "Age restriction if mentioned (e.g. 18+, 21+)",
  "is_event": true or false (is this post actually about a party/event?)
}}

Return ONLY the JSON, no markdown, no explanation."""

    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1024,
        }
    }

    try:
        response = requests.post(GEMINI_API_URL, json=payload, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        text = data["candidates"][0]["content"]["parts"][0]["text"]

        # Strip markdown fences if present
        text = re.sub(r"```json|```", "", text).strip()

        result = json.loads(text)
        result["image_url"] = image_url
        result["instagram_profile"] = username
        result["raw_caption"] = caption

        logger.info(f"Gemini extracted event: {result.get('title', 'Unknown')}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini JSON response: {e}")
        return _fallback_extract(caption, username, image_url)
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return _demo_extract(caption, username, image_url)


def batch_extract_events(posts: list[dict]) -> list[dict]:
    """
    Process multiple posts through Gemini and return list of event dicts.
    Only includes posts where is_event is True.
    """
    events = []
    for post in posts:
        caption = post.get("caption", "")
        if len(caption.strip()) < 20:
            continue

        result = extract_event_info(
            caption=caption,
            username=post.get("username", ""),
            image_url=post.get("image_url", ""),
        )

        result["instagram_post_url"] = post.get("post_url", "")

        if result.get("is_event", True):
            events.append(result)

    logger.info(f"Extracted {len(events)} events from {len(posts)} posts")
    return events


def _demo_extract(caption: str, username: str, image_url: str) -> dict:
    """Demo extraction using simple parsing when Gemini is unavailable."""
    import re

    lines = caption.split('\n')
    title_line = lines[0] if lines else "Party Event"
    title = re.sub(r'[🎉🔥✨🎊🎶💥🌟⭐]', '', title_line).strip()[:80]

    phone_match = re.search(r'(\+?\d[\d\s\-]{7,15})', caption)
    phone = phone_match.group(1).strip() if phone_match else None

    price_match = re.search(r'(\d+)\s*(MKD|EUR|USD|ден)', caption, re.IGNORECASE)
    price = f"{price_match.group(1)} {price_match.group(2)}" if price_match else None

    time_match = re.search(r'(\d{1,2}:\d{2})', caption)
    start_time = time_match.group(1) if time_match else None

    return {
        "title": title if title else "Nightlife Event",
        "venue": username.replace('_', ' ').title() if username else None,
        "location": None,
        "date": None,
        "start_time": start_time,
        "entry_price": price,
        "phone": phone,
        "description": caption[:200] + "..." if len(caption) > 200 else caption,
        "genre": None,
        "dress_code": None,
        "age_limit": "18+" if "18+" in caption else None,
        "is_event": True,
        "image_url": image_url,
        "instagram_profile": username,
        "raw_caption": caption,
    }


def _fallback_extract(caption: str, username: str, image_url: str) -> dict:
    """Fallback when parsing fails."""
    return _demo_extract(caption, username, image_url)