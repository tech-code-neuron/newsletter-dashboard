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
from flask import Blueprint, redirect, url_for, session, request, jsonify, render_template, flash

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
    Initiate Google OAuth login via Cognito.

    Redirects to:
        - Dashboard if already logged in
        - Cognito login page if not logged in
    """
    # Check if already logged in
    if 'user' in session:
        return redirect(url_for('dashboard.index'))

    # Check for 'next' parameter (redirect after login)
    next_url = request.args.get('next', url_for('dashboard.index'))
    session['next_url'] = next_url

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
    Log out user and clear session.

    Clears:
        - User session data
        - All session cookies

    Redirects to login page.
    """
    user_email = session.get('user', {}).get('email', 'unknown')
    session.clear()

    logger.info(f"User logged out: {user_email}")
    flash('You have been logged out successfully', 'success')

    return redirect(url_for('auth.login'))


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
