"""
Authentication Decorators - Protect routes with role-based access control

SOLID: Single Responsibility - Only handles route protection

Decorators:
    @login_required     - Requires any authenticated user
    @admin_required     - Requires admin role
    @viewer_required    - Requires viewer or admin role

Usage:
    from routes.auth_decorators import login_required, admin_required

    @app.route('/protected')
    @login_required
    def protected_route():
        pass

    @app.route('/admin-only')
    @admin_required
    def admin_route():
        pass
"""
import os
import logging
from functools import wraps
from flask import session, redirect, url_for, request, flash, jsonify, g

logger = logging.getLogger(__name__)


def is_auth_disabled() -> bool:
    """Check if authentication is disabled (development mode)."""
    return os.environ.get('AUTH_DISABLED', '').lower() == 'true'


def get_current_user() -> dict:
    """Get current user from session or development default."""
    if is_auth_disabled():
        return {
            'email': 'dev@localhost',
            'name': 'Developer',
            'role': 'admin'
        }

    return session.get('user', {})


def is_api_request() -> bool:
    """Check if request is an API call (expects JSON response)."""
    return (
        request.path.startswith('/api/') or
        request.headers.get('Accept', '').startswith('application/json') or
        request.is_json
    )


def login_required(f):
    """
    Decorator to require authentication for a route.

    Redirects to login page if not authenticated.
    Returns 401 JSON for API requests.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()

        if not user:
            if is_api_request():
                return jsonify({
                    'success': False,
                    'error': 'Authentication required'
                }), 401

            # Store current URL for redirect after login
            return redirect(url_for('auth.login', next=request.url))

        # Store user in g for easy access in route
        g.user = user
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """
    Decorator to require admin role for a route.

    Returns 403 if user is not an admin.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()

        if not user:
            if is_api_request():
                return jsonify({
                    'success': False,
                    'error': 'Authentication required'
                }), 401
            return redirect(url_for('auth.login', next=request.url))

        if user.get('role') != 'admin':
            logger.warning(f"Admin access denied for {user.get('email')}")

            if is_api_request():
                return jsonify({
                    'success': False,
                    'error': 'Admin access required'
                }), 403

            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('dashboard.index'))

        g.user = user
        return f(*args, **kwargs)

    return decorated_function


def viewer_required(f):
    """
    Decorator to require viewer or admin role for a route.

    Returns 403 if user is not a viewer or admin.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()

        if not user:
            if is_api_request():
                return jsonify({
                    'success': False,
                    'error': 'Authentication required'
                }), 401
            return redirect(url_for('auth.login', next=request.url))

        if user.get('role') not in ['admin', 'viewer']:
            logger.warning(f"Viewer access denied for {user.get('email')}")

            if is_api_request():
                return jsonify({
                    'success': False,
                    'error': 'Viewer access required'
                }), 403

            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('dashboard.index'))

        g.user = user
        return f(*args, **kwargs)

    return decorated_function


# =============================================================================
# Helper Functions
# =============================================================================

def is_admin() -> bool:
    """Check if current user is an admin."""
    user = get_current_user()
    return user.get('role') == 'admin'


def is_viewer() -> bool:
    """Check if current user is a viewer or admin."""
    user = get_current_user()
    return user.get('role') in ['admin', 'viewer']


def is_authenticated() -> bool:
    """Check if user is authenticated."""
    return bool(get_current_user())


def current_user_email() -> str:
    """Get current user's email."""
    user = get_current_user()
    return user.get('email', '')


def current_user_name() -> str:
    """Get current user's name."""
    user = get_current_user()
    return user.get('name', 'Guest')


def current_user_role() -> str:
    """Get current user's role."""
    user = get_current_user()
    return user.get('role', '')
