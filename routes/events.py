from flask import Blueprint, render_template, request, jsonify, Response, abort, session
from models import Event, ScrapedProfile
from database import db
from services import scrape_profile, batch_extract_events
from utils.logger import setup_logger
from utils.archiver import auto_archive_past_events, parse_and_set_event_date
from datetime import datetime
import os
import traceback
import requests as req

events_bp = Blueprint('events', __name__)
logger = setup_logger()

EVENTS_PER_PAGE = 12


@events_bp.route('/')
def index():
    genre  = request.args.get('genre', '')
    search = request.args.get('q', '')
    page   = max(request.args.get('page', 1, type=int), 1)

    # Public page: only show active (non-archived) events
    query = Event.query.filter(Event.is_archived == False)

    if genre:
        query = query.filter(Event.genre.ilike(f'%{genre}%'))
    if search:
        query = query.filter(
            (Event.title.ilike(f'%{search}%'))    |
            (Event.venue.ilike(f'%{search}%'))    |
            (Event.location.ilike(f'%{search}%')) |
            (Event.description.ilike(f'%{search}%'))
        )

    pagination = query.order_by(Event.scraped_at.desc()).paginate(
        page=page, per_page=EVENTS_PER_PAGE, error_out=False
    )
    genres_raw = (db.session.query(Event.genre)
                  .filter(Event.genre != None, Event.is_archived == False)
                  .distinct().all())
    genre_list = sorted(set(g[0] for g in genres_raw if g[0]))

    return render_template('events.html',
                           events=pagination.items,
                           pagination=pagination,
                           genres=genre_list,
                           current_genre=genre,
                           search_query=search,
                           page=page,
                           is_admin=session.get('is_admin', False))


@events_bp.route('/scrape', methods=['POST'])
def scrape():
    """Admin-only. Rejects non-admin sessions with 403."""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

    try:
        data      = request.get_json(silent=True) or {}
        usernames = data.get('usernames') or []

        if not usernames:
            profiles  = ScrapedProfile.query.filter_by(is_active=True).all()
            usernames = [p.username for p in profiles]

        if not usernames:
            usernames = ['demo_nightlife']

        logger.info(f"[scrape] admin triggered for: {usernames}")

        all_posts = []
        for username in usernames:
            try:
                posts = scrape_profile(username)
                all_posts.extend(posts)
                logger.info(f"[scrape] @{username} → {len(posts)} posts")
            except Exception as e:
                logger.error(f"[scrape] @{username} failed: {e}")

            profile = ScrapedProfile.query.filter_by(username=username).first()
            if profile:
                profile.last_scraped = datetime.utcnow()
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

        logger.info(f"[scrape] total posts: {len(all_posts)}")

        try:
            events_data = batch_extract_events(all_posts)
        except Exception as e:
            logger.error(f"[scrape] extraction failed: {e}")
            events_data = []

        saved = 0
        for ev in events_data:
            try:
                post_url = ev.get('instagram_post_url') or ''
                if post_url and Event.query.filter_by(instagram_post_url=post_url).first():
                    continue

                # Parse the AI date string into a real date object
                event_date = parse_and_set_event_date(ev)

                event = Event(
                    title              = (ev.get('title') or 'Nightlife Event')[:200],
                    venue              = ev.get('venue'),
                    location           = ev.get('location'),
                    date               = ev.get('date'),
                    event_date         = event_date,
                    start_time         = ev.get('start_time'),
                    entry_price        = ev.get('entry_price'),
                    phone              = ev.get('phone'),
                    description        = ev.get('description'),
                    genre              = ev.get('genre'),
                    dress_code         = ev.get('dress_code'),
                    age_limit          = ev.get('age_limit'),
                    instagram_profile  = ev.get('instagram_profile'),
                    instagram_post_url = post_url,
                    image_url          = ev.get('image_url'),
                    raw_caption        = ev.get('raw_caption'),
                    # If the parsed date is already in the past, archive immediately
                    is_archived        = event_date is not None and event_date < datetime.utcnow().date(),
                    archived_at        = datetime.utcnow() if (
                        event_date is not None and event_date < datetime.utcnow().date()
                    ) else None,
                )
                db.session.add(event)
                db.session.flush()
                saved += 1
            except Exception as e:
                logger.error(f"[scrape] save failed '{ev.get('title')}': {e}")
                db.session.rollback()

        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"[scrape] commit failed: {e}")
            db.session.rollback()

        # Run auto-archive after every scrape
        auto_archived = auto_archive_past_events(db)
        logger.info(f"[scrape] saved={saved} auto_archived={auto_archived}")

        return jsonify({
            'success':       True,
            'scraped_posts': len(all_posts),
            'events_found':  len(events_data),
            'events_saved':  saved,
            'auto_archived': auto_archived,
        })

    except Exception as e:
        logger.error(f"[scrape] unhandled: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route('/scrape/test')
def scrape_test():
    if not session.get('is_admin'):
        return jsonify({'error': 'Admin only'}), 403
    gemini_key  = os.environ.get('GEMINI_API_KEY', '').strip()
    apify_token = os.environ.get('APIFY_TOKEN',    '').strip()
    rapidapi    = os.environ.get('RAPIDAPI_KEY',   '').strip()
    result = {
        'env': {
            'GEMINI_API_KEY': f"{'SET' if gemini_key  else 'NOT SET'} ({len(gemini_key)} chars)",
            'APIFY_TOKEN':    f"{'SET' if apify_token else 'NOT SET'} ({len(apify_token)} chars)",
            'RAPIDAPI_KEY':   f"{'SET' if rapidapi    else 'NOT SET'} ({len(rapidapi)} chars)",
        },
        'gemini_test':    None,
        'profiles_in_db': ScrapedProfile.query.count(),
    }
    if gemini_key:
        try:
            r = req.post(
                'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent',
                json={'contents': [{'parts': [{'text': 'Reply: OK'}]}]},
                params={'key': gemini_key}, timeout=15,
            )
            result['gemini_test'] = 'OK' if r.status_code == 200 else f'FAILED {r.status_code}'
        except Exception as e:
            result['gemini_test'] = f'EXCEPTION: {e}'
    return jsonify(result)


@events_bp.route('/scrape/debug/<username>')
def scrape_debug(username):
    if not session.get('is_admin'):
        return jsonify({"error": "Admin only"}), 403
    from services.scraper_service import scrape_profile_raw
    try:
        posts = scrape_profile_raw(username.strip().lstrip("@"))
        out = []
        for p in posts:
            raw = p.get("_raw", {})
            out.append({
                "username":        p.get("username"),
                "caption_preview": (p.get("caption") or "")[:120],
                "image_url":       p.get("image_url"),
                "post_url":        p.get("post_url"),
                "image_found":     bool(p.get("image_url")),
                "raw_keys":        list(raw.keys()) if raw else [],
                "raw_image_fields": {
                    k: (str(v)[:200] if isinstance(v, str) else type(v).__name__)
                    for k, v in raw.items()
                    if any(w in k.lower() for w in
                           ("image","display","thumb","photo","media","url","cover","src","carousel","child"))
                },
            })
        return jsonify({"profile": username, "post_count": len(out), "posts": out})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@events_bp.route('/api/list')
def api_list():
    events = Event.query.filter_by(is_archived=False).order_by(Event.scraped_at.desc()).all()
    return jsonify([e.to_dict() for e in events])


@events_bp.route('/<int:event_id>')
def detail(event_id):
    event = Event.query.get_or_404(event_id)
    return render_template('event_detail.html', event=event)


@events_bp.route('/image-proxy')
def image_proxy():
    url = request.args.get("url", "").strip()
    if not url:
        abort(400)
    allowed = ("cdninstagram.com", "fbcdn.net", "instagram.com", "scontent")
    if not any(d in url for d in allowed):
        abort(403)
    try:
        r = req.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer":    "https://www.instagram.com/",
        })
        r.raise_for_status()
        return Response(r.content,
                        content_type=r.headers.get("Content-Type", "image/jpeg"),
                        headers={"Cache-Control": "public, max-age=3600"})
    except Exception as e:
        logger.error(f"[image-proxy] {url[:80]}: {e}")
        abort(502)