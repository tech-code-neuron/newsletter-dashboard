#!/usr/bin/env python3
"""
Validate Company RSS Feeds
Test each RSS feed for:
- Accessibility
- Recent entries (2026)
- Working URLs
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import feedparser
from datetime import datetime
from core.models import get_session, Company
from urllib.parse import urljoin
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

def test_rss_feed(ticker, rss_url):
    """Test a single RSS feed and return status"""
    result = {
        'ticker': ticker,
        'rss_url': rss_url,
        'status': 'unknown',
        'entries_count': 0,
        'entries_2026': 0,
        'latest_date': None,
        'latest_url': None,
        'latest_title': None,
        'url_works': False,
        'error': None
    }

    if not rss_url or rss_url.strip() == '':
        result['status'] = 'empty_url'
        result['error'] = 'RSS URL is empty'
        return result

    try:
        # Fetch RSS feed
        print(f"  Fetching RSS feed...")
        response = requests.get(rss_url, headers=HEADERS, timeout=10)

        if response.status_code == 403:
            result['status'] = 'blocked'
            result['error'] = 'HTTP 403 - Blocked'
            return result

        if response.status_code != 200:
            result['status'] = 'error'
            result['error'] = f'HTTP {response.status_code}'
            return result

        # Parse RSS feed
        feed = feedparser.parse(response.content)

        if feed.bozo:
            result['status'] = 'parse_error'
            result['error'] = f'Feed parsing error: {feed.bozo_exception}'
            return result

        if not feed.entries:
            result['status'] = 'empty_feed'
            result['error'] = 'No entries in feed'
            return result

        result['entries_count'] = len(feed.entries)

        # Check for 2026 entries and get latest
        entries_2026 = []
        latest_entry = None
        latest_date = None

        for entry in feed.entries:
            # Parse published date
            pub_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub_date = datetime(*entry.updated_parsed[:6])

            if pub_date and pub_date.year == 2026:
                entries_2026.append(entry)
                if latest_date is None or pub_date > latest_date:
                    latest_date = pub_date
                    latest_entry = entry

        result['entries_2026'] = len(entries_2026)

        if latest_entry:
            result['latest_date'] = latest_date
            result['latest_title'] = latest_entry.get('title', 'No title')[:80]
            result['latest_url'] = latest_entry.get('link', None)

            # Test if latest URL works
            if result['latest_url']:
                print(f"  Testing latest URL...")
                try:
                    url_response = requests.head(
                        result['latest_url'],
                        headers=HEADERS,
                        timeout=10,
                        allow_redirects=True
                    )
                    result['url_works'] = url_response.status_code == 200
                except Exception as e:
                    result['url_works'] = False

        # Determine overall status
        if result['entries_2026'] > 0 and result['url_works']:
            result['status'] = 'excellent'
        elif result['entries_2026'] > 0:
            result['status'] = 'good_no_url_test'
        elif result['entries_count'] > 0:
            result['status'] = 'old_entries'
        else:
            result['status'] = 'no_entries'

        return result

    except requests.exceptions.Timeout:
        result['status'] = 'timeout'
        result['error'] = 'Request timeout'
        return result
    except requests.exceptions.RequestException as e:
        result['status'] = 'error'
        result['error'] = str(e)[:100]
        return result
    except Exception as e:
        result['status'] = 'exception'
        result['error'] = str(e)[:100]
        return result

def main():
    db = get_session()

    # Get all companies with Company RSS
    companies = db.query(Company).filter(
        Company.company_rss_feed_url.isnot(None)
    ).order_by(Company.ticker).all()

    print(f"\n{'='*90}")
    print(f"VALIDATING {len(companies)} COMPANY RSS FEEDS")
    print(f"{'='*90}\n")

    results = {
        'excellent': [],
        'good_no_url_test': [],
        'old_entries': [],
        'no_2026': [],
        'empty_url': [],
        'blocked': [],
        'timeout': [],
        'error': []
    }

    for i, company in enumerate(companies, 1):
        print(f"[{i}/{len(companies)}] {company.ticker:6} - {company.name[:40]:40}")

        result = test_rss_feed(company.ticker, company.company_rss_feed_url)

        # Categorize result
        if result['status'] == 'excellent':
            print(f"  ✅ EXCELLENT - {result['entries_2026']} entries in 2026, latest URL works")
            results['excellent'].append(result)
        elif result['status'] == 'good_no_url_test':
            print(f"  ✓  GOOD - {result['entries_2026']} entries in 2026 (URL not tested)")
            results['good_no_url_test'].append(result)
        elif result['status'] == 'old_entries':
            print(f"  ⚠️  OLD - {result['entries_count']} entries, but NONE from 2026")
            results['old_entries'].append(result)
            results['no_2026'].append(result)
        elif result['status'] == 'empty_url':
            print(f"  ❌ EMPTY URL")
            results['empty_url'].append(result)
        elif result['status'] == 'blocked':
            print(f"  🚫 BLOCKED - {result['error']}")
            results['blocked'].append(result)
        elif result['status'] == 'timeout':
            print(f"  ⏱️  TIMEOUT")
            results['timeout'].append(result)
        else:
            print(f"  ❌ ERROR - {result.get('error', 'Unknown')}")
            results['error'].append(result)

        # Be polite
        time.sleep(0.5)

    db.close()

    # Print detailed report
    print(f"\n{'='*90}")
    print(f"VALIDATION REPORT")
    print(f"{'='*90}\n")

    print(f"✅ EXCELLENT ({len(results['excellent'])} feeds):")
    print("   RSS works, has 2026 entries, latest URL accessible\n")
    for r in results['excellent']:
        print(f"   {r['ticker']:6} - {r['entries_2026']:2} entries | Latest: {r['latest_date'].strftime('%Y-%m-%d')}")
        print(f"           {r['latest_title']}")
        print(f"           {r['latest_url']}\n")

    if results['good_no_url_test']:
        print(f"\n✓  GOOD ({len(results['good_no_url_test'])} feeds):")
        print("   RSS works, has 2026 entries (URL not verified)\n")
        for r in results['good_no_url_test']:
            print(f"   {r['ticker']:6} - {r['entries_2026']:2} entries | Latest: {r['latest_date'].strftime('%Y-%m-%d')}")
            print(f"           {r['latest_title']}\n")

    if results['old_entries']:
        print(f"\n⚠️  NO 2026 ENTRIES ({len(results['old_entries'])} feeds):")
        print("   🚨 RSS works but has NO entries from 2026!\n")
        for r in results['old_entries']:
            print(f"   {r['ticker']:6} - {r['entries_count']:2} total entries, newest: {r.get('latest_date', 'Unknown')}")
            print(f"           URL: {r['rss_url'][:70]}\n")

    if results['empty_url']:
        print(f"\n❌ EMPTY URL ({len(results['empty_url'])} companies):")
        for r in results['empty_url']:
            print(f"   {r['ticker']:6} - RSS URL field is empty\n")

    if results['blocked']:
        print(f"\n🚫 BLOCKED ({len(results['blocked'])} feeds):")
        for r in results['blocked']:
            print(f"   {r['ticker']:6} - {r['error']}")
            print(f"           {r['rss_url'][:70]}\n")

    if results['timeout']:
        print(f"\n⏱️  TIMEOUT ({len(results['timeout'])} feeds):")
        for r in results['timeout']:
            print(f"   {r['ticker']:6}")
            print(f"           {r['rss_url'][:70]}\n")

    if results['error']:
        print(f"\n❌ ERRORS ({len(results['error'])} feeds):")
        for r in results['error']:
            print(f"   {r['ticker']:6} - {r.get('error', 'Unknown')}")
            print(f"           {r['rss_url'][:70]}\n")

    # Summary
    print(f"\n{'='*90}")
    print(f"SUMMARY")
    print(f"{'='*90}")
    print(f"Total tested:         {len(companies)}")
    print(f"✅ Excellent:         {len(results['excellent'])} (working, current, URLs verified)")
    print(f"✓  Good:              {len(results['good_no_url_test'])} (working, current)")
    print(f"⚠️  No 2026 entries:  {len(results['old_entries'])} 🚨")
    print(f"❌ Empty URL:         {len(results['empty_url'])}")
    print(f"🚫 Blocked:           {len(results['blocked'])}")
    print(f"⏱️  Timeout:          {len(results['timeout'])}")
    print(f"❌ Errors:            {len(results['error'])}")
    print(f"{'='*90}\n")

if __name__ == '__main__':
    main()
