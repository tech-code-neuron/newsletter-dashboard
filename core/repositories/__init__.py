"""
Repository Pattern for Database Abstraction

Provides clean separation between routes and storage backends.
Supports DynamoDB (ECS) and SQLite (local) transparently.

Usage:
    from core.repositories import get_company_repo, get_press_release_repo

    repo = get_company_repo()
    companies = repo.get_all_active()
"""
from core.repositories.factory import (
    get_company_repo,
    get_press_release_repo,
    get_newsletter_repo,
    get_review_email_repo,
    get_relevance_repo
)

__all__ = [
    'get_company_repo',
    'get_press_release_repo',
    'get_newsletter_repo',
    'get_review_email_repo',
    'get_relevance_repo'
]
