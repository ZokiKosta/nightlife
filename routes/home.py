from flask import Blueprint, render_template
from models import Event, ScrapedProfile
from database import db

home_bp = Blueprint('home', __name__)


@home_bp.route('/')
@home_bp.route('/home')
def index():
    total_events = Event.query.count()
    total_profiles = ScrapedProfile.query.filter_by(is_active=True).count()
    upcoming_events = Event.query.order_by(Event.scraped_at.desc()).limit(3).all()
    return render_template('home.html',
                           total_events=total_events,
                           total_profiles=total_profiles,
                           upcoming_events=upcoming_events)