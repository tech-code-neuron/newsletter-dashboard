# ============================================================================
# REIT Sheet - Terraform Outputs
# ============================================================================
# Displays important resource identifiers after deployment
# Use these values for testing, monitoring, and integration

# -----------------------------------------------------------------------------
# S3 Outputs
# -----------------------------------------------------------------------------

output "s3_bucket_name" {
  description = "S3 bucket name for email storage (use for testing: aws s3 ls s3://BUCKET_NAME/incoming/)"
  value       = aws_s3_bucket.email_ingest.id
}

output "s3_bucket_arn" {
  description = "S3 bucket ARN for IAM policies and CloudFormation"
  value       = aws_s3_bucket.email_ingest.arn
}

# -----------------------------------------------------------------------------
# SQS Outputs
# -----------------------------------------------------------------------------

output "parse_queue_url" {
  description = "Parse queue URL for sending messages (used by producer Lambda)"
  value       = aws_sqs_queue.email_parse.url
}

output "parse_queue_arn" {
  description = "Parse queue ARN for IAM policies and event source mappings"
  value       = aws_sqs_queue.email_parse.arn
}

output "scrape_queue_url" {
  description = "Scrape queue URL for sending messages (used by parser Lambda)"
  value       = aws_sqs_queue.scrape.url
}

output "scrape_queue_arn" {
  description = "Scrape queue ARN for IAM policies and event source mappings"
  value       = aws_sqs_queue.scrape.arn
}

output "parse_dlq_url" {
  description = "Parse DLQ URL for manual inspection of failed emails"
  value       = aws_sqs_queue.email_parse_dlq.url
}

output "scrape_dlq_url" {
  description = "Scrape DLQ URL for manual inspection of failed scraping jobs"
  value       = aws_sqs_queue.scrape_dlq.url
}

# -----------------------------------------------------------------------------
# DynamoDB Outputs
# -----------------------------------------------------------------------------

output "inbound_log_table" {
  description = "Inbound log table name (idempotency tracking)"
  value       = aws_dynamodb_table.inbound_log.name
}

output "inbound_log_table_arn" {
  description = "Inbound log table ARN for IAM policies"
  value       = aws_dynamodb_table.inbound_log.arn
}

output "reit_news_table" {
  description = "DEPRECATED: V1 table - use reit_news_v2_table_name instead"
  value       = "DEPRECATED-USE-V2"
}

output "reit_news_table_arn" {
  description = "DEPRECATED: V1 table - use reit_news_v2_table_arn instead"
  value       = "DEPRECATED-USE-V2"
}

# -----------------------------------------------------------------------------
# Lambda Outputs
# -----------------------------------------------------------------------------

output "producer_function_name" {
  description = "Producer Lambda function name (use for logs: aws logs tail /aws/lambda/FUNCTION_NAME)"
  value       = aws_lambda_function.producer.function_name
}

output "producer_function_arn" {
  description = "Producer Lambda function ARN for permissions and triggers"
  value       = aws_lambda_function.producer.arn
}

output "parser_function_name" {
  description = "Parser Lambda function name (use for logs: aws logs tail /aws/lambda/FUNCTION_NAME)"
  value       = aws_lambda_function.parser.function_name
}

output "parser_function_arn" {
  description = "Parser Lambda function ARN for permissions and triggers"
  value       = aws_lambda_function.parser.arn
}

output "scraper_function_name" {
  description = "Scraper Lambda function name (use for logs: aws logs tail /aws/lambda/FUNCTION_NAME)"
  value       = aws_lambda_function.scraper.function_name
}

output "scraper_function_arn" {
  description = "Scraper Lambda function ARN for permissions and triggers"
  value       = aws_lambda_function.scraper.arn
}

# -----------------------------------------------------------------------------
# IAM Outputs
# -----------------------------------------------------------------------------

output "lambda_role_arn" {
  description = "Lambda execution role ARN (used by all Lambda functions)"
  value       = aws_iam_role.lambda_role.arn
}

output "lambda_role_name" {
  description = "Lambda execution role name"
  value       = aws_iam_role.lambda_role.name
}

# -----------------------------------------------------------------------------
# CloudWatch Outputs
# -----------------------------------------------------------------------------

output "parse_dlq_alarm_name" {
  description = "Parse DLQ alarm name (monitors email parsing failures)"
  value       = aws_cloudwatch_metric_alarm.parse_dlq_alarm.alarm_name
}

output "scrape_dlq_alarm_name" {
  description = "Scrape DLQ alarm name (monitors web scraping failures)"
  value       = aws_cloudwatch_metric_alarm.scrape_dlq_alarm.alarm_name
}

output "producer_error_alarm_name" {
  description = "Producer Lambda error alarm name"
  value       = aws_cloudwatch_metric_alarm.producer_errors.alarm_name
}

# -----------------------------------------------------------------------------
# Monitoring Quick Commands
# -----------------------------------------------------------------------------

output "monitoring_commands" {
  description = "Useful AWS CLI commands for monitoring"
  value       = <<-EOT
    # View S3 emails
    aws s3 ls s3://${aws_s3_bucket.email_ingest.id}/incoming/

    # Check queue depths
    aws sqs get-queue-attributes --queue-url ${aws_sqs_queue.email_parse.url} --attribute-names ApproximateNumberOfMessages

    # View Lambda logs
    aws logs tail /aws/lambda/${aws_lambda_function.producer.function_name} --follow
    aws logs tail /aws/lambda/${aws_lambda_function.parser.function_name} --follow
    aws logs tail /aws/lambda/${aws_lambda_function.scraper.function_name} --follow

    # Query press releases
    aws dynamodb scan --table-name ${aws_dynamodb_table.reit_news_v2.name} --limit 10
  EOT
}

# -----------------------------------------------------------------------------
# URL Testing Dashboard Outputs
# -----------------------------------------------------------------------------

output "url_testing_dashboard_url" {
  description = "URL testing dashboard website URL (open on mobile to test press release URLs)"
  value       = "http://${aws_s3_bucket_website_configuration.url_testing.website_endpoint}"
}

output "url_testing_api_endpoint" {
  description = "URL testing API Gateway endpoint (used by dashboard frontend)"
  value       = aws_apigatewayv2_stage.url_testing.invoke_url
}

output "url_test_comments_table" {
  description = "URL test comments table name (stores bug reports from mobile)"
  value       = aws_dynamodb_table.url_test_comments.name
}

# -----------------------------------------------------------------------------
# Testing Quick Commands
# -----------------------------------------------------------------------------

output "testing_commands" {
  description = "Commands for testing the pipeline"
  value       = <<-EOT
    # Send test email to: alerts@${var.domain_name}
    # Then run:
    cd infrastructure && ./test-pipeline.sh

    # URL Testing Dashboard
    # Open on mobile: http://${aws_s3_bucket_website_configuration.url_testing.website_endpoint}

    # View comments:
    aws dynamodb scan --table-name ${aws_dynamodb_table.url_test_comments.name} --limit 10
  EOT
}
