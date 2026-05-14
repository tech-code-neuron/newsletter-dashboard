# IR Email Setup Guide

How to set up free email alerts from company Investor Relations pages and forward them to your pipeline.

---

## Overview

Most public companies offer free email subscriptions for press releases. This guide shows you how to:
1. Find and subscribe to company IR email alerts
2. Set up email forwarding to your pipeline
3. Configure AWS SES to receive emails

---

## Part 1: Subscribe to Company IR Alerts

### Finding IR Email Signup Pages

1. Go to the company's website
2. Look for "Investors" or "Investor Relations" in the navigation
3. Find "Email Alerts", "Subscribe", or "Stay Informed"
4. Enter your email address and select "Press Releases"

### Example: Digital Realty (DLR)
1. Visit https://investor.digitalrealty.com
2. Click "Email Alerts" in the footer
3. Enter your email
4. Check "Press Releases"
5. Submit

### Tips
- Use a dedicated email address (e.g., `ir-alerts@yourdomain.com`)
- Subscribe to press releases, not just earnings
- Some platforms (Q4, Notified, Business Wire) host multiple companies

---

## Part 2: Set Up Email Forwarding

### Option A: Gmail Forwarding

1. **Create a filter:**
   - Go to Gmail → Settings → Filters
   - Click "Create new filter"
   - From: `*@q4web.com` OR `*@businesswire.com` OR `*@globenewswire.com`
   - Click "Create filter"

2. **Forward matching emails:**
   - Check "Forward it to:"
   - Enter your pipeline email (e.g., `alerts@your-pipeline-domain.com`)
   - Click "Create filter"

### Option B: Outlook Rules

1. **Create a rule:**
   - Go to Settings → Mail → Rules
   - Click "Add new rule"
   - Condition: "From contains" → enter IR domains
   - Action: "Forward to" → your pipeline email

### Common IR Email Domains
```
@q4web.com
@businesswire.com
@prnewswire.com
@globenewswire.com
@notified.com
@issuerservices.com
```

---

## Part 3: AWS SES Setup (for Pipeline Ingestion)

### Prerequisites
- AWS account
- Domain you control (for receiving email)

### Step 1: Verify Your Domain in SES

```bash
aws ses verify-domain-identity --domain your-domain.com --region us-east-1
```

Add the TXT record to your DNS:
```
_amazonses.your-domain.com → <verification-token>
```

### Step 2: Set Up MX Record

Point your domain's email to SES:
```
MX: 10 inbound-smtp.us-east-1.amazonaws.com
```

### Step 3: Create S3 Bucket for Email Storage

```bash
aws s3 mb s3://your-email-bucket --region us-east-1
```

Add bucket policy (see `infrastructure/terraform/s3.tf` for template).

### Step 4: Create SES Receipt Rule

In AWS Console:
1. Go to SES → Email Receiving → Rule Sets
2. Create a rule set (or use default)
3. Create a rule:
   - Recipients: `alerts@your-domain.com`
   - Actions: 
     - S3: Save to `your-email-bucket`
     - Lambda: Invoke `parser` function

### Step 5: Deploy Lambda Functions

```bash
cd infrastructure/terraform
terraform apply
```

This creates the parser and enricher Lambdas that process incoming emails.

---

## Part 4: Test the Pipeline

### Send a Test Email

Forward a press release email to your pipeline address:
```
To: alerts@your-domain.com
```

### Check Processing

1. **S3**: Verify email saved to bucket
2. **CloudWatch Logs**: Check parser Lambda logs
3. **DynamoDB**: Verify press release appeared in table

### Debug Commands

```bash
# Check recent emails in S3
aws s3 ls s3://your-email-bucket/incoming/ --recursive | tail -10

# Check parser logs
aws logs tail /aws/lambda/parser --follow

# Query DynamoDB for recent items
aws dynamodb scan --table-name your-news-table --limit 5
```

---

## Supported Email Sources

The parser recognizes these IR platforms automatically:

| Platform | Domain Pattern |
|----------|---------------|
| Q4 | `*@q4web.com` |
| Business Wire | `*@businesswire.com` |
| PR Newswire | `*@prnewswire.com` |
| GlobeNewswire | `*@globenewswire.com` |
| Notified | `*@notified.com` |
| Issuer Services | `*@issuerservices.com` |

Add more in `config/email_parser_config.py`.

---

## Troubleshooting

### Emails not arriving in S3
- Check MX record is correct
- Verify domain in SES is "verified"
- Check SES receipt rule is active

### Parser not triggering
- Check S3 event notification is configured
- Check Lambda has permissions to read S3

### Press releases not appearing
- Check CloudWatch logs for parser errors
- Verify company domain is in `email_parser_config.py`
