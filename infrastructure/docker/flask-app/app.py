"""
Flask web interface for REIT Newsletter management
REFACTORED: Thin orchestrator with modular blueprint architecture

All routes moved to blueprints in routes/ directory:
- routes/dashboard.py - Dashboard
- routes/companies.py - Company management
- routes/review.py - Relevance review
- routes/actions.py - Background actions
- routes/api.py - API endpoints

SOLID Compliance: Open/Closed Principle
- Add new features by creating new blueprints
- No need to modify this file

ECS Support:
- Health check endpoint at /health
- Graceful shutdown handler for background threads
- Auto-detection of ECS vs local environment
"""
import os
import signal
import sys
import atexit
import logging
from flask import Flask, jsonify, request
from flask_wtf.csrf import CSRFError
from jinja2 import ChainableUndefined
from dotenv import load_dotenv
from config.paths import NEWSLETTERS_DIR
from config.aws_config import aws_config
from config.security import limiter, csrf
from services.scan_manager import get_scan_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Custom URL converter for signed integers (handles negative hash IDs)
from werkzeug.routing import IntegerConverter

class SignedIntConverter(IntegerConverter):
    """URL converter that accepts both positive and negative integers.

    Flask's default 'int' converter only matches positive integers (\d+).
    This is needed because PressReleaseDTO uses hash(url) which can be negative.
    """
    regex = r'-?\d+'  # Matches optional minus sign followed by digits

app.url_map.converters['signed_int'] = SignedIntConverter

# Make templates crash-proof: None.anything returns empty string instead of crashing
# This prevents ALL jinja2.exceptions.UndefinedError for attribute access
app.jinja_env.undefined = ChainableUndefined

# Get secret key from environment or AWS Secrets Manager
app.secret_key = aws_config.flask_secret_key

# Session configuration for HTTPS (SECURITY: Prevent session hijacking)
# SESSION_COOKIE_SECURE: Only send cookies over HTTPS (prevents man-in-the-middle)
# SESSION_COOKIE_HTTPONLY: Prevent JavaScript access to cookies (XSS protection)
# SESSION_COOKIE_SAMESITE: Prevent CSRF attacks
app.config['SESSION_COOKIE_SECURE'] = True  # Require HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Block JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours
app.config['WTF_CSRF_TIME_LIMIT'] = 86400  # 24 hours (match session lifetime)

# Enable CSRF protection for all POST/PUT/DELETE requests
csrf.init_app(app)


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Return JSON for API requests, HTML for browser requests."""
    if (request.is_json or
            request.path.startswith('/api/') or
            request.path.startswith('/publisher/')):
        return jsonify({
            'success': False,
            'error': 'Session expired. Please refresh the page and try again.',
            'csrf_error': True
        }), 400
    return f"Session expired. Please <a href='{request.url}'>refresh the page</a>.", 400

# Enable rate limiting (SECURITY: Prevent brute force and API abuse)
limiter.init_app(app)

# Log environment detection
if aws_config.is_ecs:
    logger.info("Running in ECS environment")
else:
    logger.info("Running in local environment")

# =============================================================================
# STARTUP VALIDATION - Fail fast on missing critical config
# =============================================================================
# Validate email config at startup to prevent silent failures when sending
# This catches missing UNSUBSCRIBE_SECRET before any emails are attempted
try:
    from services.email_sender_service import validate_email_config
    validate_email_config()
    logger.info("Email configuration validated successfully")
except Exception as e:
    logger.error(f"EMAIL CONFIG ERROR: {e}")
    # Don't crash the app - just log loudly so it's visible in logs
    # This allows health checks to pass but makes the issue obvious

# ═══════════════════════════════════════════════════════════
# TEMPLATE FILTERS - Safe date formatting
# ═══════════════════════════════════════════════════════════

@app.template_filter('format_date')
def format_date_filter(date, fmt='%b %d, %Y', default='N/A'):
    """
    Format datetime in Eastern Time.

    Handles multiple input types (datetime, ISO strings, date-only strings).
    Auto-appends " ET" when format includes time components.

    Usage in templates:
        {{ release.published_date|format_date }}                    → 'Mar 14, 2026' or 'N/A'
        {{ release.published_date|format_date('%b %d, %Y %I:%M %p') }} → 'Mar 14, 2026 09:30 AM ET'
        {{ date|format_date('%Y-%m-%d', '') }}                      → '2026-03-14' or '' (for forms)
    """
    from utils.datetime_utils import convert_utc_to_eastern

    if date is None:
        return default
    try:
        # Convert to Eastern Time
        et_date = convert_utc_to_eastern(date)
        if et_date is None:
            return default

        result = et_date.strftime(fmt)

        # Auto-add " ET" when time components present (not for date-only formats)
        if any(x in fmt for x in ['%H', '%I', '%M', '%p']):
            result += ' ET'

        return result
    except (AttributeError, ValueError):
        return default


@app.template_filter('display_title')
def display_title_filter(release):
    """
    Get the best title to display for a press release.

    Uses centralized title_utils.get_display_title() for consistent priority.
    See core/title_utils.py for priority order documentation.
    """
    from core.title_utils import get_display_title
    return get_display_title(release)


@app.template_filter('format_number')
def format_number_filter(value, default='0'):
    """
    Format a number with thousands separators.

    Usage in templates:
        {{ 1234567|format_number }}  → '1,234,567'
        {{ None|format_number }}     → '0'
    """
    if value is None:
        return default
    try:
        return '{:,}'.format(int(value))
    except (ValueError, TypeError):
        return default


@app.template_filter('format_date_short')
def format_date_short_filter(date_str, default=''):
    """
    Format a date string (YYYY-MM-DD) as short month day (e.g., "Mar 14").

    Usage in templates:
        {{ prev_date|format_date_short }}  -> 'Mar 14'
        {{ '2026-03-14'|format_date_short }} -> 'Mar 14'
    """
    if not date_str:
        return default
    try:
        from datetime import datetime
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%b %-d')
    except (ValueError, TypeError):
        return default


@app.template_filter('is_paywalled')
def is_paywalled_filter(url):
    """Check if URL is from a paywalled domain (NYT, WSJ, FT, Bloomberg)."""
    from core.paywall_utils import is_paywalled_url
    return is_paywalled_url(url)


@app.template_filter('access_indicator')
def access_indicator_filter(url):
    """Get access indicator text: (Paywall), (Login Required), or empty."""
    from core.paywall_utils import get_access_indicator
    return get_access_indicator(url)


# ═══════════════════════════════════════════════════════════
# GLOBAL AUTHENTICATION - Require login for ALL pages
# ═══════════════════════════════════════════════════════════

from flask import session, redirect, url_for, request, make_response, g
from middleware.domain_router import is_public_domain
import uuid

@app.before_request
def require_authentication():
    """
    Require authentication for ALL routes except:
    - Public domain (reitsheet.co) - no auth required
    - /health (ALB health check)
    - /login (login page)
    - /auth/* (OAuth callbacks)
    - /static/* (static files)

    Domain architecture:
    - reitsheet.co = PUBLIC (newsletter, archives, no auth)
    - app.reitsheet.co = ADMIN (dashboard, publisher, requires auth)
    """
    # PUBLIC DOMAIN: No auth required for reitsheet.co
    if is_public_domain():
        return None

    # ADMIN DOMAIN (app.reitsheet.co): Check auth
    # Skip auth for these specific paths
    public_paths = ['/', '/health', '/login', '/auth/', '/static/', '/logged-out', '/contact',
                    '/subscribe', '/verify', '/unsubscribe', '/api/subscribe', '/api/unsubscribe',
                    '/privacy', '/track/', '/api/track-click', '/archive/', '/check-email',
                    '/subscribed', '/unsubscribed']

    for path in public_paths:
        if request.path.startswith(path) or request.path == path.rstrip('/'):
            return None

    # Check if user is authenticated
    user_in_session = session.get('user')

    if not user_in_session:
        # API requests get 401
        if request.path.startswith('/api/') or request.is_json:
            from flask import jsonify
            logger.warning(f"Unauthorized API access attempt: {request.path}")
            return jsonify({'success': False, 'error': 'Authentication required'}), 401

        # Browser requests redirect to login
        logger.info(f"Redirecting unauthenticated user to login: {request.path}")
        return redirect(url_for('auth.login', next=request.url))

    return None


@app.before_request
def ensure_visitor_id():
    """
    Ensure visitor has a unique visitor_id cookie for analytics.
    Sets cookie if not present, stores in g for access during request.
    """
    visitor_id = request.cookies.get('visitor_id')
    if not visitor_id:
        visitor_id = str(uuid.uuid4())
        g.new_visitor_id = visitor_id
    g.visitor_id = visitor_id


@app.after_request
def set_visitor_id_cookie(response):
    """
    Set visitor_id cookie on response if it was newly generated.
    """
    new_visitor_id = getattr(g, 'new_visitor_id', None)
    if new_visitor_id:
        response.set_cookie(
            'visitor_id',
            new_visitor_id,
            max_age=365 * 24 * 60 * 60,  # 1 year
            httponly=True,
            samesite='Lax',
            secure=True
        )
    return response


# ═══════════════════════════════════════════════════════════
# SECURITY HEADERS - Protect against XSS, clickjacking, etc.
# ═══════════════════════════════════════════════════════════

@app.after_request
def set_security_headers(response):
    """
    Add security headers to all responses.
    Protects against: XSS, clickjacking, MIME sniffing, etc.
    """
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'  # Allow same-origin iframes (publisher preview)
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://www.google.com https://www.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
        "frame-src 'self' https://www.google.com;"
        "connect-src 'self' https://cdn.jsdelivr.net https://www.google.com;"
    )

    # Cache control for public pages - prevent browser caching entirely
    # no-store ensures Edge and other browsers never serve stale content
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'

    return response


# ═══════════════════════════════════════════════════════════
# TEMPLATE CONTEXT PROCESSOR - Auto-inject common variables
# ═══════════════════════════════════════════════════════════

from routes.context_processors import inject_common_context

@app.context_processor
def inject_common_context_wrapper():
    """
    Auto-inject commonly-used template variables into all templates.
    Registered globally - available to all blueprints.
    """
    return inject_common_context()

# ═══════════════════════════════════════════════════════════
# BLUEPRINT REGISTRATION - Modular route organization
# ═══════════════════════════════════════════════════════════

from routes import (
    dashboard_bp,
    companies_bp,
    actions_bp,  # Uses deferred imports for SQLite-dependent modules
    api_bp,
    auth_bp,
    publisher_bp,
    publisher_styles_bp,
    publisher_email_bp,
    emails_bp,
    contact_bp,
    disclosures_bp,
    test_signup_bp,
    subscribe_bp,
    public_bp,
    sponsors_bp,
    brave_review_bp,
    og_bp,
)

# Data-driven blueprint registration (Open/Closed Principle)
# Core blueprints work in both ECS and local mode (use DynamoDB repositories)
blueprints = [
    dashboard_bp,
    companies_bp,
    actions_bp,
    api_bp,
    auth_bp,
    publisher_bp,
    publisher_styles_bp,
    publisher_email_bp,
    emails_bp,
    contact_bp,
    disclosures_bp,
    test_signup_bp,
    subscribe_bp,
    public_bp,
    sponsors_bp,
    brave_review_bp,
    og_bp,
]

# Local-only blueprints (require Gmail OAuth, Playwright)
# These features run locally, not in ECS
if not aws_config.is_ecs:
    try:
        from routes import review_emails_bp
        if review_emails_bp is not None:
            blueprints.append(review_emails_bp)
            logger.info("Local blueprints loaded: review_emails")
        else:
            logger.warning("review_emails_bp is None (import failed in routes/__init__.py)")
    except ImportError as e:
        logger.warning(f"Local blueprints not loaded: {e}")

for blueprint in blueprints:
    app.register_blueprint(blueprint)

# Log all registered routes at startup
logger.info("=== REGISTERED ROUTES ===")
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    logger.info(f"  {rule.rule} -> {rule.endpoint}")

# ═══════════════════════════════════════════════════════════
# DEBUG - Request logging and route inspection
# ═══════════════════════════════════════════════════════════

@app.before_request
def log_request():
    """Log every incoming request for debugging."""
    logger.info(f"REQUEST: {request.method} {request.path} | Host: {request.host} | X-Forwarded-Host: {request.headers.get('X-Forwarded-Host', 'none')}")


@app.route('/debug/routes')
def debug_routes():
    """List all registered routes for debugging."""
    routes = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        routes.append(f"{rule.rule} -> {rule.endpoint} [{', '.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))}]")
    return "<pre>" + "\n".join(routes) + "</pre>"

# ═══════════════════════════════════════════════════════════
# FAVICON - Prevent 404 errors
# ═══════════════════════════════════════════════════════════

@app.route('/favicon.ico')
def favicon():
    """Return empty response for favicon requests"""
    from flask import send_from_directory
    import os
    favicon_path = os.path.join(app.root_path, 'static', 'favicon.ico')
    if os.path.exists(favicon_path):
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon'
        )
    else:
        # Return 204 No Content if favicon doesn't exist
        return '', 204

# ═══════════════════════════════════════════════════════════
# SCAN MANAGER - Background email scanning service
# ═══════════════════════════════════════════════════════════

# Initialize scan manager (used by review_emails blueprint)
scan_manager = get_scan_manager()

# ═══════════════════════════════════════════════════════════
# HEALTH CHECK - Required for ECS/ALB health checks
# ═══════════════════════════════════════════════════════════

@app.route('/health')
@limiter.exempt  # ALB health checks must not be rate limited
def health_check():
    """
    Health check endpoint for ALB and ECS.

    Returns:
        200 OK with JSON body if healthy
        503 Service Unavailable if unhealthy

    Checks:
        - Application is running
        - Database connection (if using SQLite locally)
        - DynamoDB connection (if using ECS)
    """
    health_status = {
        'status': 'healthy',
        'environment': 'ecs' if aws_config.is_ecs else 'local',
        'checks': {}
    }

    try:
        # Check database connectivity
        if aws_config.is_ecs:
            # Check DynamoDB connectivity
            table = aws_config.get_dynamodb_table(aws_config.companies_table_name)
            table.table_status  # This will raise if table doesn't exist
            health_status['checks']['dynamodb'] = 'connected'
        else:
            # Check SQLite connectivity
            from core.models import get_session
            from sqlalchemy import text
            session = get_session()
            session.execute(text('SELECT 1'))
            session.close()
            health_status['checks']['sqlite'] = 'connected'

        # Check scan manager status (optional)
        if scan_manager:
            health_status['checks']['scan_manager'] = 'initialized'

        return jsonify(health_status), 200

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_status['status'] = 'unhealthy'
        health_status['error'] = str(e)
        return jsonify(health_status), 503


# ═══════════════════════════════════════════════════════════
# GRACEFUL SHUTDOWN - Clean up background threads
# ═══════════════════════════════════════════════════════════

def graceful_shutdown(signum=None, frame=None):
    """
    Graceful shutdown handler for background threads.

    Called on SIGTERM (ECS task stop) or SIGINT (Ctrl+C).
    Stops background threads and closes connections cleanly.
    """
    logger.info(f"Received shutdown signal (signum={signum})")

    # Stop scan manager if running
    if scan_manager:
        try:
            logger.info("Stopping scan manager...")
            # Signal abort if scan is in progress
            if hasattr(scan_manager, 'request_abort'):
                scan_manager.request_abort()
            elif hasattr(scan_manager, '_progress'):
                scan_manager._progress.abort = True
            logger.info("Scan manager stopped")
        except Exception as e:
            logger.error(f"Error stopping scan manager: {e}")

    logger.info("Graceful shutdown complete")

    # Exit if this was a signal (not atexit)
    if signum is not None:
        sys.exit(0)


# Register shutdown handlers
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)
atexit.register(graceful_shutdown)

# ═══════════════════════════════════════════════════════════
# APPLICATION ENTRY POINT
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    # Initialize database (local mode only)
    from core.models import init_db
    init_db()

    # Ensure required directories exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs(NEWSLETTERS_DIR, exist_ok=True)

    # Run development server
    app.run(debug=False, host='0.0.0.0', port=5001)
