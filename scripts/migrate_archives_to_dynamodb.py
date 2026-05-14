#!/usr/bin/env python3
"""
Migrate Newsletter Archives from S3 to DynamoDB

This script parses existing newsletter archive HTML files from S3 and stores
them as structured data in the reitsheet-newsletter-editions DynamoDB table.

S3 Source:
    s3://reitsheet-homepage/news/archive/YYYY-MM-DD/index.html

DynamoDB Target Table: reitsheet-newsletter-editions
    Primary Key: date (String)

Usage:
    # Dry run (default) - shows what would be migrated
    python scripts/migrate_archives_to_dynamodb.py

    # Verbose dry run
    python scripts/migrate_archives_to_dynamodb.py --dry-run --verbose

    # Migrate specific date
    python scripts/migrate_archives_to_dynamodb.py --date 2026-03-27

    # Migrate all archives
    python scripts/migrate_archives_to_dynamodb.py --migrate

    # Migrate with verbose output
    python scripts/migrate_archives_to_dynamodb.py --migrate --verbose
"""
import argparse
import boto3
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
from botocore.exceptions import ClientError

# Configure logging - only for this module, not for boto3
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress noisy boto3 debug logs
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Constants
S3_BUCKET = 'reitsheet-homepage'
S3_PREFIX = 'news/archive/'
DYNAMODB_TABLE = 'reitsheet-newsletter-editions'
AWS_REGION = 'us-east-1'

# Section names as they appear in the HTML
SECTION_HEADERS = {
    'Headlines': 'headline',
    'Financings and Offerings': 'financing',
    'Property Transactions and Leases': 'property',
    'Earnings Releases': 'earnings',
    'Other Announcements': 'other'
}


class ArchiveParser:
    """Parse newsletter archive HTML to extract structured data."""

    def __init__(self, companies_cache: Dict[str, str] = None):
        """
        Initialize parser with optional companies cache.

        Args:
            companies_cache: Dict mapping ticker -> company_name
        """
        self.companies_cache = companies_cache or {}

    def parse_archive_html(self, html: str, archive_date: str) -> Optional[Dict[str, Any]]:
        """
        Parse newsletter archive HTML and extract items.

        Args:
            html: Raw HTML content
            archive_date: Date string (YYYY-MM-DD)

        Returns:
            Dict with parsed data or None if parsing fails
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract items
            items = []
            sections = {
                'headline': [],
                'financing': [],
                'property': [],
                'earnings': [],
                'other': []
            }

            current_section = 'headline'  # Default section
            order_counter = 1

            # Find content div
            content_div = soup.find('div', style=lambda s: s and 'padding: 0 16px' in s)
            if not content_div:
                logger.warning(f"Could not find content div in archive for {archive_date}")
                return None

            # Process all elements in content div
            for element in content_div.children:
                if not hasattr(element, 'name') or element.name != 'div':
                    continue

                style = element.get('style', '')

                # Check if this is a section header
                if self._is_section_header(style):
                    text = element.get_text(strip=True)
                    for header_text, section_name in SECTION_HEADERS.items():
                        if header_text in text:
                            current_section = section_name
                            break
                    continue

                # Check if this is an item (has anchor tags)
                links = element.find_all('a')
                if len(links) >= 1:
                    item = self._parse_item(element, links, current_section, order_counter)
                    if item:
                        items.append(item)
                        sections[current_section].append(item)
                        order_counter += 1

            # Build result
            if not items:
                logger.warning(f"No items found in archive for {archive_date}")
                return None

            # Extract published_at from HTML if possible (from date header)
            date_div = soup.find('div', style=lambda s: s and 'font-style: italic' not in s and 'margin-top: 4px' in s)
            if date_div:
                # Parse date like "Friday, March 27, 2026"
                date_text = date_div.get_text(strip=True)
                try:
                    parsed_date = datetime.strptime(date_text, '%A, %B %d, %Y')
                    # Assume 8 AM ET publication time
                    published_at = parsed_date.replace(hour=8, minute=0, second=0).isoformat() + '+00:00'
                except ValueError:
                    published_at = f"{archive_date}T08:00:00+00:00"
            else:
                published_at = f"{archive_date}T08:00:00+00:00"

            return {
                'date': archive_date,
                'items': items,
                'sections': sections,
                'published_at': published_at,
                'status': 'published',
                'item_count': len(items),
                'migrated_at': datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Error parsing archive HTML for {archive_date}: {e}")
            return None

    def _is_section_header(self, style: str) -> bool:
        """Check if element style indicates a section header."""
        # Section headers have specific styling patterns
        return any(indicator in style for indicator in [
            'font-weight: bold',
            'border-bottom: 3px solid',
            'border-bottom: 1px solid'
        ]) and 'font-size: 1' in style

    def _parse_item(
        self,
        element,
        links: List,
        section: str,
        order: int
    ) -> Optional[Dict[str, Any]]:
        """
        Parse a single news item from its HTML element.

        Args:
            element: BeautifulSoup element
            links: List of anchor tags in element
            section: Current section name
            order: Display order

        Returns:
            Dict with item data or None
        """
        try:
            # Get URL from first link
            url = links[0].get('href', '')
            if not url or url == '#':
                return None

            # Skip navigation links (archive pages, your-domain.com links)
            if 'your-domain.com/news/archive' in url or url.startswith('/news/archive'):
                return None
            if 'your-domain.com' in url and '/news/' not in url:
                # Skip non-archive reitsheet links (e.g., front page)
                return None

            # Determine if this is a headline item (has company name) or condensed item
            if len(links) == 2:
                # Check if first link is company (headline format) or ticker (condensed format)
                first_text = links[0].get_text(strip=True)
                second_text = links[1].get_text(strip=True)

                # Headline format: "Company Name (TICKER)" followed by title link
                company_ticker_match = re.match(r'^(.+?)\s*\(([A-Z]+)\)$', first_text)
                if company_ticker_match:
                    company_name = company_ticker_match.group(1).strip()
                    ticker = company_ticker_match.group(2)
                    title = second_text
                else:
                    # Condensed format: "TICKER: Title"
                    ticker = first_text.upper()
                    title = second_text
                    company_name = self.companies_cache.get(ticker, '')

            elif len(links) == 1:
                # Single link - likely header link, extract ticker from text
                text = element.get_text(strip=True)
                link_text = links[0].get_text(strip=True)

                # Try to extract ticker
                ticker_match = re.search(r'^([A-Z]{1,5}):', text)
                if ticker_match:
                    ticker = ticker_match.group(1)
                    title = text.split(':', 1)[1].strip() if ':' in text else link_text
                else:
                    ticker = ''
                    title = link_text

                company_name = self.companies_cache.get(ticker, '') if ticker else ''
            else:
                return None

            return {
                'ticker': ticker,
                'company_name': company_name,
                'title': title,
                'url': url,
                'section': section,
                'order': order
            }

        except Exception as e:
            logger.debug(f"Error parsing item: {e}")
            return None


class ArchiveMigrator:
    """Migrate newsletter archives from S3 to DynamoDB."""

    def __init__(self, dry_run: bool = True, verbose: bool = False):
        """
        Initialize migrator.

        Args:
            dry_run: If True, don't write to DynamoDB
            verbose: If True, show detailed output
        """
        self.dry_run = dry_run
        self.verbose = verbose
        self.s3 = boto3.client('s3', region_name=AWS_REGION)
        self.dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        self.companies_cache = self._load_companies_cache()
        self.parser = ArchiveParser(self.companies_cache)

        # Stats
        self.stats = {
            'archives_found': 0,
            'archives_migrated': 0,
            'archives_skipped': 0,
            'archives_failed': 0,
            'total_items': 0
        }

    def _load_companies_cache(self) -> Dict[str, str]:
        """Load companies from DynamoDB for ticker -> name mapping."""
        cache = {}
        try:
            table = self.dynamodb.Table('reitsheet-companies-config')
            response = table.scan(
                ProjectionExpression='ticker, #n',
                ExpressionAttributeNames={'#n': 'name'}
            )

            for item in response.get('Items', []):
                ticker = item.get('ticker', '')
                name = item.get('name', '')
                if ticker and name:
                    cache[ticker] = name

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(
                    ProjectionExpression='ticker, #n',
                    ExpressionAttributeNames={'#n': 'name'},
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                for item in response.get('Items', []):
                    ticker = item.get('ticker', '')
                    name = item.get('name', '')
                    if ticker and name:
                        cache[ticker] = name

            logger.info(f"Loaded {len(cache)} companies into cache")
        except Exception as e:
            logger.warning(f"Could not load companies cache: {e}")

        return cache

    def _ensure_table_exists(self) -> bool:
        """Ensure DynamoDB table exists, create if not."""
        try:
            table = self.dynamodb.Table(DYNAMODB_TABLE)
            table.load()
            logger.info(f"Table {DYNAMODB_TABLE} exists")
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                if self.dry_run:
                    logger.info(f"[DRY RUN] Would create table {DYNAMODB_TABLE}")
                    return True

                logger.info(f"Creating table {DYNAMODB_TABLE}...")
                try:
                    table = self.dynamodb.create_table(
                        TableName=DYNAMODB_TABLE,
                        KeySchema=[
                            {'AttributeName': 'date', 'KeyType': 'HASH'}
                        ],
                        AttributeDefinitions=[
                            {'AttributeName': 'date', 'AttributeType': 'S'},
                            {'AttributeName': 'status', 'AttributeType': 'S'}
                        ],
                        GlobalSecondaryIndexes=[
                            {
                                'IndexName': 'status-date-index',
                                'KeySchema': [
                                    {'AttributeName': 'status', 'KeyType': 'HASH'},
                                    {'AttributeName': 'date', 'KeyType': 'RANGE'}
                                ],
                                'Projection': {'ProjectionType': 'ALL'}
                            }
                        ],
                        BillingMode='PAY_PER_REQUEST'
                    )
                    table.wait_until_exists()
                    logger.info(f"Created table {DYNAMODB_TABLE}")
                    return True
                except Exception as create_error:
                    logger.error(f"Failed to create table: {create_error}")
                    return False
            else:
                logger.error(f"Error checking table: {e}")
                return False

    def list_archives(self) -> List[str]:
        """List all archive dates in S3."""
        dates = []
        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    # Extract date from path like news/archive/2026-03-27/index.html
                    match = re.search(r'news/archive/(\d{4}-\d{2}-\d{2})/index\.html$', key)
                    if match:
                        dates.append(match.group(1))

            dates.sort()
            logger.info(f"Found {len(dates)} archives in S3")
            return dates

        except Exception as e:
            logger.error(f"Error listing S3 archives: {e}")
            return []

    def get_archive_html(self, archive_date: str) -> Optional[str]:
        """Download archive HTML from S3."""
        key = f"{S3_PREFIX}{archive_date}/index.html"
        try:
            response = self.s3.get_object(Bucket=S3_BUCKET, Key=key)
            return response['Body'].read().decode('utf-8')
        except Exception as e:
            logger.error(f"Error downloading {key}: {e}")
            return None

    def save_to_dynamodb(self, data: Dict[str, Any]) -> bool:
        """Save parsed archive data to DynamoDB."""
        if self.dry_run:
            if self.verbose:
                logger.info(f"[DRY RUN] Would save: {json.dumps(data, indent=2, default=str)}")
            else:
                logger.info(f"[DRY RUN] Would save {data['date']} ({data['item_count']} items)")
            return True

        try:
            table = self.dynamodb.Table(DYNAMODB_TABLE)
            table.put_item(Item=data)
            logger.info(f"Saved {data['date']} to DynamoDB ({data['item_count']} items)")
            return True
        except Exception as e:
            logger.error(f"Error saving to DynamoDB: {e}")
            return False

    def migrate_archive(self, archive_date: str) -> bool:
        """Migrate a single archive."""
        logger.info(f"Processing archive: {archive_date}")

        # Download HTML
        html = self.get_archive_html(archive_date)
        if not html:
            self.stats['archives_failed'] += 1
            return False

        # Parse HTML
        data = self.parser.parse_archive_html(html, archive_date)
        if not data:
            self.stats['archives_failed'] += 1
            return False

        if self.verbose:
            # Show parsed items
            logger.info(f"  Found {data['item_count']} items:")
            for section, items in data['sections'].items():
                if items:
                    logger.info(f"    {section}: {len(items)} items")
                    for item in items:
                        logger.info(f"      - {item['ticker']}: {item['title'][:50]}...")

        # Save to DynamoDB
        if self.save_to_dynamodb(data):
            self.stats['archives_migrated'] += 1
            self.stats['total_items'] += data['item_count']
            return True
        else:
            self.stats['archives_failed'] += 1
            return False

    def migrate_all(self, specific_date: Optional[str] = None):
        """Migrate all archives or a specific date."""
        # Ensure table exists
        if not self._ensure_table_exists():
            logger.error("Could not ensure table exists, aborting")
            return

        # Get list of archives
        if specific_date:
            dates = [specific_date]
        else:
            dates = self.list_archives()

        self.stats['archives_found'] = len(dates)

        if not dates:
            logger.warning("No archives to migrate")
            return

        logger.info(f"{'[DRY RUN] ' if self.dry_run else ''}Migrating {len(dates)} archives...")

        for archive_date in dates:
            self.migrate_archive(archive_date)

        # Print summary
        self._print_summary()

    def _print_summary(self):
        """Print migration summary."""
        logger.info("\n" + "=" * 50)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Archives found:    {self.stats['archives_found']}")
        logger.info(f"Archives migrated: {self.stats['archives_migrated']}")
        logger.info(f"Archives failed:   {self.stats['archives_failed']}")
        logger.info(f"Total items:       {self.stats['total_items']}")
        if self.dry_run:
            logger.info("\n[DRY RUN] No changes were made. Use --migrate to apply changes.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Migrate newsletter archives from S3 to DynamoDB',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (default) - shows what would be migrated
  python scripts/migrate_archives_to_dynamodb.py

  # Verbose dry run
  python scripts/migrate_archives_to_dynamodb.py --dry-run --verbose

  # Migrate specific date
  python scripts/migrate_archives_to_dynamodb.py --date 2026-03-27 --migrate

  # Migrate all archives
  python scripts/migrate_archives_to_dynamodb.py --migrate

  # Migrate with verbose output
  python scripts/migrate_archives_to_dynamodb.py --migrate --verbose
        """
    )

    parser.add_argument(
        '--migrate',
        action='store_true',
        help='Actually perform migration (default is dry run)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Show what would be migrated without making changes (default)'
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Migrate specific date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output'
    )

    args = parser.parse_args()

    # --migrate overrides --dry-run
    dry_run = not args.migrate

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"Newsletter Archive Migration Tool")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'MIGRATE'}")
    logger.info(f"Target: {DYNAMODB_TABLE}")
    logger.info("")

    migrator = ArchiveMigrator(dry_run=dry_run, verbose=args.verbose)
    migrator.migrate_all(specific_date=args.date)


if __name__ == '__main__':
    main()
