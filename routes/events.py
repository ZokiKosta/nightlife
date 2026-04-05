from flask import Blueprint, render_template, request, jsonify
from models import Event, ScrapedProfile
from database import db
from services import scrape_profile, batch_extract_events
from utils.logger import setup_logger
from datetime import datetime
import os
import traceback

events_bp = Blueprint('events', __name__)
logger = setup_logger()


@events_bp.route('/')
def index():
    genre  = request.args.get('genre', '')
    search = request.args.get('q', '')

    query = Event.query
    if genre:
        query = query.filter(Event.genre.ilike(f'%{genre}%'))
    if search:
        query = query.filter(
            (Event.title.ilike(f'%{search}%')) |
            (Event.venue.ilike(f'%{search}%')) |
            (Event.location.ilike(f'%{search}%'))
        )

    events     = query.order_by(Event.scraped_at.desc()).all()
    genres_raw = db.session.query(Event.genre).filter(Event.genre != None).distinct().all()
    genre_list = sorted(set(g[0] for g in genres_raw if g[0]))

    return render_template('events.html',
                           events=events,
                           genres=genre_list,
                           current_genre=genre,
                           search_query=search)


@events_bp.route('/scrape', methods=['POST'])
def scrape():
    """
    POST /events/scrape
    Body (optional): { "usernames": ["clubname1", "clubname2"] }
    If usernames is empty, scrapes all active profiles in DB.
    If DB has no profiles either, uses demo data so the UI always works.
    """
    try:
        data      = request.get_json(silent=True) or {}
        usernames = data.get('usernames') or []

        # Fall back to DB profiles
        if not usernames:
            profiles  = ScrapedProfile.query.filter_by(is_active=True).all()
            usernames = [p.username for p in profiles]

        # If still empty, use a demo username so demo data flows through
        if not usernames:
            usernames = ['demo_nightlife']

        logger.info(f"[scrape] starting for: {usernames}")

        all_posts = []
        for username in usernames:
            try:
                posts = scrape_profile(username)
                all_posts.extend(posts)
                logger.info(f"[scrape] @{username} → {len(posts)} posts")
            except Exception as e:
                logger.error(f"[scrape] failed for @{username}: {e}")
                # continue with other usernames

            # update last_scraped timestamp
            profile = ScrapedProfile.query.filter_by(username=username).first()
            if profile:
                profile.last_scraped = datetime.utcnow()
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

        logger.info(f"[scrape] total posts collected: {len(all_posts)}")

        # Run Gemini / regex extraction
        try:
            events_data = batch_extract_events(all_posts)
        except Exception as e:
            logger.error(f"[scrape] batch_extract_events failed: {e}")
            events_data = []

        logger.info(f"[scrape] events extracted: {len(events_data)}")

        # Save to DB
        saved = 0
        for ev in events_data:
            try:
                post_url = ev.get('instagram_post_url') or ''
                # avoid exact duplicates
                if post_url:
                    existing = Event.query.filter_by(instagram_post_url=post_url).first()
                    if existing:
                        continue

                event = Event(
                    title           = (ev.get('title') or 'Nightlife Event')[:200],
                    venue           = ev.get('venue'),
                    location        = ev.get('location'),
                    date            = ev.get('date'),
                    start_time      = ev.get('start_time'),
                    entry_price     = ev.get('entry_price'),
                    phone           = ev.get('phone'),
                    description     = ev.get('description'),
                    genre           = ev.get('genre'),
                    dress_code      = ev.get('dress_code'),
                    age_limit       = ev.get('age_limit'),
                    instagram_profile  = ev.get('instagram_profile'),
                    instagram_post_url = post_url,
                    image_url       = ev.get('image_url'),
                    raw_caption     = ev.get('raw_caption'),
                )
                db.session.add(event)
                db.session.flush()   # catch DB errors per-row
                saved += 1
            except Exception as e:
                logger.error(f"[scrape] could not save event '{ev.get('title')}': {e}")
                db.session.rollback()

        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"[scrape] commit failed: {e}")
            db.session.rollback()

        logger.info(f"[scrape] saved {saved} new events")
        return jsonify({
            'success':       True,
            'scraped_posts': len(all_posts),
            'events_found':  len(events_data),
            'events_saved':  saved,
        })

    except Exception as e:
        logger.error(f"[scrape] unhandled exception: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route('/scrape/test')
def scrape_test():
    """
    GET /events/scrape/test
    Quick diagnostic — shows which API keys are loaded and tests Gemini.
    Visit this in the browser if scraping seems stuck.
    """
    import requests as req

    gemini_key  = os.environ.get('GEMINI_API_KEY', '').strip()
    apify_token = os.environ.get('APIFY_TOKEN',    '').strip()
    rapidapi    = os.environ.get('RAPIDAPI_KEY',   '').strip()

    result = {
        'env': {
            'GEMINI_API_KEY': f"{'SET' if gemini_key  else 'NOT SET'} ({len(gemini_key)} chars)",
            'APIFY_TOKEN':    f"{'SET' if apify_token else 'NOT SET'} ({len(apify_token)} chars)",
            'RAPIDAPI_KEY':   f"{'SET' if rapidapi    else 'NOT SET'} ({len(rapidapi)} chars)",
        },
        'gemini_test': None,
        'profiles_in_db': ScrapedProfile.query.count(),
    }

    # Quick Gemini ping
    if gemini_key:
        try:
            r = req.post(
                'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent',
                json={'contents': [{'parts': [{'text': 'Reply with just: OK'}]}]},
                params={'key': gemini_key},
                timeout=15,
            )
            if r.status_code == 200:
                result['gemini_test'] = 'OK - API key works'
            else:
                result['gemini_test'] = f'FAILED {r.status_code}: {r.text[:200]}'
        except Exception as e:
            result['gemini_test'] = f'EXCEPTION: {e}'
    else:
        result['gemini_test'] = 'SKIPPED - no key'

    return jsonify(result)


@events_bp.route('/api/list')
def api_list():
    events = Event.query.order_by(Event.scraped_at.desc()).all()
    return jsonify([e.to_dict() for e in events])


@events_bp.route('/<int:event_id>')
def detail(event_id):
    event = Event.query.get_or_404(event_id)
    return render_template('event_detail.html', event=event)


@events_bp.route('/scrape/debug/<username>')
def scrape_debug(username):
    """
    GET /events/scrape/debug/<username>
    e.g. /events/scrape/debug/clubnoir_skopje

    Returns the raw API response for one profile — shows exact field names
    so we can verify the image URL field is being read correctly.
    Only works in debug mode (Flask debug=True).
    """
    from services.scraper_service import scrape_profile_raw
    import os

    if not os.environ.get("FLASK_DEBUG") and not os.environ.get("DEBUG"):
        # Also allow if running with app.run(debug=True)
        from flask import current_app
        if not current_app.debug:
            return jsonify({"error": "Only available in debug mode"}), 403

    try:
        posts = scrape_profile_raw(username.strip().lstrip("@"))
        # Return sanitised view: show all fields including image_url and _raw keys
        out = []
        for p in posts:
            raw   = p.get("_raw", {})
            entry = {
                "username":       p.get("username"),
                "caption_preview": (p.get("caption") or "")[:120],
                "image_url":      p.get("image_url"),
                "post_url":       p.get("post_url"),
                "image_found":    bool(p.get("image_url")),
                "raw_keys":       list(raw.keys()) if raw else [],
                # show image-related raw fields only
                "raw_image_fields": {
                    k: (str(v)[:200] if isinstance(v, str) else type(v).__name__)
                    for k, v in raw.items()
                    if any(word in k.lower() for word in
                           ("image", "display", "thumb", "photo", "media", "url",
                            "cover", "src", "carousel", "child", "sidecar"))
                },
            }
            out.append(entry)

        return jsonify({
            "profile":    username,
            "api_used":   "Apify" if os.environ.get("APIFY_TOKEN") else
                          "RapidAPI" if os.environ.get("RAPIDAPI_KEY") else "demo",
            "post_count": len(out),
            "posts":      out,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@events_bp.route('/image-proxy')
def image_proxy():
    """
    GET /events/image-proxy?url=<instagram_cdn_url>
    Proxies the Instagram CDN image through Flask so expired URLs
    can be re-fetched on demand rather than failing silently.
    Only proxies instagram CDN domains.
    """
    from flask import Response, abort
    import requests as req

    url = request.args.get("url", "").strip()
    if not url:
        abort(400)

    # Whitelist — only proxy known Instagram / Facebook CDN domains
    allowed = (
        "cdninstagram.com",
        "fbcdn.net",
        "instagram.com",
        "scontent",       # scontent-*.cdninstagram.com
    )
    if not any(d in url for d in allowed):
        abort(403)

    try:
        r = req.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.instagram.com/",
        })
        r.raise_for_status()
        return Response(
            r.content,
            content_type=r.headers.get("Content-Type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        logger.error(f"[image-proxy] failed for {url[:80]}: {e}")
        abort(502)