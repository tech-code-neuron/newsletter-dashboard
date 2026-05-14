#!/usr/bin/env python3
"""
Populate Domain Whitelist

Adds trusted REIT IR email service domains to whitelist.
Whitelisted domains bypass rate limiting.

Usage:
    python scripts/populate_domain_whitelist.py
"""
import boto3
from datetime import datetime, timezone

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('reitsheet-domain-whitelist')

# Known trusted REIT IR email service domains
TRUSTED_DOMAINS = [
    # Major IR Platform Services
    'q4inc.com',           # Q4 IR platform
    'q4web.com',           # Q4 alternative domain
    'gcs-web.com',         # GCS (Global Compliance Solutions)
    'investis.com',        # Investis Digital
    'issuer-direct.com',   # Issuer Direct
    'mzgroup.com',         # MZ Group
    'icrinc.com',          # ICR (Investor Relations)

    # News Wire Services
    'prnewswire.com',      # PR Newswire
    'businesswire.com',    # Business Wire
    'globenewswire.com',   # GlobeNewswire
    'accesswire.com',      # AccessWire

    # Email Service Providers (used by REITs)
    'sendgrid.net',        # SendGrid
    'sendgrid.info',       # SendGrid alternative
    'mailchimp.com',       # MailChimp
    'constantcontact.com', # Constant Contact

    # Add more as needed...
]


def add_to_whitelist(domain: str, reason: str = "Trusted IR service") -> None:
    """Add domain to whitelist"""
    try:
        table.put_item(
            Item={
                'domain': domain,
                'reason': reason,
                'added_at': datetime.now(timezone.utc).isoformat(),
                'added_by': 'populate_script'
            }
        )
        print(f"✅ Added: {domain}")
    except Exception as e:
        print(f"❌ Error adding {domain}: {e}")


def main():
    """Populate whitelist with trusted domains"""
    print(f"Populating whitelist with {len(TRUSTED_DOMAINS)} trusted domains...")
    print()

    for domain in TRUSTED_DOMAINS:
        add_to_whitelist(domain)

    print()
    print(f"✅ Whitelist populated with {len(TRUSTED_DOMAINS)} domains")
    print()
    print("To add custom domains:")
    print("  aws dynamodb put-item --table-name reitsheet-domain-whitelist \\")
    print('    --item \'{"domain": {"S": "example.com"}, "reason": {"S": "Custom REIT"}}\' \\')
    print("    --region us-east-1")


if __name__ == '__main__':
    main()
