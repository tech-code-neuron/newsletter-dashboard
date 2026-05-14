#!/usr/bin/env python3
"""
Pipeline Health Check

Verifies the complete email processing pipeline:
1. DynamoDB V2 has recent press releases
2. SQLite synced from DynamoDB V2 correctly
3. Routing consistency (parser, DynamoDB, Playwright all aligned)
4. CloudWatch alarms configured
5. No messages stuck in DLQs

Usage:
    python3 scripts/health_check_pipeline.py
"""

import boto3
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# AWS Configuration
AWS_REGION = 'us-east-1'
DYNAMODB_V2_TABLE = 'reitsheet-reit-news-v2'
SQLITE_DB_PATH = 'data/press_releases.db'

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
sqs = boto3.client('sqs', region_name=AWS_REGION)
cloudwatch = boto3.client('cloudwatch', region_name=AWS_REGION)

def check_dynamodb_recent_entries():
    """Check DynamoDB V2 has entries from last 24 hours"""
    print("\n" + "="*70)
    print("Check 1: DynamoDB V2 Recent Entries")
    print("="*70)

    table = dynamodb.Table(DYNAMODB_V2_TABLE)

    # Scan for entries from last 24 hours
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    try:
        response = table.scan(
            FilterExpression='first_seen_at >= :cutoff',
            ExpressionAttributeValues={':cutoff': cutoff},
            Limit=100
        )

        count = len(response.get('Items', []))

        if count > 0:
            print(f"  ✅ PASS: Found {count} press releases in last 24 hours")

            # Show sample
            sample = response['Items'][0]
            print(f"  Sample: {sample.get('ticker', 'N/A')} - {sample.get('title', 'N/A')[:60]}...")
            return True
        else:
            print(f"  ⚠️  WARNING: No press releases in last 24 hours")
            return False

    except Exception as e:
        print(f"  ❌ FAIL: Error checking DynamoDB: {e}")
        return False


def check_sqlite_sync():
    """Check SQLite has entries from last 24 hours (synced from DynamoDB)"""
    print("\n" + "="*70)
    print("Check 2: SQLite Sync Status")
    print("="*70)

    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cursor = conn.cursor()

        # Count entries from last 24 hours
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        cursor.execute("""
            SELECT COUNT(*)
            FROM press_releases
            WHERE scraped_date >= ?
        """, (cutoff,))

        count = cursor.fetchone()[0]

        if count > 0:
            print(f"  ✅ PASS: SQLite has {count} press releases from last 24 hours")

            # Show sample
            cursor.execute("""
                SELECT c.ticker, pr.title
                FROM press_releases pr
                JOIN companies c ON pr.company_id = c.id
                WHERE pr.scraped_date >= ?
                ORDER BY pr.scraped_date DESC
                LIMIT 1
            """, (cutoff,))

            sample = cursor.fetchone()
            if sample:
                print(f"  Sample: {sample[0]} - {sample[1][:60]}...")

            conn.close()
            return True
        else:
            print(f"  ⚠️  WARNING: SQLite has no press releases from last 24 hours")
            print(f"  Suggestion: Run `python3 scripts/sync_dynamodb_to_sqlite.py`")
            conn.close()
            return False

    except Exception as e:
        print(f"  ❌ FAIL: Error checking SQLite: {e}")
        return False


def check_routing_consistency():
    """Run validation script to check routing consistency"""
    print("\n" + "="*70)
    print("Check 3: Routing Consistency")
    print("="*70)

    try:
        result = subprocess.run(
            ['python3', 'scripts/validate_routing_consistency.py'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print("  ✅ PASS: Routing configuration is consistent")
            return True
        else:
            print("  ❌ FAIL: Routing inconsistencies detected")
            print("\n" + result.stdout)
            return False

    except Exception as e:
        print(f"  ❌ FAIL: Error running validation: {e}")
        return False


def check_dlq_status():
    """Check all DLQs for stuck messages"""
    print("\n" + "="*70)
    print("Check 4: Dead Letter Queue Status")
    print("="*70)

    dlqs = [
        'reitsheet-playwright-scraper-dlq',
        'reitsheet-enrich-dlq',
        'reitsheet-email-parse-dlq'
    ]

    all_clear = True

    for dlq_name in dlqs:
        try:
            # Get queue URL
            response = sqs.get_queue_url(QueueName=dlq_name)
            queue_url = response['QueueUrl']

            # Get message count
            attrs = sqs.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=['ApproximateNumberOfMessages']
            )

            count = int(attrs['Attributes']['ApproximateNumberOfMessages'])

            if count == 0:
                print(f"  ✅ {dlq_name}: 0 messages (clear)")
            else:
                print(f"  ⚠️  {dlq_name}: {count} messages stuck!")
                all_clear = False

        except Exception as e:
            print(f"  ❌ {dlq_name}: Error checking - {e}")
            all_clear = False

    return all_clear


def check_cloudwatch_alarms():
    """Check CloudWatch alarms are configured"""
    print("\n" + "="*70)
    print("Check 5: CloudWatch Alarms")
    print("="*70)

    expected_alarms = [
        'reitsheet-parser-errors',
        'reitsheet-enricher-errors',
        'reitsheet-playwright-errors',
        'reitsheet-playwright-dlq-messages',
        'reitsheet-enricher-dlq-messages',
        'reitsheet-parser-dlq-messages'
    ]

    try:
        response = cloudwatch.describe_alarms(
            AlarmNames=expected_alarms
        )

        found_alarms = {alarm['AlarmName'] for alarm in response['MetricAlarms']}

        all_configured = True
        for alarm_name in expected_alarms:
            if alarm_name in found_alarms:
                print(f"  ✅ {alarm_name}")
            else:
                print(f"  ❌ {alarm_name} - NOT CONFIGURED")
                all_configured = False

        return all_configured

    except Exception as e:
        print(f"  ❌ FAIL: Error checking alarms - {e}")
        return False


def main():
    """Run all health checks"""
    print("="*70)
    print("REIT NEWSLETTER PIPELINE HEALTH CHECK")
    print("="*70)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    checks = [
        ("DynamoDB V2 Recent Entries", check_dynamodb_recent_entries),
        ("SQLite Sync Status", check_sqlite_sync),
        ("Routing Consistency", check_routing_consistency),
        ("Dead Letter Queues", check_dlq_status),
        ("CloudWatch Alarms", check_cloudwatch_alarms)
    ]

    results = []
    for name, check_func in checks:
        try:
            passed = check_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n  ❌ ERROR in {name}: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\n{passed_count}/{total_count} checks passed")

    if passed_count == total_count:
        print("\n🎉 All systems operational!")
        print("✅ Emails will flow: Parser → Enricher/Playwright → DynamoDB V2 → SQLite → Dashboard")
        return 0
    else:
        print("\n⚠️  Some checks failed - pipeline may have issues")
        print("Review failures above and fix before overnight email processing")
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
