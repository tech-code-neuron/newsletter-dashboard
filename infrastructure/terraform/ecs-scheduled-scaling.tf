# ============================================================================
# REIT Sheet - ECS Scheduled Scaling
# ============================================================================
# Scale ECS service to 0 during off-hours to save costs
#
# Schedule (EST/EDT):
#   - Scale DOWN to 0: 11 PM (23:00)
#   - Scale UP to 1: 7 AM (07:00)
#
# Savings: ~33% of ECS costs (8 hours/day off)
#
# Cost: Free (EventBridge Scheduler)

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "ecs_scale_down_schedule" {
  description = "Cron expression for scaling down (ET)"
  type        = string
  default     = "cron(0 0 * * ? *)" # 12:00 AM ET
}

variable "ecs_scale_up_schedule" {
  description = "Cron expression for scaling up (ET)"
  type        = string
  default     = "cron(45 5 * * ? *)" # 5:45 AM ET (ready for 6 AM press releases)
}

variable "enable_scheduled_scaling" {
  description = "Enable scheduled scaling (set to false to keep service always running)"
  type        = bool
  default     = true
}

# -----------------------------------------------------------------------------
# IAM Role for EventBridge Scheduler
# -----------------------------------------------------------------------------

resource "aws_iam_role" "eventbridge_scheduler" {
  count = var.enable_scheduled_scaling ? 1 : 0
  name  = "${var.project_name}-eventbridge-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.iam_tags, {
    Name = "${var.project_name}-eventbridge-scheduler-role"
  })
}

resource "aws_iam_role_policy" "eventbridge_scheduler" {
  count = var.enable_scheduled_scaling ? 1 : 0
  name  = "${var.project_name}-eventbridge-scheduler-policy"
  role  = aws_iam_role.eventbridge_scheduler[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECSUpdateService"
        Effect = "Allow"
        Action = [
          "ecs:UpdateService"
        ]
        Resource = aws_ecs_service.flask_app.id
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# EventBridge Scheduler - Scale Down
# -----------------------------------------------------------------------------

resource "aws_scheduler_schedule" "ecs_scale_down" {
  count = var.enable_scheduled_scaling ? 1 : 0
  name  = "${var.project_name}-ecs-scale-down"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.ecs_scale_down_schedule
  schedule_expression_timezone = "America/New_York"

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ecs:updateService"
    role_arn = aws_iam_role.eventbridge_scheduler[0].arn

    input = jsonencode({
      Cluster      = aws_ecs_cluster.main.name
      Service      = aws_ecs_service.flask_app.name
      DesiredCount = 0
    })
  }

  state = "ENABLED"
}

# -----------------------------------------------------------------------------
# EventBridge Scheduler - Scale Up
# -----------------------------------------------------------------------------

resource "aws_scheduler_schedule" "ecs_scale_up" {
  count = var.enable_scheduled_scaling ? 1 : 0
  name  = "${var.project_name}-ecs-scale-up"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.ecs_scale_up_schedule
  schedule_expression_timezone = "America/New_York"

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ecs:updateService"
    role_arn = aws_iam_role.eventbridge_scheduler[0].arn

    input = jsonencode({
      Cluster      = aws_ecs_cluster.main.name
      Service      = aws_ecs_service.flask_app.name
      DesiredCount = 1
    })
  }

  state = "ENABLED"
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "scheduled_scaling_enabled" {
  description = "Whether scheduled scaling is enabled"
  value       = var.enable_scheduled_scaling
}

output "scale_down_schedule" {
  description = "Schedule for scaling down (cron expression)"
  value       = var.enable_scheduled_scaling ? var.ecs_scale_down_schedule : "N/A (disabled)"
}

output "scale_up_schedule" {
  description = "Schedule for scaling up (cron expression)"
  value       = var.enable_scheduled_scaling ? var.ecs_scale_up_schedule : "N/A (disabled)"
}
