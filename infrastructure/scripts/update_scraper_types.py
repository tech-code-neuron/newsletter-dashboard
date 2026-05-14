"""
Update Company Configs with Scraper Types
==========================================
Sets scraper_type field based on company characteristics

SOLID:
- Single Responsibility: Only updates scraper_type field
- Open/Closed: Add new companies to sets without changing logic
- Data-Driven: Company classifications in simple sets

Last Updated: 2026-03-09
"""

import boto3
import sys

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('reitsheet-companies-config')

# ============================================================================
# Company Classifications - SOLID: Open/Closed Principle
# ============================================================================
# To add new companies, just update these sets (no code changes needed)

# JavaScript-rendered companies → playwright
PLAYWRIGHT_COMPANIES = {
    'EPRT'  # Essential Properties - SvelteKit framework
}

# API-based companies (future)
API_COMPANIES = set()

# All others → simple_http (default)


def update_scraper_types():
    """
    Update all companies with scraper_type field

    Single Responsibility: Only updates scraper_type
    """
    # Scan all companies
    print("📊 Scanning companies from DynamoDB...")
    response = table.scan()
    companies = response['Items']

    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        companies.extend(response['Items'])

    print(f"Found {len(companies)} companies\n")

    # Update each company
    for company in companies:
        ticker = company['ticker']

        # Determine scraper type (Strategy Pattern - data-driven)
        if ticker in PLAYWRIGHT_COMPANIES:
            scraper_type = 'playwright'
        elif ticker in API_COMPANIES:
            scraper_type = 'api'
        else:
            scraper_type = 'simple_http'

        # Update DynamoDB
        table.update_item(
            Key={'ticker': ticker},
            UpdateExpression='SET scraper_type = :type',
            ExpressionAttributeValues={':type': scraper_type}
        )

        print(f"✓ {ticker:6s} → {scraper_type}")

    # Print summary
    simple_count = len([c for c in companies if c.get('ticker') not in PLAYWRIGHT_COMPANIES and c.get('ticker') not in API_COMPANIES])
    playwright_count = len(PLAYWRIGHT_COMPANIES)
    api_count = len(API_COMPANIES)

    print(f"\n{'='*60}")
    print(f"✅ Updated {len(companies)} companies:")
    print(f"{'='*60}")
    print(f"  Simple HTTP: {simple_count:3d} ({simple_count/len(companies)*100:5.1f}%)")
    print(f"  Playwright:  {playwright_count:3d} ({playwright_count/len(companies)*100:5.1f}%)")
    print(f"  API:         {api_count:3d} ({api_count/len(companies)*100:5.1f}%)")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    try:
        update_scraper_types()
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
