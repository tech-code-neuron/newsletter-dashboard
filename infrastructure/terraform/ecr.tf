# ============================================================================
# REIT Sheet - ECR (Elastic Container Registry)
# ============================================================================
# Container registry for Flask application images
#
# Resources:
#   - ECR repository for Flask app
#   - Lifecycle policy to limit stored images
#   - Image scanning for security

# -----------------------------------------------------------------------------
# ECR Repository
# -----------------------------------------------------------------------------

resource "aws_ecr_repository" "flask_app" {
  name                 = "${var.project_name}-flask-app"
  image_tag_mutability = "MUTABLE"

  # Enable image scanning on push for security
  image_scanning_configuration {
    scan_on_push = true
  }

  # Enable encryption at rest
  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(local.common_tags, {
    Name        = "${var.project_name}-flask-app"
    Description = "Container registry for Flask application"
    Service     = "container-registry"
  })
}

# -----------------------------------------------------------------------------
# Lifecycle Policy - Keep only last 10 images
# -----------------------------------------------------------------------------

resource "aws_ecr_lifecycle_policy" "flask_app" {
  repository = aws_ecr_repository.flask_app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "latest"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Remove untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "ecr_repository_url" {
  description = "ECR repository URL for Flask app"
  value       = aws_ecr_repository.flask_app.repository_url
}

output "ecr_repository_arn" {
  description = "ECR repository ARN"
  value       = aws_ecr_repository.flask_app.arn
}
