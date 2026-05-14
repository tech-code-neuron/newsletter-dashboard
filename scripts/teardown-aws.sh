#!/bin/bash
# AWS Infrastructure Teardown Script for reitsheet
# This will delete all AWS resources for the newsletter

set -e

echo "=== REITSHEET AWS TEARDOWN ==="
echo "This will delete all AWS resources. Press Ctrl+C to cancel."
echo ""

# 1. Stop EC2 instance
echo "1. Stopping EC2 instance..."
aws ec2 stop-instances --instance-ids i-000a30251baf4fef8 2>/dev/null || echo "   (may already be stopped)"

# 2. Delete Lambda functions
echo "2. Deleting Lambda functions..."
for fn in reitsheet-body-fetcher reitsheet-email-forwarder reitsheet-producer \
          reitsheet-dlq-processor reitsheet-ses-event-processor reitsheet-social-classifier \
          reitsheet-parser reitsheet-scraper-router reitsheet-enricher reitsheet-8k-fetcher \
          reitsheet-newsletter-signup reitsheet-rss-scheduler reitsheet-brave-news-fetcher \
          reitsheet-simple-scraper reitsheet-daily-summary reitsheet-cleanup-scheduler \
          reitsheet-8k-processor reitsheet-scraper reitsheet-playwright-scraper; do
    echo "   Deleting $fn..."
    aws lambda delete-function --function-name "$fn" 2>/dev/null || echo "   (may not exist)"
done

# 3. Disable CloudFront distributions (must be disabled before deletion)
echo "3. Disabling CloudFront distributions..."
echo "   NOTE: CloudFront distributions must be manually deleted after disabling"
echo "   Distribution IDs: E1OJKTRGT9KX3A (reitsheet.co), E3ICVZ6T66AJG2 (newsletter.reitsheet.co)"

# 4. Delete SQS queues
echo "4. Deleting SQS queues..."
for queue in reitsheet-email-parse-queue reitsheet-enricher-queue reitsheet-scrape-queue \
             reitsheet-playwright-scraper-queue reitsheet-playwright-scraper-dlq \
             reitsheet-simple-scraper-queue reitsheet-social-queue; do
    QUEUE_URL=$(aws sqs get-queue-url --queue-name "$queue" --query QueueUrl --output text 2>/dev/null) || continue
    echo "   Deleting $queue..."
    aws sqs delete-queue --queue-url "$QUEUE_URL" 2>/dev/null || echo "   (may not exist)"
done

# 5. Delete API Gateways
echo "5. Listing API Gateways (delete manually in console)..."
aws apigateway get-rest-apis --query "items[?contains(name, 'reitsheet')].{Name:name,Id:id}" --output table 2>/dev/null

# 6. Note about DynamoDB tables
echo ""
echo "6. DynamoDB tables (28 tables) - keeping for now"
echo "   To delete, run: aws dynamodb delete-table --table-name <table-name>"
echo "   Tables: reitsheet-companies-config, reitsheet-subscribers, reitsheet-reit-news-v2, etc."

# 7. Note about other resources
echo ""
echo "7. Resources to delete manually in AWS Console:"
echo "   - ALB (Application Load Balancer)"
echo "   - EC2 instance (after stopped: terminate)"
echo "   - CloudFront distributions (after disabled: delete)"
echo "   - S3 buckets (empty first, then delete)"
echo "   - Cognito user pool"
echo "   - Route53 records"
echo "   - ACM certificates"
echo "   - ECR repositories"
echo "   - CloudWatch log groups"

echo ""
echo "=== TEARDOWN INITIATED ==="
echo "EC2 stopped, Lambdas deleted, SQS queues deleted."
echo "Complete the rest manually in AWS Console."
