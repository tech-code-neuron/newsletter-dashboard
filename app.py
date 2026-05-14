"""
Flask web interface for Press Release Pipeline management
REFACTORED: Thin orchestrator with modular blueprint architecture

All routes moved to blueprints in routes/ directory:
- routes/dashboard.py - Dashboard
- routes/companies.py - Company management
- routes/press_releases.py - Press release CRUD
- routes/review.py - Relevance review
- routes/review_emails.py - Email review system
- routes/newsletters.py - Newsletter generation
- routes/actions.py - Background actions
- routes/api.py - API endpoints

SOLID Compliance: Open/Closed Principle
- Add new features by creating new blueprints
- No need to modify this file

ECS Support (Phase 1):
- Health check endpoint at /health
- Graceful shutdown handler for background threads
- Auto-detection of ECS vs local environment
"""
import os
import signal
import sys
import atexit
import logging
from flask import Flask, jsonify
from flask_wtf.csrf import CSRFProtect
from jinja2 import ChainableUndefined
from dotenv import load_dotenv
from config.paths import NEWSLETTERS_DIR
from config.aws_config import aws_config
from config.security import limiter
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

# Enable CSRF protection for all POST/PUT/DELETE requests
csrf = CSRFProtect(app)

# Enable rate limiting (SECURITY: Prevent brute force and API abuse)
limiter.init_app(app)

# Log environment detection
if aws_config.is_ecs:
    logger.info("Running in ECS environment")
else:
    logger.info("Running in local environment")

# ═══════════════════════════════════════════════════════════
# TEMPLATE FILTERS - Safe date formatting
# ═══════════════════════════════════════════════════════════

@app.template_filter('format_date')
def format_date_filter(date, fmt='%b %d, %Y', default='N/A'):
    """
    Safe date formatting filter.

    Usage in templates:
        {{ release.published_date|format_date }}              → 'Mar 14, 2026' or 'N/A'
        {{ release.published_date|format_date('%Y-%m-%d') }}  → '2026-03-14' or 'N/A'
        {{ date|format_date('%Y-%m-%d', '') }}                → '2026-03-14' or '' (for forms)
    """
    if date is None:
        return default
    try:
        return date.strftime(fmt)
    except (AttributeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════
# GLOBAL AUTHENTICATION - Require login for ALL pages
# ═══════════════════════════════════════════════════════════

from flask import session, redirect, url_for, request

@app.before_request
def require_authentication():
    """
    Require authentication for ALL routes except:
    - /health (ALB health check)
    - /login (login page)
    - /auth/* (OAuth callbacks)
    - /static/* (static files)
    """
    # Skip auth for these paths
    public_paths = ['/health', '/login', '/auth/', '/static/']

    for path in public_paths:
        if request.path.startswith(path) or request.path == path.rstrip('/'):
            return None

    # Check if user is authenticated
    if not session.get('user'):
        # API requests get 401
        if request.path.startswith('/api/') or request.is_json:
            from flask import jsonify
            return jsonify({'success': False, 'error': 'Authentication required'}), 401

        # Browser requests redirect to login
        return redirect(url_for('auth.login', next=request.url))

    return None


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
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://cdn.jsdelivr.net;"
    )
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
    press_releases_bp,
    review_bp,
    newsletters_bp,
    actions_bp,  # Uses deferred imports for SQLite-dependent modules
    api_bp,
    auth_bp,
    url_testing_bp
)

# Data-driven blueprint registration (Open/Closed Principle)
# Core blueprints work in both ECS and local mode (use DynamoDB repositories)
blueprints = [
    dashboard_bp,
    companies_bp,
    press_releases_bp,
    review_bp,
    newsletters_bp,
    actions_bp,
    api_bp,
    auth_bp,
    url_testing_bp
]

# Local-only blueprints (require Gmail OAuth, Playwright)
# These features run locally, not in ECS
if not aws_config.is_ecs:
    try:
        from routes import review_emails_bp
        blueprints.append(review_emails_bp)
        logger.info("Local blueprints loaded: review_emails")
    except ImportError as e:
        logger.warning(f"Local blueprints not loaded: {e}")

for blueprint in blueprints:
    app.register_blueprint(blueprint)

# ═══════════════════════════════════════════════════════════
# SCAN MANAGER - Background email scanning service
# ═══════════════════════════════════════════════════════════

# Initialize scan manager (used by review_emails blueprint)
scan_manager = get_scan_manager()

# ═══════════════════════════════════════════════════════════
# HEALTH CHECK - Required for ECS/ALB health checks
# ═══════════════════════════════════════════════════════════

@app.route('/health')
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
            session = get_session()
            session.execute('SELECT 1')
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
