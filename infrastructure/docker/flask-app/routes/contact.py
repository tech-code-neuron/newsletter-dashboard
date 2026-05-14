"""
Contact Routes - Public contact form with reCAPTCHA and admin-configurable settings

Routes:
    GET  /contact          - Public contact form
    POST /contact          - Process form submission, send email via SES
    GET  /contact/settings - Admin settings page (login required)
    POST /contact/settings - Save settings to DynamoDB
"""
import os
import logging
import requests
import boto3
from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from botocore.exceptions import ClientError
from functools import wraps

logger = logging.getLogger(__name__)

contact_bp = Blueprint('contact', __name__)

# reCAPTCHA configuration
RECAPTCHA_SITE_KEY = os.environ.get('RECAPTCHA_SITE_KEY', '')
RECAPTCHA_SECRET_KEY = os.environ.get('RECAPTCHA_SECRET_KEY', '')
RECAPTCHA_VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify'

# DynamoDB configuration
CONFIG_TABLE = 'reitsheet-site-config'
CONFIG_KEY = 'contact_form'

# Default configuration
DEFAULT_CONFIG = {
    'config_type': CONFIG_KEY,
    'recipient_email': 'alerts@your-domain.com',
    'headline': 'Say Hello',
    'tagline': "Questions, feedback, or just want to chat REITs? We're listening.",
    'name_placeholder': 'Warren Buffett',
    'email_placeholder': 'warren@berkshire.com',
    'message_placeholder': "I've been meaning to tell you..."
}

# Email sender (verified in SES)
SENDER_EMAIL = 'alerts@your-domain.com'


def login_required(f):
    """Decorator to require authentication for admin routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def get_dynamodb_table():
    """Get DynamoDB table resource."""
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    return dynamodb.Table(CONFIG_TABLE)


def get_contact_config() -> dict:
    """
    Load contact form configuration from DynamoDB.
    Returns default config if not found.
    """
    try:
        table = get_dynamodb_table()
        response = table.get_item(Key={'config_type': CONFIG_KEY})
        config = response.get('Item', {})

        # Merge with defaults for any missing fields
        result = DEFAULT_CONFIG.copy()
        result.update(config)
        return result
    except ClientError as e:
        logger.error(f"Failed to load contact config: {e}")
        return DEFAULT_CONFIG.copy()


def save_contact_config(config: dict) -> bool:
    """
    Save contact form configuration to DynamoDB.
    Returns True on success, False on failure.
    """
    try:
        table = get_dynamodb_table()
        config['config_type'] = CONFIG_KEY
        table.put_item(Item=config)
        logger.info("Contact config saved successfully")
        return True
    except ClientError as e:
        logger.error(f"Failed to save contact config: {e}")
        return False


def verify_recaptcha(response_token: str) -> bool:
    """
    Verify reCAPTCHA response with Google API.
    Returns True if verification passes, False otherwise.
    """
    if not RECAPTCHA_SECRET_KEY:
        logger.warning("RECAPTCHA_SECRET_KEY not configured - skipping verification")
        return True  # Allow in dev without reCAPTCHA

    if not response_token:
        return False

    try:
        response = requests.post(
            RECAPTCHA_VERIFY_URL,
            data={
                'secret': RECAPTCHA_SECRET_KEY,
                'response': response_token
            },
            timeout=5
        )
        result = response.json()
        return result.get('success', False)
    except Exception as e:
        logger.error(f"reCAPTCHA verification failed: {e}")
        return False


def send_contact_email(name: str, email: str, message: str, recipient: str) -> bool:
    """
    Send contact form submission via AWS SES.
    Returns True if email sent successfully, False otherwise.
    """
    from html import escape

    ses = boto3.client('ses', region_name='us-east-1')

    # Sanitize user input to prevent XSS in admin inbox
    safe_name = escape(name)
    safe_email = escape(email)
    safe_message = escape(message)

    subject = f"Press Release Pipeline Contact: {safe_name}"
    body_text = f"""
New contact form submission:

From: {name}
Email: {email}

Message:
{message}
"""
    body_html = f"""
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 10px;">New Contact Form Submission</h2>
    <p><strong>From:</strong> {safe_name}</p>
    <p><strong>Email:</strong> <a href="mailto:{safe_email}" style="color: #0066cc;">{safe_email}</a></p>
    <h3 style="color: #666; margin-top: 24px;">Message:</h3>
    <div style="background: #f5f5f5; padding: 16px; border-radius: 4px; white-space: pre-wrap;">{safe_message}</div>
</body>
</html>
"""

    try:
        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [recipient]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Text': {'Data': body_text, 'Charset': 'UTF-8'},
                    'Html': {'Data': body_html, 'Charset': 'UTF-8'}
                }
            }
        )
        logger.info(f"Contact email sent from {email} to {recipient}")
        return True
    except ClientError as e:
        logger.error(f"Failed to send contact email: {e}")
        return False


@contact_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    """
    Public contact form page.

    GET: Display contact form with reCAPTCHA
    POST: Validate reCAPTCHA, send email, show success/error
    """
    config = get_contact_config()

    if request.method == 'POST':
        # Get form data
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        message = request.form.get('message', '').strip()
        recaptcha_response = request.form.get('g-recaptcha-response', '')

        # Validate required fields
        if not all([name, email, message]):
            flash('All fields are required.', 'error')
            return render_template('contact.html',
                                   config=config,
                                   recaptcha_site_key=RECAPTCHA_SITE_KEY,
                                   name=name, email=email, message=message)

        # Verify reCAPTCHA
        if not verify_recaptcha(recaptcha_response):
            flash('Please complete the reCAPTCHA verification.', 'error')
            return render_template('contact.html',
                                   config=config,
                                   recaptcha_site_key=RECAPTCHA_SITE_KEY,
                                   name=name, email=email, message=message)

        # Send email
        recipient = config.get('recipient_email', DEFAULT_CONFIG['recipient_email'])
        if send_contact_email(name, email, message, recipient):
            flash("Message sent. We'll be in touch.", 'success')
            return redirect(url_for('contact.contact'))
        else:
            flash('Failed to send message. Please try again.', 'error')
            return render_template('contact.html',
                                   config=config,
                                   recaptcha_site_key=RECAPTCHA_SITE_KEY,
                                   name=name, email=email, message=message)

    # GET request - show form
    return render_template('contact.html',
                           config=config,
                           recaptcha_site_key=RECAPTCHA_SITE_KEY)


@contact_bp.route('/contact/settings', methods=['GET', 'POST'])
@login_required
def contact_settings():
    """
    Admin page to configure contact form settings.
    """
    if request.method == 'POST':
        config = {
            'recipient_email': request.form.get('recipient_email', '').strip(),
            'headline': request.form.get('headline', '').strip(),
            'tagline': request.form.get('tagline', '').strip(),
            'name_placeholder': request.form.get('name_placeholder', '').strip(),
            'email_placeholder': request.form.get('email_placeholder', '').strip(),
            'message_placeholder': request.form.get('message_placeholder', '').strip(),
        }

        # Validate required fields
        if not config['recipient_email']:
            flash('Recipient email is required.', 'error')
            return render_template('contact_settings.html', config=config)

        if save_contact_config(config):
            flash('Contact settings saved.', 'success')
            return redirect(url_for('contact.contact_settings'))
        else:
            flash('Failed to save settings.', 'error')
            return render_template('contact_settings.html', config=config)

    # GET request - show current settings
    config = get_contact_config()
    return render_template('contact_settings.html', config=config)
