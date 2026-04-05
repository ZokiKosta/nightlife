from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import ScrapedProfile, Event
from database import db
from utils.logger import setup_logger
from utils.archiver import auto_archive_past_events
from sqlalchemy import or_
from datetime import datetime

admin_bp = Blueprint('admin', __name__)
logger   = setup_logger()

ADMIN_PASSWORD    = "nightlife2025"
PROFILES_PER_PAGE = 10
EVENTS_PER_PAGE   = 15


def _require_admin():
    return session.get('is_admin')


@admin_bp.route('/', methods=['GET'])
def index():
    if not _require_admin():
        return redirect(url_for('admin.login'))

    # Run auto-archive on every admin page load
    auto_archive_past_events(db)

    search = request.args.get('q', '').strip()
    p_page = request.args.get('p_page', 1, type=int)
    e_page = request.args.get('e_page', 1, type=int)
    a_page = request.args.get('a_page', 1, type=int)

    # ── Profiles ──────────────────────────────────────────────────
    p_query = ScrapedProfile.query
    if search:
        p_query = p_query.filter(or_(
            ScrapedProfile.username.ilike(f'%{search}%'),
            ScrapedProfile.display_name.ilike(f'%{search}%'),
        ))
    profiles_pg = p_query.order_by(ScrapedProfile.created_at.desc()).paginate(
        page=p_page, per_page=PROFILES_PER_PAGE, error_out=False
    )

    # ── Active Events ─────────────────────────────────────────────
    e_query = Event.query.filter(Event.is_archived == False)
    if search:
        e_query = e_query.filter(or_(
            Event.title.ilike(f'%{search}%'),
            Event.venue.ilike(f'%{search}%'),
            Event.instagram_profile.ilike(f'%{search}%'),
            Event.location.ilike(f'%{search}%'),
        ))
    events_pg = e_query.order_by(Event.created_at.desc()).paginate(
        page=e_page, per_page=EVENTS_PER_PAGE, error_out=False
    )

    # ── Archived Events ───────────────────────────────────────────
    a_query = Event.query.filter(Event.is_archived == True)
    if search:
        a_query = a_query.filter(or_(
            Event.title.ilike(f'%{search}%'),
            Event.venue.ilike(f'%{search}%'),
            Event.instagram_profile.ilike(f'%{search}%'),
        ))
    archived_pg = a_query.order_by(Event.archived_at.desc()).paginate(
        page=a_page, per_page=EVENTS_PER_PAGE, error_out=False
    )

    return render_template('admin.html',
                           profiles_pg  = profiles_pg,
                           events_pg    = events_pg,
                           archived_pg  = archived_pg,
                           search_query = search,
                           p_page=p_page, e_page=e_page, a_page=a_page)


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password', '') == ADMIN_PASSWORD:
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
    if not _require_admin():
        return jsonify({'error': 'Unauthorized'}), 401
    username     = request.form.get('username', '').strip().lstrip('@')
    display_name = request.form.get('display_name', '').strip()
    if not username:
        flash('Username required', 'danger')
        return redirect(url_for('admin.index'))
    if ScrapedProfile.query.filter_by(username=username).first():
        flash(f'@{username} already exists', 'warning')
        return redirect(url_for('admin.index'))
    db.session.add(ScrapedProfile(username=username, display_name=display_name or username))
    db.session.commit()
    flash(f'Added @{username}', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/profiles/<int:profile_id>/delete', methods=['POST'])
def delete_profile(profile_id):
    if not _require_admin():
        return jsonify({'error': 'Unauthorized'}), 401
    p = ScrapedProfile.query.get_or_404(profile_id)
    db.session.delete(p)
    db.session.commit()
    flash(f'Deleted @{p.username}', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/events/<int:event_id>/delete', methods=['POST'])
def delete_event(event_id):
    if not _require_admin():
        return jsonify({'error': 'Unauthorized'}), 401
    ev = Event.query.get_or_404(event_id)
    db.session.delete(ev)
    db.session.commit()
    flash(f'Deleted: {ev.title}', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/events/<int:event_id>/archive', methods=['POST'])
def archive_event(event_id):
    """Manually archive an active event."""
    if not _require_admin():
        return jsonify({'error': 'Unauthorized'}), 401
    ev = Event.query.get_or_404(event_id)
    ev.archive()
    db.session.commit()
    flash(f'Archived: {ev.title}', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/events/<int:event_id>/unarchive', methods=['POST'])
def unarchive_event(event_id):
    """Restore an archived event back to active."""
    if not _require_admin():
        return jsonify({'error': 'Unauthorized'}), 401
    ev = Event.query.get_or_404(event_id)
    ev.is_archived = False
    ev.archived_at = None
    db.session.commit()
    flash(f'Restored: {ev.title}', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/archive/run', methods=['POST'])
def run_archive():
    """Manually trigger auto-archive check."""
    if not _require_admin():
        return jsonify({'error': 'Unauthorized'}), 401
    count = auto_archive_past_events(db)
    flash(f'Auto-archived {count} past event{"s" if count != 1 else ""}', 'info')
    return redirect(url_for('admin.index'))