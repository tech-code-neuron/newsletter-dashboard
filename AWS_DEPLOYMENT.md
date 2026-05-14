# AWS Deployment Guide

Complete guide to deploying the Press Release Pipeline on AWS.

---

## Prerequisites

- [ ] AWS account with admin access
- [ ] AWS CLI installed and configured
- [ ] Terraform 1.0+ installed
- [ ] Domain for receiving emails (optional but recommended)
- [ ] Anthropic API key

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│     SES     │────▶│     S3      │────▶│   Lambda    │
│  (receive)  │     │  (storage)  │     │  (parser)   │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                    ┌─────────────┐     ┌──────▼──────┐
                    │  DynamoDB   │◀────│   Lambda    │
                    │  (storage)  │     │ (enricher)  │
                    └─────────────┘     └─────────────┘
```

**Resources created:**
- Lambda functions (parser, enricher, scraper, etc.)
- DynamoDB tables (press releases, companies, subscribers)
- S3 buckets (email storage, static assets)
- SQS queues (async processing)
- API Gateway (newsletter signup)
- CloudWatch (logging, scheduling)

---

## Step 1: Configure Variables

```bash
cd infrastructure/terraform

# Copy example configuration
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:
```hcl
# Required
project_name = "my-newsletter"
environment  = "prod"
aws_region   = "us-east-1"

# Domain (optional - for email receiving)
domain_name = "your-domain.com"

# Your IP for SSH access (get from whatismyip.com)
admin_ssh_cidr = "YOUR_IP/32"

# Secrets (will be stored in AWS Secrets Manager)
anthropic_api_key = "sk-ant-xxxxx"
```

---

## Step 2: Initialize Terraform

```bash
terraform init
```

**Expected output:**
```
Terraform has been successfully initialized!
```

---

## Step 3: Review the Plan

```bash
terraform plan
```

Review the resources that will be created. Look for:
- Lambda functions
- DynamoDB tables
- S3 buckets
- IAM roles

---

## Step 4: Deploy

```bash
terraform apply
```

Type `yes` when prompted.

**This takes 5-10 minutes.** Resources are created in order of dependencies.

---

## Step 5: Verify Deployment

### Check Lambda Functions
```bash
aws lambda list-functions --query "Functions[?starts_with(FunctionName, 'my-newsletter')]"
```

### Check DynamoDB Tables
```bash
aws dynamodb list-tables
```

### Check S3 Buckets
```bash
aws s3 ls | grep my-newsletter
```

---

## Step 6: Set Up Email Receiving (Optional)

If you want to receive IR emails:

### 6a. Verify Domain in SES
```bash
aws ses verify-domain-identity --domain your-domain.com
```

Add the TXT record from output to your DNS.

### 6b. Add MX Record
```
MX: 10 inbound-smtp.us-east-1.amazonaws.com
```

### 6c. Activate SES Rule Set
```bash
aws ses set-active-receipt-rule-set --rule-set-name my-newsletter-rules
```

---

## Step 7: Deploy Flask Dashboard (Optional)

For the web dashboard, deploy to EC2:

```bash
cd infrastructure
./deploy-flask-to-ec2.sh
```

Or use the Docker image:
```bash
cd infrastructure/docker/flask-app
docker build -t newsletter-dashboard .
docker run -p 5001:5001 newsletter-dashboard
```

---

## Post-Deployment Configuration

### Add Companies
Use the dashboard or CLI:
```bash
python scripts/load_companies.py
```

### Set Up Brave Search (Optional)
Add your Brave API key to Secrets Manager:
```bash
aws secretsmanager update-secret \
  --secret-id my-newsletter/config \
  --secret-string '{"BRAVE_API_KEY": "your-key"}'
```

### Configure Newsletter Recipients
Update the subscribers table or use the signup API.

---

## Cost Monitoring

Set up a billing alert:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "newsletter-cost-alarm" \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --threshold 20 \
  --comparison-operator GreaterThanThreshold
```

Expected monthly costs:
- Lambda: ~$0.10 (free tier)
- DynamoDB: ~$0.25
- S3: ~$0.05
- SES: ~$0.10 per 1000 emails

---

## Updating the Deployment

```bash
# Pull latest code
git pull

# Apply changes
cd infrastructure/terraform
terraform plan  # Review changes
terraform apply
```

---

## Destroying the Deployment

```bash
terraform destroy
```

**Warning:** This deletes all resources including data in DynamoDB.

---

## Troubleshooting

### "Access Denied" errors
- Check AWS CLI is configured: `aws sts get-caller-identity`
- Verify IAM permissions

### Lambda timeout
- Check CloudWatch logs: `aws logs tail /aws/lambda/parser`
- Increase timeout in `terraform.tfvars`

### SES not receiving emails
- Verify domain shows "verified" in SES console
- Check MX record is correct
- Ensure receipt rule set is active

### DynamoDB throttling
- Switch to on-demand capacity (already default)
- Check for hot partitions

---

## Security Notes

- API keys stored in AWS Secrets Manager (not in code)
- Lambda functions run with minimal IAM permissions
- S3 buckets are private by default
- VPC configuration available for additional isolation
