"""
Show a full breakdown of all companies by RSS status and platform.
Helps identify which companies still need a scraping solution.

Usage:
    python company_audit.py
"""
from models import get_session, Company

session = get_session()
companies = session.query(Company).order_by(Company.ticker).all()

has_rss = [c for c in companies if c.rss_feed_url]
no_rss  = [c for c in companies if not c.rss_feed_url]

print(f"\n{'='*70}")
print(f"TOTAL COMPANIES: {len(companies)}  |  Active: {sum(1 for c in companies if c.active)}")
print(f"{'='*70}")

print(f"\n✓ HAS RSS FEED ({len(has_rss)} companies):")
print(f"  {'TICKER':<8} {'PLATFORM':<15} {'RSS URL'}")
print(f"  {'-'*65}")
for c in has_rss:
    print(f"  {c.ticker:<8} {(c.ir_platform or 'unknown'):<15} {c.rss_feed_url}")

print(f"\n✗ NO RSS FEED ({len(no_rss)} companies):")
print(f"  {'TICKER':<8} {'PLATFORM':<15} {'ACTIVE':<8} {'PRESS RELEASE URL'}")
print(f"  {'-'*65}")
for c in no_rss:
    active = '✓' if c.active else '✗'
    pr_url = c.press_release_url or c.ir_url or 'NO URL'
    print(f"  {c.ticker:<8} {(c.ir_platform or 'unknown'):<15} {active:<8} {pr_url}")

# Platform breakdown for no-RSS companies
print(f"\nNO-RSS BREAKDOWN BY PLATFORM:")
platforms = {}
for c in no_rss:
    p = c.ir_platform or 'unknown'
    platforms.setdefault(p, []).append(c.ticker)
for platform, tickers in sorted(platforms.items()):
    print(f"  {platform:<20} ({len(tickers):>3}) — {', '.join(tickers)}")

print(f"\n{'='*70}\n")
session.close()
