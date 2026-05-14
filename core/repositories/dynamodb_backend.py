"""
DynamoDB Repository Implementations

Uses boto3.resource('dynamodb') for auto-deserialization.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import logging

from config.aws_config import aws_config
from core.dto import (
    CompanyDTO, PressReleaseDTO, NewsletterDTO,
    ReviewEmailDTO, RelevanceDecisionDTO
)
from core.repositories.base import (
    CompanyRepository, PressReleaseRepository,
    NewsletterRepository, ReviewEmailRepository, RelevanceRepository
)

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
        """Get company by ID - DynamoDB uses ticker as PK, so scan"""
        # In DynamoDB, we don't have integer IDs, scan for matching hash
        # This is inefficient but maintains compatibility
        logger.warning("get_by_id called on DynamoDB - consider using get_by_ticker")
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
                           Attr('name').contains(query) |
                           Attr('company_name').contains(query),
            Limit=limit
        )
        items = response.get('Items', [])
        return [CompanyDTO(item) for item in items]

    def update(self, ticker: str, data: Dict[str, Any]) -> bool:
        """Update company data"""
        try:
            update_expr = 'SET '
            expr_values = {}
            expr_names = {}

            for i, (key, value) in enumerate(data.items()):
                if key == 'ticker':
                    continue  # Can't update PK
                placeholder = f':val{i}'
                name_placeholder = f'#attr{i}'
                update_expr += f'{name_placeholder} = {placeholder}, '
                expr_values[placeholder] = value
                expr_names[name_placeholder] = key

            update_expr = update_expr.rstrip(', ')

            self.table.update_item(
                Key={'ticker': ticker},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ExpressionAttributeNames=expr_names
            )
            return True
        except Exception as e:
            logger.error(f"Error updating company {ticker}: {e}")
            return False

    def create(self, data: Dict[str, Any]) -> CompanyDTO:
        """Create new company"""
        # Ensure required fields
        data['created_at'] = datetime.now(timezone.utc).isoformat()
        data['updated_at'] = datetime.now(timezone.utc).isoformat()
        if 'active' not in data:
            data['active'] = True

        self.table.put_item(Item=data)
        return CompanyDTO(data)

    def get_with_release_stats(self) -> List[Dict[str, Any]]:
        """Get companies with latest release date and count"""
        # Get all companies
        companies = self.get_all_active()

        # Get press releases table for stats
        news_table = aws_config.get_dynamodb_table(aws_config.reit_news_table_name)

        results = []
        for company in companies:
            # For each company, query press releases
            from boto3.dynamodb.conditions import Key
            try:
                response = news_table.query(
                    IndexName='ticker-date-index',
                    KeyConditionExpression=Key('ticker').eq(company.ticker),
                    ScanIndexForward=False,  # Descending
                    Limit=1,
                    ProjectionExpression='press_release_date'
                )
                items = response.get('Items', [])
                latest_date = items[0].get('press_release_date') if items else None

                # Get count
                count_response = news_table.query(
                    IndexName='ticker-date-index',
                    KeyConditionExpression=Key('ticker').eq(company.ticker),
                    Select='COUNT'
                )
                release_count = count_response.get('Count', 0)

                results.append({
                    'company': company,
                    'latest_date': latest_date,
                    'release_count': release_count
                })
            except Exception as e:
                logger.warning(f"Error getting stats for {company.ticker}: {e}")
                results.append({
                    'company': company,
                    'latest_date': None,
                    'release_count': 0
                })

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

    def _item_to_dto(self, item: Dict[str, Any]) -> PressReleaseDTO:
        """Convert DynamoDB item to DTO with company"""
        ticker = item.get('ticker', '')
        company = self._get_company(ticker) if ticker else None
        return PressReleaseDTO(item, company)

    def get_by_id(self, release_id: int) -> Optional[PressReleaseDTO]:
        """Get press release by ID - inefficient for DynamoDB"""
        logger.warning("get_by_id on DynamoDB is inefficient - use get_by_url")
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

        # Sort by date descending
        items.sort(key=lambda x: x.get('press_release_date', ''), reverse=True)

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
        """Update press release data"""
        try:
            update_expr = 'SET '
            expr_values = {}
            expr_names = {}

            for i, (key, value) in enumerate(data.items()):
                if key == 'url':
                    continue
                placeholder = f':val{i}'
                name_placeholder = f'#attr{i}'
                update_expr += f'{name_placeholder} = {placeholder}, '
                expr_values[placeholder] = value
                expr_names[name_placeholder] = key

            update_expr = update_expr.rstrip(', ')

            self.table.update_item(
                Key={'url': url},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ExpressionAttributeNames=expr_names
            )
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
        sort_key = 'press_release_date' if sort_by == 'date' else sort_by
        items.sort(key=lambda x: x.get(sort_key, ''), reverse=(sort_order == 'desc'))

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
        """Get recent newsletters"""
        response = self.table.scan(Limit=limit)
        items = response.get('Items', [])
        items.sort(key=lambda x: x.get('date', ''), reverse=True)
        return [NewsletterDTO(item) for item in items]

    def update(self, newsletter_id: int, data: Dict[str, Any]) -> bool:
        """Update newsletter data"""
        try:
            update_expr = 'SET '
            expr_values = {}
            expr_names = {}

            for i, (key, value) in enumerate(data.items()):
                if key == 'newsletter_id':
                    continue
                placeholder = f':val{i}'
                name_placeholder = f'#attr{i}'
                update_expr += f'{name_placeholder} = {placeholder}, '
                expr_values[placeholder] = value
                expr_names[name_placeholder] = key

            update_expr = update_expr.rstrip(', ')

            self.table.update_item(
                Key={'newsletter_id': str(newsletter_id)},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ExpressionAttributeNames=expr_names
            )
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
        # Find the gmail_message_id
        dto = self.get_by_id(review_id)
        if not dto:
            return False

        try:
            update_data = {'status': status, **kwargs}
            update_expr = 'SET '
            expr_values = {}
            expr_names = {}

            for i, (key, value) in enumerate(update_data.items()):
                placeholder = f':val{i}'
                name_placeholder = f'#attr{i}'
                update_expr += f'{name_placeholder} = {placeholder}, '
                expr_values[placeholder] = value
                expr_names[name_placeholder] = key

            update_expr = update_expr.rstrip(', ')

            self.table.update_item(
                Key={'gmail_message_id': dto.gmail_message_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ExpressionAttributeNames=expr_names
            )
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
