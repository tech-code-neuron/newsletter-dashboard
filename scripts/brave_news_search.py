#!/usr/bin/env python3
"""
Brave News Search Script

Searches PR news, business news, and global news using the Brave Search API.
API key is fetched from AWS Secrets Manager (reitsheet/brave-search-api-key).
"""

import argparse
import json
import sys
from typing import Optional

import boto3
import requests


def get_api_key() -> str:
    """Fetch Brave API key from AWS Secrets Manager."""
    client = boto3.client("secretsmanager", region_name="us-east-1")
    response = client.get_secret_value(SecretId="reitsheet/brave-search-api-key")
    return response["SecretString"]


def search_brave(
    query: str,
    api_key: str,
    count: int = 10,
    freshness: str = "pw",
    country: str = "us",
    result_filter: str = "news",
) -> dict:
    """
    Search Brave API.

    Args:
        query: Search query string
        api_key: Brave API subscription token
        count: Number of results (max 20)
        freshness: Time filter - pd (24h), pw (7 days), pm (31 days)
        country: 2-letter country code
        result_filter: Filter type - "news", "web", or comma-separated

    Returns:
        API response as dict
    """
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"X-Subscription-Token": api_key}
    params = {
        "q": query,
        "count": min(count, 20),
        "freshness": freshness,
        "country": country,
        "result_filter": result_filter,
    }

    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def search_pr_news(api_key: str, company: Optional[str] = None, count: int = 10) -> dict:
    """Search for press release / PR news."""
    if company:
        query = f'"{company}" (press release OR announcement OR investor relations)'
    else:
        query = "REIT press release announcement investor relations"

    return search_brave(query, api_key, count=count, freshness="pw", result_filter="news")


def search_business_news(api_key: str, topic: Optional[str] = None, count: int = 10) -> dict:
    """Search for business news."""
    if topic:
        query = f"{topic} business news"
    else:
        query = "real estate investment trust REIT market business news"

    return search_brave(query, api_key, count=count, freshness="pw", result_filter="news")


def search_global_news(api_key: str, topic: Optional[str] = None, count: int = 10) -> dict:
    """Search for global news."""
    if topic:
        query = f"{topic} news"
    else:
        query = "real estate market global economy news"

    return search_brave(query, api_key, count=count, freshness="pw", result_filter="news")


def format_results(results: dict, category: str) -> None:
    """Print formatted search results."""
    print(f"\n{'=' * 60}")
    print(f"  {category.upper()}")
    print(f"{'=' * 60}\n")

    news_results = results.get("news", {}).get("results", [])

    if not news_results:
        # Fall back to web results if no news-specific results
        news_results = results.get("web", {}).get("results", [])

    if not news_results:
        print("  No results found.\n")
        return

    for i, item in enumerate(news_results, 1):
        title = item.get("title", "No title")
        url = item.get("url", "")
        description = item.get("description", "")[:200]
        age = item.get("age", "")
        source = item.get("meta_url", {}).get("hostname", "") if isinstance(item.get("meta_url"), dict) else ""

        print(f"  {i}. {title}")
        if source:
            print(f"     Source: {source}")
        if age:
            print(f"     Age: {age}")
        print(f"     {url}")
        if description:
            print(f"     {description}...")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Search news using Brave Search API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all                           # Search all categories with defaults
  %(prog)s --pr --company "Prologis"       # Search PR news for specific company
  %(prog)s --business --topic "interest rates"
  %(prog)s --global --topic "commercial real estate"
  %(prog)s --query "REIT earnings Q4"      # Custom query
  %(prog)s --json --pr                     # Output raw JSON
        """,
    )

    parser.add_argument("--pr", action="store_true", help="Search PR/press release news")
    parser.add_argument("--business", action="store_true", help="Search business news")
    parser.add_argument("--global", dest="global_news", action="store_true", help="Search global news")
    parser.add_argument("--all", action="store_true", help="Search all categories")
    parser.add_argument("--query", type=str, help="Custom search query")
    parser.add_argument("--company", type=str, help="Company name for PR search")
    parser.add_argument("--topic", type=str, help="Topic for business/global search")
    parser.add_argument("--count", type=int, default=10, help="Number of results per category (max 20)")
    parser.add_argument("--freshness", type=str, default="pw",
                        help="Time filter: pd=24h, pw=7days, pm=31days")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    # Default to --all if no category specified
    if not any([args.pr, args.business, args.global_news, args.all, args.query]):
        args.all = True

    try:
        api_key = get_api_key()
    except Exception as e:
        print(f"Error fetching API key: {e}", file=sys.stderr)
        sys.exit(1)

    all_results = {}

    try:
        if args.query:
            results = search_brave(args.query, api_key, count=args.count,
                                   freshness=args.freshness, result_filter="news")
            if args.json:
                all_results["custom"] = results
            else:
                format_results(results, f"Custom Search: {args.query}")

        if args.pr or args.all:
            results = search_pr_news(api_key, company=args.company, count=args.count)
            if args.json:
                all_results["pr_news"] = results
            else:
                format_results(results, "PR / Press Release News")

        if args.business or args.all:
            results = search_business_news(api_key, topic=args.topic, count=args.count)
            if args.json:
                all_results["business_news"] = results
            else:
                format_results(results, "Business News")

        if args.global_news or args.all:
            results = search_global_news(api_key, topic=args.topic, count=args.count)
            if args.json:
                all_results["global_news"] = results
            else:
                format_results(results, "Global News")

        if args.json:
            print(json.dumps(all_results, indent=2))

    except requests.exceptions.HTTPError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
