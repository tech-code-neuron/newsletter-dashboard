# ============================================================================
# REIT Sheet - Secrets Manager
# ============================================================================
# Secure storage for sensitive configuration
#
# Secrets stored:
#   - FLASK_SECRET_KEY: Session encryption key
#   - GMAIL_CREDENTIALS: Gmail API credentials JSON
#   - ANTHROPIC_API_KEY: Claude API key
#
# Cost: ~$2/month (per secret + API calls)

# -----------------------------------------------------------------------------
# Flask Secrets
# -----------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "flask_secrets" {
  name        = "${var.project_name}/flask-app/secrets"
  description = "Secrets for REIT Newsletter Flask application"

  # Allow recovery for 7 days (minimum)
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    Name        = "${var.project_name}-flask-secrets"
    Description = "Flask application secrets"
    Service     = "secrets-management"
  })
}

# -----------------------------------------------------------------------------
# Initial Secret Value (placeholder - update via CLI after creation)
# -----------------------------------------------------------------------------
#
# After terraform apply, update secrets with:
#
# aws secretsmanager put-secret-value \
#   --secret-id reitsheet/flask-app/secrets \
#   --secret-string '{
#     "FLASK_SECRET_KEY": "your-secure-random-key",
#     "GMAIL_CREDENTIALS": "{...gmail json...}",
#     "ANTHROPIC_API_KEY": "sk-ant-..."
#   }'

resource "aws_secretsmanager_secret_version" "flask_secrets" {
  secret_id = aws_secretsmanager_secret.flask_secrets.id
  secret_string = jsonencode({
    FLASK_SECRET_KEY  = "PLACEHOLDER_CHANGE_ME_AFTER_DEPLOY"
    GMAIL_CREDENTIALS = "{}"
    ANTHROPIC_API_KEY = "PLACEHOLDER_CHANGE_ME_AFTER_DEPLOY"
  })

  lifecycle {
    # Don't overwrite manually-set secrets
    ignore_changes = [secret_string]
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "flask_secrets_arn" {
  description = "ARN of Flask secrets"
  value       = aws_secretsmanager_secret.flask_secrets.arn
}

output "flask_secrets_name" {
  description = "Name of Flask secrets"
  value       = aws_secretsmanager_secret.flask_secrets.name
}
