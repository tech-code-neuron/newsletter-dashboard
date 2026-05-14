# DynamoDB table to track forwarded emails (prevent duplicates)
resource "aws_dynamodb_table" "forward_log" {
  name         = "reitsheet-forward-log"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "message_id"

  attribute {
    name = "message_id"
    type = "S"
  }

  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  tags = {
    Name        = "reitsheet-forward-log"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Grant Lambda access to forward log
resource "aws_iam_policy" "forward_log_access" {
  name        = "reitsheet-forward-log-access"
  description = "Allow Lambda to read/write forward log"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.forward_log.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_forward_log" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.forward_log_access.arn
}

output "forward_log_table_name" {
  value       = aws_dynamodb_table.forward_log.name
  description = "DynamoDB table tracking forwarded emails"
}

output "forward_log_table_arn" {
  value       = aws_dynamodb_table.forward_log.arn
  description = "ARN of forward log table"
}
