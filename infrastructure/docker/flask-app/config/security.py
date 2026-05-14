"""
Security Configuration - Rate Limiting and CSRF

SOLID: Single Responsibility - Centralized security configuration
Provides limiter and csrf instances for use across blueprints
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

# Initialize limiter (will be bound to app in app.py)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"  # For single instance (EC2)
)

# Initialize CSRF protection (will be bound to app in app.py)
csrf = CSRFProtect()

# Rate limit configurations for different endpoint types
AUTH_RATE_LIMITS = {
    'login': "10 per minute",      # Strict limit for login attempts
    'callback': "20 per minute",   # OAuth callbacks (slightly higher)
    'api': "100 per hour",         # General API endpoints
    'admin': "200 per hour"        # Admin operations
}
