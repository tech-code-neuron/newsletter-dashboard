"""
Domain-based routing middleware.

CRITICAL ARCHITECTURE:
- reitsheet.co = PUBLIC (newsletter, archives, no auth)
- app.reitsheet.co = ADMIN (dashboard, publisher, requires auth)

Same Flask app serves both domains. This middleware ensures routes
are only accessible on the correct domain.
"""

from functools import wraps
from flask import request, abort, redirect

PUBLIC_DOMAIN = 'reitsheet.co'
ADMIN_DOMAIN = 'app.reitsheet.co'


def get_host():
    """Get the host without port."""
    return request.host.split(':')[0]


def is_public_domain():
    """Check if current request is on public domain (reitsheet.co).

    Also checks X-Forwarded-Host header for CloudFront requests.
    """
    # Check direct host
    if get_host() == PUBLIC_DOMAIN:
        return True
    # Check CloudFront forwarded host header
    forwarded_host = request.headers.get('X-Forwarded-Host', '')
    return forwarded_host == PUBLIC_DOMAIN


def is_admin_domain():
    """Check if current request is on admin domain (app.reitsheet.co).

    Returns False if X-Forwarded-Host indicates public domain.
    """
    # If forwarded from public domain via CloudFront, not admin
    forwarded_host = request.headers.get('X-Forwarded-Host', '')
    if forwarded_host == PUBLIC_DOMAIN:
        return False
    return get_host() == ADMIN_DOMAIN


def public_only(f):
    """
    Decorator: Route only accessible on reitsheet.co (public domain).

    If accessed on app.reitsheet.co:
    - Root path (/) redirects to /dashboard (admin landing)
    - Other paths redirect to reitsheet.co equivalent

    Usage:
        @public_bp.route('/')
        @public_only
        def home():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if is_admin_domain():
            # Admin domain hitting root → redirect to dashboard
            if request.path == '/':
                return redirect('/dashboard', code=302)
            # Other public routes → redirect to public domain
            return redirect(f'https://{PUBLIC_DOMAIN}{request.path}', code=302)
        return f(*args, **kwargs)
    return decorated


def admin_only(f):
    """
    Decorator: Route only accessible on app.reitsheet.co (admin domain).

    If accessed on reitsheet.co, returns 404.

    Usage:
        @dashboard_bp.route('/dashboard')
        @admin_only
        @login_required
        def dashboard():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if is_public_domain():
            # Public domain hitting admin route → 404
            abort(404)
        return f(*args, **kwargs)
    return decorated
