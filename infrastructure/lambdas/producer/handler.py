"""
S3 to SQS Producer Lambda with Email Protection
Triggered by S3 ObjectCreated events

Protection Features:
- Spam and virus filtering (SES scan results)
- File size limit enforcement (default: 5MB)
- Rate limiting per sender domain (10/min, 100/hour)
- Attachment type filtering (images and PDFs only)
"""
import json
import hashlib
import boto3
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote_plus
from typing import Dict, Tuple, Optional, List
from email import message_from_bytes
from email.message import Message

# ============================================================================
# Lazy Configuration (Deferred for Smoke Tests)
# ============================================================================

import os

_initialized = False
_config = {}
_tables = {}
_clients = {}


def _ensure_initialized():
    """
    Lazy initialization of AWS clients, env vars, and DynamoDB tables.
    Called once per Lambda container (cached for container lifetime).
    """
    global _initialized, _config, _tables, _clients

    if _initialized:
        return

    # AWS Clients
    _clients['s3'] = boto3.client('s3')
    _clients['sqs'] = boto3.client('sqs')
    _clients['dynamodb'] = boto3.resource('dynamodb')
    _clients['cloudwatch'] = boto3.client('cloudwatch')

    # Environment Variables
    _config['PARSE_QUEUE_URL'] = os.environ['PARSE_QUEUE_URL']
    _config['RATE_LIMIT_TABLE'] = os.environ['RATE_LIMIT_TABLE']
    _config['WHITELIST_TABLE'] = os.environ['WHITELIST_TABLE']
    _config['S3_BUCKET_NAME'] = os.environ['S3_BUCKET_NAME']
    _config['EMAIL_MAX_SIZE_BYTES'] = int(os.environ.get('EMAIL_MAX_SIZE_BYTES', 5 * 1024 * 1024))
    _config['EMAIL_RATE_LIMIT_PER_MINUTE'] = int(os.environ.get('EMAIL_RATE_LIMIT_PER_MINUTE', 10))
    _config['EMAIL_RATE_LIMIT_PER_HOUR'] = int(os.environ.get('EMAIL_RATE_LIMIT_PER_HOUR', 100))
    _config['EMAIL_SPAM_FILTERING_ENABLED'] = os.environ.get('EMAIL_SPAM_FILTERING_ENABLED', 'true').lower() == 'true'
    _config['EMAIL_ATTACHMENT_FILTERING_ENABLED'] = os.environ.get('EMAIL_ATTACHMENT_FILTERING_ENABLED', 'true').lower() == 'true'
    _config['EMAIL_ALLOWED_ATTACHMENT_TYPES'] = json.loads(os.environ.get('EMAIL_ALLOWED_ATTACHMENT_TYPES', '["image/jpeg", "image/png", "image/gif", "application/pdf", "text/plain", "text/html"]'))
    _config['RATE_LIMIT_MINUTE_TTL'] = int(os.environ.get('RATE_LIMIT_MINUTE_TTL', '120'))
    _config['RATE_LIMIT_HOUR_TTL'] = int(os.environ.get('RATE_LIMIT_HOUR_TTL', '3900'))

    # DynamoDB Tables
    dynamodb = _clients['dynamodb']
    _tables['rate_limit'] = dynamodb.Table(_config['RATE_LIMIT_TABLE'])
    _tables['whitelist'] = dynamodb.Table(_config['WHITELIST_TABLE'])

    _initialized = True


# Accessor functions
def _s3():
    return _clients['s3']


def _sqs():
    return _clients['sqs']


def _cloudwatch():
    return _clients['cloudwatch']


def _rate_limit_table():
    return _tables['rate_limit']


def _whitelist_table():
    return _tables['whitelist']


def extract_sender_domain(email_content: bytes) -> Optional[str]:
    """
    Extract sender domain from email headers.

    Single Responsibility: Parse sender domain only.

    Args:
        email_content: Raw email bytes

    Returns:
        Sender domain or None if not found
    """
    try:
        # Decode first 2KB of email to find headers
        header_section = email_content[:2048].decode('utf-8', errors='ignore')

        # Look for From: header
        from_match = re.search(r'^From:.*?@([\w\.-]+)', header_section, re.MULTILINE | re.IGNORECASE)
        if from_match:
            return from_match.group(1).lower()

        # Fallback: Look for Return-Path
        return_path_match = re.search(r'^Return-Path:.*?@([\w\.-]+)', header_section, re.MULTILINE | re.IGNORECASE)
        if return_path_match:
            return return_path_match.group(1).lower()

        return None
    except Exception as e:
        print(f"Error extracting sender domain: {e}")
        return None


def check_spam_virus_verdict(email_content: bytes) -> Tuple[bool, str]:
    """
    Check SES spam and virus scan results from email headers.

    Single Responsibility: Validate email safety only.

    Args:
        email_content: Raw email bytes

    Returns:
        (is_clean, reason) tuple
    """
    if not _config['EMAIL_SPAM_FILTERING_ENABLED']:
        return True, "filtering_disabled"

    try:
        # Decode first 4KB to check headers
        header_section = email_content[:4096].decode('utf-8', errors='ignore')

        # Check SES spam verdict
        if 'X-SES-Spam-Verdict: FAIL' in header_section:
            return False, "spam_detected"

        # Check SES virus verdict
        if 'X-SES-Virus-Verdict: FAIL' in header_section:
            return False, "virus_detected"

        return True, "clean"
    except Exception as e:
        print(f"Error checking spam/virus verdict: {e}")
        # Fail open: if we can't check, let it through (SES already scanned it)
        return True, "check_failed"


def check_attachment_types(email_content: bytes) -> Tuple[bool, str, List[str]]:
    """
    Check if email attachments are allowed types (images, PDFs only).

    Single Responsibility: Validate attachment types only.

    Args:
        email_content: Raw email bytes

    Returns:
        (is_allowed, reason, blocked_types) tuple
    """
    if not _config['EMAIL_ATTACHMENT_FILTERING_ENABLED']:
        return True, "filtering_disabled", []

    try:
        # Parse email message
        msg = message_from_bytes(email_content)
        blocked_attachments = []

        # Check all parts of the email
        for part in msg.walk():
            # Skip multipart containers
            if part.get_content_maintype() == 'multipart':
                continue

            content_type = part.get_content_type().lower()
            filename = part.get_filename()

            # If it has a filename, it's an attachment
            if filename:
                # Check against whitelist
                if content_type not in _config['EMAIL_ALLOWED_ATTACHMENT_TYPES']:
                    # Special handling for generic types
                    maintype = part.get_content_maintype()
                    if maintype not in ['image', 'text'] and content_type != 'application/pdf':
                        blocked_attachments.append(f"{filename}:{content_type}")

        if blocked_attachments:
            blocked_str = ",".join(blocked_attachments[:3])  # First 3 for brevity
            return False, f"blocked_attachments:{blocked_str}", blocked_attachments

        return True, "attachments_ok", []

    except Exception as e:
        print(f"Error checking attachments: {e}")
        # Fail open: if we can't parse, let it through (SES already scanned for viruses)
        return True, "check_failed", []


def increment_rate_limit_counter(limit_key: str, ttl_seconds: int) -> int:
    """
    Atomically increment counter in DynamoDB with TTL.

    Single Responsibility: Increment counter only.

    Args:
        limit_key: DynamoDB key (format: "domain:timestamp")
        ttl_seconds: TTL in seconds

    Returns:
        New counter value
    """
    expires_at = int((datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).timestamp())

    try:
        response = _rate_limit_table().update_item(
            Key={'limit_key': limit_key},
            UpdateExpression='ADD #count :inc SET #ttl = :ttl',
            ExpressionAttributeNames={
                '#count': 'count',
                '#ttl': 'expires_at'
            },
            ExpressionAttributeValues={
                ':inc': 1,
                ':ttl': expires_at
            },
            ReturnValues='UPDATED_NEW'
        )
        return int(response['Attributes']['count'])
    except Exception as e:
        print(f"Error incrementing rate limit counter: {e}")
        # Fail open: if rate limiting fails, let it through
        return 0


def is_domain_whitelisted(sender_domain: str) -> bool:
    """
    Check if domain is whitelisted (bypasses rate limits).

    Single Responsibility: Check whitelist only.

    Args:
        sender_domain: Email sender domain

    Returns:
        True if whitelisted, False otherwise
    """
    if not sender_domain:
        return False

    try:
        response = _whitelist_table().get_item(Key={'domain': sender_domain})
        return 'Item' in response
    except Exception as e:
        print(f"Error checking whitelist: {e}")
        # Fail closed: if whitelist check fails, apply rate limits
        return False


def check_rate_limit(sender_domain: str) -> Tuple[bool, str]:
    """
    Check if sender domain is within rate limits.

    Single Responsibility: Validate rate limits only.

    Args:
        sender_domain: Email sender domain

    Returns:
        (is_within_limits, reason) tuple
    """
    if not sender_domain:
        return True, "no_domain"

    # Check whitelist first - trusted domains bypass rate limits
    if is_domain_whitelisted(sender_domain):
        return True, "whitelisted"

    now = datetime.now(timezone.utc)

    # Minute-level rate limit
    minute_key = f"{sender_domain}:{now.strftime('%Y-%m-%d-%H-%M')}"
    minute_count = increment_rate_limit_counter(minute_key, _config['RATE_LIMIT_MINUTE_TTL'])

    if minute_count > _config['EMAIL_RATE_LIMIT_PER_MINUTE']:
        return False, f"minute_limit_exceeded:{minute_count}/{_config['EMAIL_RATE_LIMIT_PER_MINUTE']}"

    # Hour-level rate limit
    hour_key = f"{sender_domain}:{now.strftime('%Y-%m-%d-%H')}"
    hour_count = increment_rate_limit_counter(hour_key, _config['RATE_LIMIT_HOUR_TTL'])

    if hour_count > _config['EMAIL_RATE_LIMIT_PER_HOUR']:
        return False, f"hour_limit_exceeded:{hour_count}/{_config['EMAIL_RATE_LIMIT_PER_HOUR']}"

    return True, f"ok:{minute_count}/min,{hour_count}/hour"


def check_file_size(size_bytes: int) -> Tuple[bool, str]:
    """
    Check if file size is within limit.

    Single Responsibility: Validate file size only.

    Args:
        size_bytes: File size in bytes

    Returns:
        (is_within_limit, reason) tuple
    """
    if size_bytes > _config['EMAIL_MAX_SIZE_BYTES']:
        size_mb = size_bytes / (1024 * 1024)
        limit_mb = _config['EMAIL_MAX_SIZE_BYTES'] / (1024 * 1024)
        return False, f"size_limit_exceeded:{size_mb:.2f}MB/{limit_mb}MB"

    return True, "ok"


def publish_rejection_metric(reason: str, sender_domain: Optional[str] = None, size_bytes: int = 0) -> None:
    """
    Publish CloudWatch metric for rejected email.

    Single Responsibility: Track rejections for monitoring.

    Args:
        reason: Rejection reason (spam, virus, size_limit_exceeded, rate_limit_exceeded)
        sender_domain: Email sender domain (optional)
        size_bytes: Email size in bytes (for size limit tracking)
    """
    try:
        # Parse rejection type from reason
        rejection_type = reason.split(':')[0]  # e.g., "size_limit_exceeded" from "size_limit_exceeded:8MB/5MB"

        dimensions = [
            {'Name': 'RejectionType', 'Value': rejection_type}
        ]

        # Add domain dimension for rate limit violations
        if sender_domain and 'rate_limit' in rejection_type:
            dimensions.append({'Name': 'SenderDomain', 'Value': sender_domain})

        metrics = [
            {
                'MetricName': 'EmailRejected',
                'Value': 1,
                'Unit': 'Count',
                'Dimensions': dimensions
            }
        ]

        # Add size metric for size limit violations
        if 'size_limit' in rejection_type and size_bytes > 0:
            metrics.append({
                'MetricName': 'RejectedEmailSize',
                'Value': size_bytes / (1024 * 1024),  # Convert to MB
                'Unit': 'Megabytes',
                'Dimensions': [{'Name': 'RejectionType', 'Value': 'size_limit_exceeded'}]
            })

        _cloudwatch().put_metric_data(
            Namespace=f'{os.environ.get("PROJECT_NAME", "reitsheet")}/EmailProtection',
            MetricData=metrics
        )
    except Exception as e:
        # Don't fail email processing if metrics fail
        print(f"Error publishing rejection metric: {e}")


def delete_email_from_s3(bucket: str, key: str, reason: str, sender_domain: Optional[str] = None, size_bytes: int = 0) -> None:
    """
    Delete email from S3, log reason, and publish metrics.

    Single Responsibility: Delete rejected email only.

    Args:
        bucket: S3 bucket name
        key: S3 object key
        reason: Rejection reason (for logging)
        sender_domain: Email sender domain (for metrics)
        size_bytes: Email size (for metrics)
    """
    try:
        _s3().delete_object(Bucket=bucket, Key=key)
        print(f"REJECTED: {key} - Reason: {reason} - Domain: {sender_domain}")

        # Publish CloudWatch metric for tracking
        publish_rejection_metric(reason, sender_domain, size_bytes)
    except Exception as e:
        print(f"Error deleting rejected email {key}: {e}")


def send_to_parse_queue(message_data: Dict) -> Dict:
    """
    Send message to parse queue.

    Single Responsibility: Queue message only.

    Args:
        message_data: Message payload

    Returns:
        SQS response
    """
    return _sqs().send_message(
        QueueUrl=_config['PARSE_QUEUE_URL'],
        MessageBody=json.dumps(message_data),
        MessageAttributes={
            'idempotency_key': {
                'StringValue': message_data['idempotency_key'],
                'DataType': 'String'
            }
        }
    )


def process_email(bucket: str, key: str, size: int, etag: str) -> Tuple[bool, str]:
    """
    Process a single email with all protection checks.

    Single Responsibility: Orchestrate protection checks.

    Args:
        bucket: S3 bucket name
        key: S3 object key
        size: Object size in bytes
        etag: Object ETag

    Returns:
        (success, reason) tuple
    """
    sender_domain = None  # Will be extracted later

    # Check 1: File size limit
    size_ok, size_reason = check_file_size(size)
    if not size_ok:
        delete_email_from_s3(bucket, key, size_reason, sender_domain, size)
        return False, size_reason

    # Fetch email content for spam/virus and domain checks
    try:
        email_obj = _s3().get_object(Bucket=bucket, Key=key)
        email_content = email_obj['Body'].read()
    except Exception as e:
        print(f"Error fetching email {key}: {e}")
        return False, f"s3_fetch_error:{str(e)}"

    # Extract sender domain for tracking
    sender_domain = extract_sender_domain(email_content)

    # Check 2: Spam and virus filtering
    clean, clean_reason = check_spam_virus_verdict(email_content)
    if not clean:
        delete_email_from_s3(bucket, key, clean_reason, sender_domain, size)
        return False, clean_reason

    # Check 3: Attachment type filtering
    attachments_ok, attachment_reason, blocked_types = check_attachment_types(email_content)
    if not attachments_ok:
        delete_email_from_s3(bucket, key, attachment_reason, sender_domain, size)
        return False, attachment_reason

    # Check 4: Rate limiting
    rate_ok, rate_reason = check_rate_limit(sender_domain)
    if not rate_ok:
        delete_email_from_s3(bucket, key, rate_reason, sender_domain, size)
        return False, rate_reason

    # All checks passed - generate message and send to queue
    idempotency_key = hashlib.sha256(f"{bucket}:{key}:{etag}".encode()).hexdigest()

    message = {
        'bucket': bucket,
        'key': key,
        'etag': etag,
        'idempotency_key': idempotency_key,
        'ingested_at': datetime.now(timezone.utc).isoformat(),
        'attempts': 0,
        'sender_domain': sender_domain,
        'size_bytes': size,
        'protection_checks': {
            'size': size_reason,
            'spam_virus': clean_reason,
            'rate_limit': rate_reason
        }
    }

    response = send_to_parse_queue(message)

    print(f"ACCEPTED: {key} - Domain: {sender_domain} - MessageId: {response['MessageId']}")
    return True, "queued"


def lambda_handler(event, context):
    """
    Main Lambda handler - processes S3 ObjectCreated events.

    Orchestrates email protection and queuing.
    """
    # Lazy initialization (first invocation only)
    _ensure_initialized()

    results = {
        'accepted': 0,
        'rejected': 0,
        'errors': []
    }

    for record in event['Records']:
        try:
            # Extract S3 event details
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            size = record['s3']['object']['size']
            etag = record['s3']['object']['eTag']

            # Process email with protections
            success, reason = process_email(bucket, key, size, etag)

            if success:
                results['accepted'] += 1
            else:
                results['rejected'] += 1
                results['errors'].append({'key': key, 'reason': reason})

        except Exception as e:
            print(f"Error processing record: {e}")
            results['errors'].append({'key': 'unknown', 'reason': str(e)})

    print(f"Processing complete: {results['accepted']} accepted, {results['rejected']} rejected")

    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
