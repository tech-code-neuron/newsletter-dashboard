# ============================================================================
# REIT Sheet - Newsletter API Gateway
# ============================================================================
# HTTP API for newsletter subscription management
#
# Endpoints:
#   POST /subscribe          - Create new subscriber
#   GET /verify/{token}      - Verify email address
#   GET /unsubscribe/{token} - Unsubscribe from newsletter
#
# Features:
#   - CORS enabled (public endpoints)
#   - No authentication (public signup)
#   - Lambda proxy integration

# -----------------------------------------------------------------------------
# API Gateway HTTP API
# -----------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "newsletter" {
  name          = "${var.project_name}-newsletter-api"
  protocol_type = "HTTP"
  description   = "Newsletter subscription API for REIT Sheet"

  cors_configuration {
    # Restrict CORS to prevent cross-origin API abuse
    # Note: HTML form POST ignores CORS - this only blocks fetch/XHR from other origins
    allow_origins = ["https://reitsheet.co", "https://app.reitsheet.co"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["content-type", "authorization"]
    max_age       = 300
  }

  tags = merge(local.common_tags, {
    Name    = "REIT-Sheet-Newsletter-API"
    Purpose = "newsletter-subscription"
  })
}

# -----------------------------------------------------------------------------
# API Gateway Stage (Auto-deploy)
# -----------------------------------------------------------------------------

resource "aws_apigatewayv2_stage" "newsletter" {
  api_id      = aws_apigatewayv2_api.newsletter.id
  name        = "prod"
  auto_deploy = true

  # Rate limiting to prevent DDoS and abuse
  default_route_settings {
    throttling_rate_limit  = 100  # requests per second
    throttling_burst_limit = 200  # burst capacity
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.newsletter_api_logs.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      responseLength   = "$context.responseLength"
      integrationError = "$context.integrationErrorMessage"
    })
  }

  tags = merge(local.common_tags, {
    Name    = "REIT-Sheet-Newsletter-API-Stage"
    Purpose = "newsletter-subscription"
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group for API Gateway
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "newsletter_api_logs" {
  name              = "/aws/apigateway/${var.project_name}-newsletter-api"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name = "Newsletter-API-Gateway-Logs"
  })
}

# -----------------------------------------------------------------------------
# Lambda Integration
# -----------------------------------------------------------------------------

resource "aws_apigatewayv2_integration" "newsletter_signup" {
  api_id                 = aws_apigatewayv2_api.newsletter.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.newsletter_signup.invoke_arn
  payload_format_version = "2.0"
}

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

# POST /subscribe - Create new subscriber
resource "aws_apigatewayv2_route" "subscribe" {
  api_id    = aws_apigatewayv2_api.newsletter.id
  route_key = "POST /subscribe"
  target    = "integrations/${aws_apigatewayv2_integration.newsletter_signup.id}"
}

# GET /verify/{token} - Verify email address
resource "aws_apigatewayv2_route" "verify" {
  api_id    = aws_apigatewayv2_api.newsletter.id
  route_key = "GET /verify/{token}"
  target    = "integrations/${aws_apigatewayv2_integration.newsletter_signup.id}"
}

# GET /unsubscribe/{token} - Unsubscribe from newsletter
resource "aws_apigatewayv2_route" "unsubscribe" {
  api_id    = aws_apigatewayv2_api.newsletter.id
  route_key = "GET /unsubscribe/{token}"
  target    = "integrations/${aws_apigatewayv2_integration.newsletter_signup.id}"
}

# -----------------------------------------------------------------------------
# Lambda Permission for API Gateway
# -----------------------------------------------------------------------------

resource "aws_lambda_permission" "newsletter_api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.newsletter_signup.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.newsletter.execution_arn}/*/*"
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "newsletter_api_endpoint" {
  description = "Newsletter API endpoint URL"
  value       = aws_apigatewayv2_stage.newsletter.invoke_url
}

output "newsletter_subscribe_url" {
  description = "Full URL for subscription endpoint"
  value       = "${aws_apigatewayv2_stage.newsletter.invoke_url}/subscribe"
}

output "newsletter_api_id" {
  description = "Newsletter API Gateway ID"
  value       = aws_apigatewayv2_api.newsletter.id
}
