"""
Validate Scraper Split Cost Savings
====================================
Calculate cost savings from splitting scrapers

SOLID:
- Single Responsibility: Only calculates and validates costs
- No Hardcoded Values: All costs in constants
- Data-Driven: Reads actual company distribution from DynamoDB

Last Updated: 2026-03-09
"""

import boto3
import sys

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('reitsheet-companies-config')

# ============================================================================
# Cost Constants - SOLID: No Magic Numbers
# ============================================================================

# Cost per invocation (assumes 10 PRs/month per company)
COSTS = {
    'simple_http': 0.001,    # 256MB, 5s avg
    'playwright': 0.01,       # 2GB, 60s avg
    'api': 0.0001            # 128MB, 1s avg
}

INVOCATIONS_PER_COMPANY_PER_MONTH = 10

# Expected savings threshold (validation passes if >= this)
MINIMUM_SAVINGS_PERCENTAGE = 70


def calculate_costs():
    """
    Calculate current vs optimized costs

    Single Responsibility: Only calculates costs
    """
    # Get all companies
    print("📊 Scanning companies from DynamoDB...\n")
    response = table.scan()
    companies = response['Items']

    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        companies.extend(response['Items'])

    # Count by scraper type
    counts = {
        'simple_http': 0,
        'playwright': 0,
        'api': 0
    }

    for company in companies:
        scraper_type = company.get('scraper_type', 'simple_http')
        counts[scraper_type] += 1

    total_companies = len(companies)

    # Calculate costs
    # Current: All companies use Playwright config (worst case)
    current_cost = total_companies * INVOCATIONS_PER_COMPANY_PER_MONTH * COSTS['playwright']

    # Optimized: Use actual scraper types
    optimized_cost = sum(
        counts[scraper_type] * INVOCATIONS_PER_COMPANY_PER_MONTH * cost
        for scraper_type, cost in COSTS.items()
    )

    savings = current_cost - optimized_cost
    savings_pct = (savings / current_cost) * 100

    # Print report
    print("="*60)
    print("SCRAPER SPLIT COST ANALYSIS")
    print("="*60)
    print(f"\nCompany Distribution ({total_companies} total):")
    for scraper_type, count in counts.items():
        pct = (count / total_companies) * 100
        print(f"  {scraper_type:12s}: {count:3d} companies ({pct:5.1f}%)")

    print(f"\nCost Comparison ({INVOCATIONS_PER_COMPANY_PER_MONTH} PRs/company/month):")
    print(f"  Current (all Playwright): ${current_cost:8.2f}/month")
    print(f"  Optimized (split):        ${optimized_cost:8.2f}/month")
    print(f"  Savings:                  ${savings:8.2f}/month ({savings_pct:.0f}%)")

    # Project to 1000 companies
    scale_factor = 1000 / total_companies
    projected_current = current_cost * scale_factor
    projected_optimized = optimized_cost * scale_factor
    projected_savings = savings * scale_factor

    print(f"\nProjected at 1000 companies:")
    print(f"  Current:   ${projected_current:8.2f}/month")
    print(f"  Optimized: ${projected_optimized:8.2f}/month")
    print(f"  Savings:   ${projected_savings:8.2f}/month")

    print("\n" + "="*60)

    return {
        'current_cost': current_cost,
        'optimized_cost': optimized_cost,
        'savings': savings,
        'savings_pct': savings_pct
    }


def validate_savings(results):
    """
    Validate savings meet expectations

    Single Responsibility: Only validates against threshold
    """
    if results['savings_pct'] >= MINIMUM_SAVINGS_PERCENTAGE:
        print(f"\n✅ VALIDATION PASSED - Savings: {results['savings_pct']:.0f}%")
        print(f"   (Expected minimum: {MINIMUM_SAVINGS_PERCENTAGE}%)\n")
        return True
    else:
        print(f"\n⚠️  WARNING - Expected >{MINIMUM_SAVINGS_PERCENTAGE}% savings, got {results['savings_pct']:.0f}%\n")
        return False


if __name__ == '__main__':
    try:
        results = calculate_costs()
        passed = validate_savings(results)
        sys.exit(0 if passed else 1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
