"""
scraper_service.py — Instagram post scraper.
Scrapes exactly the last MAX_POSTS (5) posts per profile.
Priority: Apify → RapidAPI → built-in demo data.
"""

import os
import json
import requests
from utils.logger import setup_logger

logger = setup_logger()

MAX_POSTS = 5


def _token() -> str:
    return os.environ.get("APIFY_TOKEN", "").strip()


def _rapidapi_key() -> str:
    return os.environ.get("RAPIDAPI_KEY", "").strip()


def _extract_image_apify(item: dict, username: str) -> str:
    """
    Exhaustively walk every known Apify instagram-scraper field
    to find the post image URL. Logs what it finds for debugging.
    """
    # Log all keys so we can see the real shape in Flask console
    keys = list(item.keys())
    logger.debug(f"[Apify] item keys: {keys}")

    # 1. Direct image fields (most common)
    for field in ("displayUrl", "imageUrl", "image_url", "thumbnailUrl",
                  "thumbnail_url", "media_url", "mediaUrl"):
        val = item.get(field, "")
        if val and isinstance(val, str) and val.startswith("http"):
            logger.debug(f"[Apify] image from field '{field}': {val[:80]}")
            return val

    # 2. images[] array
    imgs = item.get("images") or item.get("Images") or []
    if isinstance(imgs, list) and imgs:
        first = imgs[0]
        if isinstance(first, str) and first.startswith("http"):
            logger.debug(f"[Apify] image from images[0]: {first[:80]}")
            return first
        if isinstance(first, dict):
            for f in ("url", "src", "displayUrl"):
                if first.get(f, "").startswith("http"):
                    logger.debug(f"[Apify] image from images[0].{f}")
                    return first[f]

    # 3. latestImages[] (some actor versions)
    latest = item.get("latestImages") or []
    if isinstance(latest, list) and latest:
        img = latest[0]
        if isinstance(img, str) and img.startswith("http"):
            return img

    # 4. Carousel / childPosts
    for carousel_key in ("childPosts", "children", "carouselMedia", "carousel_media",
                         "sidecar_media", "sidecars"):
        children = item.get(carousel_key) or []
        if isinstance(children, list) and children:
            first_child = children[0]
            if isinstance(first_child, dict):
                for f in ("displayUrl", "imageUrl", "thumbnailUrl", "url"):
                    if first_child.get(f, "").startswith("http"):
                        logger.debug(f"[Apify] image from {carousel_key}[0].{f}")
                        return first_child[f]

    # 5. video thumbnail fallback for video posts
    for field in ("videoThumbnailUrl", "video_thumbnail_url", "coverUrl"):
        val = item.get(field, "")
        if val and isinstance(val, str) and val.startswith("http"):
            logger.debug(f"[Apify] image fallback from '{field}'")
            return val

    logger.warning(f"[Apify] NO image found for post from @{username}. Keys were: {keys}")
    return ""


def _extract_image_rapidapi(item: dict, username: str) -> str:
    """
    Walk every known RapidAPI instagram-scraper-api2 field to find image URL.
    """
    keys = list(item.keys())
    logger.debug(f"[RapidAPI] item keys: {keys}")

    # 1. image_versions2.candidates[] — standard private API shape
    iv2 = item.get("image_versions2") or {}
    candidates = iv2.get("candidates") or []
    if candidates:
        # Sort by width descending — pick highest resolution
        try:
            candidates = sorted(candidates, key=lambda c: int(c.get("width") or 0), reverse=True)
        except Exception:
            pass
        url = candidates[0].get("url", "")
        if url.startswith("http"):
            logger.debug(f"[RapidAPI] image from image_versions2.candidates[0]: {url[:80]}")
            return url

    # 2. carousel_media[0].image_versions2 — carousel posts
    carousel = item.get("carousel_media") or []
    if isinstance(carousel, list) and carousel:
        first = carousel[0]
        iv2c = first.get("image_versions2") or {}
        cands = iv2c.get("candidates") or []
        if cands:
            try:
                cands = sorted(cands, key=lambda c: int(c.get("width") or 0), reverse=True)
            except Exception:
                pass
            url = cands[0].get("url", "")
            if url.startswith("http"):
                logger.debug(f"[RapidAPI] image from carousel_media[0].image_versions2")
                return url

    # 3. Direct URL fields
    for field in ("thumbnail_url", "display_url", "thumbnail_src",
                  "cover_media_cropped_image_version", "image_url"):
        val = item.get(field) or ""
        if isinstance(val, str) and val.startswith("http"):
            logger.debug(f"[RapidAPI] image from field '{field}'")
            return val

    # 4. cover_media nested
    cover = item.get("cover_media") or {}
    if isinstance(cover, dict):
        cropped = cover.get("cropped_image_version") or {}
        url = cropped.get("url", "")
        if url.startswith("http"):
            return url

    # 5. video_versions thumbnail fallback
    video_versions = item.get("video_versions") or []
    if video_versions:
        # video post — use thumbnail from image_versions2 already tried above
        # try video_versions[0] as last resort
        vv = video_versions[0] if isinstance(video_versions, list) else {}
        url = vv.get("url", "") if isinstance(vv, dict) else ""
        if url.startswith("http"):
            logger.debug(f"[RapidAPI] image from video_versions[0] (video thumbnail)")
            return url

    logger.warning(f"[RapidAPI] NO image found for post from @{username}. Keys: {keys}")
    return ""


# ── Apify ─────────────────────────────────────────────────────────
def _scrape_apify(username: str) -> list:
    url    = "https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items"
    params = {"token": _token(), "timeout": 90, "memory": 256}
    payload = {
        "directUrls":    [f"https://www.instagram.com/{username}/"],
        "resultsType":   "posts",
        "resultsLimit":  MAX_POSTS,
        "addParentData": False,
    }
    try:
        logger.info(f"[Apify] scraping last {MAX_POSTS} posts from @{username}")
        resp = requests.post(url, json=payload, params=params, timeout=120)
        resp.raise_for_status()
        items = resp.json()[:MAX_POSTS]

        # Log first raw item so we can see real field names in console
        if items:
            logger.info(f"[Apify] first item keys: {list(items[0].keys())}")
            # Log full first item at DEBUG level
            logger.debug(f"[Apify] first item dump:\n{json.dumps(items[0], indent=2, default=str)[:2000]}")

        posts = []
        for item in items:
            caption  = item.get("caption") or item.get("alt") or ""
            image    = _extract_image_apify(item, username)

            post_url = item.get("url") or ""
            if post_url and not post_url.startswith("http"):
                post_url = f"https://www.instagram.com/p/{post_url}/"
            if not post_url:
                sc = item.get("shortCode") or item.get("shortcode") or item.get("id", "")
                post_url = (f"https://www.instagram.com/p/{sc}/"
                            if sc else f"https://www.instagram.com/{username}/")

            logger.info(f"[Apify] post: url={post_url[:60]} image={'YES' if image else 'NO'} caption_len={len(caption)}")

            posts.append({
                "caption":   caption,
                "image_url": image,
                "post_url":  post_url,
                "timestamp": item.get("timestamp", ""),
                "username":  username,
                "_raw":      item,   # keep raw for debug endpoint
            })

        logger.info(f"[Apify] done: {len(posts)} posts from @{username}")
        return posts

    except requests.HTTPError as e:
        logger.error(f"[Apify] HTTP {e.response.status_code}: {e.response.text[:400]}")
        return []
    except Exception as e:
        logger.error(f"[Apify] exception: {e}", exc_info=True)
        return []


# ── RapidAPI ──────────────────────────────────────────────────────
def _scrape_rapidapi(username: str) -> list:
    url     = "https://instagram-scraper-api2.p.rapidapi.com/v1.2/posts"
    headers = {
        "x-rapidapi-key":  _rapidapi_key(),
        "x-rapidapi-host": "instagram-scraper-api2.p.rapidapi.com",
    }
    try:
        logger.info(f"[RapidAPI] scraping last {MAX_POSTS} posts from @{username}")
        resp = requests.get(url, headers=headers,
                            params={"username_or_id_or_url": username}, timeout=30)
        resp.raise_for_status()
        data  = resp.json()
        items = ((data.get("data") or {}).get("items") or [])[:MAX_POSTS]

        if items:
            logger.info(f"[RapidAPI] first item keys: {list(items[0].keys())}")
            logger.debug(f"[RapidAPI] first item dump:\n{json.dumps(items[0], indent=2, default=str)[:2000]}")

        posts = []
        for item in items:
            cap     = item.get("caption") or {}
            caption = cap.get("text", "") if isinstance(cap, dict) else str(cap or "")
            image   = _extract_image_rapidapi(item, username)

            code     = item.get("code") or item.get("shortcode") or ""
            post_url = (f"https://www.instagram.com/p/{code}/"
                        if code else f"https://www.instagram.com/{username}/")

            logger.info(f"[RapidAPI] post: url={post_url[:60]} image={'YES' if image else 'NO'} caption_len={len(caption)}")

            posts.append({
                "caption":   caption,
                "image_url": image,
                "post_url":  post_url,
                "timestamp": str(item.get("taken_at", "")),
                "username":  username,
                "_raw":      item,
            })

        logger.info(f"[RapidAPI] done: {len(posts)} posts from @{username}")
        return posts

    except requests.HTTPError as e:
        logger.error(f"[RapidAPI] HTTP {e.response.status_code}: {e.response.text[:400]}")
        return []
    except Exception as e:
        logger.error(f"[RapidAPI] exception: {e}", exc_info=True)
        return []


# ── Demo data ─────────────────────────────────────────────────────
def _demo_posts(username: str) -> list:
    logger.warning(f"No API keys — returning {MAX_POSTS} demo posts for @{username}")
    demos = [
        {
            "caption": (
                "🎉 PARTY ALERT! Join us this Saturday at Club Noir! "
                "Doors open at 23:00. Entry: 500 MKD. "
                "Reservations: +389 70 123 456. "
                "Location: Bulevar Partizanski Odredi 59, Skopje. "
                "House & Techno by DJ Shadow. Dress code: Elegant. 18+. "
                "#nightlife #party #skopje"
            ),
            "image_url": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=1200",
            "post_url":  f"https://www.instagram.com/{username}/",
            "timestamp": "2025-01-15T21:00:00",
            "username":  username,
        },
        {
            "caption": (
                "🔥 NEW YEAR SPECIAL at Vertigo Club! Date: December 31st. "
                "Open bar 22:00–01:00. Ticket: 1500 MKD. "
                "Reservations: +389 78 987 654. "
                "Address: Ul. Makedonija 12, Skopje. DJ Marco + Live Act. "
                "#newyear #party #skopjenightlife"
            ),
            "image_url": "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?w=1200",
            "post_url":  f"https://www.instagram.com/{username}/",
            "timestamp": "2025-01-10T18:00:00",
            "username":  username,
        },
        {
            "caption": (
                "✨ LADIES NIGHT every Friday at Club Euphoria! "
                "Free entry for ladies before midnight. Men: 300 MKD. "
                "Starts 22:30. TC Bunjakovec, Skopje. "
                "Table reservations: +389 71 555 777. R&B & Hip-Hop. 21+. "
                "#ladiesnight #euphoria #friday"
            ),
            "image_url": "https://images.unsplash.com/photo-1429962714451-bb934ecdc4ec?w=1200",
            "post_url":  f"https://www.instagram.com/{username}/",
            "timestamp": "2025-01-08T15:00:00",
            "username":  username,
        },
        {
            "caption": (
                "🎶 TECHNO NIGHT at Industrial Club! Saturday 25 January. "
                "Doors: 00:00. Entry: 400 MKD. "
                "Lineup: DJ Vortex b2b DJ Pulse. 18+. "
                "Reservations: +389 75 333 111. Ul. Industriska 5, Skopje. "
                "#techno #industrial #skopje"
            ),
            "image_url": "https://images.unsplash.com/photo-1598387993441-a364f854c3e1?w=1200",
            "post_url":  f"https://www.instagram.com/{username}/",
            "timestamp": "2025-01-07T12:00:00",
            "username":  username,
        },
        {
            "caption": (
                "💜 CARNIVAL PARTY at Club Mirage! February 8th. "
                "Doors: 22:00. Entry: 600 MKD. "
                "Reservations: +389 76 444 222. Bulevar ASNOM 25, Skopje. "
                "Commercial & House. Dress code: Costume. 18+. "
                "#carnival #mirage #costume #party"
            ),
            "image_url": "https://images.unsplash.com/photo-1545128485-c400e7702796?w=1200",
            "post_url":  f"https://www.instagram.com/{username}/",
            "timestamp": "2025-01-06T09:00:00",
            "username":  username,
        },
    ]
    return demos[:MAX_POSTS]


# ── Public entry point ────────────────────────────────────────────
def scrape_profile(username: str) -> list:
    username = username.strip().lstrip("@")

    if _token():
        posts = _scrape_apify(username)
        if posts:
            # Strip _raw before returning to keep memory clean
            return [{k: v for k, v in p.items() if k != "_raw"} for p in posts]
        logger.warning("[Apify] 0 results — trying RapidAPI")

    if _rapidapi_key():
        posts = _scrape_rapidapi(username)
        if posts:
            return [{k: v for k, v in p.items() if k != "_raw"} for p in posts]
        logger.warning("[RapidAPI] 0 results — using demo data")

    return _demo_posts(username)


def scrape_profile_raw(username: str) -> list:
    """Same as scrape_profile but keeps _raw field — used by the debug endpoint."""
    username = username.strip().lstrip("@")
    if _token():
        posts = _scrape_apify(username)
        if posts:
            return posts
    if _rapidapi_key():
        posts = _scrape_rapidapi(username)
        if posts:
            return posts
    return _demo_posts(username)