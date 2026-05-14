# ============================================================================
# REIT Sheet - EC2 Flask Application
# ============================================================================
# EC2 instance for running Flask application (replacing ECS Fargate)
#
# Benefits over ECS:
#   - 5-second deploys (git pull + restart) vs 3-5 minute Docker builds
#   - Direct SSH access for debugging
#   - Lower cost (~$8/month vs ~$25/month)
#
# Cost estimate: ~$7-8/month (t3.micro)

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "flask_ec2_instance_type" {
  description = "EC2 instance type for Flask app"
  type        = string
  default     = "t3.micro"
}

variable "flask_ec2_key_name" {
  description = "SSH key pair name for EC2 access"
  type        = string
  default     = "reitsheet-flask"
}

variable "admin_ssh_cidr" {
  description = "CIDR block for SSH access (your IP). Find your IP with: curl ifconfig.me"
  type        = string
  # No default - must be provided via terraform.tfvars for security
  # Example: admin_ssh_cidr = "203.0.113.45/32"
}

# -----------------------------------------------------------------------------
# Latest Ubuntu 24.04 LTS AMI
# -----------------------------------------------------------------------------

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# -----------------------------------------------------------------------------
# EC2 Security Group
# -----------------------------------------------------------------------------

resource "aws_security_group" "flask_ec2" {
  name        = "${var.project_name}-flask-ec2-sg"
  description = "Security group for Flask EC2 instance"
  vpc_id      = aws_vpc.main.id

  # Allow inbound from ALB on port 5001
  ingress {
    from_port       = 5001
    to_port         = 5001
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
    description     = "Allow traffic from ALB"
  }

  # Allow SSH access (restrict to your IP in production)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_ssh_cidr]
    description = "SSH access"
  }

  # Allow all outbound (for AWS API calls, pip install, etc.)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-flask-ec2-sg"
  })
}

# -----------------------------------------------------------------------------
# IAM Role for EC2
# -----------------------------------------------------------------------------
# Same permissions as ECS task role, but for EC2

resource "aws_iam_role" "flask_ec2" {
  name        = "${var.project_name}-flask-ec2-role"
  description = "IAM role for Flask EC2 instance"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.iam_tags, {
    Name     = "${var.project_name}-flask-ec2-role"
    RoleType = "ec2-instance-role"
  })
}

resource "aws_iam_instance_profile" "flask_ec2" {
  name = "${var.project_name}-flask-ec2-profile"
  role = aws_iam_role.flask_ec2.name

  tags = merge(local.iam_tags, {
    Name = "${var.project_name}-flask-ec2-profile"
  })
}

# EC2 role policy - same as ECS task role
resource "aws_iam_role_policy" "flask_ec2" {
  name = "${var.project_name}-flask-ec2-policy"
  role = aws_iam_role.flask_ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # DynamoDB - Full access to REIT tables
      {
        Sid    = "DynamoDBTableAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeTable",
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          # Press releases table (used by publisher for marking items as published)
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/reitsheet-press-releases",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/reitsheet-press-releases/index/*",
          aws_dynamodb_table.reit_news_v2.arn,
          "${aws_dynamodb_table.reit_news_v2.arn}/index/*",
          aws_dynamodb_table.companies_config.arn,
          "${aws_dynamodb_table.companies_config.arn}/index/*",
          aws_dynamodb_table.url_test_comments.arn,
          "${aws_dynamodb_table.url_test_comments.arn}/index/*",
          aws_dynamodb_table.press_release_audit.arn,
          "${aws_dynamodb_table.press_release_audit.arn}/index/*",
          aws_dynamodb_table.newsletters.arn,
          "${aws_dynamodb_table.newsletters.arn}/index/*",
          aws_dynamodb_table.review_emails.arn,
          "${aws_dynamodb_table.review_emails.arn}/index/*",
          aws_dynamodb_table.relevance_decisions.arn,
          "${aws_dynamodb_table.relevance_decisions.arn}/index/*",
          aws_dynamodb_table.app_settings.arn,
          "${aws_dynamodb_table.app_settings.arn}/index/*",
          aws_dynamodb_table.email_tracking.arn,
          "${aws_dynamodb_table.email_tracking.arn}/index/*",
          aws_dynamodb_table.sec_8k_disclosures.arn,
          "${aws_dynamodb_table.sec_8k_disclosures.arn}/index/*",
          aws_dynamodb_table.subscribers.arn,
          "${aws_dynamodb_table.subscribers.arn}/index/*",
          aws_dynamodb_table.subscriber_engagement.arn,
          "${aws_dynamodb_table.subscriber_engagement.arn}/index/*",
          aws_dynamodb_table.campaigns.arn,
          "${aws_dynamodb_table.campaigns.arn}/index/*",
          aws_dynamodb_table.email_events.arn,
          "${aws_dynamodb_table.email_events.arn}/index/*",
          aws_dynamodb_table.newsletter_editions.arn,
          "${aws_dynamodb_table.newsletter_editions.arn}/index/*",
          # Site Editor config tables
          aws_dynamodb_table.site_editor_config.arn,
          "${aws_dynamodb_table.site_editor_config.arn}/index/*",
          aws_dynamodb_table.site_editor_versions.arn,
          "${aws_dynamodb_table.site_editor_versions.arn}/index/*"
        ]
      },

      # S3 - Read emails for review
      {
        Sid    = "S3EmailReadAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.email_ingest.arn,
          "${aws_s3_bucket.email_ingest.arn}/*"
        ]
      },

      # S3 - Write to homepage bucket for publishing
      {
        Sid    = "S3HomepageWriteAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = [
          aws_s3_bucket.homepage.arn,
          "${aws_s3_bucket.homepage.arn}/*"
        ]
      },

      # CloudWatch - Write application metrics and logs
      {
        Sid    = "CloudWatchAccess"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "*"
      },

      # Secrets Manager - Read Flask and Cognito secrets
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.flask_secrets.arn,
          aws_secretsmanager_secret.cognito_config.arn
        ]
      },

      # SES - Send emails from publisher
      {
        Sid    = "SESsendEmail"
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      },

      # CloudFront - Update archive redirect function
      {
        Sid    = "CloudFrontFunctionUpdate"
        Effect = "Allow"
        Action = [
          "cloudfront:DescribeFunction",
          "cloudfront:UpdateFunction",
          "cloudfront:PublishFunction"
        ]
        Resource = "arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:function/reitsheet-archive-redirect"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# EC2 Instance
# -----------------------------------------------------------------------------

resource "aws_instance" "flask_app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.flask_ec2_instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.flask_ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.flask_ec2.name
  key_name               = var.flask_ec2_key_name

  # Enable detailed monitoring (optional, costs extra)
  monitoring = false

  # Root volume
  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true

    tags = merge(local.common_tags, {
      Name = "${var.project_name}-flask-ec2-root"
    })
  }

  # User data to set up the instance
  user_data = base64encode(<<-EOF
    #!/bin/bash
    set -e

    # Log to file for debugging
    exec > >(tee /var/log/user-data.log) 2>&1
    echo "Starting user data script at $(date)"

    # Update system
    apt-get update
    apt-get upgrade -y

    # Add deadsnakes PPA for Python 3.11
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update

    # Install Python 3.11 and dependencies
    apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip git

    # Create app directory
    mkdir -p /home/ubuntu/reit-newsletter
    chown ubuntu:ubuntu /home/ubuntu/reit-newsletter

    echo "User data script completed at $(date)"
    echo "Ready for manual setup - see /home/ubuntu/SETUP_INSTRUCTIONS.md"

    # Create setup instructions
    cat > /home/ubuntu/SETUP_INSTRUCTIONS.md << 'SETUP'
    # Flask App Setup Instructions

    ## 1. Clone the repository
    cd /home/ubuntu
    git clone https://github.com/YOUR_USER/reit-newsletter.git
    cd reit-newsletter/infrastructure/docker/flask-app

    ## 2. Create virtual environment
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt gunicorn boto3

    ## 3. Test the app (no .env file needed - uses Secrets Manager)
    IS_ECS=true AWS_REGION=us-east-1 gunicorn --bind 0.0.0.0:5001 app:app

    ## 4. Enable systemd service
    sudo systemctl enable flask-app
    sudo systemctl start flask-app
    sudo systemctl status flask-app
    SETUP
    chown ubuntu:ubuntu /home/ubuntu/SETUP_INSTRUCTIONS.md

    # Create systemd service file
    # IMPORTANT: Sets IS_ECS=true to force Secrets Manager usage (no .env file needed)
    cat > /etc/systemd/system/flask-app.service << 'SYSTEMD'
    [Unit]
    Description=REIT Newsletter Flask App
    After=network.target

    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/reit-newsletter/infrastructure/docker/flask-app
    Environment="IS_ECS=true"
    Environment="AWS_REGION=us-east-1"
    Environment="APP_BASE_URL=https://app.reitsheet.co"
    Environment="COMPANIES_TABLE=reitsheet-companies-config"
    Environment="REIT_NEWS_TABLE=reitsheet-reit-news-v2"
    ExecStart=/home/ubuntu/reit-newsletter/infrastructure/docker/flask-app/venv/bin/gunicorn \
      --bind 0.0.0.0:5001 --workers 2 --threads 4 --timeout 120 app:app
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    SYSTEMD

    systemctl daemon-reload
  EOF
  )

  tags = merge(local.common_tags, {
    Name        = "${var.project_name}-flask-app"
    Description = "Flask application EC2 instance"
    Backup      = "true"  # Enables DLM daily snapshots (see ec2-backup.tf)
  })

  lifecycle {
    # Prevent accidental destruction
    prevent_destroy = false

    # Ignore changes to user_data and ami after initial creation
    # ami: Prevents EC2 replacement when Canonical releases new Ubuntu AMIs
    ignore_changes = [user_data, ami]
  }
}

# -----------------------------------------------------------------------------
# Elastic IP (Optional - uncomment if you want a static IP)
# -----------------------------------------------------------------------------
# Cost: ~$3.65/month if instance is stopped, free when attached and running

# resource "aws_eip" "flask_app" {
#   instance = aws_instance.flask_app.id
#   domain   = "vpc"
#
#   tags = merge(local.common_tags, {
#     Name = "${var.project_name}-flask-eip"
#   })
# }

# -----------------------------------------------------------------------------
# Target Group for EC2 (Instance Type)
# -----------------------------------------------------------------------------
# New target group for EC2 - ALB listener will be updated to use this

resource "aws_lb_target_group" "flask_ec2" {
  name        = "${var.project_name}-flask-ec2-tg"
  port        = 5001
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 3
  }

  # Deregistration delay
  deregistration_delay = 30

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-flask-ec2-tg"
  })
}

# Attach EC2 instance to target group
resource "aws_lb_target_group_attachment" "flask_ec2" {
  target_group_arn = aws_lb_target_group.flask_ec2.arn
  target_id        = aws_instance.flask_app.id
  port             = 5001
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group for EC2 App Logs (Optional)
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "flask_ec2" {
  name              = "/ec2/${var.project_name}/flask-app"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name        = "${var.project_name}-flask-ec2-logs"
    Description = "Flask EC2 application logs"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "flask_ec2_instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.flask_app.id
}

output "flask_ec2_public_ip" {
  description = "EC2 public IP address"
  value       = aws_instance.flask_app.public_ip
}

output "flask_ec2_public_dns" {
  description = "EC2 public DNS name"
  value       = aws_instance.flask_app.public_dns
}

output "flask_ec2_target_group_arn" {
  description = "EC2 target group ARN"
  value       = aws_lb_target_group.flask_ec2.arn
}

output "flask_ec2_ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh -i ~/.ssh/${var.flask_ec2_key_name}.pem ubuntu@${aws_instance.flask_app.public_ip}"
}
