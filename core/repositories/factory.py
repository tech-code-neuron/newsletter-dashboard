"""
Repository Factory - DynamoDB Only

Returns DynamoDB repositories for all data access.

Usage:
    from core.repositories import get_company_repo

    repo = get_company_repo()
    companies = repo.get_all_active()
"""
from functools import lru_cache


@lru_cache(maxsize=1)
def get_company_repo():
    """Get company repository (DynamoDB)"""
    from core.repositories.dynamodb_backend import DynamoDBCompanyRepository
    return DynamoDBCompanyRepository()


@lru_cache(maxsize=1)
def get_press_release_repo():
    """Get press release repository (DynamoDB)"""
    from core.repositories.dynamodb_backend import DynamoDBPressReleaseRepository
    return DynamoDBPressReleaseRepository()


@lru_cache(maxsize=1)
def get_newsletter_repo():
    """Get newsletter repository (DynamoDB)"""
    from core.repositories.dynamodb_backend import DynamoDBNewsletterRepository
    return DynamoDBNewsletterRepository()


@lru_cache(maxsize=1)
def get_review_email_repo():
    """Get review email repository (DynamoDB)"""
    from core.repositories.dynamodb_backend import DynamoDBReviewEmailRepository
    return DynamoDBReviewEmailRepository()


@lru_cache(maxsize=1)
def get_relevance_repo():
    """Get relevance repository (DynamoDB)"""
    from core.repositories.dynamodb_backend import DynamoDBRelevanceRepository
    return DynamoDBRelevanceRepository()
