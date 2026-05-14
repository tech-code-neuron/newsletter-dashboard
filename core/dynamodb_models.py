"""
DynamoDB Models - SQLAlchemy-like interface for DynamoDB tables

SOLID: Single Responsibility - Only handles DynamoDB CRUD operations

Provides a consistent interface that mirrors SQLAlchemy patterns for easier migration.

Usage:
    from core.dynamodb_models import DynamoDBSession, Newsletter, ReviewEmail

    with DynamoDBSession() as db:
        # Query like SQLAlchemy
        newsletters = db.query(Newsletter).filter_by(status='draft').all()

        # Create new record
        newsletter = Newsletter(newsletter_id='123', date='2026-03-14', ...)
        db.add(newsletter)
        db.commit()
"""
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, TypeVar, Generic
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Type variable for generic model operations
T = TypeVar('T')


# =============================================================================
# Base Classes
# =============================================================================

@dataclass
class DynamoDBModel:
    """Base class for DynamoDB models with common functionality."""

    @classmethod
    def table_name(cls) -> str:
        """Override in subclass to specify table name."""
        raise NotImplementedError

    @classmethod
    def primary_key(cls) -> str:
        """Override in subclass to specify primary key field."""
        raise NotImplementedError

    @classmethod
    def sort_key(cls) -> Optional[str]:
        """Override in subclass if table has a sort key."""
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to DynamoDB-compatible dict."""
        data = asdict(self)
        # Remove None values (DynamoDB doesn't like them)
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DynamoDBModel':
        """Create model from DynamoDB item dict."""
        # Filter to only fields defined in the dataclass
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


# =============================================================================
# Model Definitions (matching SQLite schema)
# =============================================================================

@dataclass
class Newsletter(DynamoDBModel):
    """Newsletter model - mirrors SQLite newsletters table."""
    newsletter_id: str
    date: str  # ISO format: YYYY-MM-DD
    newsletter_type: str = 'daily'  # 'daily' | 'weekly'
    status: str = 'draft'  # 'draft' | 'sent'
    subject_line: Optional[str] = None
    html_content: Optional[str] = None
    recipient_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sent_at: Optional[str] = None

    @classmethod
    def table_name(cls) -> str:
        return os.environ.get('NEWSLETTERS_TABLE', 'reitsheet-newsletters')

    @classmethod
    def primary_key(cls) -> str:
        return 'newsletter_id'

    @classmethod
    def sort_key(cls) -> str:
        return 'date'

    @staticmethod
    def generate_id() -> str:
        """Generate a unique newsletter ID."""
        return str(uuid.uuid4())


@dataclass
class ReviewEmail(DynamoDBModel):
    """Review email model - mirrors SQLite review_emails table."""
    gmail_message_id: str  # Primary key
    subject: str
    from_header: Optional[str] = None
    from_email: Optional[str] = None
    from_domain: Optional[str] = None
    date: Optional[str] = None
    raw_email: Optional[str] = None
    screenshot_path: Optional[str] = None
    classification_reason: Optional[str] = None
    status: str = 'pending'  # 'pending' | 'processed' | 'rejected'
    press_release_url: Optional[str] = None  # If added as PR
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    processed_at: Optional[str] = None

    @classmethod
    def table_name(cls) -> str:
        return os.environ.get('REVIEW_EMAILS_TABLE', 'reitsheet-review-emails')

    @classmethod
    def primary_key(cls) -> str:
        return 'gmail_message_id'


@dataclass
class RelevanceDecision(DynamoDBModel):
    """Relevance decision model - mirrors SQLite relevance_decisions table."""
    decision_id: str  # Primary key
    press_release_url: str
    ticker: str
    decision: str  # 'relevant' | 'not_relevant'
    decided_by: str = 'user'  # 'user' | 'ml_model' | 'rule'
    decided_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def table_name(cls) -> str:
        return os.environ.get('RELEVANCE_TABLE', 'reitsheet-relevance-decisions')

    @classmethod
    def primary_key(cls) -> str:
        return 'decision_id'

    @staticmethod
    def generate_id() -> str:
        """Generate a unique decision ID."""
        return str(uuid.uuid4())


# =============================================================================
# Query Builder (SQLAlchemy-like interface)
# =============================================================================

class QueryBuilder(Generic[T]):
    """
    SQLAlchemy-like query builder for DynamoDB.

    Supports:
        - filter_by(key=value) for exact matches
        - filter(condition) for complex conditions (limited)
        - first() for single result
        - all() for all results
        - count() for counting
    """

    def __init__(self, model_class: type, dynamodb_resource):
        self.model_class = model_class
        self.table = dynamodb_resource.Table(model_class.table_name())
        self._filters: Dict[str, Any] = {}
        self._limit: Optional[int] = None
        self._index_name: Optional[str] = None

    def filter_by(self, **kwargs) -> 'QueryBuilder[T]':
        """Add equality filters."""
        self._filters.update(kwargs)
        return self

    def limit(self, n: int) -> 'QueryBuilder[T]':
        """Limit results."""
        self._limit = n
        return self

    def using_index(self, index_name: str) -> 'QueryBuilder[T]':
        """Use a specific GSI."""
        self._index_name = index_name
        return self

    def first(self) -> Optional[T]:
        """Get first matching result."""
        results = self.limit(1).all()
        return results[0] if results else None

    def all(self) -> List[T]:
        """Get all matching results."""
        pk_field = self.model_class.primary_key()

        # If filtering by primary key, use get_item
        if pk_field in self._filters and len(self._filters) == 1:
            key = {pk_field: self._filters[pk_field]}
            sk_field = self.model_class.sort_key()
            if sk_field and sk_field in self._filters:
                key[sk_field] = self._filters[sk_field]

            response = self.table.get_item(Key=key)
            if 'Item' in response:
                return [self.model_class.from_dict(response['Item'])]
            return []

        # Otherwise, use scan with filter
        scan_kwargs = {}

        if self._filters:
            filter_expr_parts = []
            expr_attr_names = {}
            expr_attr_values = {}

            for i, (key, value) in enumerate(self._filters.items()):
                name_placeholder = f'#k{i}'
                value_placeholder = f':v{i}'
                filter_expr_parts.append(f'{name_placeholder} = {value_placeholder}')
                expr_attr_names[name_placeholder] = key
                expr_attr_values[value_placeholder] = value

            scan_kwargs['FilterExpression'] = ' AND '.join(filter_expr_parts)
            scan_kwargs['ExpressionAttributeNames'] = expr_attr_names
            scan_kwargs['ExpressionAttributeValues'] = expr_attr_values

        if self._limit:
            scan_kwargs['Limit'] = self._limit

        if self._index_name:
            scan_kwargs['IndexName'] = self._index_name

        response = self.table.scan(**scan_kwargs)
        items = response.get('Items', [])

        # Handle pagination
        while 'LastEvaluatedKey' in response and (not self._limit or len(items) < self._limit):
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = self.table.scan(**scan_kwargs)
            items.extend(response.get('Items', []))

        if self._limit:
            items = items[:self._limit]

        return [self.model_class.from_dict(item) for item in items]

    def count(self) -> int:
        """Count matching results."""
        scan_kwargs = {'Select': 'COUNT'}

        if self._filters:
            filter_expr_parts = []
            expr_attr_names = {}
            expr_attr_values = {}

            for i, (key, value) in enumerate(self._filters.items()):
                name_placeholder = f'#k{i}'
                value_placeholder = f':v{i}'
                filter_expr_parts.append(f'{name_placeholder} = {value_placeholder}')
                expr_attr_names[name_placeholder] = key
                expr_attr_values[value_placeholder] = value

            scan_kwargs['FilterExpression'] = ' AND '.join(filter_expr_parts)
            scan_kwargs['ExpressionAttributeNames'] = expr_attr_names
            scan_kwargs['ExpressionAttributeValues'] = expr_attr_values

        if self._index_name:
            scan_kwargs['IndexName'] = self._index_name

        response = self.table.scan(**scan_kwargs)
        count = response.get('Count', 0)

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = self.table.scan(**scan_kwargs)
            count += response.get('Count', 0)

        return count

    def delete(self) -> int:
        """Delete all matching items. Returns count deleted."""
        items = self.all()
        pk_field = self.model_class.primary_key()
        sk_field = self.model_class.sort_key()

        for item in items:
            key = {pk_field: getattr(item, pk_field)}
            if sk_field:
                key[sk_field] = getattr(item, sk_field)
            self.table.delete_item(Key=key)

        return len(items)


# =============================================================================
# DynamoDB Session (SQLAlchemy-like interface)
# =============================================================================

class DynamoDBSession:
    """
    SQLAlchemy-like session for DynamoDB operations.

    Usage:
        with DynamoDBSession() as db:
            newsletters = db.query(Newsletter).filter_by(status='draft').all()
            db.add(Newsletter(...))
            db.commit()
    """

    def __init__(self, region: str = None):
        from config.aws_config import aws_config
        self.dynamodb = aws_config.dynamodb
        self._pending_adds: List[DynamoDBModel] = []
        self._pending_deletes: List[DynamoDBModel] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()

    def query(self, model_class: type) -> QueryBuilder:
        """Start a query for a model type."""
        return QueryBuilder(model_class, self.dynamodb)

    def add(self, item: DynamoDBModel):
        """Add an item to be saved on commit."""
        self._pending_adds.append(item)

    def delete(self, item: DynamoDBModel):
        """Mark an item for deletion on commit."""
        self._pending_deletes.append(item)

    def commit(self):
        """Save all pending changes to DynamoDB."""
        # Process adds
        for item in self._pending_adds:
            table = self.dynamodb.Table(item.table_name())
            table.put_item(Item=item.to_dict())
            logger.debug(f"Saved {item.__class__.__name__} to {item.table_name()}")

        # Process deletes
        for item in self._pending_deletes:
            table = self.dynamodb.Table(item.table_name())
            pk_field = item.primary_key()
            key = {pk_field: getattr(item, pk_field)}
            sk_field = item.sort_key()
            if sk_field:
                key[sk_field] = getattr(item, sk_field)
            table.delete_item(Key=key)
            logger.debug(f"Deleted {item.__class__.__name__} from {item.table_name()}")

        # Clear pending
        self._pending_adds = []
        self._pending_deletes = []

    def rollback(self):
        """Discard all pending changes."""
        self._pending_adds = []
        self._pending_deletes = []


# =============================================================================
# Convenience Functions
# =============================================================================

@contextmanager
def dynamodb_session():
    """Context manager for DynamoDB session."""
    session = DynamoDBSession()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
