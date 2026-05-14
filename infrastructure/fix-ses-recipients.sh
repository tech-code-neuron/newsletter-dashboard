#!/bin/bash
# Fix SES receipt rule to only accept alerts@reitsheet.co
# Currently accepts ALL emails @reitsheet.co (security risk!)

set -e

echo "🔧 Updating SES receipt rule to only accept alerts@reitsheet.co"

# Delete the old rule
aws ses delete-receipt-rule \
  --rule-set-name reitsheet-rules \
  --rule-name route-to-s3 \
  --region us-east-1

echo "✅ Deleted old rule (accepted all @reitsheet.co)"

# Create new rule with specific recipient
aws ses create-receipt-rule \
  --rule-set-name reitsheet-rules \
  --region us-east-1 \
  --rule '{
    "Name": "route-to-s3",
    "Enabled": true,
    "Recipients": ["alerts@reitsheet.co"],
    "Actions": [{
      "S3Action": {
        "BucketName": "reitsheet-email-ingest",
        "ObjectKeyPrefix": "incoming/"
      }
    }],
    "ScanEnabled": true
  }'

echo "✅ Created new rule (only accepts alerts@reitsheet.co)"
echo ""
echo "Verification:"
aws ses describe-receipt-rule \
  --rule-set-name reitsheet-rules \
  --rule-name route-to-s3 \
  --region us-east-1 \
  --query 'Rule.Recipients'

echo ""
echo "✅ Done! Only alerts@reitsheet.co is now accepted."
