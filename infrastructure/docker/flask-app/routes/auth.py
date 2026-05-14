"""
Authentication Routes - Thin Controllers (REFACTORED)

SOLID Principles:
- Single Responsibility: HTTP handling only
- Dependency Inversion: Depends on AuthService abstraction
- Open/Closed: OAuth changes don't affect routes

Architecture:
Routes → AuthService → Cognito API

Routes:
    GET  /login          - Show login page
    GET  /auth/callback  - Handle OAuth callback
    GET  /logout         - Log out and clear session
    GET  /auth/user      - Get current user info (API)
"""
import logging
from flask import Blueprint, redirect, url_for, session, request, jsonify, render_template, flash, make_response

from services.auth_service import get_auth_service

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# Get service instance
service = get_auth_service()


# =============================================================================
# Login
# =============================================================================

@auth_bp.route('/login')
def login():
    """
    Show login page with Google sign-in button.

    Requires user to click button before starting OAuth flow.
    This prevents auto-login after logout.
    """
    # Check if already logged in (verify session is actually valid)
    if 'user' in session:
        user = session.get('user', {})
        # Verify session has required fields (defense against corrupted session)
        if user.get('email') and user.get('role'):
            return redirect(url_for('dashboard.index'))
        else:
            # Invalid session data - clear it
            session.clear()
            logger.warning("Cleared invalid session data in /login")

    # Check for 'next' parameter (redirect after login)
    next_url = request.args.get('next', url_for('dashboard.index'))
    session['next_url'] = next_url

    # Show login page - user must click to proceed
    response = make_response(render_template('login.html'))

    # Prevent caching of login page
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'

    return response


@auth_bp.route('/auth/start')
def start_oauth():
    """
    Start the OAuth flow after user confirms.
    """
    # Redirect to Cognito login
    login_url = service.get_login_url()
    return redirect(login_url)


# =============================================================================
# OAuth Callback
# =============================================================================

@auth_bp.route('/auth/callback')
def callback():
    """
    Handle OAuth callback from Cognito.

    Query parameters:
        - code: Authorization code (if successful)
        - error: Error code (if failed)
    """
    # Check for OAuth errors
    error = request.args.get('error')
    if error:
        error_description = request.args.get('error_description', 'Unknown error')
        logger.error(f"OAuth error: {error} - {error_description}")
        flash(f'Login failed: {error_description}', 'error')
        return redirect(url_for('auth.login'))

    # Get authorization code
    code = request.args.get('code')
    if not code:
        logger.error("No authorization code in callback")
        flash('Login failed: No authorization code received', 'error')
        return redirect(url_for('auth.login'))

    # Exchange code for tokens
    tokens = service.exchange_code_for_tokens(code)
    if not tokens:
        flash('Login failed: Could not exchange authorization code', 'error')
        return redirect(url_for('auth.login'))

    # Get user info
    access_token = tokens.get('access_token')
    user_info = service.get_user_info(access_token)
    if not user_info:
        flash('Login failed: Could not fetch user information', 'error')
        return redirect(url_for('auth.login'))

    # Determine user role
    email = user_info.get('email')
    if not email:
        flash('Login failed: No email in user profile', 'error')
        return redirect(url_for('auth.login'))

    role = service.get_user_role(email)

    if role == 'unauthorized':
        logger.warning(f"Unauthorized login attempt: {email}")
        flash(f'Your email ({email}) is not authorized to access this application. Please contact the administrator.', 'error')
        return render_template('unauthorized.html', email=email)

    # Store user in session
    session['user'] = service.create_session_data(user_info, role)
    session['refresh_token'] = tokens.get('refresh_token')  # Store for logout revocation
    session.permanent = True

    logger.info(f"User logged in: {email} (role: {role})")

    # Redirect to original destination or dashboard
    next_url = session.pop('next_url', url_for('dashboard.index'))
    return redirect(next_url)


# =============================================================================
# Logout
# =============================================================================

@auth_bp.route('/logout')
def logout():
    """
    Log out user by revoking tokens, clearing session, and deleting cookies.

    Process:
        1. Revoke refresh token (invalidates Cognito OAuth session)
        2. Clear Flask session data
        3. Build redirect response with EXPLICIT cookie deletion
        4. Redirect to Cognito logout endpoint
        5. Cognito redirects to /logged-out page
    """
    user_email = session.get('user', {}).get('email', 'unknown')

    # Revoke the refresh token BEFORE clearing session
    refresh_token = session.get('refresh_token')
    if refresh_token:
        service.revoke_token(refresh_token)
        logger.info(f"Revoked refresh token for: {user_email}")

    # Clear session data
    session.clear()

    # Build response with EXPLICIT cookie deletion
    logout_url = service.get_logout_url()
    response = make_response(redirect(logout_url))

    # Delete the session cookie explicitly with multiple path/domain combinations
    # Flask's default session cookie name is 'session'
    response.delete_cookie('session')
    response.delete_cookie('session', path='/')
    response.delete_cookie('session', domain='app.your-domain.com')
    response.delete_cookie('session', domain='.your-domain.com')

    # Belt and suspenders: also set cookie to expire immediately
    response.set_cookie('session', '', expires=0, path='/')

    logger.info(f"User logged out: {user_email}")
    return response


@auth_bp.route('/logged-out')
def logged_out():
    """
    Landing page after logout - user must click to log in again.

    This breaks the auto-login loop by requiring explicit user action.
    """
    # Ensure session is clear (defense in depth)
    session.clear()

    response = make_response(render_template('logged_out.html'))

    # Prevent browser from caching this page
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    # Also delete session cookie here as a fallback
    response.delete_cookie('session')
    response.delete_cookie('session', path='/')

    return response


# =============================================================================
# API Endpoints
# =============================================================================

@auth_bp.route('/auth/user')
def get_current_user():
    """
    Get current authenticated user info (API endpoint).

    Returns:
        JSON: User info if authenticated, error otherwise

    Example response:
        {
            "authenticated": true,
            "email": "user@example.com",
            "name": "John Doe",
            "role": "admin"
        }
    """
    if 'user' in session:
        return jsonify({
            'authenticated': True,
            **session['user']
        }), 200
    else:
        return jsonify({
            'authenticated': False
        }), 401
