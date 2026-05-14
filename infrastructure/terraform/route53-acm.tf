# ============================================================================
# REIT Sheet - Route53 + ACM for HTTPS
# ============================================================================
# Sets up:
#   - Route53 hosted zone for reitsheet.co
#   - ACM certificate for app.reitsheet.co
#   - DNS validation
#   - ALB HTTPS listener
#
# Cost: ~$0.50/month (Route53 hosted zone)

# -----------------------------------------------------------------------------
# Route53 Hosted Zone
# -----------------------------------------------------------------------------

resource "aws_route53_zone" "main" {
  name    = "reitsheet.co"
  comment = "Managed by Terraform - REIT Newsletter"

  tags = merge(local.common_tags, {
    Name = "reitsheet.co"
  })
}

# -----------------------------------------------------------------------------
# ACM Certificate
# -----------------------------------------------------------------------------

resource "aws_acm_certificate" "app" {
  domain_name       = "app.reitsheet.co"
  validation_method = "DNS"

  tags = merge(local.common_tags, {
    Name = "app.reitsheet.co"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# DNS validation record
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.app.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = aws_route53_zone.main.zone_id
}

# Certificate validation
resource "aws_acm_certificate_validation" "app" {
  certificate_arn         = aws_acm_certificate.app.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

# -----------------------------------------------------------------------------
# DNS Record for App
# -----------------------------------------------------------------------------

resource "aws_route53_record" "app" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "app.reitsheet.co"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# -----------------------------------------------------------------------------
# ALB HTTPS Listener
# -----------------------------------------------------------------------------

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.app.certificate_arn

  default_action {
    type = "forward"
    # Use EC2 target group when use_ec2_backend is true
    target_group_arn = var.use_ec2_backend ? aws_lb_target_group.flask_ec2.arn : aws_lb_target_group.flask.arn
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-https-listener"
  })
}

# Redirect HTTP to HTTPS
resource "aws_lb_listener_rule" "redirect_http_to_https" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 1

  action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }

  condition {
    path_pattern {
      values = ["/*"]
    }
  }
}

# -----------------------------------------------------------------------------
# Security Group Update - Allow HTTPS
# -----------------------------------------------------------------------------
# Note: HTTPS ingress rule already exists on ALB security group

# -----------------------------------------------------------------------------
# ACM Certificate for Newsletter Tracking Domain
# -----------------------------------------------------------------------------
# Enables HTTPS for newsletter.reitsheet.co (SES email tracking)
# CloudFront uses this certificate to serve tracking links securely

resource "aws_acm_certificate" "newsletter_tracking" {
  domain_name       = "newsletter.reitsheet.co"
  validation_method = "DNS"

  tags = merge(local.common_tags, {
    Name    = "newsletter-tracking-cert"
    Purpose = "SES email tracking HTTPS"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# DNS validation record for newsletter tracking cert
resource "aws_route53_record" "newsletter_tracking_validation" {
  for_each = {
    for dvo in aws_acm_certificate.newsletter_tracking.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = aws_route53_zone.main.zone_id
}

# Certificate validation for newsletter tracking
resource "aws_acm_certificate_validation" "newsletter_tracking" {
  certificate_arn         = aws_acm_certificate.newsletter_tracking.arn
  validation_record_fqdns = [for record in aws_route53_record.newsletter_tracking_validation : record.fqdn]
}

# -----------------------------------------------------------------------------
# ACM Certificate for Homepage (reitsheet.co apex domain)
# -----------------------------------------------------------------------------

resource "aws_acm_certificate" "homepage" {
  domain_name       = "reitsheet.co"
  validation_method = "DNS"

  tags = merge(local.common_tags, {
    Name    = "homepage-cert"
    Purpose = "Homepage HTTPS"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# DNS validation record for homepage cert
resource "aws_route53_record" "homepage_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.homepage.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = aws_route53_zone.main.zone_id
}

# Certificate validation for homepage
resource "aws_acm_certificate_validation" "homepage" {
  certificate_arn         = aws_acm_certificate.homepage.arn
  validation_record_fqdns = [for record in aws_route53_record.homepage_cert_validation : record.fqdn]
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "app_url" {
  description = "Application URL (HTTPS)"
  value       = "https://app.reitsheet.co"
}

output "route53_nameservers" {
  description = "Nameservers to configure at your domain registrar"
  value       = aws_route53_zone.main.name_servers
}

output "certificate_arn" {
  description = "ACM certificate ARN"
  value       = aws_acm_certificate.app.arn
}
