#!/usr/bin/env python3
"""
Debug script: Inspect GlobeNewswire HTML structure for AAT
"""

import requests
from bs4 import BeautifulSoup

ORG_ID = "34254"
URL = f"https://www.globenewswire.com/en/search/organization-id/{ORG_ID}"

print("Fetching page...")
response = requests.get(URL, timeout=15, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

soup = BeautifulSoup(response.content, 'html.parser')

# Save full HTML for inspection
with open('aat_debug.html', 'w', encoding='utf-8') as f:
    f.write(soup.prettify())
print("✓ Saved full HTML to aat_debug.html")

# Look for any links
print("\n" + "=" * 80)
print("All links on page (first 20):")
print("=" * 80)
for i, link in enumerate(soup.find_all('a', href=True)[:20], 1):
    print(f"\n{i}. HREF: {link['href'][:80]}")
    print(f"   TEXT: {link.get_text(strip=True)[:80]}")

# Look for anything that might be a press release
print("\n" + "=" * 80)
print("Looking for news-release patterns:")
print("=" * 80)
import re
news_links = soup.find_all('a', href=re.compile(r'news-release'))
print(f"Found {len(news_links)} links with 'news-release' in href")
for i, link in enumerate(news_links[:5], 1):
    print(f"\n{i}. {link['href'][:100]}")
    print(f"   {link.get_text(strip=True)[:80]}")

# Look for common press release containers
print("\n" + "=" * 80)
print("Looking for article/result containers:")
print("=" * 80)
containers = soup.find_all(['article', 'div'], class_=re.compile(r'result|article|press|news', re.I))
print(f"Found {len(containers)} potential containers")
for i, container in enumerate(containers[:3], 1):
    print(f"\n{i}. Tag: {container.name}, Class: {container.get('class')}")
    print(f"   Text preview: {container.get_text(strip=True)[:100]}")

print("\n" + "=" * 80)
print("Check aat_debug.html to see the full page structure")
print("=" * 80)
