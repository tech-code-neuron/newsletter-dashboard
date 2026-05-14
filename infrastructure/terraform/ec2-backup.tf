# ============================================================================
# EC2 Backup - Daily EBS Snapshots via Data Lifecycle Manager
# ============================================================================
# Automated daily backups with 14-day retention
#
# Cost estimate: ~$0.05/GB/month for snapshot storage
#   - 20GB volume = ~$1/month (assuming ~50% change rate)

# -----------------------------------------------------------------------------
# IAM Role for DLM
# -----------------------------------------------------------------------------

resource "aws_iam_role" "dlm_lifecycle" {
  name = "${var.project_name}-dlm-lifecycle-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "dlm.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.iam_tags, {
    Name = "${var.project_name}-dlm-lifecycle-role"
  })
}

resource "aws_iam_role_policy" "dlm_lifecycle" {
  name = "${var.project_name}-dlm-lifecycle-policy"
  role = aws_iam_role.dlm_lifecycle.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateSnapshot",
          "ec2:CreateSnapshots",
          "ec2:DeleteSnapshot",
          "ec2:DescribeInstances",
          "ec2:DescribeVolumes",
          "ec2:DescribeSnapshots"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateTags"
        ]
        Resource = "arn:aws:ec2:*::snapshot/*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# DLM Lifecycle Policy - Daily Snapshots
# -----------------------------------------------------------------------------

resource "aws_dlm_lifecycle_policy" "flask_ec2_backup" {
  description        = "Daily backup of Flask EC2 instance"
  execution_role_arn = aws_iam_role.dlm_lifecycle.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["INSTANCE"]

    # Target instances with Backup=true tag
    target_tags = {
      Backup = "true"
    }

    schedule {
      name = "Daily snapshots"

      create_rule {
        # Run at 5 AM UTC (midnight EST / 1 AM EDT)
        cron_expression = "cron(0 5 * * ? *)"
      }

      retain_rule {
        count = 14  # Keep 14 daily snapshots
      }

      tags_to_add = {
        SnapshotCreator = "DLM"
        Project         = var.project_name
      }

      copy_tags = true
    }
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-flask-backup-policy"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "dlm_policy_arn" {
  description = "DLM lifecycle policy ARN"
  value       = aws_dlm_lifecycle_policy.flask_ec2_backup.arn
}
