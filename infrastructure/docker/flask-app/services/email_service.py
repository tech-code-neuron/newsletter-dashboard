"""
Email Service - Business logic for email viewing and retrieval

SOLID Principles:
- Single Responsibility: Email display and S3 operations only
- Dependency Inversion: Works with EmailDTO abstraction
- Open/Closed: Easy to extend with DynamoDB integration later

Architecture:
Routes → EmailService → S3 Email Parsing → EmailDTO → Templates
"""
import boto3
import email
from email import policy
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import re
import logging

from core.dto import EmailDTO
from config.aws_config import aws_config

logger = logging.getLogger(__name__)


class EmailService:
    """
    Service for email operations (list, view, download).

    Handles S3 email retrieval, parsing, and DTO conversion.
    """

    def __init__(self):
        """Initialize S3 client and bucket config"""
        self.s3_client = boto3.client('s3', region_name=aws_config.aws_region)
        self.dynamodb = boto3.resource('dynamodb', region_name=aws_config.aws_region)
        self.bucket = 'reitsheet-email-ingest'
        self.prefix = 'incoming/'
        self.tracking_table = self.dynamodb.Table('reitsheet-email-tracking')

    def get_emails_for_display(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        search_query: Optional[str] = None,
        continuation_token: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get emails with filtering for display.

        Args:
            start_date: Start date for filtering (default: 7 days ago)
            end_date: End date for filtering (default: now)
            search_query: Search term for subject/from filtering
            continuation_token: S3 pagination token
            limit: Max emails per page (default: 50)

        Returns:
            {
                'emails': [EmailDTO, ...],
                'total_count': int,
                'next_token': str or None,
                'filters': {...}
            }
        """
        # Default date range: last 7 days
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=7)

        # Ensure timezone-aware
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        logger.info(f"Fetching emails from {start_date} to {end_date}")

        # List S3 objects
        list_params = {
            'Bucket': self.bucket,
            'Prefix': self.prefix,
            'MaxKeys': limit * 3  # Fetch extra to allow for filtering
        }

        if continuation_token:
            list_params['ContinuationToken'] = continuation_token

        try:
            response = self.s3_client.list_objects_v2(**list_params)
        except Exception as e:
            logger.error(f"Error listing S3 objects: {e}")
            return {
                'emails': [],
                'total_count': 0,
                'next_token': None,
                'filters': {
                    'start_date': start_date,
                    'end_date': end_date,
                    'search_query': search_query
                },
                'error': str(e)
            }

        # Parse email headers from S3 objects
        emails = []
        objects = response.get('Contents', [])

        for obj in objects:
            # Parse email headers FIRST (before date filtering)
            email_dto = self._parse_email_headers(obj['Key'], obj)

            if not email_dto:
                continue

            # Filter by email date (display_date uses email Date header)
            email_date = email_dto.display_date
            if email_date:
                if email_date < start_date or email_date > end_date:
                    continue
            else:
                # Fallback to S3 LastModified if no email date
                if obj['LastModified'] < start_date or obj['LastModified'] > end_date:
                    continue

            # Apply search filter
            if search_query:
                search_lower = search_query.lower()
                if not (
                    search_lower in email_dto.subject.lower() or
                    search_lower in email_dto.from_header.lower() or
                    search_lower in email_dto.from_domain.lower() or
                    (email_dto.ticker and search_lower in email_dto.ticker.lower())
                ):
                    continue

            emails.append(email_dto)

            # Stop if we have enough emails
            if len(emails) >= limit:
                break

        # Sort by date (newest first)
        emails.sort(
            key=lambda e: e.display_date or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )

        # Get next token for pagination
        next_token = response.get('NextContinuationToken')

        return {
            'emails': emails,
            'total_count': len(emails),
            'has_more': next_token is not None,
            'next_token': next_token,
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'search_query': search_query
            }
        }

    def _parse_email_headers(
        self,
        s3_key: str,
        s3_object_metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[EmailDTO]:
        """
        Parse email headers from S3 object (lightweight - headers only).

        Args:
            s3_key: S3 object key
            s3_object_metadata: Optional S3 object metadata from list_objects_v2

        Returns:
            EmailDTO with headers parsed, or None if parsing fails
        """
        try:
            # Download email (use BytesRange to get first 10KB for headers only)
            # Most email headers are < 2KB, but some have long headers
            response = self.s3_client.get_object(
                Bucket=self.bucket,
                Key=s3_key,
                Range='bytes=0-10239'  # First 10KB
            )

            partial_content = response['Body'].read()

            # Parse email (headers only - body will be truncated)
            msg = email.message_from_bytes(partial_content, policy=policy.default)

            # Extract headers
            from_header = msg.get('from', '')
            from_name, from_email = parseaddr(from_header)
            from_domain = from_email.split('@')[1] if '@' in from_email else ''

            # Parse email date
            email_date = None
            date_header = msg.get('date')
            if date_header:
                try:
                    email_date = parsedate_to_datetime(date_header)
                except Exception:
                    pass

            # Extract ticker from subject (common patterns)
            subject = msg.get('subject', '')
            ticker = self._extract_ticker_from_subject(subject)

            # Build DTO
            email_data = {
                'id': s3_key,
                'size': s3_object_metadata.get('Size', 0) if s3_object_metadata else 0,
                'last_modified': s3_object_metadata.get('LastModified') if s3_object_metadata else None,
                'message_id': msg.get('message-id', ''),
                'subject': subject,
                'from_header': from_header,
                'from_email': from_email,
                'from_domain': from_domain,
                'from_name': from_name,
                'to_header': msg.get('to', ''),
                'date': email_date,
                'ticker': ticker,
                'headers': dict(msg.items()),  # All headers as dict
            }

            return EmailDTO(email_data)

        except Exception as e:
            logger.warning(f"Error parsing email headers for {s3_key}: {e}")
            return None

    def get_email_by_id(self, email_id: str) -> Optional[EmailDTO]:
        """
        Get single email with full body content by S3 object key.

        Args:
            email_id: S3 object key

        Returns:
            EmailDTO with headers and body parsed, or None if not found
        """
        try:
            # Download full email
            response = self.s3_client.get_object(
                Bucket=self.bucket,
                Key=email_id
            )

            email_content = response['Body'].read()

            # Parse email
            msg = email.message_from_bytes(email_content, policy=policy.default)

            # Extract headers
            from_header = msg.get('from', '')
            from_name, from_email = parseaddr(from_header)
            from_domain = from_email.split('@')[1] if '@' in from_email else ''

            # Parse email date
            email_date = None
            date_header = msg.get('date')
            if date_header:
                try:
                    email_date = parsedate_to_datetime(date_header)
                except Exception:
                    pass

            # Extract body
            body_html = ''
            body_text = ''
            has_attachments = False
            attachment_count = 0

            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get('Content-Disposition', ''))

                    # Check for attachments
                    if 'attachment' in content_disposition:
                        has_attachments = True
                        attachment_count += 1
                        continue

                    # Extract body
                    if content_type == 'text/html' and not body_html:
                        try:
                            body_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except Exception:
                            pass
                    elif content_type == 'text/plain' and not body_text:
                        try:
                            body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except Exception:
                            pass
            else:
                # Single-part message
                content_type = msg.get_content_type()
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        decoded = payload.decode('utf-8', errors='ignore')
                        if content_type == 'text/html':
                            body_html = decoded
                        else:
                            body_text = decoded
                except Exception:
                    pass

            # Extract ticker from subject
            subject = msg.get('subject', '')
            ticker = self._extract_ticker_from_subject(subject)

            # Get S3 metadata
            head_response = self.s3_client.head_object(
                Bucket=self.bucket,
                Key=email_id
            )

            # Build DTO
            email_data = {
                'id': email_id,
                'size': head_response.get('ContentLength', 0),
                'last_modified': head_response.get('LastModified'),
                'message_id': msg.get('message-id', ''),
                'subject': subject,
                'from_header': from_header,
                'from_email': from_email,
                'from_domain': from_domain,
                'from_name': from_name,
                'to_header': msg.get('to', ''),
                'date': email_date,
                'body_html': body_html,
                'body_text': body_text,
                'has_attachments': has_attachments,
                'attachment_count': attachment_count,
                'ticker': ticker,
                'headers': dict(msg.items()),
            }

            return EmailDTO(email_data)

        except self.s3_client.exceptions.NoSuchKey:
            logger.warning(f"Email not found: {email_id}")
            return None
        except Exception as e:
            logger.error(f"Error getting email {email_id}: {e}")
            return None

    def generate_presigned_download_url(
        self,
        email_id: str,
        expires_in: int = 300
    ) -> Optional[str]:
        """
        Generate presigned S3 URL for raw email download.

        Args:
            email_id: S3 object key
            expires_in: URL expiration in seconds (default: 5 minutes)

        Returns:
            Presigned URL, or None if error
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket,
                    'Key': email_id,
                    'ResponseContentDisposition': 'attachment; filename="email.eml"'
                },
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            logger.error(f"Error generating presigned URL for {email_id}: {e}")
            return None

    def _extract_ticker_from_subject(self, subject: str) -> str:
        """
        Extract ticker from email subject (common patterns).

        Examples:
            "AMT - American Tower Announces..." → "AMT"
            "Realty Income (O) Declares..." → "O"
            "[PLD] Prologis Reports..." → "PLD"

        Returns:
            Ticker symbol (uppercase), or empty string if not found
        """
        if not subject:
            return ''

        # Pattern 1: "TICKER - " at start
        match = re.match(r'^([A-Z]{1,5})\s*-\s*', subject)
        if match:
            return match.group(1)

        # Pattern 2: "TICKER:" at start
        match = re.match(r'^([A-Z]{1,5}):\s*', subject)
        if match:
            return match.group(1)

        # Pattern 3: "(TICKER)" anywhere
        match = re.search(r'\(([A-Z]{1,5})\)', subject)
        if match:
            return match.group(1)

        # Pattern 4: "[TICKER]" anywhere
        match = re.search(r'\[([A-Z]{1,5})\]', subject)
        if match:
            return match.group(1)

        return ''

    # =========================================================================
    # Pipeline Status Tracking
    # =========================================================================

    def get_failed_and_stuck_emails(self, hours: int = 72) -> Dict[str, Dict]:
        """
        Get emails that failed or are stuck in the pipeline.

        Queries the email-tracking table for:
        - stage='failed' (explicit failures)
        - stage in ['parser','enricher','playwright'] with old updated_at (stuck)

        Args:
            hours: Look back hours (default: 72)

        Returns:
            Dict mapping idempotency_key to tracking info
        """
        from boto3.dynamodb.conditions import Attr

        cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        stuck_threshold = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()

        try:
            # Scan for recent failed/stuck items (table is TTL'd so this is bounded)
            response = self.tracking_table.scan(
                FilterExpression=Attr('updated_at').gte(cutoff_time)
            )

            items = response.get('Items', [])
            result = {}

            for item in items:
                stage = item.get('stage', '')
                updated_at = item.get('updated_at', '')
                idempotency_key = item.get('idempotency_key', '')

                # Include if failed
                if stage == 'failed':
                    result[idempotency_key] = {
                        'status': 'failed',
                        'stage': item.get('metadata', {}).get('failed_at_stage', 'unknown'),
                        'error': item.get('error_message', ''),
                        'ticker': item.get('ticker', ''),
                        'subject': item.get('subject', ''),
                        'updated_at': updated_at
                    }
                # Include if stuck (in processing stage for > 30 min)
                elif stage in ['parser', 'enricher', 'playwright', 'scraper']:
                    if updated_at < stuck_threshold:
                        result[idempotency_key] = {
                            'status': 'stuck',
                            'stage': stage,
                            'ticker': item.get('ticker', ''),
                            'subject': item.get('subject', ''),
                            'updated_at': updated_at
                        }

            logger.info(f"Found {len(result)} failed/stuck emails")
            return result

        except Exception as e:
            logger.error(f"Error querying tracking table: {e}")
            return {}

    def get_pipeline_stats(self, hours: int = 24) -> Dict[str, int]:
        """
        Get count of emails by pipeline stage.

        Returns:
            Dict with stage counts: {'completed': N, 'failed': N, 'parser': N, ...}
        """
        from boto3.dynamodb.conditions import Attr

        cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        try:
            response = self.tracking_table.scan(
                FilterExpression=Attr('updated_at').gte(cutoff_time)
            )

            items = response.get('Items', [])
            stats = {}

            for item in items:
                stage = item.get('stage', 'unknown')
                stats[stage] = stats.get(stage, 0) + 1

            return stats

        except Exception as e:
            logger.error(f"Error getting pipeline stats: {e}")
            return {}


# Singleton instance
_email_service = None


def get_email_service() -> EmailService:
    """Get or create EmailService singleton"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
