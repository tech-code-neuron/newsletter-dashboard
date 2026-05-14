"""
Brave Search API client with confidence scoring for company name matching.
"""

import re
from urllib.parse import urlparse

import requests

PR_NEWSWIRE_DOMAINS = {
    "businesswire.com",
    "globenewswire.com",
    "prnewswire.com",
    "www.businesswire.com",
    "www.globenewswire.com",
    "www.prnewswire.com"
}

JOURNALIST_PUBLICATION_DOMAINS = {
    "nytimes.com",
    "wsj.com",
    "bloomberg.com",
    "ft.com",
    "bisnow.com",
    "www.nytimes.com",
    "www.wsj.com",
    "www.bloomberg.com",
    "www.ft.com",
    "www.bisnow.com"
}


class BraveSearchClient:
    """Client for Brave Search API."""

    BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["X-Subscription-Token"] = api_key

    def search_pr_newswires(self, company_name: str, start_date: str, end_date: str, count: int = 10) -> list:
        """
        Search for company press releases on PR newswire sites.

        Args:
            company_name: Company name to search for
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            count: Max results to return

        Returns:
            List of search result dicts with title, url, description
        """
        # Build query: exact match on company name across PR sites
        query = (
            f'"{company_name}" '
            f'(site:businesswire.com OR site:globenewswire.com OR site:prnewswire.com)'
        )

        params = {
            "q": query,
            "count": min(count, 20),
            "freshness": f"{start_date}to{end_date}"
        }

        response = self.session.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        return data.get("web", {}).get("results", [])

    def search_journalist_publications(self, company_name: str, start_date: str, end_date: str, count: int = 10) -> list:
        """
        Search for company news on major journalist publications.

        Args:
            company_name: Company name to search for
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            count: Max results to return

        Returns:
            List of search result dicts with title, url, description
        """
        # Build query: exact match on company name across journalist publication sites
        query = (
            f'"{company_name}" '
            f'(site:nytimes.com OR site:wsj.com OR site:bloomberg.com OR site:ft.com OR site:bisnow.com)'
        )

        params = {
            "q": query,
            "count": min(count, 20),
            "freshness": f"{start_date}to{end_date}"
        }

        response = self.session.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        return data.get("web", {}).get("results", [])

    def search_all_sources(self, company_name: str, start_date: str, end_date: str, count: int = 20) -> list:
        """
        Search for company across newswires AND publications in a single API call.

        Args:
            company_name: Company name to search for
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            count: Max results to return

        Returns:
            List of search result dicts with title, url, description
        """
        query = (
            f'"{company_name}" '
            f'(site:businesswire.com OR site:globenewswire.com OR site:prnewswire.com '
            f'OR site:nytimes.com OR site:wsj.com OR site:bloomberg.com OR site:ft.com OR site:bisnow.com)'
        )

        params = {
            "q": query,
            "count": min(count, 20),
            "freshness": f"{start_date}to{end_date}"
        }

        response = self.session.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        return data.get("web", {}).get("results", [])


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, remove extra spaces/punctuation."""
    if not text:
        return ""
    # Lowercase and remove special characters except spaces
    text = re.sub(r"[^\w\s]", " ", text.lower())
    # Collapse multiple spaces
    return " ".join(text.split())


def calculate_confidence_score(company_name: str, title: str, url: str,
                                description: str) -> int:
    """
    Calculate confidence score (0-100) that a search result is about the company.

    Scoring:
    - Exact company name in title: +50%
    - Company name in URL path: +25%
    - Company name in description: +15%
    - Domain is PR newswire: +10%

    Returns:
        Confidence score 0-100
    """
    score = 0
    company_normalized = normalize_text(company_name)
    company_words = set(company_normalized.split())

    # Must have at least 2 words to avoid matching common words
    if len(company_words) < 2:
        company_pattern = company_normalized
    else:
        # For multi-word names, require all significant words
        company_pattern = company_normalized

    # Title check (+50)
    title_normalized = normalize_text(title)
    if company_pattern in title_normalized:
        score += 50
    elif all(word in title_normalized for word in company_words if len(word) > 2):
        # Partial match if all significant words present
        score += 35

    # URL check (+25)
    url_normalized = normalize_text(urlparse(url).path)
    if company_pattern.replace(" ", "-") in url_normalized.replace(" ", "-"):
        score += 25
    elif company_pattern.replace(" ", "") in url_normalized.replace(" ", ""):
        score += 20

    # Description check (+15)
    desc_normalized = normalize_text(description)
    if company_pattern in desc_normalized:
        score += 15
    elif all(word in desc_normalized for word in company_words if len(word) > 2):
        score += 10

    # Trusted domain check (+10)
    try:
        domain = urlparse(url).netloc.lower()
        if domain in PR_NEWSWIRE_DOMAINS or domain in JOURNALIST_PUBLICATION_DOMAINS:
            score += 10
    except Exception:
        pass

    return min(score, 100)
