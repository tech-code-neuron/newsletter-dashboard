# DynamoDB table for URL testing comments
# Stores user feedback about busted URLs from the mobile testing dashboard

resource "aws_dynamodb_table" "url_test_comments" {
  name         = "url_test_comments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "comment_id"

  attribute {
    name = "comment_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  # GSI for querying open comments (used by debugging/admin interface)
  global_secondary_index {
    name            = "status-created-index"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  tags = {
    Project = "reitsheet"
    Purpose = "url_testing_comments"
  }
}
