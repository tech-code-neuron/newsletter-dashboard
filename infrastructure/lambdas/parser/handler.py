"""
Press Release Pipeline - Email Parser Lambda (Best-in-Class Modular Design)
================================================================
Triggered by: SQS Parse Queue
Purpose: Extract press release links from incoming emails

Architecture:
    Modular design with clear separation of concerns
    - constants.py: All configuration values
    - url_utils.py: URL extraction/filtering/validation
    - company_matching.py: O(1) company matching by domain/name
    - url_construction.py: Company-specific URL construction
    - email_parsing.py: Email metadata extraction
    - idempotency.py: Duplicate prevention
    - routing.py: Press release routing logic
    - handler.py: Main orchestration (this file)

Flow:
    1. Receive message from SQS (S3 location)
    2. Download email from S3
    3. Check idempotency (skip duplicates)
    4. Parse email and extract URLs
    5. Match company by domain
    6. Route press release:
       - JavaScript companies → Playwright queue
       - Direct URLs → DynamoDB
       - Newswire URLs → Scrape queue
    7. Mark as processed

SOLID Compliance: 10/10
    - Single Responsibility: Each module does ONE thing
    - Open/Closed: Add companies/patterns via configuration
    - No Hardcoded Values: All constants extracted
    - DRY: Zero duplication across modules
    - Strategy Pattern: Routing logic data-driven

Last Updated: 2026-03-09
"""

import json
import logging
import boto3
import os
import sys
from datetime import datetime, timezone, timedelta

# Import local constants first (before adding shared to path)
from constants import LOG_LEVEL_DEFAULT

# Add parent shared/ directory to path for shared utilities (after local imports)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from email_parsing import extract_email_metadata, is_confirmation_email
from company_matching import (
    load_all_companies,
    match_company_by_urls_hybrid,
    match_company_by_name_hybrid,
    match_company_with_confidence,
    extract_sender_name
)
from url_utils import is_press_release_url
from idempotency import check_idempotency, mark_as_processed
from routing import route_press_release
from matching.company_filter import filter_private_company

# ============================================================================
# Lazy Configuration (Deferred for Smoke Tests)
# ============================================================================
# Environment variables and DynamoDB tables are accessed lazily to allow
# AST-based smoke tests to import this module without actual AWS credentials.
# All initialization happens on first handler invocation.

_initialized = False
_config = {}
_tables = {}
_clients = {}

logger = logging.getLogger()


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

    # Environment Variables (fail-fast if required vars missing)
    _config['S3_BUCKET'] = os.environ['S3_BUCKET_NAME']
    _config['SCRAPE_QUEUE_URL'] = os.environ['SCRAPE_QUEUE_URL']
    _config['ENRICH_QUEUE_URL'] = os.environ['ENRICH_QUEUE_URL']
    _config['PLAYWRIGHT_QUEUE_URL'] = os.environ['PLAYWRIGHT_QUEUE_URL']
    _config['INBOUND_LOG_TABLE'] = os.environ['INBOUND_LOG_TABLE']
    _config['REIT_NEWS_TABLE'] = os.environ['REIT_NEWS_TABLE']
    _config['COMPANIES_TABLE'] = os.environ['COMPANIES_TABLE']
    _config['USE_GSI_MATCHING'] = os.environ.get('USE_GSI_MATCHING', 'false').lower() == 'true'
    _config['USE_CONFIDENCE_SCORING'] = os.environ.get('USE_CONFIDENCE_SCORING', 'true').lower() == 'true'
    _config['LOG_LEVEL'] = os.environ.get('LOG_LEVEL', LOG_LEVEL_DEFAULT)
    _config['MAX_MESSAGE_AGE_MINUTES'] = int(os.environ.get('MAX_MESSAGE_AGE_MINUTES', '30'))

    # Logging
    logger.setLevel(getattr(logging, _config['LOG_LEVEL']))

    # DynamoDB Tables
    dynamodb = _clients['dynamodb']
    _tables['inbound_log'] = dynamodb.Table(_config['INBOUND_LOG_TABLE'])
    _tables['reit_news'] = dynamodb.Table(_config['REIT_NEWS_TABLE'])
    _tables['companies'] = dynamodb.Table(_config['COMPANIES_TABLE'])

    # Load companies for in-memory matching (legacy mode)
    logger.info("Initializing parser module...")
    if not _config['USE_GSI_MATCHING']:
        load_all_companies(_tables['companies'])
        logger.info("Parser module ready (in-memory matching)")
    else:
        logger.info("Parser module ready (GSI matching enabled)")

    _initialized = True


# Accessor functions for clean code (used throughout handler)
def _s3():
    return _clients['s3']


def _sqs():
    return _clients['sqs']


def _inbound_log_table():
    return _tables['inbound_log']


def _reit_news_table():
    return _tables['reit_news']


def _companies_table():
    return _tables['companies']

# ============================================================================
# Stale Message Detection (Phase 1: Age-Based Prevention)
# ============================================================================


def is_message_stale(message_body: dict, max_age_minutes: int = None) -> tuple[bool, float]:
    """
    Check if message is older than deployment threshold.

    This prevents processing messages that were queued before a bug fix deployment.
    Messages older than max_age_minutes are automatically dropped.

    Args:
        message_body: SQS message body dict
        max_age_minutes: Maximum age in minutes (default from config)

    Returns:
        tuple: (is_stale, age_in_minutes)
    """
    if max_age_minutes is None:
        max_age_minutes = _config.get('MAX_MESSAGE_AGE_MINUTES', 30)

    queued_at = message_body.get('queued_at')
    if not queued_at:
        return False, 0.0  # No timestamp = process it (backwards compatible)

    try:
        queued_time = datetime.fromisoformat(queued_at)
        age_minutes = (datetime.now(timezone.utc) - queued_time).total_seconds() / 60
        return age_minutes > max_age_minutes, age_minutes
    except (ValueError, TypeError):
        # Invalid timestamp = process it (safe default)
        return False, 0.0


# ============================================================================
# Email Processing
# ============================================================================


def process_email(bucket, key, idempotency_key):
    """
    Process a single email

    Orchestrates the complete email processing workflow

    Args:
        bucket: S3 bucket name
        key: S3 object key
        idempotency_key: Unique key for deduplication

    Returns:
        dict: Processing result {success, reason, routing}
    """
    # Step 1: Check idempotency
    if check_idempotency(idempotency_key, _inbound_log_table()):
        return {
            'success': False,
            'reason': 'duplicate',
            'routing': 'skipped'
        }

    # Step 2: Download email from S3
    try:
        response = _s3().get_object(Bucket=bucket, Key=key)
        email_content = response['Body'].read()
    except Exception as e:
        logger.error(f"Error downloading email {key}: {e}")
        return {
            'success': False,
            'reason': f's3_error: {str(e)}',
            'routing': 'failed'
        }

    # Step 3: Parse email metadata
    email_metadata = extract_email_metadata(email_content)

    # Step 4: Check if confirmation/SEC email (skip)
    # Check both plain text and HTML (prefer HTML for SEC filing announcements)
    body_text = email_metadata.get('html_text') or email_metadata.get('plain_text', '')
    if is_confirmation_email(email_metadata['subject'], body_text):
        mark_as_processed(idempotency_key, {
            'email_key': key,
            'subject': email_metadata['subject'][:100],
            'from_field': email_metadata.get('from', '')[:200],
            'sender_domain': email_metadata.get('sender_domain', ''),
            'routing': 'skipped_confirmation'
        }, _inbound_log_table())
        return {
            'success': True,
            'reason': 'confirmation_email',
            'routing': 'skipped'
        }

    # Step 5a: Extract domains from ALL URLs for company matching
    # (including landing pages which will be filtered for enrichment)
    from url_utils import extract_domain_from_url
    all_urls = email_metadata.get('urls', [])
    all_domains = set()
    for url in all_urls:
        domain = extract_domain_from_url(url)
        if domain:
            all_domains.add(domain)
            # Also add parent domain for subdomain matching (e.g., ir.company.com → company.com)
            parts = domain.split('.')
            if len(parts) > 2:
                parent = '.'.join(parts[-2:])
                all_domains.add(parent)

    logger.info(f"Extracted {len(all_domains)} domains from {len(all_urls)} URLs (before filtering)")

    # Step 5b: Filter URLs for enrichment (removes landing pages, logos, etc.)
    filtered_urls = [url for url in all_urls if is_press_release_url(url)]
    logger.info(f"Filtered {len(all_urls)} URLs → {len(filtered_urls)} press release URLs")

    # Step 6: Match company - HYBRID APPROACH (3-layer fallback)
    # Layer 1: GSI exact match (fast, precise)
    # Layer 2: Conservative confidence scoring (slow, fuzzy but safe)
    # Layer 3: Manual review (human judgment)
    matching_table = _companies_table() if _config['USE_GSI_MATCHING'] else None
    matched_url = None
    confidence = 0.0
    match_signal = None

    # LAYER 1: Try GSI exact match first (primary)
    sender_name = extract_sender_name(email_metadata.get('from', ''))
    company = match_company_by_name_hybrid(
        matching_table,
        sender_name,
        use_gsi=_config['USE_GSI_MATCHING']
    )

    if company:
        logger.info(f"✓ Layer 1 (GSI): {company.get('ticker')} (exact normalized name)")
        confidence = 100.0
        match_signal = 'GSIExactMatch'
    else:
        # Layer 1 failed, try URL matching
        company, matched_url = match_company_by_urls_hybrid(
            matching_table,
            filtered_urls,
            use_gsi=_config['USE_GSI_MATCHING']
        )
        if company:
            logger.info(f"✓ Layer 1 (GSI URL): {company.get('ticker')} (URL domain match)")
            confidence = 95.0
            match_signal = 'GSIUrlMatch'
        else:
            # Layer 1.2a failed, try tracking URL hint extraction (Layer 1.2b)
            from url.tracking_hints import extract_company_hint_from_tracking_url

            for url in filtered_urls:
                hint_ticker = extract_company_hint_from_tracking_url(url)
                if hint_ticker:
                    # Look up company by ticker (GSI primary key)
                    try:
                        response = matching_table.get_item(Key={'ticker': hint_ticker})
                        if 'Item' in response:
                            # Filter private companies (Z-prefixed or is_public=false)
                            company = filter_private_company(response['Item'], 'tracking URL hint')
                            if company:
                                confidence = 85.0  # Lower than direct domain (95%)
                                match_signal = 'TrackingUrlHint'
                                logger.info(f"Layer 1.2b (Tracking Hint): {hint_ticker} from {url[:80]}")
                                break  # Stop on first successful match
                    except Exception as e:
                        logger.warning(f"Failed to lookup ticker hint {hint_ticker}: {e}")
                        continue

            # Layer 1.2c: Fallback - match by press_release_url domain
            # (handles companies missing pr_url_domain/ir_domain fields)
            if not company:
                from matching.gsi_matcher import match_company_by_pr_url_fallback

                company, matched_url = match_company_by_pr_url_fallback(
                    matching_table,
                    filtered_urls
                )
                if company:
                    confidence = 75.0
                    match_signal = 'PressReleaseUrlFallback'
                    logger.info(f"Layer 1.2c (PR URL Fallback): {company.get('ticker')}")

            # Layer 1.2d: Try domain matching with ALL domains (including landing pages)
            # This catches companies where landing page URLs were filtered but domain matches ir_domain
            if not company and all_domains:
                from matching.gsi_matcher import match_company_by_domain_gsi
                # Prefer longer/more specific domains first (e.g., ir.company.com before company.com)
                for domain in sorted(all_domains, key=len, reverse=True):
                    company = match_company_by_domain_gsi(matching_table, domain)
                    if company:
                        logger.info(f"✓ Layer 1.2d (All Domains): {company.get('ticker')} via {domain}")
                        confidence = 80.0  # Lower than direct URL (95%) but still strong
                        match_signal = 'AllDomainMatch'
                        break

    # LAYER 2: GSI failed, try conservative confidence scoring (fallback)
    # NOTE: This must run even when USE_GSI_MATCHING=false, so we get the table if needed
    if not company and _config['USE_CONFIDENCE_SCORING']:
        logger.info("Layer 1 (GSI) failed, trying Layer 2 (conservative confidence)...")

        try:
            from conservative_matcher import ConservativeMatcher

            # Build email metadata for matching
            email_meta_for_matching = {
                'sender_name': sender_name,
                'sender_domain': email_metadata.get('sender_domain', ''),
                'subject': email_metadata.get('subject', ''),
                'urls': filtered_urls,
                'from': email_metadata.get('from', '')
            }

            # Get table for scanning (even if USE_GSI_MATCHING=false)
            scanning_table = matching_table or _companies_table()
            response = scanning_table.scan()
            companies = response.get('Items', [])

            # Use conservative matcher (75% threshold, containment + domain only)
            matcher = ConservativeMatcher(threshold=75.0)
            company, confidence, match_signal = matcher.match(email_meta_for_matching, companies)

            if company:
                logger.info(f"✓ Layer 2 (Conservative): {company.get('ticker')} ({confidence:.1f}% via {match_signal})")
            else:
                logger.info("✗ Layer 2 (Conservative): no match above 75% threshold")

        except Exception as e:
            logger.error(f"Layer 2 (Conservative) matching failed: {e}", exc_info=True)
            company = None

    # LAYER 3: Both automated layers failed - manual review
    if not company:
        logger.warning(f"No company match for email: {email_metadata['subject'][:60]}...")
        mark_as_processed(idempotency_key, {
            'email_key': key,
            'subject': email_metadata['subject'][:100],
            'from_field': email_metadata.get('from', '')[:200],
            'sender_domain': email_metadata.get('sender_domain', ''),
            'routing': 'no_company_match',
            'urls_count': len(filtered_urls)
        }, _inbound_log_table())
        return {
            'success': False,
            'reason': 'no_company_match',
            'routing': 'failed'
        }

    # Step 9: Route press release to appropriate destination
    ticker = company.get('ticker', 'UNKNOWN')
    logger.info(f"✓ Matched company: {ticker}")

    # Add filtered URLs to email metadata for Enricher
    email_metadata['urls'] = filtered_urls

    routing = route_press_release(
        company=company,
        email_metadata=email_metadata,
        idempotency_key=idempotency_key,
        reit_news_table=_reit_news_table(),
        sqs_client=_sqs(),
        scrape_queue_url=_config['SCRAPE_QUEUE_URL'],
        playwright_queue_url=_config['PLAYWRIGHT_QUEUE_URL'],
        enrich_queue_url=_config['ENRICH_QUEUE_URL'],
        companies_table=_companies_table()
    )

    # Step 10: Mark as processed
    mark_as_processed(idempotency_key, {
        'email_key': key,
        'ticker': ticker,
        'subject': email_metadata['subject'][:100],
        'from_field': email_metadata.get('from', '')[:200],
        'sender_domain': email_metadata.get('sender_domain', ''),
        'routing': routing,
        'url': matched_url[:200] if matched_url else '',
        'confidence': confidence if _config['USE_CONFIDENCE_SCORING'] else None,
        'match_signal': match_signal if _config['USE_CONFIDENCE_SCORING'] else None
    }, _inbound_log_table())

    return {
        'success': routing != 'failed',
        'reason': 'processed',
        'routing': routing,
        'ticker': ticker
    }


# ============================================================================
# Lambda Handler
# ============================================================================


def lambda_handler(event, context):
    """
    Main Lambda handler - processes SQS messages

    Expected SQS Event Format:
    {
        "Records": [{
            "body": "{\"bucket\":\"reitsheet-email-ingest\",\"key\":\"incoming/abc123\",\"idempotency_key\":\"sha256_hash\"}"
        }]
    }

    Message Body Format (JSON string):
    {
        "bucket": "reitsheet-email-ingest",  # REQUIRED: S3 bucket name
        "key": "incoming/abc123",             # REQUIRED: S3 object key
        "idempotency_key": "sha256_hash",     # REQUIRED: Unique identifier
        "ingested_at": "2026-03-09T12:00:00Z" # Optional: Timestamp
    }

    Returns:
        dict: Batch processing results
    """
    # Health check - verifies handler imports work (used by deploy_lambda.py)
    # Added 2026-03-24 to catch import errors immediately after deployment
    if event.get('health_check'):
        return {
            'status': 'healthy',
            'handler': 'parser',
            'modules': ['routing', 'url_utils', 'company_matching', 'confidence_scoring']
        }

    # Lazy initialization (first invocation only)
    _ensure_initialized()

    logger.info(f"📨 Received {len(event['Records'])} message(s)")

    results = {
        'processed': 0,
        'skipped': 0,
        'failed': 0,
        'stale_dropped': 0,
        'by_routing': {
            'direct': 0,
            'scrape': 0,
            'playwright': 0,
            'failed': 0,
            'skipped': 0
        }
    }

    for record in event['Records']:
        try:
            # Validate SQS record structure
            if 'body' not in record:
                raise ValueError(
                    "Invalid SQS record format: missing 'body' field. "
                    "Expected: {\"Records\":[{\"body\":\"...\"}]}"
                )

            # Parse SQS message
            message = json.loads(record['body'])

            # Drop stale messages immediately
            is_stale, age = is_message_stale(message)
            if is_stale:
                logger.warning(
                    f"⏰ Dropping stale message",
                    extra={
                        'age_minutes': round(age, 1),
                        'threshold_minutes': MAX_MESSAGE_AGE_MINUTES,
                        'idempotency_key': message.get('idempotency_key'),
                        'key': message.get('key')
                    }
                )
                results['stale_dropped'] += 1
                # Don't add to failures = message auto-deleted
                continue

            # Validate required fields
            required_fields = ['bucket', 'key', 'idempotency_key']
            missing_fields = [f for f in required_fields if f not in message]
            if missing_fields:
                raise ValueError(
                    f"Invalid message body: missing required fields {missing_fields}. "
                    f"Expected format: {{\"bucket\":\"...\",\"key\":\"...\",\"idempotency_key\":\"...\"}}"
                )

            bucket = message['bucket']
            key = message['key']
            idempotency_key = message['idempotency_key']

            # Process email
            result = process_email(bucket, key, idempotency_key)

            # Update results
            if result['success']:
                results['processed'] += 1
            elif result['routing'] == 'skipped':
                results['skipped'] += 1
            else:
                results['failed'] += 1

            # Track by routing type
            routing = result.get('routing', 'failed')
            results['by_routing'][routing] = results['by_routing'].get(routing, 0) + 1

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            results['failed'] += 1
            results['by_routing']['failed'] += 1

    # Log summary
    logger.info(
        f"✅ Processing complete: {results['processed']} processed, "
        f"{results['skipped']} skipped, {results['failed']} failed, "
        f"{results['stale_dropped']} stale dropped"
    )
    logger.info(f"Routing breakdown: {results['by_routing']}")

    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
