# ============================================================================
# Press Release Pipeline - Main Terraform Configuration
# ============================================================================
# AWS Infrastructure for Automated Email Ingestion Pipeline
#
# Architecture:
#   Email → SES → S3 → Lambda Producer → SQS Parse Queue → Lambda Parser
#   → SQS Scrape Queue (or direct to DynamoDB) → Lambda Scraper → DynamoDB
#
# Resources are organized into logical modules:
#   - s3.tf: S3 buckets and policies
#   - sqs.tf: SQS queues and dead letter queues
#   - dynamodb.tf: DynamoDB tables
#   - iam.tf: IAM roles and policies
#   - lambdas.tf: Lambda functions and triggers
#   - cloudwatch.tf: CloudWatch logs and alarms
#   - variables.tf: Input variables
#   - locals.tf: Computed values and common tags
#   - outputs.tf: Output values
#
# Documentation: ../INFRASTRUCTURE_REVIEW.md
# Repository: https://github.com/YOUR_USERNAME/reit-newsletter

# -----------------------------------------------------------------------------
# Terraform Configuration
# -----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# -----------------------------------------------------------------------------
# AWS Provider
# -----------------------------------------------------------------------------

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {
  # Provides AWS account ID for IAM policies and resource restrictions
}

data "aws_region" "current" {
  # Provides current region for dynamic resource naming
}

# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------
# All infrastructure resources are defined in separate files:
#
# Resource Organization:
#   - S3 storage: s3.tf
#   - Message queues: sqs.tf
#   - Database tables: dynamodb.tf
#   - IAM security: iam.tf
#   - Lambda functions: lambdas.tf
#   - Monitoring: cloudwatch.tf
#
# Configuration:
#   - Input variables: variables.tf
#   - Local values: locals.tf
#   - Output values: outputs.tf
#
# Deployment:
#   1. Initialize: terraform init
#   2. Plan: terraform plan
#   3. Apply: terraform apply
#   4. Configure SES: aws ses create-receipt-rule-set ...
#   5. Test: Send email to alerts@reitsheet.co
#
# Destruction (if needed):
#   terraform destroy
#
# Cost: ~$0.31/month for expected usage (120 REITs, ~5 emails/day)
