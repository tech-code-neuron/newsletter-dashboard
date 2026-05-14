# ============================================================================
# REIT Sheet - CloudFront for Newsletter Tracking HTTPS
# ============================================================================
# Provides HTTPS frontend for SES custom tracking domain.
#
# Architecture:
#   User clicks: https://newsletter.reitsheet.co/r/abc123...
#        ↓
#   CloudFront (SSL via ACM certificate)
#        ↓
#   Origin: r.us-east-1.awstrack.me (AWS SES tracking backend)
#        ↓
#   SES handles tracking + redirects to destination URL
#
# Cost: ~$0.01/10,000 requests + $0.085/GB transfer (~$1-5/month typical)

# -----------------------------------------------------------------------------
# CloudFront Distribution
# -----------------------------------------------------------------------------

resource "aws_cloudfront_distribution" "newsletter_tracking" {
  enabled         = true
  comment         = "HTTPS frontend for SES tracking domain newsletter.reitsheet.co"
  aliases         = ["newsletter.reitsheet.co"]
  price_class     = "PriceClass_100" # US, Canada, Europe only (cost optimization)
  http_version    = "http2and3"
  is_ipv6_enabled = true

  # Origin: AWS SES tracking endpoint
  origin {
    domain_name = "r.us-east-1.awstrack.me"
    origin_id   = "ses-tracking"

    # Pass original domain to awstrack.me for custom domain lookup
    custom_header {
      name  = "X-Forwarded-Host"
      value = "newsletter.reitsheet.co"
    }

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only" # Use HTTPS to origin
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Origin: Flask app (ALB) for subscription endpoints
  # Uses app.reitsheet.co domain so HTTPS cert matches
  origin {
    domain_name = "app.reitsheet.co"
    origin_id   = "flask-app"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # -----------------------------------------------------------------------------
  # Subscription Endpoints - Route to Flask App
  # -----------------------------------------------------------------------------

  # Subscribe page and form submission
  ordered_cache_behavior {
    path_pattern           = "/subscribe*"
    target_origin_id       = "flask-app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # CachingDisabled
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3" # AllViewer
  }

  # Email verification endpoint
  ordered_cache_behavior {
    path_pattern           = "/verify*"
    target_origin_id       = "flask-app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  # Unsubscribe endpoint (one-click)
  ordered_cache_behavior {
    path_pattern           = "/unsubscribe*"
    target_origin_id       = "flask-app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  # API unsubscribe (RFC 8058 List-Unsubscribe-Post)
  ordered_cache_behavior {
    path_pattern           = "/api/unsubscribe*"
    target_origin_id       = "flask-app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  # Static assets for subscription pages
  ordered_cache_behavior {
    path_pattern           = "/static/*"
    target_origin_id       = "flask-app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # Cache static assets
    cache_policy_id          = "658327ea-f89d-4fab-a63d-7e88639e58f6" # CachingOptimized
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  # -----------------------------------------------------------------------------
  # Default: SES Email Tracking
  # -----------------------------------------------------------------------------

  # Default cache behavior - no caching for real-time tracking
  default_cache_behavior {
    target_origin_id       = "ses-tracking"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = false

    # AWS managed policies for no caching
    # CachingDisabled: 4135ea2d-6df8-44a3-9df3-4b5a84be39ad
    # AllViewer: 216adef6-5c7f-47e4-b989-5492eafa07d3 (forwards ALL headers including Host)
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  # SSL certificate from ACM
  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.newsletter_tracking.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  # No geo restrictions
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  tags = merge(local.common_tags, {
    Name    = "${var.project_name}-newsletter-tracking"
    Purpose = "SES email tracking HTTPS"
  })

  # Wait for certificate validation before creating distribution
  depends_on = [aws_acm_certificate_validation.newsletter_tracking]
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "newsletter_tracking_cloudfront_domain" {
  description = "CloudFront distribution domain for newsletter tracking"
  value       = aws_cloudfront_distribution.newsletter_tracking.domain_name
}

output "newsletter_tracking_cloudfront_id" {
  description = "CloudFront distribution ID for newsletter tracking"
  value       = aws_cloudfront_distribution.newsletter_tracking.id
}
