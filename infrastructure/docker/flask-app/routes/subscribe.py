"""
Newsletter Subscription Routes - Double Opt-In Flow

Endpoints:
    GET/POST /subscribe - Public signup page with Flask-WTF form
    GET /verify - Verify email and activate subscription
    GET /unsubscribe - One-click unsubscribe
    POST /api/unsubscribe - List-Unsubscribe-Post handler (RFC 8058)

SOLID Principles:
    - Single Responsibility: Subscription management only
    - Dependency Injection: Service layer handles business logic
"""

import logging
import uuid
import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Email, Length, ValidationError

from services.subscriber_service import SubscriberService
from config.security import limiter, csrf
from config.site_config import get_public_config
from utils.input_validator import (
    validate_email_strict,
    validate_uuid_token,
    validate_hex_string,
    sanitize_text_input
)
from utils.unsubscribe import (
    generate_unsubscribe_signature,
    verify_unsubscribe_signature,
    generate_unsubscribe_url
)

logger = logging.getLogger(__name__)

subscribe_bp = Blueprint('subscribe', __name__)


# =============================================================================
# Flask-WTF Form
# =============================================================================

def validate_email_security(form, field):
    """Custom validator with security checks against injection attacks."""
    is_valid, result = validate_email_strict(field.data)
    if not is_valid:
        raise ValidationError(result)
    field.data = result  # Use sanitized version


class SubscribeForm(FlaskForm):
    """Newsletter subscription form with CSRF protection."""
    email = StringField('Email', validators=[
        DataRequired(message='Email is required.'),
        Email(message='Please enter a valid email address.'),
        Length(max=254, message='Email address is too long.'),
        validate_email_security
    ])


# =============================================================================
# Public Signup Page (Flask-WTF)
# =============================================================================

@subscribe_bp.route('/subscribe', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def subscribe_page():
    """
    Public signup page with Flask-WTF form.

    GET: Render signup form
    POST: Process subscription
    """
    form = SubscribeForm()

    if form.validate_on_submit():
        email = form.email.data.lower().strip()

        try:
            service = SubscriberService()

            # Check existing subscriber - SECURITY: Always return same response
            # to prevent email enumeration (revealing who is subscribed)
            existing = service.get_subscriber(email)
            if existing:
                status = existing.get('status')
                if status == 'verified':
                    # Send private notification - don't reveal status publicly
                    service.send_already_subscribed_email(email)
                    logger.info(f"Already subscribed: {email[:3]}***@{email.split('@')[1]}")
                    # Return SAME success page as new signups (uniform response)
                    return render_template('subscribe_success.html',
                        message='Check your email to confirm your subscription.',
                        config=get_public_config())
                elif status == 'pending':
                    # Resend confirmation email with fresh token
                    service.resend_confirmation(email)
                    logger.info(f"Resent confirmation: {email[:3]}***@{email.split('@')[1]}")
                    # Return SAME success page (uniform response)
                    return render_template('subscribe_success.html',
                        message='Check your email to confirm your subscription.',
                        config=get_public_config())
                # status == 'unsubscribed' falls through to create new subscription

            # Create new subscriber or update unsubscribed
            verification_token = str(uuid.uuid4())
            # Sanitize user-agent to prevent XSS if ever displayed
            user_agent = sanitize_text_input(
                request.headers.get('User-Agent', ''),
                max_length=500
            )
            service.create_or_update_subscriber(
                email=email,
                verification_token=verification_token,
                source='website',
                ip_address=request.remote_addr,
                user_agent=user_agent
            )

            # Send confirmation email
            service.send_confirmation_email(email, verification_token)

            logger.info(f"New subscription initiated: {email[:3]}***@{email.split('@')[1]}")

            return render_template('subscribe_success.html',
                message='Check your email to confirm your subscription.',
                config=get_public_config())

        except Exception as e:
            logger.error(f"Subscription error: {e}")
            flash('An error occurred. Please try again.', 'error')

    return render_template('subscribe.html', form=form)


# =============================================================================
# API Subscribe (AJAX - No CSRF Token Required)
# =============================================================================

@subscribe_bp.route('/api/subscribe', methods=['POST'])
@csrf.exempt
@limiter.limit("10 per hour")
def api_subscribe():
    """
    API endpoint for AJAX subscription from homepage.

    POST /api/subscribe
    Body: {"email": "user@example.com"}

    Returns JSON response. Uses rate limiting + honeypot for bot protection
    instead of CSRF tokens (since CSRF requires session cookies that may not
    be set on first visit).
    """
    data = request.get_json() or {}

    # Honeypot check - if 'website' field is filled, it's a bot
    if data.get('website'):
        logger.warning(f"Honeypot triggered on /api/subscribe")
        # Return fake success to not tip off bots
        return jsonify({'success': True, 'message': 'Check your email to confirm.'})

    email = data.get('email', '').lower().strip()

    if not email:
        return jsonify({'success': False, 'error': 'Email is required.'}), 400

    # Validate email format
    is_valid, result = validate_email_strict(email)
    if not is_valid:
        return jsonify({'success': False, 'error': result}), 400
    email = result  # Use sanitized version

    try:
        service = SubscriberService()

        # Check existing subscriber - always return same response (prevent enumeration)
        existing = service.get_subscriber(email)
        if existing:
            status = existing.get('status')
            if status == 'verified':
                service.send_already_subscribed_email(email)
                logger.info(f"API subscribe - already subscribed: {email[:3]}***")
                return jsonify({'success': True, 'message': 'Check your email to confirm.'})
            elif status == 'pending':
                service.resend_confirmation(email)
                logger.info(f"API subscribe - resent confirmation: {email[:3]}***")
                return jsonify({'success': True, 'message': 'Check your email to confirm.'})
            # status == 'unsubscribed' falls through to create new subscription

        # Create new subscriber
        verification_token = str(uuid.uuid4())
        user_agent = sanitize_text_input(
            request.headers.get('User-Agent', ''),
            max_length=500
        )
        service.create_or_update_subscriber(
            email=email,
            verification_token=verification_token,
            source='website_ajax',
            ip_address=request.remote_addr,
            user_agent=user_agent
        )

        service.send_confirmation_email(email, verification_token)
        logger.info(f"API subscribe - new: {email[:3]}***")

        return jsonify({'success': True, 'message': 'Check your email to confirm.'})

    except Exception as e:
        logger.error(f"API subscription error: {e}")
        return jsonify({'success': False, 'error': 'An error occurred. Please try again.'}), 500


# =============================================================================
# Email Verification
# =============================================================================

@subscribe_bp.route('/verify', methods=['GET', 'POST'])
@csrf.exempt  # Public endpoint - rate limiting provides protection
@limiter.limit("5 per minute")
def verify():
    """
    Verify email and activate subscription (two-step for scanner protection).

    GET /verify?token=<uuid> - Shows confirmation page (scanners stop here)
    POST /verify?token=<uuid> - Actually verifies (only real users click button)

    Email security scanners (Proofpoint, URLDefense, SafeLinks) click GET links
    automatically. The two-step flow prevents scanners from auto-verifying users.
    """
    token = request.args.get('token', '')

    # Validate token format BEFORE database lookup (prevent injection)
    if not token or not validate_uuid_token(token):
        return render_template('verify_error.html',
            message='Invalid verification link.',
            config=get_public_config()), 400

    service = SubscriberService()

    # Look up subscriber by token
    subscriber = service.get_subscriber_by_token(token)

    if not subscriber:
        return render_template('verify_error.html',
            message='This link is invalid or has expired. Please sign up again.',
            config=get_public_config()), 400

    # Check token expiry (24 hours)
    token_expires = subscriber.get('token_expires_at', 0)
    if token_expires < int(datetime.now(timezone.utc).timestamp()):
        return render_template('verify_error.html',
            message='This link has expired. Please sign up again.',
            config=get_public_config()), 400

    # GET = show confirmation page (scanner sees this but can't proceed)
    if request.method == 'GET':
        # Already verified? Show success directly
        if subscriber.get('status') == 'verified':
            return render_template('verify_success.html',
                message='Your email is already verified. You are subscribed!',
                config=get_public_config())

        return render_template('verify_confirm.html',
            token=token,
            config=get_public_config())

    # POST = actually verify (only real user clicks button)
    if subscriber.get('status') == 'verified':
        return render_template('verify_success.html',
            message='Your email is already verified. You are subscribed!',
            config=get_public_config())

    try:
        success, error = service.verify_subscriber(
            subscriber['email'],
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )

        if not success:
            if error == 'unsubscribed':
                return render_template('verify_error.html',
                    message='This email has been unsubscribed. Sign up again if you want to re-subscribe.',
                    config=get_public_config()), 400
            raise Exception(error)

        logger.info(f"Subscriber verified: {subscriber['email'][:3]}***")

        config = get_public_config()
        brand_name = config.get('brand', {}).get('name', 'The Press Release Pipeline')
        return render_template('verify_success.html',
            message=f'Your email has been verified. Welcome to {brand_name}!',
            config=config)

    except Exception as e:
        logger.error(f"Verification error: {e}")
        return render_template('verify_error.html',
            message='An error occurred. Please try again.',
            config=get_public_config()), 500


# =============================================================================
# Resend Verification
# =============================================================================

@subscribe_bp.route('/subscribe/resend', methods=['POST'])
@csrf.exempt
@limiter.limit("6 per hour")
def resend_verification():
    """
    Resend verification email for pending subscribers.

    POST /resend-verification
    Body: email (form data)

    Returns same response regardless of email status (prevent enumeration).
    """
    email = request.form.get('email', '').lower().strip()

    if not email:
        flash('Please enter your email address.', 'error')
        return render_template('verify_error.html',
            message='This verification link has expired.',
            config=get_public_config())

    # Validate email format
    is_valid, result = validate_email_strict(email)
    if not is_valid:
        flash('Please enter a valid email address.', 'error')
        return render_template('verify_error.html',
            message='This verification link has expired.',
            config=get_public_config())

    email = result  # Use sanitized version

    try:
        service = SubscriberService()
        existing = service.get_subscriber(email)

        if existing and existing.get('status') == 'pending':
            service.resend_confirmation(email)
            logger.info(f"Resent verification via form: {email[:3]}***@{email.split('@')[1]}")

        # Uniform response (prevent email enumeration)
        flash('If this email is pending verification, a new link has been sent.', 'success')
        return render_template('verify_error.html',
            message='Check your inbox',
            config=get_public_config())

    except Exception as e:
        logger.error(f"Resend verification error: {e}")
        flash('An error occurred. Please try again.', 'error')
        return render_template('verify_error.html',
            message='This verification link has expired.',
            config=get_public_config())


# =============================================================================
# Unsubscribe
# =============================================================================

@subscribe_bp.route('/unsubscribe', methods=['GET'])
@limiter.limit("5 per minute")
def unsubscribe():
    """
    One-click unsubscribe (HMAC-signed for security).

    GET /unsubscribe?email=<email>&sig=<hmac>

    Shows confirmation page.
    """
    email = request.args.get('email', '').lower().strip()
    sig = request.args.get('sig', '')

    # Validate parameter formats before processing (prevent injection)
    if not email or not sig:
        return render_template('unsubscribe_error.html',
            message='Invalid unsubscribe link.',
            config=get_public_config()), 400

    # Validate signature format (16 hex characters)
    if not validate_hex_string(sig, 16):
        return render_template('unsubscribe_error.html',
            message='Invalid unsubscribe link.',
            config=get_public_config()), 400

    # Validate email format
    is_valid, sanitized_email = validate_email_strict(email)
    if not is_valid:
        return render_template('unsubscribe_error.html',
            message='Invalid unsubscribe link.',
            config=get_public_config()), 400
    email = sanitized_email

    # Verify HMAC signature
    if not verify_unsubscribe_signature(email, sig):
        logger.warning(f"Invalid unsubscribe signature for {email[:3]}***")
        return render_template('unsubscribe_error.html',
            message='Invalid unsubscribe link.',
            config=get_public_config()), 400

    service = SubscriberService()

    try:
        # Check if subscriber exists
        subscriber = service.get_subscriber(email)
        if not subscriber:
            return render_template('unsubscribe_success.html',
                message='You have been unsubscribed.',
                config=get_public_config())

        if subscriber.get('status') == 'unsubscribed':
            return render_template('unsubscribe_success.html',
                message='You are already unsubscribed.',
                config=get_public_config())

        # Unsubscribe
        service.unsubscribe(email)
        logger.info(f"Subscriber unsubscribed: {email[:3]}***")

        return render_template('unsubscribe_success.html',
            message='You have been successfully unsubscribed. We\'re sorry to see you go.',
            config=get_public_config())

    except Exception as e:
        logger.error(f"Unsubscribe error: {e}")
        return render_template('unsubscribe_error.html',
            message='An error occurred. Please try again.',
            config=get_public_config()), 500


# =============================================================================
# List-Unsubscribe POST Handler (RFC 8058)
# =============================================================================

@subscribe_bp.route('/api/unsubscribe', methods=['POST'])
def unsubscribe_post():
    """
    Handle List-Unsubscribe-Post one-click unsubscribe.

    POST /api/unsubscribe?email=<email>&sig=<hmac>
    Body: List-Unsubscribe=One-Click

    This is called by email clients (Gmail, Outlook) when user clicks
    the "Unsubscribe" button in the email header.
    """
    email = request.args.get('email', '').lower().strip()
    sig = request.args.get('sig', '')

    if not email or not sig:
        return jsonify({'error': 'Invalid request'}), 400

    # Validate signature format (16 hex characters)
    if not validate_hex_string(sig, 16):
        return jsonify({'error': 'Invalid request'}), 400

    # Validate email format
    is_valid, sanitized_email = validate_email_strict(email)
    if not is_valid:
        return jsonify({'error': 'Invalid request'}), 400
    email = sanitized_email

    if not verify_unsubscribe_signature(email, sig):
        return jsonify({'error': 'Invalid signature'}), 400

    service = SubscriberService()

    try:
        service.unsubscribe(email)
        logger.info(f"One-click unsubscribe: {email[:3]}***")
        return jsonify({'status': 'unsubscribed'}), 200
    except Exception as e:
        logger.error(f"One-click unsubscribe error: {e}")
        return jsonify({'error': 'Failed to unsubscribe'}), 500
