# ============================================================================
# REIT Sheet - ECS Service & Task Definition
# ============================================================================
# ECS Fargate service for running Flask application
#
# Cost estimate: ~$9/month (0.25 vCPU, 0.5GB RAM, FARGATE_SPOT)

# -----------------------------------------------------------------------------
# Variables for ECS Configuration
# -----------------------------------------------------------------------------

variable "flask_cpu" {
  description = "CPU units for Flask container (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "flask_memory" {
  description = "Memory in MB for Flask container"
  type        = number
  default     = 512
}

variable "flask_desired_count" {
  description = "Desired number of Flask tasks"
  type        = number
  default     = 1
}

# -----------------------------------------------------------------------------
# Task Definition
# -----------------------------------------------------------------------------

resource "aws_ecs_task_definition" "flask_app" {
  family                   = "${var.project_name}-flask-app"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.flask_cpu
  memory                   = var.flask_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "flask-app"
      image     = "${aws_ecr_repository.flask_app.repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = 5001
          hostPort      = 5001
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "FLASK_ENV"
          value = "production"
        },
        {
          name  = "IS_ECS"
          value = "true"
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "REIT_NEWS_TABLE"
          value = aws_dynamodb_table.reit_news_v2.name
        },
        {
          name  = "COMPANIES_TABLE"
          value = aws_dynamodb_table.companies_config.name
        },
        {
          name  = "APP_BASE_URL"
          value = "https://app.reitsheet.co"
        }
      ]

      secrets = [
        {
          name      = "FLASK_SECRET_KEY"
          valueFrom = "${aws_secretsmanager_secret.flask_secrets.arn}:FLASK_SECRET_KEY::"
        },
        {
          name      = "GMAIL_CREDENTIALS"
          valueFrom = "${aws_secretsmanager_secret.flask_secrets.arn}:GMAIL_CREDENTIALS::"
        },
        {
          name      = "ANTHROPIC_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.flask_secrets.arn}:ANTHROPIC_API_KEY::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_flask.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "flask"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/health')\" || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = merge(local.common_tags, {
    Name        = "${var.project_name}-flask-app-task"
    Description = "Task definition for Flask application"
  })
}

# -----------------------------------------------------------------------------
# ECS Service
# -----------------------------------------------------------------------------

resource "aws_ecs_service" "flask_app" {
  name            = "${var.project_name}-flask-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.flask_app.arn
  desired_count   = var.use_ec2_backend ? 0 : var.flask_desired_count
  # Using capacity_provider_strategy instead of launch_type for FARGATE_SPOT

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  dynamic "load_balancer" {
    for_each = var.use_ec2_backend ? [] : [1]
    content {
      target_group_arn = aws_lb_target_group.flask.arn
      container_name   = "flask-app"
      container_port   = 5001
    }
  }

  # Allow service to start even if no healthy instances yet
  health_check_grace_period_seconds = 60

  # Ensure new task starts before old one stops
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  # Enable ECS managed tags
  enable_ecs_managed_tags = true
  propagate_tags          = "TASK_DEFINITION"

  # Use capacity provider strategy for FARGATE_SPOT
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
    base              = 1
  }

  tags = merge(local.common_tags, {
    Name        = "${var.project_name}-flask-service"
    Description = "ECS service for Flask application"
  })

  depends_on = [
    aws_lb_listener.http
  ]

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# -----------------------------------------------------------------------------
# Security Group for ECS Tasks
# -----------------------------------------------------------------------------

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "Security group for ECS Flask tasks"
  vpc_id      = aws_vpc.main.id

  # Allow inbound from ALB only
  ingress {
    from_port       = 5001
    to_port         = 5001
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
    description     = "Allow traffic from ALB"
  }

  # Allow all outbound (for AWS API calls, external requests)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-ecs-tasks-sg"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.flask_app.name
}

output "ecs_task_definition_arn" {
  description = "ECS task definition ARN"
  value       = aws_ecs_task_definition.flask_app.arn
}
