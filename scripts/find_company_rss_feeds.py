#!/usr/bin/env python3
"""
Scan company press release URLs for RSS feeds
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup
from core.models import get_session, Company
from urllib.parse import urljoin
import time

# User agent to avoid blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def find_rss_in_html(html_content, base_url):
    """Find RSS feed URLs in HTML content"""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Look for RSS links in <link> tags
    rss_links = []

    # Method 1: <link rel="alternate" type="application/rss+xml">
    for link in soup.find_all('link', {'type': 'application/rss+xml'}):
        href = link.get('href')
        if href:
            rss_links.append(urljoin(base_url, href))

    # Method 2: <link rel="alternate" type="application/atom+xml">
    for link in soup.find_all('link', {'type': 'application/atom+xml'}):
        href = link.get('href')
        if href:
            rss_links.append(urljoin(base_url, href))

    # Method 3: Look for links with "rss" or "feed" in href
    for link in soup.find_all('a', href=True):
        href = link.get('href', '').lower()
        if 'rss' in href or '/feed' in href or 'atom.xml' in href:
            full_url = urljoin(base_url, link['href'])
            if full_url not in rss_links:
                rss_links.append(full_url)

    return rss_links

def scan_company_for_rss(company, db):
    """Scan a single company's press release URL for RSS feed"""
    url = company.press_release_url or company.ir_url

    if not url:
        return {'status': 'no_url', 'company': company.ticker}

    try:
        print(f"  Checking {company.ticker} - {url[:60]}...")
        response = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)

        if response.status_code == 403:
            return {'status': 'blocked', 'company': company.ticker, 'url': url}

        if response.status_code != 200:
            return {'status': 'error', 'company': company.ticker, 'code': response.status_code}

        # Check if it's a Cloudflare block page
        if 'cloudflare' in response.text.lower() and 'checking your browser' in response.text.lower():
            return {'status': 'cloudflare', 'company': company.ticker, 'url': url}

        # Find RSS feeds
        rss_feeds = find_rss_in_html(response.text, url)

        if rss_feeds:
            # Use the first RSS feed found
            rss_url = rss_feeds[0]

            # Update database
            company.company_rss_feed_url = rss_url
            db.commit()

            return {
                'status': 'found',
                'company': company.ticker,
                'url': url,
                'rss_url': rss_url,
                'count': len(rss_feeds)
            }
        else:
            return {'status': 'no_rss', 'company': company.ticker, 'url': url}

    except requests.exceptions.Timeout:
        return {'status': 'timeout', 'company': company.ticker, 'url': url}

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'company': company.ticker, 'error': str(e)[:100]}

    except Exception as e:
        return {'status': 'exception', 'company': company.ticker, 'error': str(e)[:100]}

def main():
    db = get_session()

    # Get all active companies
    companies = db.query(Company).filter_by(active=True).order_by(Company.ticker).all()

    print(f"\n{'='*70}")
    print(f"SCANNING {len(companies)} COMPANIES FOR RSS FEEDS")
    print(f"{'='*70}\n")

    results = {
        'found': [],
        'blocked': [],
        'cloudflare': [],
        'no_rss': [],
        'no_url': [],
        'timeout': [],
        'error': []
    }

    for i, company in enumerate(companies, 1):
        print(f"[{i}/{len(companies)}] {company.ticker:5} - {company.name[:40]:40}", end=' ')

        result = scan_company_for_rss(company, db)
        status = result['status']

        if status == 'found':
            print(f"✅ RSS FOUND")
            results['found'].append(result)
        elif status in ['blocked', 'cloudflare']:
            print(f"🚫 BLOCKED")
            results[status].append(result)
        elif status == 'no_rss':
            print(f"❌ No RSS")
            results['no_rss'].append(result)
        elif status == 'no_url':
            print(f"⚠️  No URL")
            results['no_url'].append(result)
        elif status == 'timeout':
            print(f"⏱️  Timeout")
            results['timeout'].append(result)
        else:
            print(f"❌ Error")
            results['error'].append(result)

        # Be polite - small delay between requests
        time.sleep(0.5)

    db.close()

    # Print report
    print(f"\n{'='*70}")
    print(f"SCAN COMPLETE - RESULTS")
    print(f"{'='*70}\n")

    print(f"✅ RSS FEEDS FOUND: {len(results['found'])}")
    for r in results['found']:
        print(f"   {r['company']:5} - {r['rss_url']}")

    print(f"\n🚫 BLOCKED/CLOUDFLARE: {len(results['blocked']) + len(results['cloudflare'])}")
    for r in results['blocked'] + results['cloudflare']:
        print(f"   {r['company']:5} - {r['url'][:60]}")

    print(f"\n❌ NO RSS FOUND: {len(results['no_rss'])}")
    for r in results['no_rss'][:10]:  # Show first 10
        print(f"   {r['company']:5} - {r['url'][:60]}")
    if len(results['no_rss']) > 10:
        print(f"   ... and {len(results['no_rss']) - 10} more")

    print(f"\n⚠️  NO URL SET: {len(results['no_url'])}")
    for r in results['no_url']:
        print(f"   {r['company']:5}")

    if results['timeout']:
        print(f"\n⏱️  TIMEOUTS: {len(results['timeout'])}")
        for r in results['timeout']:
            print(f"   {r['company']:5}")

    if results['error']:
        print(f"\n❌ ERRORS: {len(results['error'])}")
        for r in results['error']:
            print(f"   {r['company']:5} - {r.get('error', 'Unknown error')}")

    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Total scanned:    {len(companies)}")
    print(f"RSS found:        {len(results['found'])}")
    print(f"No RSS:           {len(results['no_rss'])}")
    print(f"Blocked:          {len(results['blocked']) + len(results['cloudflare'])}")
    print(f"No URL:           {len(results['no_url'])}")
    print(f"Timeouts:         {len(results['timeout'])}")
    print(f"Errors:           {len(results['error'])}")
    print(f"{'='*70}\n")

if __name__ == '__main__':
    main()
