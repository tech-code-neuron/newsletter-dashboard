# S3 bucket for URL testing dashboard static website

resource "aws_s3_bucket" "url_testing_dashboard" {
  bucket = "reitsheet-url-testing"

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_dashboard"
  }
}

# Website configuration
resource "aws_s3_bucket_website_configuration" "url_testing" {
  bucket = aws_s3_bucket.url_testing_dashboard.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}

# Public access block configuration (allow public access)
resource "aws_s3_bucket_public_access_block" "url_testing" {
  bucket = aws_s3_bucket.url_testing_dashboard.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# Bucket policy for public read access
resource "aws_s3_bucket_policy" "url_testing_public_read" {
  bucket = aws_s3_bucket.url_testing_dashboard.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicReadGetObject"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.url_testing_dashboard.arn}/*"
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.url_testing]
}
