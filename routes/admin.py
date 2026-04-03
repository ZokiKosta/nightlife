from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import ScrapedProfile, Event
from database import db
from utils.logger import setup_logger

admin_bp = Blueprint('admin', __name__)
logger = setup_logger()

ADMIN_PASSWORD = "nightlife2025"  # Change this / move to env var


@admin_bp.route('/', methods=['GET', 'POST'])
def index():
    if not session.get('is_admin'):
        return redirect(url_for('admin.login'))

    profiles = ScrapedProfile.query.order_by(ScrapedProfile.created_at.desc()).all()
    events = Event.query.order_by(Event.created_at.desc()).all()
    return render_template('admin.html', profiles=profiles, events=events)


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin.index'))
        flash('Wrong password', 'danger')
    return render_template('admin_login.html')


@admin_bp.route('/logout')
def logout():
    session.pop('is_admin', None)
    return redirect(url_for('home.index'))


@admin_bp.route('/profiles/add', methods=['POST'])
def add_profile():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    username = request.form.get('username', '').strip().lstrip('@')
    display_name = request.form.get('display_name', '').strip()

    if not username:
        flash('Username required', 'danger')
        return redirect(url_for('admin.index'))

    existing = ScrapedProfile.query.filter_by(username=username).first()
    if existing:
        flash(f'Profile @{username} already exists', 'warning')
        return redirect(url_for('admin.index'))

    profile = ScrapedProfile(username=username, display_name=display_name or username)
    db.session.add(profile)
    db.session.commit()
    flash(f'Added profile @{username}', 'success')
    logger.info(f"Admin added profile @{username}")
    return redirect(url_for('admin.index'))


@admin_bp.route('/profiles/<int:profile_id>/delete', methods=['POST'])
def delete_profile(profile_id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    profile = ScrapedProfile.query.get_or_404(profile_id)
    db.session.delete(profile)
    db.session.commit()
    flash(f'Deleted profile @{profile.username}', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/events/<int:event_id>/delete', methods=['POST'])
def delete_event(event_id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    event = Event.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    flash(f'Deleted event: {event.title}', 'success')
    return redirect(url_for('admin.index'))