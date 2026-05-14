# ============================================================================
# REIT Sheet - Social Media Cards S3 Storage
# ============================================================================
# S3 bucket for generated social media card images
# - Stores OG images for X link previews
# - Stores Instagram portrait cards
# - Public read access for social platform crawlers
# - Lifecycle: delete after 365 days (cards are cheap to regenerate)

# -----------------------------------------------------------------------------
# S3 Bucket
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "social_cards" {
  bucket = "${var.project_name}-social-cards"

  tags = merge(local.storage_tags, {
    Name        = "REIT-Sheet-Social-Cards"
    Description = "Generated social media card images for X and Instagram"
    DataType    = "images"
    Retention   = "365-days"
    Access      = "public-read"
  })
}

# -----------------------------------------------------------------------------
# S3 Public Access Block - Allow public read for social cards
# -----------------------------------------------------------------------------
# Social cards need to be publicly readable so X and Instagram crawlers
# can fetch them for link previews

resource "aws_s3_bucket_public_access_block" "social_cards" {
  bucket = aws_s3_bucket.social_cards.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# -----------------------------------------------------------------------------
# S3 Bucket Policy - Public read access
# -----------------------------------------------------------------------------

resource "aws_s3_bucket_policy" "social_cards_public_read" {
  bucket = aws_s3_bucket.social_cards.id

  # Depends on public access block being configured first
  depends_on = [aws_s3_bucket_public_access_block.social_cards]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadForSocialCards"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.social_cards.arn}/*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# S3 Encryption
# -----------------------------------------------------------------------------

resource "aws_s3_bucket_server_side_encryption_configuration" "social_cards" {
  bucket = aws_s3_bucket.social_cards.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# -----------------------------------------------------------------------------
# S3 Lifecycle - Delete old cards after 1 year
# -----------------------------------------------------------------------------

resource "aws_s3_bucket_lifecycle_configuration" "social_cards" {
  bucket = aws_s3_bucket.social_cards.id

  rule {
    id     = "expire-old-cards"
    status = "Enabled"

    filter {} # Apply to all objects

    expiration {
      days = 365
    }
  }
}

# -----------------------------------------------------------------------------
# S3 CORS Configuration - Allow cross-origin access for previews
# -----------------------------------------------------------------------------

resource "aws_s3_bucket_cors_configuration" "social_cards" {
  bucket = aws_s3_bucket.social_cards.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = [
      "https://reitsheet.co",
      "https://app.reitsheet.co",
      "https://*.reitsheet.co"
    ]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "social_cards_bucket_name" {
  value       = aws_s3_bucket.social_cards.bucket
  description = "Social cards S3 bucket name"
}

output "social_cards_bucket_arn" {
  value       = aws_s3_bucket.social_cards.arn
  description = "Social cards S3 bucket ARN"
}

output "social_cards_bucket_domain" {
  value       = aws_s3_bucket.social_cards.bucket_regional_domain_name
  description = "Social cards S3 bucket domain for image URLs"
}
