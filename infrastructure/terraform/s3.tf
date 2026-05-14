# ============================================================================
# REIT Sheet - S3 Storage Configuration
# ============================================================================
# S3 bucket for temporary email storage
# - Receives emails from AWS SES
# - Triggers Lambda producer on ObjectCreated events
# - Automatically deletes emails after 14 days
# - Versioning enabled for data integrity

# -----------------------------------------------------------------------------
# S3 Bucket
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "email_ingest" {
  bucket = local.s3_bucket_name

  tags = merge(local.storage_tags, {
    Name        = "REIT-Sheet-Email-Ingest-Bucket"
    Description = "Temporary-storage-for-incoming-press-release-emails-from-SES"
    DataType    = "email-raw"
    Retention   = "${var.s3_lifecycle_days}-days"
    TriggerFor  = "lambda-producer"
  })
}

# -----------------------------------------------------------------------------
# S3 Access Logs Bucket (SECURITY: Audit trail for email bucket access)
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "email_access_logs" {
  bucket = "${var.project_name}-email-access-logs"

  tags = merge(local.storage_tags, {
    Name        = "REIT-Sheet-Email-Access-Logs"
    Description = "Audit trail for email bucket access"
    DataType    = "access-logs"
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "email_access_logs" {
  bucket = aws_s3_bucket.email_access_logs.id

  rule {
    id     = "expire-old-logs"
    status = "Enabled"

    filter {} # Apply to all objects in bucket

    expiration {
      days = 90 # Keep logs for 90 days
    }
  }
}

resource "aws_s3_bucket_public_access_block" "email_access_logs" {
  bucket = aws_s3_bucket.email_access_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# -----------------------------------------------------------------------------
# S3 Encryption (SECURITY: Encrypt emails at rest)
# -----------------------------------------------------------------------------
# Explicitly configure server-side encryption with AES-256
# Enables bucket key for reduced encryption costs

resource "aws_s3_bucket_server_side_encryption_configuration" "email_ingest" {
  bucket = aws_s3_bucket.email_ingest.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# -----------------------------------------------------------------------------
# S3 Public Access Block (SECURITY: Prevent accidental public exposure)
# -----------------------------------------------------------------------------
# Blocks all public access to email bucket
# Prevents misconfiguration from exposing private email data

resource "aws_s3_bucket_public_access_block" "email_ingest" {
  bucket = aws_s3_bucket.email_ingest.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# -----------------------------------------------------------------------------
# S3 Versioning
# -----------------------------------------------------------------------------
# Protects against accidental overwrites and deletions
# Enables point-in-time recovery

resource "aws_s3_bucket_versioning" "email_ingest" {
  bucket = aws_s3_bucket.email_ingest.id

  versioning_configuration {
    status = "Enabled"
  }
}

# -----------------------------------------------------------------------------
# S3 Lifecycle Policy
# -----------------------------------------------------------------------------
# Automatically deletes emails after retention period
# Applies only to incoming/ prefix to preserve any manual uploads
# Reduces storage costs and maintains data hygiene

resource "aws_s3_bucket_lifecycle_configuration" "email_ingest" {
  bucket = aws_s3_bucket.email_ingest.id

  rule {
    id     = "delete-old-emails"
    status = "Enabled"

    filter {
      prefix = var.s3_email_prefix
    }

    expiration {
      days = var.s3_lifecycle_days
    }
  }
}

# -----------------------------------------------------------------------------
# S3 Bucket Policy
# -----------------------------------------------------------------------------
# Grants AWS SES permission to write emails to this bucket
# Restricted to our AWS account for security

resource "aws_s3_bucket_policy" "email_ingest" {
  bucket = aws_s3_bucket.email_ingest.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSESPuts"
        Effect = "Allow"
        Principal = {
          Service = "ses.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.email_ingest.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# S3 Access Logging (SECURITY: Track who accesses emails)
# -----------------------------------------------------------------------------

resource "aws_s3_bucket_logging" "email_ingest" {
  bucket = aws_s3_bucket.email_ingest.id

  target_bucket = aws_s3_bucket.email_access_logs.id
  target_prefix = "email-bucket-access/"
}

# -----------------------------------------------------------------------------
# S3 Event Notification
# -----------------------------------------------------------------------------
# Triggers Lambda producer when new email arrives
# Only fires for ObjectCreated events in incoming/ prefix
# Enables real-time processing of incoming emails

resource "aws_s3_bucket_notification" "email_notification" {
  bucket = aws_s3_bucket.email_ingest.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.producer.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = var.s3_email_prefix
  }

  depends_on = [aws_lambda_permission.allow_s3]
}
