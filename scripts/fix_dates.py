"""
One-time script to fix press release dates that were set to ingestion
time instead of actual publish date.

Detection: if published_date and scraped_date are within 5 minutes of
each other, the date was never properly parsed and needs fixing.

Run once:
  python fix_dates.py

To preview without writing changes:
  python fix_dates.py --dry-run
"""
import sys
import feedparser
from datetime import datetime
from dateutil import parser as dateparser
from models import get_session, Company, PressRelease
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

DRY_RUN = '--dry-run' in sys.argv


def parse_feed_date(entry):
    if getattr(entry, 'published_parsed', None):
        return datetime(*entry.published_parsed[:6])
    if getattr(entry, 'updated_parsed', None):
        return datetime(*entry.updated_parsed[:6])
    for field in ('published', 'updated'):
        raw = entry.get(field, '').strip()
        if raw:
            try:
                return dateparser.parse(raw, ignoretz=True)
            except Exception:
                pass
    return None


def fix_dates():
    db = get_session()

    # Find all releases where published_date is within 5 min of scraped_date
    # These are the ones where date parsing failed and fell back to now()
    all_releases = db.query(PressRelease).filter(
        PressRelease.scraped_date.isnot(None)
    ).all()

    bad_records = []
    for r in all_releases:
        if r.scraped_date and r.published_date:
            diff = abs((r.published_date - r.scraped_date).total_seconds())
            if diff < 18060:  # within 5 minutes = date was set to now()
                bad_records.append(r)

    logger.info(f"Found {len(bad_records)} records with bad dates")

    if not bad_records:
        logger.info("Nothing to fix.")
        db.close()
        return

    # Group bad records by company
    by_company = {}
    for r in bad_records:
        by_company.setdefault(r.company_id, []).append(r)

    companies = {c.id: c for c in db.query(Company).all()}

    total_fixed = 0
    total_unfixable = 0

    for company_id, releases in by_company.items():
        company = companies.get(company_id)
        if not company or not company.rss_feed_url:
            logger.warning(f"  No RSS feed for company_id={company_id}, skipping {len(releases)} records")
            total_unfixable += len(releases)
            continue

        logger.info(f"\n[{company.ticker}] Fetching RSS to fix {len(releases)} records...")

        try:
            feed = feedparser.parse(company.rss_feed_url)
        except Exception as e:
            logger.error(f"  Failed to fetch RSS: {e}")
            total_unfixable += len(releases)
            continue

        # Build URL -> date map from feed
        url_to_date = {}
        for entry in feed.entries:
            url = entry.get('link', '').strip()
            date = parse_feed_date(entry)
            if url and date:
                url_to_date[url] = date

        fixed = 0
        unfixable = 0

        for release in releases:
            real_date = url_to_date.get(release.url)
            if real_date:
                old_date = release.published_date
                if not DRY_RUN:
                    release.published_date = real_date
                logger.info(f"  {'[DRY RUN] ' if DRY_RUN else ''}Fixed: {release.title[:60]}")
                logger.info(f"    {old_date.strftime('%Y-%m-%d %H:%M')} -> {real_date.strftime('%Y-%m-%d %H:%M')}")
                fixed += 1
            else:
                logger.warning(f"  Not in RSS (too old?): {release.title[:60]}")
                unfixable += 1

        if not DRY_RUN and fixed:
            db.commit()

        logger.info(f"  -> Fixed: {fixed}, Not in feed: {unfixable}")
        total_fixed += fixed
        total_unfixable += unfixable

    db.close()

    logger.info(f"\n{'='*50}")
    if DRY_RUN:
        logger.info(f"DRY RUN complete. Would fix: {total_fixed}, Cannot fix: {total_unfixable}")
    else:
        logger.info(f"Done. Fixed: {total_fixed}, Could not fix: {total_unfixable}")
    logger.info(f"{'='*50}")

    if total_unfixable > 0:
        logger.info(f"\nNote: {total_unfixable} records could not be fixed because they're")
        logger.info(f"no longer in the RSS feed (too old). Consider archiving them manually.")


if __name__ == "__main__":
    fix_dates()
