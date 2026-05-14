"""
Newsletter Signup Lambda - Manages subscriber operations

Endpoints:
  POST /subscribe: Create new subscriber with verification email
  GET /verify/{token}: Verify email address
  GET /unsubscribe/{token}: Unsubscribe from newsletter

Uses boto3.resource('dynamodb') per project conventions (auto-deserializes).
"""

import base64
import json
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs
from botocore.exceptions import ClientError

# ============================================================================
# Constants
# ============================================================================

VERIFICATION_TOKEN_TTL_HOURS = 24  # Token expires after 24 hours

# ============================================================================
# Lazy Configuration (Deferred for Smoke Tests)
# ============================================================================

_initialized = False
_config = {}
_tables = {}
_clients = {}


def _ensure_initialized():
    """Lazy initialization of AWS clients, env vars, and DynamoDB tables."""
    global _initialized, _config, _tables, _clients

    if _initialized:
        return

    import boto3

    _clients['dynamodb'] = boto3.resource('dynamodb')
    _clients['ses'] = boto3.client('ses')

    _config['SUBSCRIBERS_TABLE'] = os.environ['SUBSCRIBERS_TABLE']
    _config['SES_SENDER_EMAIL'] = os.environ['SES_SENDER_EMAIL']
    _config['REPLY_TO_EMAIL'] = os.environ.get('REPLY_TO_EMAIL', 'hello@reitsheet.co')
    _config['BASE_URL'] = os.environ.get('BASE_URL', 'https://reitsheet.co')
    _config['COMPANY_ADDRESS'] = os.environ.get('COMPANY_ADDRESS', '3010 Edgeview Ln #312, Charlotte, NC 28209')

    _tables['subscribers'] = _clients['dynamodb'].Table(_config['SUBSCRIBERS_TABLE'])

    _initialized = True


def _subscribers_table():
    return _tables['subscribers']


def _ses():
    return _clients['ses']


def _config_value(key):
    return _config[key]


def _refresh_verification_token(email: str) -> str:
    """
    Generate fresh verification token and update subscriber record.

    Args:
        email: Subscriber email address

    Returns:
        New verification token
    """
    token = str(uuid.uuid4())
    expires = int((datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_TOKEN_TTL_HOURS)).timestamp())

    _subscribers_table().update_item(
        Key={'email': email},
        UpdateExpression='SET verification_token = :token, token_expires_at = :expires',
        ExpressionAttributeValues={
            ':token': token,
            ':expires': expires
        }
    )

    return token


# ============================================================================
# Email Validation
# ============================================================================

# Common disposable email domains to reject
DISPOSABLE_DOMAINS = {
    'tempmail.com', 'throwaway.com', 'guerrillamail.com', 'mailinator.com',
    'temp-mail.org', '10minutemail.com', 'fakeinbox.com', 'trashmail.com',
    'sharklasers.com', 'guerrillamail.info', 'grr.la', 'guerrillamail.biz',
    'guerrillamail.de', 'guerrillamail.net', 'guerrillamail.org', 'spam4.me',
    'dispostable.com', 'yopmail.com', 'mailnesia.com', 'maildrop.cc',
    'tempinbox.com', 'getairmail.com', 'getnada.com', 'mohmal.com',
}

# Email validation regex (RFC 5322 simplified)
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


def validate_email(email: str) -> tuple[bool, str]:
    """
    Validate email address format and domain.

    Returns:
        tuple: (is_valid, error_message)
    """
    if not email:
        return False, 'Email address is required'

    email = email.strip().lower()

    if len(email) > 254:
        return False, 'Email address is too long'

    if not EMAIL_REGEX.match(email):
        return False, 'Invalid email address format'

    # Extract domain
    domain = email.split('@')[1]

    if domain in DISPOSABLE_DOMAINS:
        return False, 'Disposable email addresses are not allowed'

    return True, ''


# ============================================================================
# Response Helpers
# ============================================================================

def json_response(status_code: int, body: dict) -> dict:
    """Create API Gateway response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        },
        'body': json.dumps(body)
    }


def redirect_response(url: str) -> dict:
    """Create redirect response."""
    return {
        'statusCode': 302,
        'headers': {
            'Location': url,
            'Access-Control-Allow-Origin': '*',
        },
        'body': ''
    }


# ============================================================================
# Email Sending
# ============================================================================

def send_verification_email(email: str, verification_token: str) -> bool:
    """
    Send verification email via SES.

    Returns:
        bool: True if email sent successfully
    """
    base_url = _config_value('BASE_URL')
    company_address = _config_value('COMPANY_ADDRESS')
    verify_url = f"{base_url}/verify?token={verification_token}"
    logo_url = f"{base_url}/logo.png"
    current_year = datetime.now().year

    subject = "Confirm your subscription to The Press Release Pipeline"

    text_body = f"""THE REIT SHEET

Confirm your subscription

Click the link below to confirm your email address and start receiving the daily brief:

{verify_url}

If you didn't sign up for The Press Release Pipeline, you can safely ignore this email.

--
Never miss a REIT release
{company_address}
Copyright {current_year} The Press Release Pipeline. All rights reserved.
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f9f9f9;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f9f9f9;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <!-- Header -->
                    <tr>
                        <td align="center" style="padding: 32px 40px 24px 40px; background-color: #f9f9f9; border-radius: 8px 8px 0 0;">
                            <a href="{base_url}" style="text-decoration: none;">
                                <img src="{logo_url}" alt="THE REIT SHEET" style="max-width: 280px; height: auto;">
                            </a>
                        </td>
                    </tr>
                    <!-- Body -->
                    <tr>
                        <td style="padding: 40px;">
                            <h1 style="margin: 0 0 16px 0; font-family: Georgia, 'Times New Roman', Times, serif; font-size: 24px; color: #1a1a1a; font-weight: normal;">Confirm your subscription</h1>
                            <p style="margin: 0 0 24px 0; font-family: Georgia, 'Times New Roman', Times, serif; font-size: 16px; line-height: 1.6; color: #666;">
                                Click the button below to confirm your email address and start receiving the daily brief before the market opens.
                            </p>
                            <table role="presentation" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="border-radius: 4px; background-color: #0066cc;">
                                        <a href="{verify_url}" style="display: inline-block; padding: 14px 32px; font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #ffffff; text-decoration: none; font-weight: bold;">Confirm Subscription</a>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin: 24px 0 0 0; font-family: Georgia, 'Times New Roman', Times, serif; font-size: 13px; color: #999;">
                                Or copy and paste this link into your browser:<br>
                                <a href="{verify_url}" style="color: #0066cc; word-break: break-all;">{verify_url}</a>
                            </p>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 24px 40px; background-color: #fafafa; border-top: 1px solid #eee; border-radius: 0 0 8px 8px;">
                            <p style="margin: 0 0 8px 0; font-family: Georgia, 'Times New Roman', Times, serif; font-size: 14px; font-style: italic; color: #666; text-align: center;">
                                Never miss a REIT release
                            </p>
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #999; text-align: center;">
                                If you didn't sign up for The Press Release Pipeline, you can safely ignore this email.
                            </p>
                            <p style="margin: 12px 0 0 0; font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #999; text-align: center;">
                                {company_address}
                            </p>
                            <p style="margin: 8px 0 0 0; font-family: Arial, Helvetica, sans-serif; font-size: 10px; color: #bbb; text-align: center;">
                                Copyright {current_year} The Press Release Pipeline. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

    try:
        sender_email = _config_value('SES_SENDER_EMAIL')
        print(f"Attempting to send verification email to {email} via SES")
        print(f"Sender: The Press Release Pipeline <{sender_email}>, Verify URL: {verify_url}")

        response = _ses().send_email(
            Source=f'"The Press Release Pipeline" <{sender_email}>',
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': subject},
                'Body': {
                    'Text': {'Data': text_body},
                    'Html': {'Data': html_body}
                }
            }
        )
        message_id = response.get('MessageId', 'unknown')
        print(f"SES accepted verification email for {email} - MessageId: {message_id}")
        return True
    except Exception as e:
        print(f"Failed to send verification email to {email}: {e}")
        return False


def send_already_subscribed_notification(email: str) -> bool:
    """
    Send notification to already-subscribed user.

    This is sent privately when someone tries to subscribe with an
    already-verified email. We send this email instead of revealing
    the subscription status publicly (prevents email enumeration).

    Returns:
        bool: True if email sent successfully
    """
    base_url = _config_value('BASE_URL')
    company_address = _config_value('COMPANY_ADDRESS')
    current_year = datetime.now().year

    subject = "You're already subscribed to The Press Release Pipeline"

    text_body = f"""THE REIT SHEET

You're already subscribed!

Someone (hopefully you!) just tried to sign up for The Press Release Pipeline using this email address.

Good news: You're already subscribed! No action is needed.

You'll continue to receive our daily REIT press release digest.

If this wasn't you, you can safely ignore this email. Your subscription remains unchanged.

--
Never miss a REIT release
{company_address}
Copyright {current_year} The Press Release Pipeline. All rights reserved.
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f9f9f9;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f9f9f9;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <!-- Header -->
                    <tr>
                        <td align="center" style="padding: 32px 40px 24px 40px; background-color: #f9f9f9; border-radius: 8px 8px 0 0;">
                            <a href="{base_url}" style="text-decoration: none;">
                                <img src="{base_url}/logo.png" alt="THE REIT SHEET" style="max-width: 280px; height: auto;">
                            </a>
                        </td>
                    </tr>
                    <!-- Body -->
                    <tr>
                        <td style="padding: 40px;">
                            <h1 style="margin: 0 0 16px 0; font-family: Georgia, 'Times New Roman', Times, serif; font-size: 24px; color: #1a1a1a; font-weight: normal;">You're already subscribed!</h1>
                            <p style="margin: 0 0 16px 0; font-family: Georgia, 'Times New Roman', Times, serif; font-size: 16px; line-height: 1.6; color: #666;">
                                Someone (hopefully you!) just tried to sign up for The Press Release Pipeline using this email address.
                            </p>
                            <p style="margin: 0 0 16px 0; font-family: Georgia, 'Times New Roman', Times, serif; font-size: 16px; line-height: 1.6; color: #666;">
                                <strong>Good news:</strong> You're already subscribed! No action is needed.
                            </p>
                            <p style="margin: 0 0 16px 0; font-family: Georgia, 'Times New Roman', Times, serif; font-size: 16px; line-height: 1.6; color: #666;">
                                You'll continue to receive our daily REIT press release digest before the market opens.
                            </p>
                            <p style="margin: 0; font-family: Georgia, 'Times New Roman', Times, serif; font-size: 13px; color: #999;">
                                If this wasn't you, you can safely ignore this email. Your subscription remains unchanged.
                            </p>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 24px 40px; background-color: #fafafa; border-top: 1px solid #eee; border-radius: 0 0 8px 8px;">
                            <p style="margin: 0 0 8px 0; font-family: Georgia, 'Times New Roman', Times, serif; font-size: 14px; font-style: italic; color: #666; text-align: center;">
                                Never miss a REIT release
                            </p>
                            <p style="margin: 12px 0 0 0; font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #999; text-align: center;">
                                {company_address}
                            </p>
                            <p style="margin: 8px 0 0 0; font-family: Arial, Helvetica, sans-serif; font-size: 10px; color: #bbb; text-align: center;">
                                Copyright {current_year} The Press Release Pipeline. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

    try:
        sender_email = _config_value('SES_SENDER_EMAIL')
        _ses().send_email(
            Source=f'"The Press Release Pipeline" <{sender_email}>',
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': subject},
                'Body': {
                    'Text': {'Data': text_body},
                    'Html': {'Data': html_body}
                }
            }
        )
        print(f"Already-subscribed notification sent to {email}")
        return True
    except Exception as e:
        print(f"Failed to send already-subscribed notification: {e}")
        # Don't raise - this is a non-critical notification
        return False


# ============================================================================
# Subscriber Operations
# ============================================================================

def handle_subscribe(event: dict) -> dict:
    """
    Handle POST /subscribe request.

    Creates new subscriber with pending status and sends verification email.
    Supports both JSON API and HTML form submissions.
    """
    _ensure_initialized()
    base_url = _config_value('BASE_URL')
    content_type = event.get('headers', {}).get('content-type', '')

    # Detect if this is an HTML form submission
    is_form = 'application/x-www-form-urlencoded' in content_type

    if is_form:
        # HTML form submission - parse form data
        body_str = event.get('body', '')

        # Check if body is base64 encoded (API Gateway v2 may encode it)
        if event.get('isBase64Encoded', False):
            try:
                body_str = base64.b64decode(body_str).decode('utf-8')
                print(f"DEBUG: Decoded base64 body")
            except Exception as e:
                print(f"Base64 decode failed: {e}")

        print(f"DEBUG: is_form={is_form}, body_len={len(body_str)}, body_preview={body_str[:100]}")

        parsed = parse_qs(body_str)
        email = parsed.get('email', [''])[0].strip().lower()

        print(f"DEBUG: parsed_keys={list(parsed.keys())}, email='{email}'")
    else:
        # JSON API submission
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return json_response(400, {'error': 'Invalid JSON body'})
        email = body.get('email', '').strip().lower()

    # Validate email
    is_valid, error = validate_email(email)
    print(f"DEBUG: email='{email}', is_valid={is_valid}, error='{error}'")

    if not is_valid:
        print(f"Email validation failed: email='{email}' error='{error}'")
        if is_form:
            return redirect_response(f"{base_url}/signup-error.html")
        return json_response(400, {'error': error})

    # Check if already subscribed
    # SECURITY: Always return same response to prevent email enumeration
    try:
        response = _subscribers_table().get_item(Key={'email': email})
        if 'Item' in response:
            existing = response['Item']
            status = existing.get('status')

            if status == 'verified':
                # Send private notification - don't reveal status publicly
                send_already_subscribed_notification(email)
                print(f"Already subscribed: {email}")
                # Return SAME response as new signups (uniform response)
                if is_form:
                    return redirect_response(f"{base_url}/check-email.html")
                return json_response(200, {
                    'message': 'Please check your email to confirm your subscription.'
                })
            elif status == 'pending':
                # Generate fresh token and resend verification email
                verification_token = _refresh_verification_token(email)
                send_verification_email(email, verification_token)
                print(f"Resent verification with fresh token: {email}")
                # Return SAME response (uniform response)
                if is_form:
                    return redirect_response(f"{base_url}/check-email.html")
                return json_response(200, {
                    'message': 'Please check your email to confirm your subscription.'
                })
            elif status == 'unsubscribed':
                # Allow re-subscription - generate new tokens
                pass
    except Exception as e:
        print(f"Error checking existing subscriber: {e}")
        if is_form:
            return redirect_response(f"{base_url}/signup-error.html")
        return json_response(500, {'error': 'Internal server error'})

    # Generate tokens
    verification_token = str(uuid.uuid4())
    unsubscribe_token = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Extract source info from request
    request_context = event.get('requestContext', {})
    http_context = request_context.get('http', {})
    source_ip = http_context.get('sourceIp', 'unknown')
    user_agent = event.get('headers', {}).get('user-agent', 'unknown')

    # Create subscriber record
    token_expires_at = int((datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_TOKEN_TTL_HOURS)).timestamp())

    subscriber = {
        'email': email,
        'status': 'pending',
        'subscribed_at': now,
        'verified_at': None,
        'verification_token': verification_token,
        'token_expires_at': token_expires_at,
        'unsubscribe_token': unsubscribe_token,
        'source': 'website',
        'ip_address': source_ip,
        'user_agent': user_agent,
    }

    try:
        _subscribers_table().put_item(Item=subscriber)
    except Exception as e:
        print(f"Error creating subscriber: {e}")
        if is_form:
            return redirect_response(f"{base_url}/signup-error.html")
        return json_response(500, {'error': 'Failed to create subscription'})

    # Send verification email
    if not send_verification_email(email, verification_token):
        if is_form:
            return redirect_response(f"{base_url}/signup-error.html")
        return json_response(500, {'error': 'Failed to send verification email'})

    # Success
    if is_form:
        return redirect_response(f"{base_url}/check-email.html")
    return json_response(200, {
        'message': 'Please check your email to confirm your subscription.'
    })


def handle_verify(event: dict) -> dict:
    """
    Handle GET /verify/{token} request.

    Verifies email address and updates subscriber status.
    """
    # Extract token from path
    path_params = event.get('pathParameters', {}) or {}
    token = path_params.get('token')

    if not token:
        return json_response(400, {'error': 'Verification token is required'})

    # Find subscriber by verification token (scan - infrequent operation)
    try:
        response = _subscribers_table().scan(
            FilterExpression='verification_token = :token',
            ExpressionAttributeValues={':token': token}
        )
        items = response.get('Items', [])

        if not items:
            return json_response(404, {'error': 'Invalid or expired verification link'})

        subscriber = items[0]
        email = subscriber['email']
        status = subscriber.get('status')

        if status == 'verified':
            # Already verified - redirect to success page
            return redirect_response(f"{_config_value('BASE_URL')}/subscribed.html?already=true")

        # Update subscriber status
        # ConditionExpression blocks verification if user has unsubscribed
        now = datetime.now(timezone.utc).isoformat()
        _subscribers_table().update_item(
            Key={'email': email},
            UpdateExpression='SET #status = :status, verified_at = :verified_at, verification_token = :null_token',
            ConditionExpression='#status <> :unsubscribed',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'verified',
                ':verified_at': now,
                ':null_token': None,  # Clear verification token after use
                ':unsubscribed': 'unsubscribed'
            }
        )

        print(f"Email verified: {email}")
        return redirect_response(f"{_config_value('BASE_URL')}/subscribed.html")

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            print(f"Blocked verification for unsubscribed user: {email}")
            return redirect_response(f"{_config_value('BASE_URL')}/verify-error.html?reason=unsubscribed")
        print(f"Error verifying subscription: {e}")
        return json_response(500, {'error': 'Verification failed'})
    except Exception as e:
        print(f"Error verifying subscription: {e}")
        return json_response(500, {'error': 'Verification failed'})


def handle_unsubscribe(event: dict) -> dict:
    """
    Handle GET /unsubscribe/{token} request.

    Unsubscribes user from newsletter.
    """
    # Extract token from path
    path_params = event.get('pathParameters', {}) or {}
    token = path_params.get('token')

    if not token:
        return json_response(400, {'error': 'Unsubscribe token is required'})

    # Find subscriber by unsubscribe token (scan - infrequent operation)
    try:
        response = _subscribers_table().scan(
            FilterExpression='unsubscribe_token = :token',
            ExpressionAttributeValues={':token': token}
        )
        items = response.get('Items', [])

        if not items:
            return json_response(404, {'error': 'Invalid unsubscribe link'})

        subscriber = items[0]
        email = subscriber['email']
        status = subscriber.get('status')

        if status == 'unsubscribed':
            # Already unsubscribed
            return redirect_response(f"{_config_value('BASE_URL')}/unsubscribed.html?already=true")

        # Update subscriber status
        now = datetime.now(timezone.utc).isoformat()
        _subscribers_table().update_item(
            Key={'email': email},
            UpdateExpression='SET #status = :status, unsubscribed_at = :unsubscribed_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'unsubscribed',
                ':unsubscribed_at': now,
            }
        )

        print(f"Unsubscribed: {email}")
        return redirect_response(f"{_config_value('BASE_URL')}/unsubscribed.html")

    except Exception as e:
        print(f"Error unsubscribing: {e}")
        return json_response(500, {'error': 'Unsubscribe failed'})


# ============================================================================
# Lambda Handler
# ============================================================================

def handler(event, context):
    """
    Main Lambda handler for newsletter signup operations.

    Routes requests based on HTTP method and path.
    """
    # Lazy initialization
    _ensure_initialized()

    # Handle OPTIONS (CORS preflight)
    http_method = event.get('requestContext', {}).get('http', {}).get('method', '')
    if http_method == 'OPTIONS':
        return json_response(200, {})

    # Get route key from API Gateway v2
    route_key = event.get('routeKey', '')
    print(f"Handling route: {route_key}")

    # Route to appropriate handler
    if route_key == 'POST /subscribe':
        return handle_subscribe(event)
    elif route_key.startswith('GET /verify/'):
        return handle_verify(event)
    elif route_key.startswith('GET /unsubscribe/'):
        return handle_unsubscribe(event)
    else:
        return json_response(404, {'error': 'Not found'})
