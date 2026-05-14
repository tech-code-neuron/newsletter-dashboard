#!/bin/bash
# Test the email ingestion pipeline

echo "🔍 Checking S3 for incoming emails..."
aws s3 ls s3://reitsheet-email-ingest/incoming/ --region us-east-1

echo ""
echo "📊 Checking SQS Parse Queue..."
aws sqs get-queue-attributes \
  --queue-url $(cd terraform && terraform output -raw parse_queue_url) \
  --attribute-names ApproximateNumberOfMessages \
  --region us-east-1

echo ""
echo "📝 Checking Lambda logs (last 5 minutes)..."
aws logs tail /aws/lambda/reitsheet-producer \
  --since 5m \
  --region us-east-1 \
  --follow
