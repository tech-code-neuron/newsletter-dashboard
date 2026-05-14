# ============================================================================
# REIT Sheet - ECS Cluster
# ============================================================================
# ECS Fargate cluster for running containerized Flask application
#
# Cost: Minimal - cluster itself is free, you pay for tasks

# -----------------------------------------------------------------------------
# ECS Cluster
# -----------------------------------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  # Enable Container Insights for monitoring
  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(local.common_tags, {
    Name        = "${var.project_name}-cluster"
    Description = "ECS cluster for Flask application"
    Service     = "container-orchestration"
  })
}

# -----------------------------------------------------------------------------
# Cluster Capacity Providers
# -----------------------------------------------------------------------------

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  # Use FARGATE_SPOT by default for cost savings (~70% cheaper)
  # Falls back to FARGATE if spot unavailable
  default_capacity_provider_strategy {
    base              = 1
    weight            = 1
    capacity_provider = "FARGATE_SPOT"
  }
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group for ECS
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "ecs_flask" {
  name              = "/ecs/${var.project_name}-flask-app"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name        = "ECS-Flask-App-Logs"
    Description = "Container logs for Flask application"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "ecs_cluster_id" {
  description = "ECS cluster ID"
  value       = aws_ecs_cluster.main.id
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}
