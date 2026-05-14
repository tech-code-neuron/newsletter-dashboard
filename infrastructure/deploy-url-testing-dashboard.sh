#!/bin/bash
# Deploy URL Testing Dashboard
# This script:
# 1. Applies Terraform changes (creates S3, Lambda, API Gateway, DynamoDB)
# 2. Gets API Gateway URL from outputs
# 3. Updates index.html with API Gateway URL
# 4. Uploads index.html to S3 bucket

set -e

echo "🚀 Deploying URL Testing Dashboard..."
echo ""

# Check if user wants to change the default password
echo "⚠️  SECURITY: The default password is 'reit2024!'"
echo "   You can change it in: infrastructure/terraform/variables.tf"
echo "   Variable name: url_testing_password"
echo ""
read -p "Continue with deployment? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi
echo ""

# Change to terraform directory
cd "$(dirname "$0")/terraform"

# Step 1: Apply Terraform changes
echo "📦 Step 1: Applying Terraform changes..."
terraform init -upgrade
terraform apply -auto-approve

# Step 2: Get API Gateway URL
echo ""
echo "🔍 Step 2: Getting API Gateway URL..."
API_URL=$(terraform output -raw url_testing_api_endpoint)
S3_WEBSITE_URL=$(terraform output -raw url_testing_dashboard_url)
S3_BUCKET=$(terraform output -raw s3_bucket_name | sed 's/reitsheet-email-ingest/reitsheet-url-testing/')

echo "   API Gateway URL: $API_URL"
echo "   S3 Website URL: $S3_WEBSITE_URL"
echo "   S3 Bucket: $S3_BUCKET"

# Step 3: Update index.html with API Gateway URL
echo ""
echo "✏️  Step 3: Updating index.html with API Gateway URL..."
HTML_SOURCE="../lambdas/url-testing-api/static/index.html"
HTML_TEMP="/tmp/index.html"

# Replace placeholder with actual API Gateway URL
sed "s|API_GATEWAY_URL_PLACEHOLDER|${API_URL}|g" "$HTML_SOURCE" > "$HTML_TEMP"

echo "   ✅ Updated API_BASE to: $API_URL"

# Step 4: Upload to S3
echo ""
echo "📤 Step 4: Uploading index.html to S3..."
aws s3 cp "$HTML_TEMP" "s3://${S3_BUCKET}/index.html" \
  --content-type "text/html" \
  --cache-control "no-cache, no-store, must-revalidate"

echo "   ✅ Uploaded to S3"

# Clean up
rm -f "$HTML_TEMP"

# Step 5: Display success message
echo ""
echo "✅ Deployment complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔗 URL Testing Dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📱 Open on your phone:"
echo "   $S3_WEBSITE_URL"
echo ""
echo "🔗 API Endpoint:"
echo "   $API_URL"
echo ""
echo "📊 View comments:"
echo "   aws dynamodb scan --table-name url_test_comments --limit 10"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Usage:"
echo "   1. Open dashboard URL on mobile"
echo "   2. Enter password when prompted (saved in localStorage)"
echo "   3. Tap any press release URL to test"
echo "   4. Tap 'Report Issue' to leave comments"
echo "   5. Comments saved to DynamoDB for you to review later"
echo ""
echo "🔒 Security:"
echo "   - Password is stored in localStorage on your phone"
echo "   - All API requests require Authorization header"
echo "   - Change password in variables.tf and redeploy"
echo ""
