# ============================================================================
# REIT Sheet - Route53 DNS Records
# ============================================================================
# Migrated from Namecheap - matches existing DNS configuration
#
# Records:
#   - MX: SES inbound email
#   - TXT: SPF for SES
#   - CNAME: DKIM for SES (3 records)

# -----------------------------------------------------------------------------
# MX Record - SES Inbound Email
# -----------------------------------------------------------------------------

resource "aws_route53_record" "mx" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "reitsheet.co"
  type    = "MX"
  ttl     = 300

  records = [
    "10 inbound-smtp.us-east-1.amazonaws.com"
  ]
}

# -----------------------------------------------------------------------------
# TXT Record - SPF for SES
# -----------------------------------------------------------------------------

resource "aws_route53_record" "spf" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "reitsheet.co"
  type    = "TXT"
  ttl     = 300

  records = [
    "v=spf1 include:amazonses.com ~all"
  ]
}

# -----------------------------------------------------------------------------
# CNAME Records - DKIM for SES
# -----------------------------------------------------------------------------

resource "aws_route53_record" "dkim1" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "ouwu7wpw4n6esimwckfkkzsnjra5f3ci._domainkey.reitsheet.co"
  type    = "CNAME"
  ttl     = 300

  records = [
    "ouwu7wpw4n6esimwckfkkzsnjra5f3ci.dkim.amazonses.com"
  ]
}

resource "aws_route53_record" "dkim2" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "fovfwciu367xynfwkfvewnsy3q3a5k5r._domainkey.reitsheet.co"
  type    = "CNAME"
  ttl     = 300

  records = [
    "fovfwciu367xynfwkfvewnsy3q3a5k5r.dkim.amazonses.com"
  ]
}

resource "aws_route53_record" "dkim3" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "pnmenzgvk64h3w7pjwbg47qc3kxafcr3._domainkey.reitsheet.co"
  type    = "CNAME"
  ttl     = 300

  records = [
    "pnmenzgvk64h3w7pjwbg47qc3kxafcr3.dkim.amazonses.com"
  ]
}

# -----------------------------------------------------------------------------
# alerts subdomain - SES receiving (if needed)
# -----------------------------------------------------------------------------
# Note: SES receiving uses MX record on root domain,
# alerts@reitsheet.co routes via SES receipt rules

# -----------------------------------------------------------------------------
# newsletter subdomain - SES click/open tracking via CloudFront
# -----------------------------------------------------------------------------
# HTTPS frontend for SES tracking links
# CloudFront serves SSL, forwards to AWS tracking backend

resource "aws_route53_record" "newsletter_tracking" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "newsletter.reitsheet.co"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.newsletter_tracking.domain_name
    zone_id                = aws_cloudfront_distribution.newsletter_tracking.hosted_zone_id
    evaluate_target_health = false
  }
}
