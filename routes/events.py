from flask import Blueprint, render_template, request, jsonify
from models import Event, ScrapedProfile
from database import db
from services import scrape_profile, batch_extract_events
from utils.logger import setup_logger
from datetime import datetime

events_bp = Blueprint('events', __name__)
logger = setup_logger()


@events_bp.route('/')
def index():
    genre = request.args.get('genre', '')
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

    events = query.order_by(Event.scraped_at.desc()).all()
    genres = db.session.query(Event.genre).filter(Event.genre != None).distinct().all()
    genre_list = sorted(set(g[0] for g in genres if g[0]))

    return render_template('events.html',
                           events=events,
                           genres=genre_list,
                           current_genre=genre,
                           search_query=search)


@events_bp.route('/scrape', methods=['POST'])
def scrape():
    """Trigger scraping of Instagram profiles and process with Gemini."""
    data = request.get_json() or {}
    usernames = data.get('usernames', [])

    if not usernames:
        # Scrape all active profiles in DB
        profiles = ScrapedProfile.query.filter_by(is_active=True).all()
        usernames = [p.username for p in profiles]

    if not usernames:
        return jsonify({'error': 'No profiles to scrape'}), 400

    all_posts = []
    for username in usernames:
        posts = scrape_profile(username, max_posts=10)
        all_posts.extend(posts)

        # Update last_scraped
        profile = ScrapedProfile.query.filter_by(username=username).first()
        if profile:
            profile.last_scraped = datetime.utcnow()
            db.session.commit()

    events_data = batch_extract_events(all_posts)

    saved = 0
    for ev in events_data:
        existing = Event.query.filter_by(
            instagram_post_url=ev.get('instagram_post_url', ''),
        ).first()

        if not existing or not ev.get('instagram_post_url'):
            event = Event(
                title=ev.get('title') or 'Nightlife Event',
                venue=ev.get('venue'),
                location=ev.get('location'),
                date=ev.get('date'),
                start_time=ev.get('start_time'),
                entry_price=ev.get('entry_price'),
                phone=ev.get('phone'),
                description=ev.get('description'),
                genre=ev.get('genre'),
                dress_code=ev.get('dress_code'),
                age_limit=ev.get('age_limit'),
                instagram_profile=ev.get('instagram_profile'),
                instagram_post_url=ev.get('instagram_post_url'),
                image_url=ev.get('image_url'),
                raw_caption=ev.get('raw_caption'),
            )
            db.session.add(event)
            saved += 1

    db.session.commit()
    logger.info(f"Saved {saved} new events from scrape")

    return jsonify({
        'success': True,
        'scraped_posts': len(all_posts),
        'events_found': len(events_data),
        'events_saved': saved,
    })


@events_bp.route('/api/list')
def api_list():
    events = Event.query.order_by(Event.scraped_at.desc()).all()
    return jsonify([e.to_dict() for e in events])


@events_bp.route('/<int:event_id>')
def detail(event_id):
    event = Event.query.get_or_404(event_id)
    return render_template('event_detail.html', event=event)