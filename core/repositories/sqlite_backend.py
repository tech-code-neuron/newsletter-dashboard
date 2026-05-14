"""
SQLite Repository Implementations

Wraps existing SQLAlchemy models for local development.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import logging

from core.models import (
    get_session, Company, PressRelease,
    Newsletter, ReviewEmail, RelevanceDecision
)
from core.dto import (
    CompanyDTO, PressReleaseDTO, NewsletterDTO,
    ReviewEmailDTO, RelevanceDecisionDTO
)
from core.repositories.base import (
    CompanyRepository, PressReleaseRepository,
    NewsletterRepository, ReviewEmailRepository, RelevanceRepository
)
from sqlalchemy.orm import joinedload
from sqlalchemy import func

logger = logging.getLogger(__name__)


def _model_to_company_dto(model: Company) -> CompanyDTO:
    """Convert SQLAlchemy Company to DTO"""
    return CompanyDTO({
        'id': model.id,
        'ticker': model.ticker,
        'name': model.name,
        'ir_url': model.ir_url,
        'press_release_url': model.press_release_url,
        'rss_feed_url': model.rss_feed_url,
        'company_rss_feed_url': model.company_rss_feed_url,
        'ir_platform': model.ir_platform,
        'sector': model.sector,
        'active': model.active,
        'emails_activated': model.emails_activated,
        'ignore_company_rss': model.ignore_company_rss,
        'newswire_provider': model.newswire_provider,
        'newswire_id': model.newswire_id,
        'scraping_status': model.scraping_status,
        'scraper_variant': model.scraper_variant,
        'created_at': model.created_at,
        'updated_at': model.updated_at,
    })


def _model_to_pr_dto(model: PressRelease) -> PressReleaseDTO:
    """Convert SQLAlchemy PressRelease to DTO"""
    company = _model_to_company_dto(model.company) if model.company else None
    return PressReleaseDTO({
        'id': model.id,
        'url': model.url,
        'title': model.title,
        'ticker': model.company.ticker if model.company else '',
        'unique_id': model.unique_id,
        'slug': model.slug,
        'company_id': model.company_id,
        'published_date': model.published_date,
        'scraped_date': model.scraped_date,
        'content': model.content,
        'full_text': model.full_text,
        'summary': model.summary,
        'category': model.category,
        'subcategory': model.subcategory,
        'is_breaking': model.is_breaking,
        'relevance': model.relevance,
        'included_in_newsletter': model.included_in_newsletter,
        'manually_edited': model.manually_edited,
        'editor_notes': model.editor_notes,
        'newsletter_id': model.newsletter_id,
        'deleted_at': model.deleted_at,
    }, company)


def _model_to_newsletter_dto(model: Newsletter) -> NewsletterDTO:
    """Convert SQLAlchemy Newsletter to DTO"""
    return NewsletterDTO({
        'id': model.id,
        'newsletter_type': model.newsletter_type,
        'date': model.date,
        'created_at': model.created_at,
        'status': model.status,
        'sent_at': model.sent_at,
        'html_content': model.html_content,
        'subject_line': model.subject_line,
        'recipient_count': model.recipient_count,
    })


def _model_to_review_dto(model: ReviewEmail) -> ReviewEmailDTO:
    """Convert SQLAlchemy ReviewEmail to DTO"""
    return ReviewEmailDTO({
        'id': model.id,
        'gmail_message_id': model.gmail_message_id,
        'subject': model.subject,
        'from_header': model.from_header,
        'from_email': model.from_email,
        'from_domain': model.from_domain,
        'date': model.date,
        'raw_email': model.raw_email,
        'screenshot_path': model.screenshot_path,
        'classification_reason': model.classification_reason,
        'status': model.status,
        'press_release_id': model.press_release_id,
        'created_at': model.created_at,
        'processed_at': model.processed_at,
    })


def _model_to_relevance_dto(model: RelevanceDecision) -> RelevanceDecisionDTO:
    """Convert SQLAlchemy RelevanceDecision to DTO"""
    return RelevanceDecisionDTO({
        'id': model.id,
        'press_release_id': model.press_release_id,
        'decision': model.decision,
        'decided_at': model.decided_at,
        'decided_by': model.decided_by,
    })


class SQLiteCompanyRepository(CompanyRepository):
    """SQLite implementation for companies"""

    def get_all(self, limit: int = 500) -> List[CompanyDTO]:
        db = get_session()
        companies = db.query(Company).limit(limit).all()
        result = [_model_to_company_dto(c) for c in companies]
        db.close()
        return result

    def get_all_active(self, limit: int = 500) -> List[CompanyDTO]:
        db = get_session()
        companies = db.query(Company).filter_by(active=True).order_by(Company.ticker).limit(limit).all()
        result = [_model_to_company_dto(c) for c in companies]
        db.close()
        return result

    def get_by_ticker(self, ticker: str) -> Optional[CompanyDTO]:
        db = get_session()
        company = db.query(Company).filter_by(ticker=ticker).first()
        result = _model_to_company_dto(company) if company else None
        db.close()
        return result

    def get_by_id(self, company_id: int) -> Optional[CompanyDTO]:
        db = get_session()
        company = db.query(Company).filter_by(id=company_id).first()
        result = _model_to_company_dto(company) if company else None
        db.close()
        return result

    def search(self, query: str, limit: int = 100) -> List[CompanyDTO]:
        db = get_session()
        companies = db.query(Company).filter(
            (Company.ticker.contains(query)) |
            (Company.name.contains(query))
        ).limit(limit).all()
        result = [_model_to_company_dto(c) for c in companies]
        db.close()
        return result

    def update(self, ticker: str, data: Dict[str, Any]) -> bool:
        db = get_session()
        try:
            company = db.query(Company).filter_by(ticker=ticker).first()
            if not company:
                db.close()
                return False
            for key, value in data.items():
                if hasattr(company, key):
                    setattr(company, key, value)
            db.commit()
            db.close()
            return True
        except Exception as e:
            db.rollback()
            db.close()
            logger.error(f"Error updating company {ticker}: {e}")
            return False

    def create(self, data: Dict[str, Any]) -> CompanyDTO:
        db = get_session()
        company = Company(**data)
        db.add(company)
        db.commit()
        result = _model_to_company_dto(company)
        db.close()
        return result

    def get_with_release_stats(self) -> List[Dict[str, Any]]:
        db = get_session()

        latest_release = db.query(
            PressRelease.company_id,
            func.max(PressRelease.published_date).label('latest_date'),
            func.count(PressRelease.id).label('release_count')
        ).group_by(PressRelease.company_id).subquery()

        results = db.query(
            Company,
            latest_release.c.latest_date,
            latest_release.c.release_count
        ).outerjoin(
            latest_release,
            Company.id == latest_release.c.company_id
        ).filter(Company.active == True).order_by(Company.ticker).all()

        output = []
        for company, latest_date, release_count in results:
            output.append({
                'company': _model_to_company_dto(company),
                'latest_date': latest_date,
                'release_count': release_count or 0
            })

        db.close()
        return output


class SQLitePressReleaseRepository(PressReleaseRepository):
    """SQLite implementation for press releases"""

    def get_by_id(self, release_id: int) -> Optional[PressReleaseDTO]:
        db = get_session()
        release = db.query(PressRelease).options(
            joinedload(PressRelease.company)
        ).filter_by(id=release_id).first()
        result = _model_to_pr_dto(release) if release else None
        db.close()
        return result

    def get_by_url(self, url: str) -> Optional[PressReleaseDTO]:
        db = get_session()
        release = db.query(PressRelease).options(
            joinedload(PressRelease.company)
        ).filter_by(url=url).first()
        result = _model_to_pr_dto(release) if release else None
        db.close()
        return result

    def get_by_unique_id(self, unique_id: str) -> Optional[PressReleaseDTO]:
        db = get_session()
        release = db.query(PressRelease).options(
            joinedload(PressRelease.company)
        ).filter_by(unique_id=unique_id).first()
        result = _model_to_pr_dto(release) if release else None
        db.close()
        return result

    def get_recent(
        self,
        limit: int = 50,
        days: Optional[int] = None,
        category: Optional[str] = None,
        tickers: Optional[List[str]] = None,
        include_deleted: bool = False
    ) -> List[PressReleaseDTO]:
        db = get_session()

        query = db.query(PressRelease).options(
            joinedload(PressRelease.company)
        ).join(Company)

        if not include_deleted:
            query = query.filter(PressRelease.deleted_at.is_(None))

        if days and days != 9999:
            since = datetime.now() - timedelta(days=days)
            query = query.filter(PressRelease.published_date >= since)

        if category and category != 'all':
            query = query.filter(PressRelease.category == category)

        if tickers:
            query = query.filter(Company.ticker.in_(tickers))

        releases = query.order_by(PressRelease.published_date.desc()).limit(limit).all()
        result = [_model_to_pr_dto(r) for r in releases]
        db.close()
        return result

    def get_archived(self, limit: int = 100) -> List[PressReleaseDTO]:
        db = get_session()
        releases = db.query(PressRelease).options(
            joinedload(PressRelease.company)
        ).join(Company).filter(
            PressRelease.deleted_at.isnot(None)
        ).order_by(PressRelease.deleted_at.desc()).limit(limit).all()
        result = [_model_to_pr_dto(r) for r in releases]
        db.close()
        return result

    def get_by_company(
        self,
        ticker: str,
        limit: int = 50,
        include_deleted: bool = False
    ) -> List[PressReleaseDTO]:
        db = get_session()

        query = db.query(PressRelease).options(
            joinedload(PressRelease.company)
        ).join(Company).filter(Company.ticker == ticker)

        if not include_deleted:
            query = query.filter(PressRelease.deleted_at.is_(None))

        releases = query.order_by(PressRelease.published_date.desc()).limit(limit).all()
        result = [_model_to_pr_dto(r) for r in releases]
        db.close()
        return result

    def get_uncategorized_count(self) -> int:
        db = get_session()
        count = db.query(PressRelease).filter(
            PressRelease.category.is_(None),
            PressRelease.deleted_at.is_(None)
        ).count()
        db.close()
        return count

    def get_total_count(self, include_deleted: bool = False) -> int:
        db = get_session()
        query = db.query(PressRelease)
        if not include_deleted:
            query = query.filter(PressRelease.deleted_at.is_(None))
        count = query.count()
        db.close()
        return count

    def update(self, url: str, data: Dict[str, Any]) -> bool:
        db = get_session()
        try:
            release = db.query(PressRelease).filter_by(url=url).first()
            if not release:
                db.close()
                return False
            for key, value in data.items():
                if hasattr(release, key):
                    setattr(release, key, value)
            db.commit()
            db.close()
            return True
        except Exception as e:
            db.rollback()
            db.close()
            logger.error(f"Error updating press release {url}: {e}")
            return False

    def create(self, data: Dict[str, Any]) -> PressReleaseDTO:
        db = get_session()
        release = PressRelease(**data)
        db.add(release)
        db.commit()
        db.refresh(release)
        result = _model_to_pr_dto(release)
        db.close()
        return result

    def soft_delete(self, url: str) -> bool:
        return self.update(url, {'deleted_at': datetime.now(timezone.utc)})

    def restore(self, url: str) -> bool:
        return self.update(url, {'deleted_at': None})

    def hard_delete(self, url: str) -> bool:
        db = get_session()
        try:
            release = db.query(PressRelease).filter_by(url=url).first()
            if release:
                db.delete(release)
                db.commit()
            db.close()
            return True
        except Exception as e:
            db.rollback()
            db.close()
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
        db = get_session()

        query = db.query(PressRelease).options(
            joinedload(PressRelease.company)
        ).join(Company).filter(PressRelease.deleted_at.is_(None))

        if relevance_filter == 'uncategorized':
            query = query.filter(PressRelease.relevance.is_(None))
        elif relevance_filter == 'relevant':
            query = query.filter(PressRelease.relevance == 'relevant')
        elif relevance_filter == 'not_relevant':
            query = query.filter(PressRelease.relevance == 'not_relevant')

        if company_filter:
            query = query.filter(Company.ticker.in_(company_filter))

        # Sorting
        sort_col = {
            'date': PressRelease.published_date,
            'title': PressRelease.title,
            'company': Company.ticker
        }.get(sort_by, PressRelease.published_date)

        if sort_order == 'desc':
            query = query.order_by(sort_col.desc())
        else:
            query = query.order_by(sort_col.asc())

        total_count = query.count()
        releases = query.offset(offset).limit(limit).all()
        result = [_model_to_pr_dto(r) for r in releases]

        # Get counts
        base_query = db.query(PressRelease).filter(PressRelease.deleted_at.is_(None))
        counts = {
            'all': base_query.count(),
            'uncategorized': base_query.filter(PressRelease.relevance.is_(None)).count(),
            'relevant': base_query.filter(PressRelease.relevance == 'relevant').count(),
            'not_relevant': base_query.filter(PressRelease.relevance == 'not_relevant').count()
        }

        db.close()
        return result, total_count, counts


class SQLiteNewsletterRepository(NewsletterRepository):
    """SQLite implementation for newsletters"""

    def get_by_id(self, newsletter_id: int) -> Optional[NewsletterDTO]:
        db = get_session()
        newsletter = db.query(Newsletter).get(newsletter_id)
        result = _model_to_newsletter_dto(newsletter) if newsletter else None
        db.close()
        return result

    def get_recent(self, limit: int = 50) -> List[NewsletterDTO]:
        db = get_session()
        newsletters = db.query(Newsletter).order_by(Newsletter.date.desc()).limit(limit).all()
        result = [_model_to_newsletter_dto(n) for n in newsletters]
        db.close()
        return result

    def update(self, newsletter_id: int, data: Dict[str, Any]) -> bool:
        db = get_session()
        try:
            newsletter = db.query(Newsletter).get(newsletter_id)
            if not newsletter:
                db.close()
                return False
            for key, value in data.items():
                if hasattr(newsletter, key):
                    setattr(newsletter, key, value)
            db.commit()
            db.close()
            return True
        except Exception as e:
            db.rollback()
            db.close()
            logger.error(f"Error updating newsletter {newsletter_id}: {e}")
            return False

    def create(self, data: Dict[str, Any]) -> NewsletterDTO:
        db = get_session()
        newsletter = Newsletter(**data)
        db.add(newsletter)
        db.commit()
        db.refresh(newsletter)
        result = _model_to_newsletter_dto(newsletter)
        db.close()
        return result


class SQLiteReviewEmailRepository(ReviewEmailRepository):
    """SQLite implementation for review emails"""

    def get_by_id(self, review_id: int) -> Optional[ReviewEmailDTO]:
        db = get_session()
        review = db.query(ReviewEmail).filter_by(id=review_id).first()
        result = _model_to_review_dto(review) if review else None
        db.close()
        return result

    def get_by_gmail_id(self, gmail_message_id: str) -> Optional[ReviewEmailDTO]:
        db = get_session()
        review = db.query(ReviewEmail).filter_by(gmail_message_id=gmail_message_id).first()
        result = _model_to_review_dto(review) if review else None
        db.close()
        return result

    def get_pending(self) -> List[ReviewEmailDTO]:
        db = get_session()
        reviews = db.query(ReviewEmail).filter_by(status='pending').order_by(ReviewEmail.date.desc()).all()
        result = [_model_to_review_dto(r) for r in reviews]
        db.close()
        return result

    def update_status(self, review_id: int, status: str, **kwargs) -> bool:
        db = get_session()
        try:
            review = db.query(ReviewEmail).filter_by(id=review_id).first()
            if not review:
                db.close()
                return False
            review.status = status
            for key, value in kwargs.items():
                if hasattr(review, key):
                    setattr(review, key, value)
            db.commit()
            db.close()
            return True
        except Exception as e:
            db.rollback()
            db.close()
            logger.error(f"Error updating review email {review_id}: {e}")
            return False

    def create(self, data: Dict[str, Any]) -> ReviewEmailDTO:
        db = get_session()
        review = ReviewEmail(**data)
        db.add(review)
        db.commit()
        db.refresh(review)
        result = _model_to_review_dto(review)
        db.close()
        return result


class SQLiteRelevanceRepository(RelevanceRepository):
    """SQLite implementation for relevance decisions"""

    def create(self, data: Dict[str, Any]) -> RelevanceDecisionDTO:
        db = get_session()
        decision = RelevanceDecision(**data)
        db.add(decision)
        db.commit()
        db.refresh(decision)
        result = _model_to_relevance_dto(decision)
        db.close()
        return result

    def get_by_press_release(self, press_release_id: int) -> List[RelevanceDecisionDTO]:
        db = get_session()
        decisions = db.query(RelevanceDecision).filter_by(press_release_id=press_release_id).all()
        result = [_model_to_relevance_dto(d) for d in decisions]
        db.close()
        return result
