"""
Auto-detect IR platform for all companies and update the database.
Run: python3 /tmp/detect_platforms.py
"""
import requests
from bs4 import BeautifulSoup
from models import get_session, Company
from concurrent.futures import ThreadPoolExecutor
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def detect_platform(company):
    # Already has RSS — mark it
    if company.rss_feed_url:
        return company.ticker, 'rss', 'has RSS feed'

    url = company.press_release_url or company.ir_url
    if not url:
        return company.ticker, None, 'no URL'

    try:
        r = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if r.status_code != 200:
            return company.ticker, None, f'HTTP {r.status_code}'

        html = r.text
        soup = BeautifulSoup(html, 'html.parser')

        # Q4 JS-rendered: says "Loading..." with no actual releases in HTML
        if 'q4inc.com' in html or 'q4cdn.com' in html:
            # Check if releases are actually in the HTML
            has_release_links = bool(soup.find('a', href=lambda h: h and 'news-release-details' in h))
            if has_release_links:
                return company.ticker, 'q4_drupal', 'Q4 with HTML content'
            else:
                return company.ticker, 'q4_js', 'Q4 JS-rendered (Loading...)'

        # Drupal IR platform (non-Q4) - DLR, CCI, AAT style
        if 'news-release-details' in html and 'news-releases' in url:
            has_release_links = bool(soup.find('a', href=lambda h: h and 'news-release-details' in h))
            if has_release_links:
                return company.ticker, 'q4_drupal', 'Drupal IR with HTML content'

        # GlobeNewswire hosted
        if 'globenewswire.com' in html or 'globenewswire' in url:
            return company.ticker, 'globenewswire', 'GlobeNewswire'

        # BusinessWire
        if 'businesswire.com' in html or 'businesswire' in url:
            return company.ticker, 'businesswire', 'BusinessWire'

        # PRNewswire
        if 'prnewswire.com' in html or 'prnewswire' in url:
            return company.ticker, 'prnewswire', 'PRNewswire'

        # Generic HTML with detectable press release links
        release_links = soup.find_all('a', href=lambda h: h and any(
            x in (h or '').lower() for x in ['press-release', 'news-release', 'news-releases']
        ))
        if len(release_links) >= 2:
            return company.ticker, 'custom', f'Custom HTML ({len(release_links)} links found)'

        return company.ticker, 'custom', 'unknown structure'

    except Exception as e:
        return company.ticker, None, f'ERROR: {str(e)[:60]}'

db = get_session()
companies = db.query(Company).filter(
    Company.active == True,
    Company.active == True
).order_by(Company.ticker).all()

print(f"Detecting platforms for {len(companies)} companies...\n")

results = []
# Run with limited concurrency to be polite
with ThreadPoolExecutor(max_workers=5) as ex:
    results = list(ex.map(detect_platform, companies))

# Update DB and print results
updated = 0
for ticker, platform, reason in results:
    print(f"{ticker:<8} {(platform or 'unknown'):<15} {reason}")
    if platform:
        co = db.query(Company).filter_by(ticker=ticker).first()
        if co:
            co.ir_platform = platform
            updated += 1

db.commit()
db.close()
print(f"\nUpdated {updated} companies.")
