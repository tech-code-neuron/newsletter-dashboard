"""
RSS Scheduler Lambda - Fetches RSS feeds on a schedule for companies that don't send press release emails.

Triggered by EventBridge at 8:05 AM ET daily.
Currently configured for: STAG Industrial (only sends financial report emails, not press releases)
"""

import json
import boto3
import os
import logging
import feedparser
import re
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
companies_table = dynamodb.Table(os.environ.get('COMPANIES_TABLE', 'reitsheet-companies-config'))
news_table = dynamodb.Table(os.environ.get('REIT_NEWS_TABLE', 'reitsheet-reit-news-v2'))

PRESERVE_UPPER = {
    'REIT', 'CEO', 'CFO', 'COO', 'CIO', 'NYSE', 'NASDAQ', 'SEC', 'IPO', 'FFO',
    'Q1', 'Q2', 'Q3', 'Q4', 'FY', 'YTD', 'US', 'USA', 'UK', 'EU', 'AI', 'IT',
    'LLC', 'LP', 'LTD', 'PLC', 'ETF', 'S&P', 'ESG', 'JV',
    'CBD', 'NOI', 'NAV', 'EBITDA', 'M&A', 'PR', 'IR', 'NYC', 'LA', 'DC', 'SF',
    'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
    'UMH', 'UDR', 'AMH', 'BXP', 'JLL', 'KKR', 'TPG', 'BGO', 'STAG',
}

KEEP_LOWER = {'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'so', 'yet',
              'at', 'by', 'in', 'of', 'on', 'to', 'up', 'as', 'is', 'if'}


def is_all_caps(text: str) -> bool:
    letters = re.sub(r'[^a-zA-Z]', '', text)
    return letters.isupper() if letters else False


def smart_title_case(text: str) -> str:
    if not text or not is_all_caps(text):
        return text

    words = text.split()
    result = []

    for i, word in enumerate(words):
        clean_word = re.sub(r'[^\w]', '', word.upper())
        if clean_word in PRESERVE_UPPER:
            result.append(re.sub(r'[a-zA-Z]+', clean_word, word, count=1))
        elif i > 0 and word.lower() in KEEP_LOWER:
            result.append(word.lower())
        else:
            result.append(word.capitalize())

    return ' '.join(result)


def get_scheduled_rss_companies():
    """Get companies configured for scheduled RSS fetching."""
    try:
        response = companies_table.scan(
            FilterExpression='attribute_exists(rss_url) AND attribute_exists(scheduled_rss)',
            ProjectionExpression='ticker, rss_url, company_name'
        )
        companies = response.get('Items', [])

        if not companies:
            response = companies_table.get_item(Key={'ticker': 'STAG'})
            if 'Item' in response and response['Item'].get('rss_url'):
                companies = [response['Item']]

        return companies
    except Exception as e:
        logger.error(f"Error fetching companies: {e}")
        return []


def url_exists(url: str) -> bool:
    """Check if URL already exists in news table."""
    try:
        response = news_table.get_item(
            Key={'url': url},
            ProjectionExpression='url'
        )
        return 'Item' in response
    except Exception as e:
        logger.error(f"Error checking URL: {e}")
        return True


def save_press_release(url: str, title: str, ticker: str, pub_date: str):
    """Save new press release to DynamoDB."""
    display_title = smart_title_case(title) if is_all_caps(title) else title

    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    date_only = pub_date[:10] if pub_date else now[:10]

    item = {
        'url': url,
        'ticker': ticker,
        'title': title,
        'display_title': display_title,
        'first_seen_at': now,
        'press_release_date': date_only,
        'source': 'rss_scheduled',
        'construction_method': 'rss_scheduled',
        'needs_scraping': False,
    }

    try:
        news_table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(#url)',
            ExpressionAttributeNames={'#url': 'url'}
        )
        logger.info(f"Saved: {ticker} - {display_title[:60]}")
        return True
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        logger.info(f"Already exists: {url[:60]}")
        return False
    except Exception as e:
        logger.error(f"Error saving: {e}")
        return False


def fetch_rss(ticker: str, rss_url: str) -> dict:
    """Fetch and process RSS feed for a company."""
    result = {'ticker': ticker, 'new': 0, 'existing': 0, 'errors': 0}

    try:
        feed = feedparser.parse(rss_url)

        if feed.bozo and not feed.entries:
            logger.error(f"Failed to parse RSS for {ticker}: {feed.bozo_exception}")
            result['errors'] = 1
            return result

        for entry in feed.entries[:10]:
            url = entry.get('link', '')
            title = entry.get('title', '')
            pub_date = entry.get('published', '')

            if not url or not title:
                continue

            if url_exists(url):
                result['existing'] += 1
            else:
                if save_press_release(url, title, ticker, pub_date):
                    result['new'] += 1
                else:
                    result['existing'] += 1

        return result

    except Exception as e:
        logger.error(f"Error fetching RSS for {ticker}: {e}")
        result['errors'] = 1
        return result


def handler(event, context):
    """Lambda handler - triggered by EventBridge schedule."""
    logger.info("RSS Scheduler started")

    companies = get_scheduled_rss_companies()

    if not companies:
        logger.info("No companies configured for scheduled RSS")
        return {'statusCode': 200, 'body': 'No companies to process'}

    results = []
    total_new = 0

    for company in companies:
        ticker = company.get('ticker')
        rss_url = company.get('rss_url')

        if not ticker or not rss_url:
            continue

        logger.info(f"Fetching RSS for {ticker}: {rss_url}")
        result = fetch_rss(ticker, rss_url)
        results.append(result)
        total_new += result['new']

    summary = {
        'companies_processed': len(results),
        'total_new_entries': total_new,
        'results': results
    }

    logger.info(f"RSS Scheduler complete: {json.dumps(summary)}")

    return {
        'statusCode': 200,
        'body': json.dumps(summary)
    }
