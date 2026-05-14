"""
Email Forwarder Lambda - Forward to Outlook with 8-K filtering and idempotency
"""
import json
import boto3
import os
import sys
import re
from email import message_from_bytes
from datetime import datetime, timedelta, timezone

# Add parent shared/ directory to path for shared utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
try:
    from shared.constants import CONFIRMATION_KEYWORDS
except ImportError:
    try:
        from constants import CONFIRMATION_KEYWORDS
    except ImportError:
        # Fallback for smoke tests - define minimum needed
        CONFIRMATION_KEYWORDS = []

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

    # AWS Clients
    _clients['s3'] = boto3.client('s3')
    _clients['ses'] = boto3.client('ses')
    _clients['dynamodb'] = boto3.resource('dynamodb')

    # Environment Variables
    _config['FORWARD_TO'] = os.environ['FORWARD_TO']
    _config['S3_BUCKET'] = os.environ['S3_BUCKET']
    _config['FORWARD_LOG_TABLE'] = os.environ.get('FORWARD_LOG_TABLE', 'reitsheet-forward-log')
    _config['EMAIL_STATS_TABLE'] = os.environ.get('EMAIL_STATS_TABLE', 'reitsheet-email-stats')

    # Filter patterns
    filter_value = os.environ.get('FORWARD_FILTER_PATTERNS', '8-K,8K,Form 8-K,Form 8K')
    _config['FORWARD_FILTER_PATTERNS'] = filter_value.split(',') if filter_value else []

    # DynamoDB Tables
    _tables['forward_log'] = _clients['dynamodb'].Table(_config['FORWARD_LOG_TABLE'])
    _tables['email_stats'] = _clients['dynamodb'].Table(_config['EMAIL_STATS_TABLE'])

    _initialized = True


def _s3():
    return _clients['s3']


def _ses():
    return _clients['ses']


def _forward_log_table():
    return _tables['forward_log']


def _email_stats_table():
    return _tables['email_stats']

# SEC filing type patterns for categorization (order matters - most specific first)
SEC_FILING_TYPES = {
    '424': r'424',  # Any 424 filing (424, 424A, 424B, 424B5, 424B3, etc.)
    'FWP': r'\bFWP\b|Free\s*Writing\s*Prospectus',
    '8-K': r'8-?K(?:/A)?',
    'Form 4': r'Form\s*4',
    'DEF 14A': r'DEF(?:INITIVE)?\s*14A',
    'DEFA14A': r'DEFA14A|Additional\s*Proxy\s*Soliciting\s*Materials',
    'PRE 14A': r'PRE(?:LIMINARY)?\s*14A',
    'ARS': r'\bARS\b|Annual\s*Report\s*to\s*Security\s*Holders',
    '10-Q': r'10-?Q(?:/A)?',
    '10-K': r'10-?K(?:/A)?',
    'Form 3': r'Form\s*3',
    'Form 5': r'Form\s*5',
    'S-3': r'S-3',
    'S-8': r'S-8',
    'Other SEC': r'SEC|EDGAR|Filing'
}

# SEC filing types to BLOCK (do not forward)
# Form 3/4/5 = statement of ownership forms (insider trading)
# DEF 14A / PRE 14A = proxy statements
BLOCKED_FILING_TYPES = {'Form 3', 'Form 4', 'Form 5', 'DEF 14A', 'DEFA14A', 'PRE 14A', 'ARS'}

# SEC filing types to FORWARD
ALLOWED_FILING_TYPES = {'8-K', '424', 'FWP'}

# CONFIRMATION_KEYWORDS imported from shared/constants.py (SSOT)
# These detect Form 4s and other SEC filings regardless of sender domain


def detect_filing_type(subject, body):
    """
    Detect SEC filing type from email subject/body.

    Args:
        subject: Email subject line
        body: Email body text

    Returns:
        str: Filing type (e.g., '8-K', '10-Q', 'Form 4', 'Other SEC')
    """
    content = f"{subject} {body}".lower()

    # Check each filing type pattern (order matters - most specific first)
    for filing_type, pattern in SEC_FILING_TYPES.items():
        if re.search(pattern, content, re.IGNORECASE):
            return filing_type

    return 'Unknown'


def increment_email_stat(stat_type, filing_type='general'):
    """
    Increment daily email statistics counter in DynamoDB.

    Single Responsibility: Only updates statistics
    Non-blocking: Failures don't affect email processing

    Args:
        stat_type: Type of stat (forwarded_company, forwarded_8k, filtered, spam)
        filing_type: SEC filing type if applicable
    """
    try:
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        # Build attribute name based on stat type and filing type
        if stat_type == 'forwarded_company':
            attr_name = 'forwarded_company_count'
        elif stat_type == 'forwarded_8k':
            attr_name = 'forwarded_8k_count'
        elif stat_type == 'filtered':
            # Sanitize filing type for DynamoDB attribute name
            safe_filing = filing_type.replace('-', '_').replace(' ', '_').lower()
            attr_name = f'filtered_{safe_filing}_count'
        elif stat_type == 'spam':
            attr_name = 'spam_count'
        else:
            attr_name = f'{stat_type}_count'

        # Increment counter atomically using boto3.resource
        _email_stats_table().update_item(
            Key={'date': today},
            UpdateExpression=f'ADD {attr_name} :inc, total_count :inc',
            ExpressionAttributeValues={':inc': 1}
        )
    except Exception as e:
        # Non-critical - log but don't fail email processing
        print(f"Failed to update stats (non-critical): {e}")


def should_forward_email(msg):
    """
    Determine if email should be forwarded based on source and content.

    Filter Logic:
    1. Content-based Form 4 detection (FIRST - catches Form 4s from any sender)
    2. SEC EDGAR emails: Forward 8-K, 424, FWP only (block Form 4, DEF 14A, PRE 14A)
    3. Company IR/PR emails: Forward everything (news, press releases)

    Single Responsibility: Only checks filter criteria
    Open/Closed: Modify ALLOWED_FILING_TYPES and BLOCKED_FILING_TYPES

    Args:
        msg: Email message object

    Returns:
        tuple: (should_forward: bool, reason: str, is_sec: bool, filing_type: str)
    """
    subject = msg.get('Subject', '').lower()
    from_addr = msg.get('From', '').lower()

    # Get email body (check both plain text and HTML)
    body_text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                try:
                    body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore').lower()
                    break
                except:
                    pass
    else:
        try:
            body_text = msg.get_payload(decode=True).decode('utf-8', errors='ignore').lower()
        except:
            pass

    # NEW: Content-based Form 4 filtering (BEFORE sender check)
    # This catches Form 4s from company IR emails (e.g., noreply@q4inc.com)
    # that bypass SEC sender domain filtering
    content_sample = f"{subject} {body_text[:2000]}"

    for keyword in CONFIRMATION_KEYWORDS:
        if keyword in content_sample:
            return False, f"BLOCKED - Content keyword: '{keyword}'", False, 'Form 4 or SEC'

    # Check if email is from SEC EDGAR
    is_sec_email = any(domain in from_addr for domain in [
        '@sec.gov',
        '@updates.sec.gov',
        'edgar',
        'sec.gov'
    ])

    # If NOT from SEC → Forward everything (IR/PR emails that passed content filter)
    if not is_sec_email:
        return True, "Company IR/PR email (forward all)", False, 'N/A'

    # Detect filing type for SEC emails
    filing_type = detect_filing_type(subject, body_text)

    # Check if filing type is blocked
    if filing_type in BLOCKED_FILING_TYPES:
        return False, f"SEC {filing_type} filing - BLOCKED (not useful)", True, filing_type

    # Check if filing type is allowed
    if filing_type in ALLOWED_FILING_TYPES:
        return True, f"SEC {filing_type} filing - FORWARDED", True, filing_type

    # Unknown SEC filing type - default to block
    return False, f"SEC {filing_type} filing - BLOCKED (not in allowed list)", True, filing_type


def lambda_handler(event, context):
    # Lazy initialization (first invocation only)
    _ensure_initialized()

    try:
        record = event['Records'][0]
        message_id = record['ses']['mail']['messageId']
        s3_key = f"incoming/{message_id}"

        print(f"Checking forward status for {message_id}")

        # Check if already forwarded (idempotency)
        try:
            response = _forward_log_table().get_item(Key={'message_id': message_id})

            if 'Item' in response:
                item = response['Item']
                forward_count = int(item.get('forward_count', 0))
                last_forwarded = item.get('forwarded_at', 'unknown')

                print(f"⚠️ Email {message_id} already forwarded {forward_count} time(s)")
                print(f"   Last forwarded: {last_forwarded}")
                print(f"   Skipping to prevent duplicate")

                return {
                    'statusCode': 200,
                    'body': json.dumps(f'Already forwarded {forward_count} times - skipped')
                }
        except Exception as e:
            print(f"Forward log check failed (continuing): {e}")

        # Download email
        response = _s3().get_object(Bucket=_config['S3_BUCKET'], Key=s3_key)
        email_bytes = response['Body'].read()

        # Parse email
        msg = message_from_bytes(email_bytes)

        # Check if email should be forwarded (filter SEC non-8-K filings)
        should_forward, reason, is_sec, filing_type = should_forward_email(msg)

        if not should_forward:
            # Structured logging for filtered emails
            from_field = msg.get('From', '')[:80]
            subject = msg.get('Subject', '')[:100]
            print(json.dumps({
                'action': 'filtered',
                'message_id': message_id,
                'from': from_field,
                'subject': subject,
                'filing_type': filing_type,
                'reason': reason,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }))

            # Track filtered SEC filing in stats
            increment_email_stat('filtered', filing_type)

            return {
                'statusCode': 200,
                'body': json.dumps(f'Email filtered (not forwarded): {reason}')
            }

        print(f"✅ Forwarding {message_id} (first time)")
        print(f"   Reason: {reason}")

        # Track forwarded email in stats
        if is_sec:
            increment_email_stat('forwarded_8k')
        else:
            increment_email_stat('forwarded_company')

        # Remove problematic headers
        # - Return-Path: Contains unverified bounce addresses
        # - DKIM-Signature: Becomes invalid when we modify From/Subject, and some emails have duplicates
        if 'Return-Path' in msg:
            del msg['Return-Path']

        # Remove ALL DKIM-Signature headers (some emails have multiple)
        while 'DKIM-Signature' in msg:
            del msg['DKIM-Signature']

        # Simple changes: From = alerts@reitsheet.co, add Fw: to subject
        msg.replace_header('From', 'alerts@reitsheet.co')
        subject = msg.get('Subject', '')
        msg.replace_header('Subject', f'Fw: {subject}')

        # Send it
        _ses().send_raw_email(
            Source='alerts@reitsheet.co',
            Destinations=[_config['FORWARD_TO']],
            RawMessage={'Data': msg.as_bytes()}
        )

        # Structured logging for easy searching
        from_field = msg.get('From', '')[:80]
        print(json.dumps({
            'action': 'forwarded',
            'message_id': message_id,
            'from': from_field,
            'subject': subject[:100],
            'to': _config['FORWARD_TO'],
            'filing_type': filing_type if filing_type else 'company_ir',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }))

        # Log the forward to prevent duplicates
        ttl = int((datetime.now(timezone.utc) + timedelta(days=90)).timestamp())
        try:
            _forward_log_table().put_item(
                Item={
                    'message_id': message_id,
                    'forwarded_at': datetime.now(timezone.utc).isoformat(),
                    'forwarded_to': _config['FORWARD_TO'],
                    'forward_count': 1,
                    'ttl': ttl
                }
            )
            print(f"Logged forward in DynamoDB")
        except Exception as e:
            print(f"Failed to log forward (non-critical): {e}")

        return {'statusCode': 200, 'body': json.dumps('Success')}

    except Exception as e:
        print(f"Error: {e}")
        return {'statusCode': 200, 'body': json.dumps(f'Error: {str(e)}')}
