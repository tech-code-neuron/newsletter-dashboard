# Lambda functions for URL testing dashboard API

# IAM role for URL testing Lambda functions
resource "aws_iam_role" "url_testing_lambda_role" {
  name = "url_testing_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# CloudWatch Logs policy
resource "aws_iam_role_policy_attachment" "url_testing_lambda_logs" {
  role       = aws_iam_role.url_testing_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB access policy
resource "aws_iam_role_policy" "url_testing_lambda_dynamodb" {
  name = "url_testing_lambda_dynamodb"
  role = aws_iam_role.url_testing_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:Query",
          "dynamodb:GetItem"
        ]
        Resource = [
          aws_dynamodb_table.reit_news_v2.arn,
          "${aws_dynamodb_table.reit_news_v2.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:Query",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.url_test_comments.arn,
          "${aws_dynamodb_table.url_test_comments.arn}/index/*"
        ]
      }
    ]
  })
}

# Package Lambda deployment (will be created manually or via script)
data "archive_file" "url_testing_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/url-testing-api"
  output_path = "${path.module}/../lambdas/url-testing-api.zip"
  excludes    = ["static", "*.zip", "__pycache__", "*.pyc"]
}

# Lambda function for getting recent URLs
resource "aws_lambda_function" "url_testing_get_urls" {
  filename         = data.archive_file.url_testing_lambda.output_path
  function_name    = "url-testing-get-urls"
  role             = aws_iam_role.url_testing_lambda_role.arn
  handler          = "handler.get_recent_urls"
  source_code_hash = data.archive_file.url_testing_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
      COMMENTS_TABLE  = aws_dynamodb_table.url_test_comments.name
      API_PASSWORD    = var.url_testing_password # Simple password auth for MVP
    }
  }

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_api"
  }
}

# Lambda function for submitting comments
resource "aws_lambda_function" "url_testing_comments" {
  filename         = data.archive_file.url_testing_lambda.output_path
  function_name    = "url-testing-submit-comment"
  role             = aws_iam_role.url_testing_lambda_role.arn
  handler          = "handler.submit_comment"
  source_code_hash = data.archive_file.url_testing_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
      COMMENTS_TABLE  = aws_dynamodb_table.url_test_comments.name
      API_PASSWORD    = var.url_testing_password # Simple password auth for MVP
    }
  }

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_api"
  }
}

# Lambda function for getting comments (debugging)
resource "aws_lambda_function" "url_testing_get_comments" {
  filename         = data.archive_file.url_testing_lambda.output_path
  function_name    = "url-testing-get-comments"
  role             = aws_iam_role.url_testing_lambda_role.arn
  handler          = "handler.get_comments"
  source_code_hash = data.archive_file.url_testing_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
      COMMENTS_TABLE  = aws_dynamodb_table.url_test_comments.name
      API_PASSWORD    = var.url_testing_password # Simple password auth for MVP
    }
  }

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_api"
  }
}

# Lambda function for adding press releases
resource "aws_lambda_function" "url_testing_add_press_release" {
  filename         = data.archive_file.url_testing_lambda.output_path
  function_name    = "url-testing-add-press-release"
  role             = aws_iam_role.url_testing_lambda_role.arn
  handler          = "handler.add_press_release"
  source_code_hash = data.archive_file.url_testing_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 256
  description      = "URL Testing Dashboard API - Manually adds press release to database with audit trail"

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
      COMMENTS_TABLE  = aws_dynamodb_table.url_test_comments.name
      API_PASSWORD    = var.url_testing_password # Simple password auth for MVP
    }
  }

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_api"
  }
}

# Lambda function for updating press releases
resource "aws_lambda_function" "url_testing_update_press_release" {
  filename         = data.archive_file.url_testing_lambda.output_path
  function_name    = "url-testing-update-press-release"
  role             = aws_iam_role.url_testing_lambda_role.arn
  handler          = "handler.update_press_release"
  source_code_hash = data.archive_file.url_testing_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 256
  description      = "URL Testing Dashboard API - Updates press release metadata, relevance, and categorization"

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
      COMMENTS_TABLE  = aws_dynamodb_table.url_test_comments.name
      API_PASSWORD    = var.url_testing_password # Simple password auth for MVP
    }
  }

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_api"
  }
}

# Lambda function for deleting press releases
resource "aws_lambda_function" "url_testing_delete_press_release" {
  filename         = data.archive_file.url_testing_lambda.output_path
  function_name    = "url-testing-delete-press-release"
  role             = aws_iam_role.url_testing_lambda_role.arn
  handler          = "handler.delete_press_release"
  source_code_hash = data.archive_file.url_testing_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 256
  description      = "URL Testing Dashboard API - Soft-deletes press release from database with audit trail"

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
      COMMENTS_TABLE  = aws_dynamodb_table.url_test_comments.name
      API_PASSWORD    = var.url_testing_password # Simple password auth for MVP
    }
  }

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_api"
  }
}

# Lambda function for getting companies
resource "aws_lambda_function" "url_testing_get_companies" {
  filename         = data.archive_file.url_testing_lambda.output_path
  function_name    = "url-testing-get-companies"
  role             = aws_iam_role.url_testing_lambda_role.arn
  handler          = "handler.get_companies"
  source_code_hash = data.archive_file.url_testing_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 256
  description      = "URL Testing Dashboard API - Returns list of all companies for autocomplete"

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
      COMMENTS_TABLE  = aws_dynamodb_table.url_test_comments.name
      API_PASSWORD    = var.url_testing_password # Simple password auth for MVP
    }
  }

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_api"
  }
}
