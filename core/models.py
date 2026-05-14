"""
Database models for Press Release Pipeline

SOLID: Single Responsibility - This file contains ONLY model definitions
Migration logic moved to utils/db_migrations.py
Backup logic moved to utils/db_backup.py
"""
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timezone
import os
import re  # Used by PressRelease.generate_slug()
from config.paths import DB_PATH, DB_URL
from config.query_limits import DB_POOL_SIZE, DB_MAX_OVERFLOW

Base = declarative_base()

class Company(Base):
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(200))
    ir_url = Column(String(500))
    press_release_url = Column(String(500))
    rss_feed_url = Column(String(500))  # Wire service RSS feed (e.g., GlobeNewswire, PR Newswire)
    company_rss_feed_url = Column(String(500))  # Company's own RSS feed
    ignore_company_rss = Column(Boolean, default=False)  # If True, don't use company RSS feed
    ir_platform = Column(String(50))
    sector = Column(String(100), index=True)  # Indexed for filtering by sector
    active = Column(Boolean, default=True, index=True)  # Indexed for filtering active/inactive
    emails_activated = Column(Boolean, default=False)  # Whether email signup has been activated
    newswire_provider = Column(String(100))
    newswire_id = Column(String(50))
    scraping_status = Column(String(20))  # 'RSS', 'Scraped', or 'Manual'
    scraper_variant = Column(String(50))  # Cache: 'evergreen', 'irw', 'module', 'wrapper', 'nir-widget', 'gcs', etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    press_releases = relationship("PressRelease", back_populates="company")
    
    def __repr__(self):
        return f"<Company {self.ticker}: {self.name}>"


class PressRelease(Base):
    __tablename__ = 'press_releases'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    
    title = Column(String(500), nullable=False)
    url = Column(String(500), unique=True, nullable=False, index=True)  # Original source URL
    unique_id = Column(String(8), unique=True, nullable=True, index=True)  # 8-digit unique ID for URLs
    slug = Column(String(200), nullable=True)  # URL-friendly slug from title
    published_date = Column(DateTime, nullable=False, index=True)
    scraped_date = Column(DateTime, default=datetime.utcnow)

    content = Column(Text)
    full_text = Column(Text)  # First 2000 words of press release
    summary = Column(Text)
    
    category = Column(String(100), index=True)
    subcategory = Column(String(100))
    is_breaking = Column(Boolean, default=False)
    
    included_in_newsletter = Column(Boolean, default=True)
    manually_edited = Column(Boolean, default=False)
    editor_notes = Column(Text)
    
    newsletter_id = Column(Integer, ForeignKey('newsletters.id'))

    # Soft delete: None = active, timestamp = archived
    deleted_at = Column(DateTime, nullable=True, default=None, index=True)  # Indexed for filtering active/archived

    # Binary relevance categorization (MVP)
    relevance = Column(String(20), nullable=True, index=True)  # 'relevant', 'not_relevant', or NULL

    company = relationship("Company", back_populates="press_releases")
    newsletter = relationship("Newsletter", back_populates="press_releases")
    
    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self):
        self.deleted_at = None

    def generate_slug(self):
        """
        Generate URL slug from first 4 words of title (no punctuation)

        SOLID: Single Responsibility - Generate slug only
        """
        # Remove punctuation and split into words
        words = re.sub(r'[^\w\s]', '', self.title.lower()).split()
        # Take first 4 words
        slug_words = words[:4]
        # Join with hyphens
        return '-'.join(slug_words)

    def generate_unique_id(self, db_session):
        """Generate random 8-digit unique ID"""
        import random
        while True:
            unique_id = str(random.randint(10000000, 99999999))
            # Check if it already exists
            exists = db_session.query(PressRelease).filter_by(unique_id=unique_id).first()
            if not exists:
                return unique_id

    def get_detail_url(self):
        """Get the new URL format: /press-release/TICKER/YEAR/UNIQUEID/slug"""
        if not self.unique_id or not self.slug:
            return None
        ticker = self.company.ticker if self.company else 'unknown'
        year = self.published_date.year
        return f'/press-release/{ticker}/{year}/{self.unique_id}/{self.slug}'

    def __repr__(self):
        return f"<PressRelease {self.company.ticker if self.company else 'Unknown'}: {self.title[:50]}>"


class Newsletter(Base):
    __tablename__ = 'newsletters'

    id = Column(Integer, primary_key=True)
    newsletter_type = Column(String(50), nullable=False)
    date = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default='draft')
    sent_at = Column(DateTime)
    html_content = Column(Text)
    subject_line = Column(String(200))
    recipient_count = Column(Integer, default=0)

    press_releases = relationship("PressRelease", back_populates="newsletter")

    def __repr__(self):
        return f"<Newsletter {self.newsletter_type} {self.date.strftime('%Y-%m-%d')}>"


class ReviewEmail(Base):
    __tablename__ = 'review_emails'

    id = Column(Integer, primary_key=True)
    gmail_message_id = Column(String(100), unique=True, nullable=False, index=True)  # Gmail message ID for deletion

    subject = Column(String(500), nullable=False)
    from_header = Column(String(200))
    from_email = Column(String(200))
    from_domain = Column(String(100))
    date = Column(DateTime)

    # Email content (for extraction if needed)
    raw_email = Column(Text)  # Store raw email for PR URL extraction
    screenshot_path = Column(String(500))  # Path to email screenshot

    # Classification info
    classification_reason = Column(String(500))

    # Status
    status = Column(String(20), default='pending', index=True)  # Indexed for filtering by status

    # If added to press releases
    press_release_id = Column(Integer, ForeignKey('press_releases.id'), nullable=True)
    press_release = relationship("PressRelease")

    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<ReviewEmail {self.subject[:50]}>"


class RelevanceDecision(Base):
    """
    Track relevance decisions for learning system

    SOLID: Single Responsibility - Only tracks decision history
    """
    __tablename__ = 'relevance_decisions'

    id = Column(Integer, primary_key=True)
    press_release_id = Column(Integer, ForeignKey('press_releases.id'), nullable=False)
    decision = Column(String(20), nullable=False)  # 'relevant' or 'not_relevant'
    decided_at = Column(DateTime, default=datetime.utcnow)
    decided_by = Column(String(50), default='user')

    # Relationship
    press_release = relationship('PressRelease', backref='relevance_decisions')

    def __repr__(self):
        return f'<RelevanceDecision {self.press_release_id}: {self.decision}>'


def init_db(db_path=DB_PATH, auto_backup=True):
    """
    Initialize database and run migrations.

    SOLID: Single Responsibility - Orchestrates initialization (delegates to utilities)

    Args:
        db_path: Path to database file
        auto_backup: If True, creates automatic backup before migrations (default: True)

    Returns:
        engine: SQLAlchemy engine
    """
    # 1. Create backup (delegates to utils/db_backup.py)
    if auto_backup:
        from utils.db_backup import create_backup
        create_backup(reason='pre-migration')

    # 2. Create engine with connection pooling
    engine = create_engine(
        f'sqlite:///{db_path}',
        echo=False,
        connect_args={'check_same_thread': False},  # SQLite thread safety
        pool_pre_ping=True,  # Verify connections before using
        pool_size=DB_POOL_SIZE,  # Keep connections in pool
        max_overflow=DB_MAX_OVERFLOW  # Allow additional connections if needed
    )

    # 3. Create tables if they don't exist
    Base.metadata.create_all(engine)

    # 4. Run migrations (delegates to utils/db_migrations.py)
    from utils.db_migrations import run_migrations
    run_migrations(engine, verbose=True)

    return engine


# Global engine instance (reused across requests)
_global_engine = None

def get_engine():
    """Get or create the global database engine (with connection pooling)"""
    global _global_engine
    if _global_engine is None:
        _global_engine = create_engine(
            DB_URL,
            echo=False,
            connect_args={'check_same_thread': False},
            pool_pre_ping=True,
            pool_size=DB_POOL_SIZE,
            max_overflow=DB_MAX_OVERFLOW
        )
    return _global_engine


def get_session(engine=None):
    """Get a new database session (reuses pooled connections)"""
    if engine is None:
        engine = get_engine()  # Use global pooled engine
    Session = sessionmaker(bind=engine)
    return Session()


def db_session():
    """
    Context manager for database sessions.

    Automatically handles commit/rollback and close.

    Usage:
        with db_session() as db:
            company = db.query(Company).filter_by(ticker='AMT').first()
            # db.commit() and db.close() happen automatically

    Yields:
        Session: Database session
    """
    from contextlib import contextmanager

    @contextmanager
    def _session():
        db = get_session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    return _session()


if __name__ == "__main__":
    engine = init_db()
    print("Database initialized successfully!")
