# API Gateway HTTP API for URL testing dashboard

resource "aws_apigatewayv2_api" "url_testing" {
  name          = "reitsheet-url-testing-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["content-type", "authorization"]
    max_age       = 300
  }

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_api"
  }
}

# Stage (auto-deploy)
resource "aws_apigatewayv2_stage" "url_testing" {
  api_id      = aws_apigatewayv2_api.url_testing.id
  name        = "prod"
  auto_deploy = true

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_api"
  }
}

# Integration: GET /api/recent-urls
resource "aws_apigatewayv2_integration" "get_recent_urls" {
  api_id                 = aws_apigatewayv2_api.url_testing.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.url_testing_get_urls.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "get_recent_urls" {
  api_id    = aws_apigatewayv2_api.url_testing.id
  route_key = "GET /api/recent-urls"
  target    = "integrations/${aws_apigatewayv2_integration.get_recent_urls.id}"
}

# Integration: POST /api/comments
resource "aws_apigatewayv2_integration" "submit_comment" {
  api_id                 = aws_apigatewayv2_api.url_testing.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.url_testing_comments.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "submit_comment" {
  api_id    = aws_apigatewayv2_api.url_testing.id
  route_key = "POST /api/comments"
  target    = "integrations/${aws_apigatewayv2_integration.submit_comment.id}"
}

# Integration: GET /api/comments (debugging)
resource "aws_apigatewayv2_integration" "get_comments" {
  api_id                 = aws_apigatewayv2_api.url_testing.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.url_testing_get_comments.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "get_comments" {
  api_id    = aws_apigatewayv2_api.url_testing.id
  route_key = "GET /api/comments"
  target    = "integrations/${aws_apigatewayv2_integration.get_comments.id}"
}

# Lambda permissions for API Gateway
resource "aws_lambda_permission" "api_gateway_get_urls" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.url_testing_get_urls.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.url_testing.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_gateway_comments" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.url_testing_comments.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.url_testing.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_gateway_get_comments" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.url_testing_get_comments.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.url_testing.execution_arn}/*/*"
}

# Integration: DELETE /api/press-release
resource "aws_apigatewayv2_integration" "delete_press_release" {
  api_id                 = aws_apigatewayv2_api.url_testing.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.url_testing_delete_press_release.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "delete_press_release" {
  api_id    = aws_apigatewayv2_api.url_testing.id
  route_key = "DELETE /api/press-release"
  target    = "integrations/${aws_apigatewayv2_integration.delete_press_release.id}"
}

resource "aws_lambda_permission" "api_gateway_delete_press_release" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.url_testing_delete_press_release.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.url_testing.execution_arn}/*/*"
}

# Integration: PUT /api/press-release
resource "aws_apigatewayv2_integration" "update_press_release" {
  api_id                 = aws_apigatewayv2_api.url_testing.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.url_testing_update_press_release.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "update_press_release" {
  api_id    = aws_apigatewayv2_api.url_testing.id
  route_key = "PUT /api/press-release"
  target    = "integrations/${aws_apigatewayv2_integration.update_press_release.id}"
}

resource "aws_lambda_permission" "api_gateway_update_press_release" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.url_testing_update_press_release.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.url_testing.execution_arn}/*/*"
}

# Integration: POST /api/press-release
resource "aws_apigatewayv2_integration" "add_press_release" {
  api_id                 = aws_apigatewayv2_api.url_testing.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.url_testing_add_press_release.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "add_press_release" {
  api_id    = aws_apigatewayv2_api.url_testing.id
  route_key = "POST /api/press-release"
  target    = "integrations/${aws_apigatewayv2_integration.add_press_release.id}"
}

resource "aws_lambda_permission" "api_gateway_add_press_release" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.url_testing_add_press_release.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.url_testing.execution_arn}/*/*"
}

# Integration: GET /api/companies
resource "aws_apigatewayv2_integration" "get_companies" {
  api_id                 = aws_apigatewayv2_api.url_testing.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.url_testing_get_companies.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "get_companies" {
  api_id    = aws_apigatewayv2_api.url_testing.id
  route_key = "GET /api/companies"
  target    = "integrations/${aws_apigatewayv2_integration.get_companies.id}"
}

resource "aws_lambda_permission" "api_gateway_get_companies" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.url_testing_get_companies.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.url_testing.execution_arn}/*/*"
}
