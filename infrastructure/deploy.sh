#!/bin/bash
# REIT Sheet Infrastructure Deployment Script

set -e  # Exit on error

echo "========================================="
echo "REIT Sheet Infrastructure Deployment"
echo "========================================="
echo ""

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install it first."
    exit 1
fi

# Check Terraform
if ! command -v terraform &> /dev/null; then
    echo "❌ Terraform not found. Installing..."
    brew install terraform
fi

# Get current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "📦 Step 1: Package Lambda Functions"
echo "-----------------------------------"

# Package producer Lambda
cd lambdas/producer
echo "Packaging producer Lambda..."
zip -q ../producer.zip handler.py
cd ../..

# Package parser Lambda
cd lambdas/parser
echo "Packaging parser Lambda..."
zip -q ../parser.zip handler.py
cd ../..

# Package scraper Lambda
cd lambdas/scraper
echo "Packaging scraper Lambda..."
# Note: Scraper needs requests library - install to package directory first
# pip install requests -t . --upgrade
zip -q ../scraper.zip handler.py
cd ../..

echo "✅ Lambda packaged"
echo ""

echo "🏗️  Step 2: Initialize Terraform"
echo "-----------------------------------"
cd terraform

if [ ! -d ".terraform" ]; then
    terraform init
else
    echo "Terraform already initialized"
fi
echo ""

echo "📋 Step 3: Review Infrastructure Plan"
echo "-----------------------------------"
terraform plan
echo ""

read -p "Deploy this infrastructure? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Deployment cancelled"
    exit 0
fi

echo ""
echo "🚀 Step 4: Deploy Infrastructure"
echo "-----------------------------------"
terraform apply -auto-approve

echo ""
echo "========================================="
echo "✅ Deployment Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Configure SES receipt rule to route emails to S3"
echo "2. Test by sending email to alerts@reitsheet.co"
echo ""

# Show outputs
terraform output
