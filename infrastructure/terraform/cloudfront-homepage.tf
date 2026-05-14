# ============================================================================
# REIT Sheet - CloudFront for Homepage (reitsheet.co)
# ============================================================================
# Public homepage distribution serving both static content and Flask app routes.
#
# Architecture:
#   reitsheet.co → CloudFront → Flask app (app.reitsheet.co)
#                            → S3 homepage bucket (static fallback)
#
# Behaviors:
#   /subscribe* → Flask (POST enabled for form submission)
#   /verify*    → Flask (email verification)
#   /*          → Flask (default, with archive redirect function)

# -----------------------------------------------------------------------------
# CloudFront Function - Archive URL Handler
# -----------------------------------------------------------------------------

resource "aws_cloudfront_function" "archive_redirect" {
  name    = "reitsheet-archive-redirect"
  runtime = "cloudfront-js-2.0"
  comment = "Archive URL handler"
  publish = true
  code    = file("${path.module}/../cloudfront-functions/archive-redirect.js")
}

# -----------------------------------------------------------------------------
# CloudFront Distribution
# -----------------------------------------------------------------------------

resource "aws_cloudfront_distribution" "homepage" {
  enabled         = true
  comment         = "REIT Sheet Public Homepage"
  aliases         = ["reitsheet.co"]
  price_class     = "PriceClass_All"
  http_version    = "http2"
  is_ipv6_enabled = true

  # Origin: Flask app via app.reitsheet.co
  origin {
    domain_name = "app.reitsheet.co"
    origin_id   = "flask-app"

    custom_header {
      name  = "X-Forwarded-Host"
      value = "reitsheet.co"
    }

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Origin: S3 homepage bucket (static content fallback)
  origin {
    domain_name = "${aws_s3_bucket.homepage.bucket}.s3-website-${var.aws_region}.amazonaws.com"
    origin_id   = "S3-reitsheet-homepage"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # -----------------------------------------------------------------------------
  # Subscription Endpoints - Route to Flask App with POST support
  # -----------------------------------------------------------------------------

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

  # API Subscribe endpoint - AJAX form submissions (CSRF-exempt)
  ordered_cache_behavior {
    path_pattern           = "/api/subscribe*"
    target_origin_id       = "flask-app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # CachingDisabled
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3" # AllViewer
  }

  # Email verification endpoint (POST required for scanner protection)
  ordered_cache_behavior {
    path_pattern           = "/verify*"
    target_origin_id       = "flask-app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  # -----------------------------------------------------------------------------
  # Default Behavior - Flask App with Archive Redirect
  # -----------------------------------------------------------------------------

  default_cache_behavior {
    target_origin_id       = "flask-app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.archive_redirect.arn
    }
  }

  # SSL certificate
  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.homepage.certificate_arn
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
    Name    = "${var.project_name}-homepage"
    Purpose = "Public homepage"
  })

  depends_on = [aws_acm_certificate_validation.homepage]
}

# -----------------------------------------------------------------------------
# Route53 A Record - Apex Domain
# -----------------------------------------------------------------------------

resource "aws_route53_record" "homepage" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "reitsheet.co"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.homepage.domain_name
    zone_id                = aws_cloudfront_distribution.homepage.hosted_zone_id
    evaluate_target_health = false
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "homepage_cloudfront_domain" {
  description = "CloudFront distribution domain for homepage"
  value       = aws_cloudfront_distribution.homepage.domain_name
}

output "homepage_cloudfront_id" {
  description = "CloudFront distribution ID for homepage"
  value       = aws_cloudfront_distribution.homepage.id
}
