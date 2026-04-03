import os
import requests
import time
from utils.logger import setup_logger

from dotenv import load_dotenv
load_dotenv()

logger = setup_logger()

# Use Apify Instagram Scraper or RapidAPI Instagram scraper
APIFY_TOKEN = os.environ.get('APIFY_TOKEN', '')
RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY', '')


def scrape_instagram_profile_apify(username: str, max_posts: int = 10) -> list[dict]:
    """
    Scrape recent posts from an Instagram profile using Apify.
    Returns list of post dicts with caption, image_url, post_url, timestamp.
    """
    if not APIFY_TOKEN:
        logger.warning("APIFY_TOKEN not set, returning mock data")
        return _mock_posts(username)

    actor_id = "apify/instagram-post-scraper"
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"

    payload = {
        "directUrls": [f"https://www.instagram.com/{username}/"],
        "resultsLimit": max_posts,
        "resultsType": "posts",
        "addParentData": False,
    }

    headers = {
        "Content-Type": "application/json",
    }

    params = {"token": APIFY_TOKEN}

    try:
        logger.info(f"Scraping Instagram profile: {username}")
        response = requests.post(url, json=payload, headers=headers, params=params, timeout=120)
        response.raise_for_status()
        items = response.json()

        posts = []
        for item in items:
            post = {
                "caption": item.get("caption", ""),
                "image_url": item.get("displayUrl", "") or item.get("imageUrl", ""),
                "post_url": item.get("url", f"https://www.instagram.com/{username}/"),
                "timestamp": item.get("timestamp", ""),
                "username": username,
            }
            posts.append(post)

        logger.info(f"Scraped {len(posts)} posts from @{username}")
        return posts

    except Exception as e:
        logger.error(f"Apify scraping failed for {username}: {e}")
        return _mock_posts(username)


def scrape_instagram_profile_rapidapi(username: str, max_posts: int = 10) -> list[dict]:
    """
    Alternate: Scrape via RapidAPI Instagram scraper.
    """
    if not RAPIDAPI_KEY:
        logger.warning("RAPIDAPI_KEY not set, returning mock data")
        return _mock_posts(username)

    url = "https://instagram-scraper-api2.p.rapidapi.com/v1/posts"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "instagram-scraper-api2.p.rapidapi.com",
    }
    params = {"username_or_id_or_url": username}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        items = data.get("data", {}).get("items", [])[:max_posts]
        posts = []
        for item in items:
            caption_text = ""
            if item.get("caption"):
                caption_text = item["caption"].get("text", "")

            image_url = ""
            if item.get("image_versions2"):
                candidates = item["image_versions2"].get("candidates", [])
                if candidates:
                    image_url = candidates[0].get("url", "")

            post = {
                "caption": caption_text,
                "image_url": image_url,
                "post_url": f"https://www.instagram.com/p/{item.get('code', '')}/",
                "timestamp": item.get("taken_at", ""),
                "username": username,
            }
            posts.append(post)

        logger.info(f"RapidAPI scraped {len(posts)} posts from @{username}")
        return posts

    except Exception as e:
        logger.error(f"RapidAPI scraping failed for {username}: {e}")
        return _mock_posts(username)


def scrape_profile(username: str, max_posts: int = 10) -> list[dict]:
    """
    Main entry point: tries Apify first, then RapidAPI, then mock.
    """
    if APIFY_TOKEN:
        return scrape_instagram_profile_apify(username, max_posts)
    elif RAPIDAPI_KEY:
        return scrape_instagram_profile_rapidapi(username, max_posts)
    else:
        logger.warning("No scraping API keys configured. Using demo data.")
        return _mock_posts(username)


def _mock_posts(username: str) -> list[dict]:
    """Demo data when no API keys are configured."""
    return [
        {
            "caption": f"🎉 PARTY ALERT! Join us this Saturday at Club Noir for an unforgettable night! "
                       f"Doors open at 23:00. Entry: 500 MKD. "
                       f"For reservations call +389 70 123 456. "
                       f"Location: Bulevar Partizanski Odredi 59, Skopje. "
                       f"Music: House & Techno by DJ Shadow. Dress code: Elegant. 18+. "
                       f"#nightlife #party #skopje #clubnoir",
            "image_url": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=800",
            "post_url": f"https://www.instagram.com/{username}/",
            "timestamp": "2025-01-15T21:00:00",
            "username": username,
        },
        {
            "caption": f"🔥 NEW YEAR SPECIAL EVENT at Vertigo Club! "
                       f"Date: December 31st. "
                       f"Open bar from 22:00 to 01:00. Ticket price: 1500 MKD includes open bar. "
                       f"Limited seats! Reservations: +389 78 987 654. "
                       f"Address: Ul. Makedonija 12, Skopje. "
                       f"Performers: DJ Marco + Live Act. "
                       f"#newyear #party #vertigo #skopjenightlife",
            "image_url": "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?w=800",
            "post_url": f"https://www.instagram.com/{username}/",
            "timestamp": "2025-01-10T18:00:00",
            "username": username,
        },
        {
            "caption": f"✨ LADIES NIGHT every Friday at Club Euphoria! "
                       f"Free entry for ladies before midnight. Men: 300 MKD. "
                       f"Starts at 22:30. "
                       f"Location: TC Bunjakovec, Skopje. "
                       f"Call for table reservations: +389 71 555 777. "
                       f"R&B and Hip-Hop all night. 21+. "
                       f"#ladiesnight #euphoria #friday #skopje",
            "image_url": "https://images.unsplash.com/photo-1429962714451-bb934ecdc4ec?w=800",
            "post_url": f"https://www.instagram.com/{username}/",
            "timestamp": "2025-01-08T15:00:00",
            "username": username,
        },
    ]