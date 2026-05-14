"""
Performance Benchmark Script

Measures query execution times to verify performance improvements.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from core.models import get_session, Company, PressRelease
from sqlalchemy import func

def benchmark_query(name, query_func):
    """Benchmark a query and return execution time"""
    db = get_session()
    start = time.time()
    result = query_func(db)
    end = time.time()
    db.close()
    elapsed = (end - start) * 1000  # Convert to milliseconds
    print(f"✓ {name}: {elapsed:.2f}ms")
    return elapsed

def main():
    print("🔍 Running Performance Benchmarks...\n")

    # Benchmark 1: Get all active companies
    def query_active_companies(db):
        return db.query(Company).filter_by(active=True).limit(1000).all()

    benchmark_query("Active companies query", query_active_companies)

    # Benchmark 2: Get press releases with company (joinedload)
    def query_press_releases(db):
        from sqlalchemy.orm import joinedload
        return db.query(PressRelease).options(
            joinedload(PressRelease.company)
        ).filter(
            PressRelease.deleted_at.is_(None)
        ).order_by(PressRelease.published_date.desc()).limit(100).all()

    benchmark_query("Press releases with companies", query_press_releases)

    # Benchmark 3: RSS companies with latest scraped date (optimized subquery)
    def query_rss_feed_health(db):
        from datetime import datetime, timedelta

        latest_pr_subquery = db.query(
            PressRelease.company_id,
            func.max(PressRelease.scraped_date).label('latest_scraped')
        ).group_by(PressRelease.company_id).subquery()

        return db.query(
            Company,
            latest_pr_subquery.c.latest_scraped
        ).outerjoin(
            latest_pr_subquery,
            Company.id == latest_pr_subquery.c.company_id
        ).filter(
            Company.active == True,
            Company.rss_feed_url.isnot(None)
        ).all()

    benchmark_query("RSS feed health (optimized)", query_rss_feed_health)

    # Benchmark 4: Count active press releases by category
    def query_category_counts(db):
        return db.query(
            PressRelease.category,
            func.count(PressRelease.id)
        ).filter(
            PressRelease.deleted_at.is_(None)
        ).group_by(PressRelease.category).all()

    benchmark_query("Category counts", query_category_counts)

    # Benchmark 5: Latest press releases per company (subquery)
    def query_latest_per_company(db):
        latest_release = db.query(
            PressRelease.company_id,
            func.max(PressRelease.published_date).label('latest_date'),
            func.count(PressRelease.id).label('release_count')
        ).group_by(PressRelease.company_id).subquery()

        return db.query(
            Company,
            latest_release.c.latest_date,
            latest_release.c.release_count
        ).outerjoin(
            latest_release,
            Company.id == latest_release.c.company_id
        ).filter(Company.active == True).limit(100).all()

    benchmark_query("Latest releases per company", query_latest_per_company)

    print("\n✅ Benchmark complete!")
    print("\n📊 Performance Notes:")
    print("  • Queries should complete in <50ms for small datasets")
    print("  • Queries >100ms may need optimization")
    print("  • Indexed columns are 10-100x faster than non-indexed")

if __name__ == '__main__':
    main()
