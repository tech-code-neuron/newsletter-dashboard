# S3 bucket for public homepage (reitsheet.co)
# Stores the latest newsletter HTML for public viewing

resource "aws_s3_bucket" "homepage" {
  bucket = "${var.project_name}-homepage"

  tags = {
    Name        = "${var.project_name}-homepage"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_s3_bucket_website_configuration" "homepage" {
  bucket = aws_s3_bucket.homepage.id

  index_document {
    suffix = "index.html"
  }
}

resource "aws_s3_bucket_public_access_block" "homepage" {
  bucket = aws_s3_bucket.homepage.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "homepage" {
  bucket = aws_s3_bucket.homepage.id
  depends_on = [aws_s3_bucket_public_access_block.homepage]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.homepage.arn}/*"
      }
    ]
  })
}

output "homepage_bucket_name" {
  description = "Homepage S3 bucket name"
  value       = aws_s3_bucket.homepage.bucket
}

output "homepage_website_endpoint" {
  description = "Homepage S3 website endpoint"
  value       = aws_s3_bucket_website_configuration.homepage.website_endpoint
}
