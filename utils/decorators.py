from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify


def login_required(f):
    """Redirect to login if user not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('home.login', next=request.url))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Restrict route to admin users only."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Admin access required.', 'danger')
            return redirect(url_for('home.index'))
        return f(*args, **kwargs)
    return decorated


def api_key_required(f):
    """Protect API endpoints with a simple key."""
    @wraps(f)
    def decorated(*args, **kwargs):
        import os
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        expected = os.environ.get('API_SECRET_KEY', 'dev-secret')
        if key != expected:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated