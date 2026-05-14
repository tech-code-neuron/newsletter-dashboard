"""
DynamoDB Repository Implementations

Uses boto3.resource('dynamodb') for auto-deserialization.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import List, Optional, Dict, Any
import logging
import traceback

from config.aws_config import aws_config
from core.dto import (
    CompanyDTO, PressReleaseDTO, NewsletterDTO,
    ReviewEmailDTO, RelevanceDecisionDTO, DisclosureDTO
)
from core.repositories.base import (
    CompanyRepository, PressReleaseRepository,
    NewsletterRepository, ReviewEmailRepository, RelevanceRepository,
    DisclosureRepository
)
from core.repositories.dynamodb_utils import DynamoDBUpdateBuilder, paginated_scan

logger = logging.getLogger(__name__)


class DynamoDBCompanyRepository(CompanyRepository):
    """DynamoDB implementation for companies"""

    def __init__(self):
        self.table = aws_config.get_dynamodb_table(aws_config.companies_table_name)

    def get_all(self, limit: int = 500) -> List[CompanyDTO]:
        """Get all companies"""
        response = self.table.scan(Limit=limit)
        items = response.get('Items', [])
        return [CompanyDTO(item) for item in items]

    def get_all_active(self, limit: int = 500) -> List[CompanyDTO]:
        """Get all active companies"""
        from boto3.dynamodb.conditions import Attr

        response = self.table.scan(
            FilterExpression=Attr('active').eq(True) | Attr('active').not_exists(),
            Limit=limit
        )
        items = response.get('Items', [])
        # Sort by ticker
        items.sort(key=lambda x: x.get('ticker', ''))
        return [CompanyDTO(item) for item in items]

    def get_by_ticker(self, ticker: str) -> Optional[CompanyDTO]:
        """Get company by ticker"""
        response = self.table.get_item(Key={'ticker': ticker})
        item = response.get('Item')
        return CompanyDTO(item) if item else None

    def get_by_id(self, company_id: int) -> Optional[CompanyDTO]:
        """
        Get company by ID - INEFFICIENT O(n) table scan.

        DEPRECATED: Use get_by_ticker() instead for O(1) DynamoDB lookup.
        This method scans the entire table to find a matching ID.
        """
        stack_trace = ''.join(traceback.format_stack()[-4:-1])
        logger.warning(
            f"PERFORMANCE WARNING: get_by_id({company_id}) performs O(n) table scan. "
            f"Use get_by_ticker() for O(1) lookup instead.\n"
            f"Called from:\n{stack_trace}"
        )
        companies = self.get_all()
        for company in companies:
            if company.id == company_id:
                return company
        return None

    def search(self, query: str, limit: int = 100) -> List[CompanyDTO]:
        """Search companies by ticker or name"""
        from boto3.dynamodb.conditions import Attr

        query_lower = query.lower()
        response = self.table.scan(
            FilterExpression=Attr('ticker').contains(query.upper()) |
                           Attr('company_name').contains(query),
            Limit=limit
        )
        items = response.get('Items', [])
        return [CompanyDTO(item) for item in items]

    def update(self, ticker: str, data: Dict[str, Any]) -> bool:
        """Update company data"""
        try:
            builder = DynamoDBUpdateBuilder(primary_key='ticker')
            update_kwargs = builder.build(data, remove_none=True)

            if not update_kwargs:
                return True  # Nothing to update

            self.table.update_item(Key={'ticker': ticker}, **update_kwargs)
            return True
        except Exception as e:
            logger.error(f"Error updating company {ticker}: {e}")
            return False

    def create(self, data: Dict[str, Any]) -> CompanyDTO:
        """Create new company with field validation"""
        # Validate Playwright configuration
        url_method = data.get('url_construction_method') or data.get('ir_platform')
        if url_method == 'playwright_scraper':
            required_fields = ['playwright_url', 'playwright_selector', 'playwright_wait_for']
            missing = [f for f in required_fields if not data.get(f)]
            if missing:
                raise ValueError(
                    f"Playwright configuration incomplete: missing {', '.join(missing)}. "
                    f"Required fields: playwright_url, playwright_selector, playwright_wait_for"
                )

        # Note: direct_url doesn't require press_release_url for initial creation
        # User can add IR URL later via edit form

        # Ensure required fields
        data['created_at'] = datetime.now(timezone.utc).isoformat()
        data['updated_at'] = datetime.now(timezone.utc).isoformat()
        if 'active' not in data:
            data['active'] = True

        self.table.put_item(Item=data)
        return CompanyDTO(data)

    def delete(self, ticker: str) -> bool:
        """Delete company by ticker"""
        try:
            self.table.delete_item(Key={'ticker': ticker})
            logger.info(f"Deleted company: {ticker}")
            return True
        except Exception as e:
            logger.error(f"Error deleting company {ticker}: {e}")
            return False

    def get_with_release_stats(self) -> List[Dict[str, Any]]:
        """Get companies with latest release date and count - parallelized for performance"""
        # Get all companies (both active and inactive)
        companies = self.get_all()

        # Get press releases table for stats
        news_table = aws_config.get_dynamodb_table(aws_config.reit_news_table_name)

        results = []
        results_lock = Lock()  # Thread-safe appends

        def fetch_stats(company):
            """Fetch stats for a single company - thread-safe"""
            from boto3.dynamodb.conditions import Key
            try:
                # Query 1: Get latest release date
                response = news_table.query(
                    IndexName='ticker-date-index',
                    KeyConditionExpression=Key('ticker').eq(company.ticker),
                    ScanIndexForward=False,  # Descending
                    Limit=1,
                    ProjectionExpression='press_release_date'
                )
                items = response.get('Items', [])
                latest_date = items[0].get('press_release_date') if items else None

                # Query 2: Get count
                count_response = news_table.query(
                    IndexName='ticker-date-index',
                    KeyConditionExpression=Key('ticker').eq(company.ticker),
                    Select='COUNT'
                )
                release_count = count_response.get('Count', 0)

                result = {
                    'company': company,
                    'latest_date': latest_date,
                    'release_count': release_count
                }
            except Exception as e:
                logger.warning(f"Error getting stats for {company.ticker}: {e}")
                result = {
                    'company': company,
                    'latest_date': None,
                    'release_count': 0
                }

            with results_lock:
                results.append(result)

        # Execute all queries in parallel (max 10 concurrent to avoid throttling)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_stats, c) for c in companies]
            # Wait for all to complete
            for future in as_completed(futures):
                pass  # Results collected via lock in fetch_stats

        # Re-sort to maintain original order (callers may depend on it)
        ticker_order = {c.ticker: i for i, c in enumerate(companies)}
        results.sort(key=lambda r: ticker_order.get(r['company'].ticker, 999))

        return results


class DynamoDBPressReleaseRepository(PressReleaseRepository):
    """DynamoDB implementation for press releases"""

    def __init__(self):
        self.table = aws_config.get_dynamodb_table(aws_config.reit_news_table_name)
        self._company_cache: Dict[str, CompanyDTO] = {}

    def _get_company(self, ticker: str) -> CompanyDTO:
        """Get company with caching"""
        if ticker not in self._company_cache:
            company_table = aws_config.get_dynamodb_table(aws_config.companies_table_name)
            response = company_table.get_item(Key={'ticker': ticker})
            item = response.get('Item', {'ticker': ticker})
            self._company_cache[ticker] = CompanyDTO(item)
        return self._company_cache[ticker]

    def clear_company_cache(self, ticker: str) -> None:
        """Clear cached company data after mutation.

        Call this when a company is created, updated, or deleted to ensure
        press release queries reflect the current company state.
        """
        self._company_cache.pop(ticker, None)

    def _item_to_dto(self, item: Dict[str, Any]) -> PressReleaseDTO:
        """Convert DynamoDB item to DTO with company"""
        ticker = item.get('ticker', '')
        company = self._get_company(ticker) if ticker else None
        return PressReleaseDTO(item, company)

    def get_by_id(self, release_id: int) -> Optional[PressReleaseDTO]:
        """
        Get press release by ID - INEFFICIENT O(n) table scan.

        DEPRECATED: Use get_by_url() instead for O(1) DynamoDB lookup.
        This method scans up to 500 items to find a matching ID (100-500ms).
        get_by_url() performs O(1) primary key lookup (5-10ms).

        Performance impact: 90% slower than get_by_url().
        """
        stack_trace = ''.join(traceback.format_stack()[-4:-1])
        logger.warning(
            f"PERFORMANCE WARNING: get_by_id({release_id}) performs O(n) table scan (100-500ms). "
            f"Use get_by_url() for O(1) lookup (5-10ms) - 90% faster!\n"
            f"Called from:\n{stack_trace}"
        )
        response = self.table.scan(Limit=500)
        for item in response.get('Items', []):
            dto = self._item_to_dto(item)
            if dto.id == release_id:
                return dto
        return None

    def get_by_url(self, url: str) -> Optional[PressReleaseDTO]:
        """Get press release by URL"""
        response = self.table.get_item(Key={'url': url})
        item = response.get('Item')
        return self._item_to_dto(item) if item else None

    def get_by_unique_id(self, unique_id: str) -> Optional[PressReleaseDTO]:
        """Get press release by unique_id"""
        from boto3.dynamodb.conditions import Attr

        response = self.table.scan(
            FilterExpression=Attr('unique_id').eq(unique_id),
            Limit=1
        )
        items = response.get('Items', [])
        return self._item_to_dto(items[0]) if items else None

    def get_recent(
        self,
        limit: int = 50,
        days: Optional[int] = None,
        category: Optional[str] = None,
        tickers: Optional[List[str]] = None,
        include_deleted: bool = False
    ) -> List[PressReleaseDTO]:
        """Get recent press releases with filtering"""
        from boto3.dynamodb.conditions import Attr

        # Build filter expression
        filters = []

        if not include_deleted:
            filters.append(Attr('deleted_at').not_exists())

        if days and days != 9999:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            filters.append(Attr('press_release_date').gte(cutoff))

        if category and category != 'all':
            filters.append(Attr('category').eq(category))

        if tickers:
            # OR condition for multiple tickers
            ticker_filter = None
            for ticker in tickers:
                if ticker_filter is None:
                    ticker_filter = Attr('ticker').eq(ticker)
                else:
                    ticker_filter = ticker_filter | Attr('ticker').eq(ticker)
            if ticker_filter:
                filters.append(ticker_filter)

        # Combine filters
        filter_expr = None
        for f in filters:
            filter_expr = f if filter_expr is None else filter_expr & f

        # Query
        scan_kwargs = {'Limit': limit}
        if filter_expr:
            scan_kwargs['FilterExpression'] = filter_expr

        response = self.table.scan(**scan_kwargs)
        items = response.get('Items', [])

        # Sort by date descending - prefer email_received_at (has time) over press_release_date (date-only)
        # NOTE: first_seen_at EXCLUDED - it's Lambda processing time, not email time
        items.sort(
            key=lambda x: x.get('email_received_at') or x.get('press_release_date', ''),
            reverse=True
        )

        return [self._item_to_dto(item) for item in items[:limit]]

    def get_archived(self, limit: int = 100) -> List[PressReleaseDTO]:
        """Get archived (soft-deleted) press releases"""
        from boto3.dynamodb.conditions import Attr

        response = self.table.scan(
            FilterExpression=Attr('deleted_at').exists(),
            Limit=limit
        )
        items = response.get('Items', [])
        items.sort(key=lambda x: x.get('deleted_at', ''), reverse=True)
        return [self._item_to_dto(item) for item in items]

    def get_by_company(
        self,
        ticker: str,
        limit: int = 50,
        include_deleted: bool = False
    ) -> List[PressReleaseDTO]:
        """Get press releases for a company"""
        from boto3.dynamodb.conditions import Key, Attr

        query_kwargs = {
            'IndexName': 'ticker-date-index',
            'KeyConditionExpression': Key('ticker').eq(ticker),
            'ScanIndexForward': False,
            'Limit': limit
        }

        if not include_deleted:
            query_kwargs['FilterExpression'] = Attr('deleted_at').not_exists()

        response = self.table.query(**query_kwargs)
        items = response.get('Items', [])
        return [self._item_to_dto(item) for item in items]

    def get_uncategorized_count(self) -> int:
        """Get count of uncategorized press releases"""
        from boto3.dynamodb.conditions import Attr

        response = self.table.scan(
            FilterExpression=Attr('category').not_exists() & Attr('deleted_at').not_exists(),
            Select='COUNT'
        )
        return response.get('Count', 0)

    def get_total_count(self, include_deleted: bool = False) -> int:
        """Get total press release count"""
        from boto3.dynamodb.conditions import Attr

        if include_deleted:
            response = self.table.scan(Select='COUNT')
        else:
            response = self.table.scan(
                FilterExpression=Attr('deleted_at').not_exists(),
                Select='COUNT'
            )
        return response.get('Count', 0)

    def update(self, url: str, data: Dict[str, Any]) -> bool:
        """Update press release data

        Handles None values by using REMOVE instead of SET to properly
        delete attributes from DynamoDB (avoids NULL serialization issues).
        """
        try:
            builder = DynamoDBUpdateBuilder(primary_key='url')
            update_kwargs = builder.build(data, remove_none=True)

            if not update_kwargs:
                logger.info(f"[TITLE_SYNC] No updates to apply for {url}")
                return True

            # Debug logging for title sync troubleshooting
            logger.info(f"[TITLE_SYNC] DynamoDB update - Key: {url[:80]}...")
            logger.info(f"[TITLE_SYNC] UpdateExpression: {update_kwargs['UpdateExpression']}")
            if 'display_title' in data:
                logger.info(f"[TITLE_SYNC] Title-related update - Values: {update_kwargs.get('ExpressionAttributeValues', {})}")

            self.table.update_item(Key={'url': url}, **update_kwargs)
            return True
        except Exception as e:
            logger.error(f"Error updating press release {url}: {e}")
            return False

    def create(self, data: Dict[str, Any]) -> PressReleaseDTO:
        """Create new press release"""
        data['scraped_date'] = datetime.now(timezone.utc).isoformat()
        self.table.put_item(Item=data)
        return self._item_to_dto(data)

    def soft_delete(self, url: str) -> bool:
        """Soft delete a press release"""
        return self.update(url, {'deleted_at': datetime.now(timezone.utc).isoformat()})

    def restore(self, url: str) -> bool:
        """Restore a soft-deleted press release"""
        try:
            self.table.update_item(
                Key={'url': url},
                UpdateExpression='REMOVE deleted_at'
            )
            return True
        except Exception as e:
            logger.error(f"Error restoring press release {url}: {e}")
            return False

    def hard_delete(self, url: str) -> bool:
        """Permanently delete a press release"""
        try:
            self.table.delete_item(Key={'url': url})
            return True
        except Exception as e:
            logger.error(f"Error deleting press release {url}: {e}")
            return False

    def get_by_date_range(
        self,
        start_date,
        end_date,
        limit: int = 200,
        include_deleted: bool = False
    ) -> List[PressReleaseDTO]:
        """
        Get press releases within a date/time range.

        For time-window queries (e.g., 8:01am-8:00am), uses email_received_at
        (actual email timestamp) with fallback to first_seen_at.

        Args:
            start_date: Start of range (datetime or date)
            end_date: End of range (datetime or date)
            limit: Maximum results
            include_deleted: Include deleted releases

        Returns:
            List of press releases in range, sorted by timestamp descending
        """
        from boto3.dynamodb.conditions import Attr
        from datetime import timezone as tz

        # Convert datetimes to UTC ISO strings for comparison
        # This is critical because data is stored in UTC (+00:00) and string
        # comparison of ISO timestamps with different offsets doesn't work correctly.
        # Example: "2026-03-16T10:44:34+00:00" > "2026-03-16T08:00:00-04:00" in string
        # comparison, but 10:44 UTC (6:44 AM ET) is BEFORE 8:00 AM ET (12:00 PM UTC).
        def to_utc_iso(dt):
            if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                # Convert to UTC, then format without offset (use +00:00)
                utc_dt = dt.astimezone(tz.utc)
                return utc_dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
            elif hasattr(dt, 'isoformat'):
                return dt.isoformat()
            return str(dt)

        start_iso = to_utc_iso(start_date)
        end_iso = to_utc_iso(end_date)

        # Build filter:
        # Use email_received_at (actual timestamp) if available,
        # fallback to press_release_date (date-only for old records)
        # NOTE: first_seen_at EXCLUDED - it's Lambda processing time, not email time
        time_filter = (
            (
                Attr('email_received_at').exists() &
                Attr('email_received_at').gte(start_iso) &
                Attr('email_received_at').lte(end_iso)
            ) | (
                Attr('email_received_at').not_exists() &
                Attr('press_release_date').exists() &
                Attr('press_release_date').gte(start_iso[:10]) &
                Attr('press_release_date').lte(end_iso[:10])
            )
        )

        # Add deleted filter if needed
        if not include_deleted:
            time_filter = time_filter & Attr('deleted_at').not_exists()

        # Scan with pagination - Limit in DynamoDB limits items EVALUATED, not returned
        # So we need to paginate through all items and collect matches
        items = []
        last_key = None

        while True:
            scan_kwargs = {'FilterExpression': time_filter}
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = last_key

            response = self.table.scan(**scan_kwargs)
            items.extend(response.get('Items', []))

            # Check if we have enough items
            if len(items) >= limit:
                items = items[:limit]
                break

            # Check for more pages
            last_key = response.get('LastEvaluatedKey')
            if not last_key:
                break

        # Sort by actual timestamp descending (email_received_at > press_release_date)
        # NOTE: first_seen_at EXCLUDED - it's Lambda processing time, not email time
        items.sort(
            key=lambda x: x.get('email_received_at') or x.get('press_release_date', ''),
            reverse=True
        )

        return [self._item_to_dto(item) for item in items]

    def get_for_review(
        self,
        relevance_filter: str = 'all',
        company_filter: Optional[List[str]] = None,
        sort_by: str = 'date',
        sort_order: str = 'desc',
        offset: int = 0,
        limit: int = 50
    ) -> tuple:
        """Get press releases for review page with counts"""
        from boto3.dynamodb.conditions import Attr

        # Build filter
        filters = [Attr('deleted_at').not_exists()]

        if relevance_filter == 'uncategorized':
            filters.append(Attr('relevance').not_exists())
        elif relevance_filter == 'relevant':
            filters.append(Attr('relevance').eq('relevant'))
        elif relevance_filter == 'not_relevant':
            filters.append(Attr('relevance').eq('not_relevant'))

        if company_filter:
            ticker_filter = None
            for ticker in company_filter:
                if ticker_filter is None:
                    ticker_filter = Attr('ticker').eq(ticker)
                else:
                    ticker_filter = ticker_filter | Attr('ticker').eq(ticker)
            if ticker_filter:
                filters.append(ticker_filter)

        filter_expr = filters[0]
        for f in filters[1:]:
            filter_expr = filter_expr & f

        # Get all matching items for counts
        response = self.table.scan(FilterExpression=filter_expr)
        items = response.get('Items', [])

        # Sort
        if sort_by == 'date':
            # Prefer email_received_at (has time) over press_release_date (date-only)
            # NOTE: first_seen_at EXCLUDED - it's Lambda processing time, not email time
            items.sort(
                key=lambda x: x.get('email_received_at') or x.get('press_release_date', ''),
                reverse=(sort_order == 'desc')
            )
        else:
            items.sort(key=lambda x: x.get(sort_by, ''), reverse=(sort_order == 'desc'))

        # Paginate
        paginated = items[offset:offset + limit]
        releases = [self._item_to_dto(item) for item in paginated]

        # Get counts
        all_response = self.table.scan(
            FilterExpression=Attr('deleted_at').not_exists(),
            Select='COUNT'
        )
        uncategorized_response = self.table.scan(
            FilterExpression=Attr('deleted_at').not_exists() & Attr('relevance').not_exists(),
            Select='COUNT'
        )
        relevant_response = self.table.scan(
            FilterExpression=Attr('deleted_at').not_exists() & Attr('relevance').eq('relevant'),
            Select='COUNT'
        )
        not_relevant_response = self.table.scan(
            FilterExpression=Attr('deleted_at').not_exists() & Attr('relevance').eq('not_relevant'),
            Select='COUNT'
        )

        counts = {
            'all': all_response.get('Count', 0),
            'uncategorized': uncategorized_response.get('Count', 0),
            'relevant': relevant_response.get('Count', 0),
            'not_relevant': not_relevant_response.get('Count', 0)
        }

        return releases, len(items), counts


class DynamoDBNewsletterRepository(NewsletterRepository):
    """DynamoDB implementation for newsletters"""

    TABLE_NAME = 'reitsheet-newsletters'

    def __init__(self):
        self.table = aws_config.get_dynamodb_table(self.TABLE_NAME)

    def get_by_id(self, newsletter_id: int) -> Optional[NewsletterDTO]:
        """Get newsletter by ID"""
        response = self.table.get_item(Key={'newsletter_id': str(newsletter_id)})
        item = response.get('Item')
        return NewsletterDTO(item) if item else None

    def get_recent(self, limit: int = 50) -> List[NewsletterDTO]:
        """Get recent newsletters (excludes metadata records)"""
        response = self.table.scan(Limit=limit * 2)  # Get extra to account for filtering
        items = response.get('Items', [])

        # Filter out metadata records (status != 'published')
        newsletters = [item for item in items if item.get('status') == 'published']

        # Sort by date descending
        newsletters.sort(key=lambda x: x.get('date', ''), reverse=True)

        # Limit results
        return [NewsletterDTO(item) for item in newsletters[:limit]]

    def update(self, newsletter_id: int, data: Dict[str, Any]) -> bool:
        """Update newsletter data"""
        try:
            builder = DynamoDBUpdateBuilder(primary_key='newsletter_id')
            update_kwargs = builder.build(data, remove_none=False)

            if not update_kwargs:
                return True

            self.table.update_item(Key={'newsletter_id': str(newsletter_id)}, **update_kwargs)
            return True
        except Exception as e:
            logger.error(f"Error updating newsletter {newsletter_id}: {e}")
            return False

    def create(self, data: Dict[str, Any]) -> NewsletterDTO:
        """Create new newsletter"""
        import uuid
        if 'newsletter_id' not in data:
            data['newsletter_id'] = str(uuid.uuid4())
        data['created_at'] = datetime.now(timezone.utc).isoformat()
        self.table.put_item(Item=data)
        return NewsletterDTO(data)

    def get_by_date(self, date_str: str) -> Optional[NewsletterDTO]:
        """Get newsletter by date string (YYYY-MM-DD)"""
        from boto3.dynamodb.conditions import Attr

        try:
            response = self.table.scan(
                FilterExpression=Attr('date').eq(date_str)
            )
            items = response.get('Items', [])
            if items:
                return NewsletterDTO(items[0])
            return None
        except Exception as e:
            logger.error(f"Error getting newsletter by date {date_str}: {e}")
            return None

    def find_by_included_url(self, url: str) -> List[NewsletterDTO]:
        """Find all newsletters that include a specific press release URL"""
        from boto3.dynamodb.conditions import Attr

        try:
            response = self.table.scan(
                FilterExpression=Attr('included_urls').contains(url)
            )
            items = response.get('Items', [])
            return [NewsletterDTO(item) for item in items]
        except Exception as e:
            logger.error(f"Error finding newsletters by URL {url}: {e}")
            return []


class DynamoDBReviewEmailRepository(ReviewEmailRepository):
    """DynamoDB implementation for review emails"""

    TABLE_NAME = 'reitsheet-review-emails'

    def __init__(self):
        self.table = aws_config.get_dynamodb_table(self.TABLE_NAME)

    def get_by_id(self, review_id: int) -> Optional[ReviewEmailDTO]:
        """Get review email by ID - scan required"""
        response = self.table.scan(Limit=500)
        for item in response.get('Items', []):
            dto = ReviewEmailDTO(item)
            if dto.id == review_id:
                return dto
        return None

    def get_by_gmail_id(self, gmail_message_id: str) -> Optional[ReviewEmailDTO]:
        """Get review email by Gmail message ID"""
        response = self.table.get_item(Key={'gmail_message_id': gmail_message_id})
        item = response.get('Item')
        return ReviewEmailDTO(item) if item else None

    def get_pending(self) -> List[ReviewEmailDTO]:
        """Get all pending review emails"""
        from boto3.dynamodb.conditions import Attr

        response = self.table.scan(
            FilterExpression=Attr('status').eq('pending')
        )
        items = response.get('Items', [])
        items.sort(key=lambda x: x.get('date', ''), reverse=True)
        return [ReviewEmailDTO(item) for item in items]

    def update_status(self, review_id: int, status: str, **kwargs) -> bool:
        """Update review email status - find by ID first"""
        dto = self.get_by_id(review_id)
        if not dto:
            return False

        try:
            update_data = {'status': status, **kwargs}
            builder = DynamoDBUpdateBuilder()  # No PK to skip
            update_kwargs = builder.build(update_data, remove_none=False)

            if not update_kwargs:
                return True

            self.table.update_item(Key={'gmail_message_id': dto.gmail_message_id}, **update_kwargs)
            return True
        except Exception as e:
            logger.error(f"Error updating review email {review_id}: {e}")
            return False

    def create(self, data: Dict[str, Any]) -> ReviewEmailDTO:
        """Create new review email"""
        data['created_at'] = datetime.now(timezone.utc).isoformat()
        if 'status' not in data:
            data['status'] = 'pending'
        self.table.put_item(Item=data)
        return ReviewEmailDTO(data)


class DynamoDBRelevanceRepository(RelevanceRepository):
    """DynamoDB implementation for relevance decisions"""

    TABLE_NAME = 'reitsheet-relevance-decisions'

    def __init__(self):
        self.table = aws_config.get_dynamodb_table(self.TABLE_NAME)

    def create(self, data: Dict[str, Any]) -> RelevanceDecisionDTO:
        """Create new relevance decision"""
        import uuid
        if 'decision_id' not in data:
            data['decision_id'] = str(uuid.uuid4())
        data['decided_at'] = datetime.now(timezone.utc).isoformat()
        self.table.put_item(Item=data)
        return RelevanceDecisionDTO(data)

    def get_by_press_release(self, press_release_id: int) -> List[RelevanceDecisionDTO]:
        """Get relevance decisions for a press release"""
        from boto3.dynamodb.conditions import Attr

        response = self.table.scan(
            FilterExpression=Attr('press_release_id').eq(press_release_id)
        )
        items = response.get('Items', [])
        return [RelevanceDecisionDTO(item) for item in items]


class DynamoDBDisclosureRepository(DisclosureRepository):
    """DynamoDB implementation for 8-K disclosures (simplified)"""

    TABLE_NAME = 'reitsheet-8k-disclosures'

    def __init__(self):
        self.table = aws_config.get_dynamodb_table(self.TABLE_NAME)

    def get_by_filing_url(self, filing_url: str) -> Optional[DisclosureDTO]:
        """Get disclosure by filing URL (primary key)"""
        response = self.table.get_item(Key={'filing_url': filing_url})
        item = response.get('Item')
        return DisclosureDTO(item) if item else None

    def get_recent(self, days: int = 7, limit: int = 500) -> List[DisclosureDTO]:
        """Get recent disclosures sorted by date descending"""
        from boto3.dynamodb.conditions import Attr

        # Calculate cutoff date
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d')

        # Simple filter: filings within date range
        filter_expr = Attr('filing_date').gte(cutoff_date)

        items = []
        last_key = None

        # Paginate through results
        while True:
            scan_kwargs = {'FilterExpression': filter_expr}
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = last_key

            response = self.table.scan(**scan_kwargs)
            items.extend(response.get('Items', []))

            last_key = response.get('LastEvaluatedKey')
            if not last_key or len(items) >= limit:
                break

        # Sort by filing_date descending, then by ticker
        items.sort(key=lambda x: (x.get('filing_date', ''), x.get('ticker', '')), reverse=True)

        return [DisclosureDTO(item) for item in items[:limit]]

    def update_title(self, filing_url: str, title: str) -> bool:
        """Update the AI summary title for a disclosure."""
        try:
            self.table.update_item(
                Key={'filing_url': filing_url},
                UpdateExpression='SET ai_summary_title = :title',
                ExpressionAttributeValues={':title': title}
            )
            logger.info(f"Updated disclosure title: {filing_url[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to update disclosure title: {e}")
            return False

    def get_by_date_range(
        self,
        start_dt: datetime,
        end_dt: datetime,
        limit: int = 500
    ) -> List[DisclosureDTO]:
        """
        Get disclosures within a datetime range.

        Uses sec_accepted_at (SEC's official acceptance timestamp) for accurate
        time-based filtering. Falls back to first_seen_at for legacy items.

        Returns sorted by sec_accepted_at descending.
        """
        from boto3.dynamodb.conditions import Attr

        # Convert ET window to UTC for comparison with UTC-stored timestamps
        start_utc = start_dt.astimezone(timezone.utc)
        end_utc = end_dt.astimezone(timezone.utc)

        start_iso = start_utc.isoformat()
        end_iso = end_utc.isoformat()

        # Query by sec_accepted_at (preferred - SEC's official timestamp)
        # Falls back to first_seen_at for items without sec_accepted_at
        # NOTE: Also handles empty string "" which DynamoDB treats as "exists"
        filter_expr = (
            (
                Attr('sec_accepted_at').exists() &
                Attr('sec_accepted_at').ne('') &  # Must be non-empty
                Attr('sec_accepted_at').gte(start_iso) &
                Attr('sec_accepted_at').lte(end_iso)
            ) | (
                (
                    Attr('sec_accepted_at').not_exists() |
                    Attr('sec_accepted_at').eq('')  # Treat empty as missing
                ) &
                Attr('first_seen_at').exists() &
                Attr('first_seen_at').gte(start_iso) &
                Attr('first_seen_at').lte(end_iso)
            )
        )

        items = []
        last_key = None

        # Paginate through results
        while True:
            scan_kwargs = {'FilterExpression': filter_expr}
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = last_key

            response = self.table.scan(**scan_kwargs)
            items.extend(response.get('Items', []))

            last_key = response.get('LastEvaluatedKey')
            if not last_key or len(items) >= limit:
                break

        # Sort by sec_accepted_at descending (fall back to first_seen_at for older items)
        items.sort(key=lambda x: x.get('sec_accepted_at') or x.get('first_seen_at', ''), reverse=True)

        return [DisclosureDTO(item) for item in items[:limit]]

    def update(self, filing_url: str, updates: Dict[str, Any]) -> bool:
        """
        Update disclosure fields.

        Args:
            filing_url: Primary key
            updates: Dict of field names to values

        Returns:
            True if successful
        """
        if not updates:
            return True

        try:
            builder = DynamoDBUpdateBuilder(primary_key='filing_url')
            update_kwargs = builder.build(updates, remove_none=False)

            if not update_kwargs:
                return True

            self.table.update_item(Key={'filing_url': filing_url}, **update_kwargs)
            logger.info(f"Updated disclosure: {filing_url[:50]}... fields={list(updates.keys())}")
            return True
        except Exception as e:
            logger.error(f"Failed to update disclosure: {e}")
            return False

    def hard_delete(self, filing_url: str) -> bool:
        """Permanently delete a disclosure."""
        try:
            self.table.delete_item(Key={'filing_url': filing_url})
            logger.info(f"Deleted disclosure: {filing_url[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Error deleting disclosure {filing_url}: {e}")
            return False

