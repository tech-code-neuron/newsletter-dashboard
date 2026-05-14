# ============================================================================
# REIT Sheet - AWS Cognito Authentication
# ============================================================================
# Google OAuth authentication via Cognito User Pool
#
# Access levels:
#   - Admin: Full access (scrape, edit, delete) - whitelisted emails
#   - Viewer: Read-only (view URLs, press releases) - whitelisted emails
#   - Public: Newsletter archive only (future)
#
# Cost: Free (Cognito free tier: 50,000 MAUs)

# -----------------------------------------------------------------------------
# Variables for Cognito Configuration
# -----------------------------------------------------------------------------

variable "cognito_callback_urls" {
  description = "Allowed callback URLs after authentication"
  type        = list(string)
  default = [
    "https://app.reitsheet.co/auth/callback"
  ]
}

variable "cognito_logout_urls" {
  description = "Allowed logout redirect URLs"
  type        = list(string)
  default = [
    "https://app.reitsheet.co/",
    "https://app.reitsheet.co/logged-out"
  ]
}

variable "google_client_id" {
  description = "Google OAuth Client ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "google_client_secret" {
  description = "Google OAuth Client Secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "admin_emails" {
  description = "List of email addresses with admin access"
  type        = list(string)
  default     = []
}

variable "viewer_emails" {
  description = "List of email addresses with viewer access"
  type        = list(string)
  default     = []
}

# -----------------------------------------------------------------------------
# Cognito User Pool
# -----------------------------------------------------------------------------

resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-user-pool"

  # Use email as username
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Password policy (SECURITY: Require strong passwords if email/password auth added)
  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true # SECURITY: Require special characters for stronger passwords
    require_uppercase = true
  }

  # Schema - email is required
  schema {
    attribute_data_type = "String"
    name                = "email"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  # Account recovery via email
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Admin create user config
  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  tags = merge(local.common_tags, {
    Name        = "${var.project_name}-user-pool"
    Description = "Cognito User Pool for authentication"
    Service     = "authentication"
  })
}

# -----------------------------------------------------------------------------
# Cognito User Pool Domain
# -----------------------------------------------------------------------------

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-auth"
  user_pool_id = aws_cognito_user_pool.main.id
}

# -----------------------------------------------------------------------------
# Google Identity Provider
# -----------------------------------------------------------------------------

resource "aws_cognito_identity_provider" "google" {
  count = var.google_client_id != "" ? 1 : 0

  user_pool_id  = aws_cognito_user_pool.main.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    client_id                     = var.google_client_id
    client_secret                 = var.google_client_secret
    authorize_scopes              = "email profile openid"
    attributes_url                = "https://people.googleapis.com/v1/people/me?personFields="
    attributes_url_add_attributes = "true"
    authorize_url                 = "https://accounts.google.com/o/oauth2/v2/auth"
    oidc_issuer                   = "https://accounts.google.com"
    token_request_method          = "POST"
    token_url                     = "https://www.googleapis.com/oauth2/v4/token"
  }

  attribute_mapping = {
    email    = "email"
    username = "sub"
    name     = "name"
    picture  = "picture"
  }
}

# -----------------------------------------------------------------------------
# Cognito User Pool Client
# -----------------------------------------------------------------------------

resource "aws_cognito_user_pool_client" "flask_app" {
  name         = "${var.project_name}-flask-client"
  user_pool_id = aws_cognito_user_pool.main.id

  # OAuth configuration
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  callback_urls                        = var.cognito_callback_urls
  logout_urls                          = var.cognito_logout_urls
  supported_identity_providers         = var.google_client_id != "" ? ["COGNITO", "Google"] : ["COGNITO"]

  # Generate client secret
  generate_secret = true

  # Token validity (SECURITY: Shorter refresh tokens limit token theft window)
  access_token_validity  = 1 # 1 hour
  id_token_validity      = 1 # 1 hour
  refresh_token_validity = 7 # 7 days (reduced from 30 for security)

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # Prevent user existence errors
  prevent_user_existence_errors = "ENABLED"

  # Enable token revocation
  enable_token_revocation = true

  depends_on = [
    aws_cognito_identity_provider.google
  ]
}

# -----------------------------------------------------------------------------
# Admin Users Group
# -----------------------------------------------------------------------------

resource "aws_cognito_user_group" "admins" {
  name         = "admins"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Administrators with full access"
  precedence   = 1
}

# -----------------------------------------------------------------------------
# Viewer Users Group
# -----------------------------------------------------------------------------

resource "aws_cognito_user_group" "viewers" {
  name         = "viewers"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Viewers with read-only access"
  precedence   = 10
}

# -----------------------------------------------------------------------------
# Store Cognito Configuration in Secrets Manager
# -----------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "cognito_config" {
  name        = "${var.project_name}/cognito/config"
  description = "Cognito configuration for Flask app"

  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    Name    = "${var.project_name}-cognito-config"
    Service = "secrets-management"
  })
}

resource "aws_secretsmanager_secret_version" "cognito_config" {
  secret_id = aws_secretsmanager_secret.cognito_config.id
  secret_string = jsonencode({
    user_pool_id  = aws_cognito_user_pool.main.id
    client_id     = aws_cognito_user_pool_client.flask_app.id
    client_secret = aws_cognito_user_pool_client.flask_app.client_secret
    domain        = "${var.project_name}-auth.auth.${var.aws_region}.amazoncognito.com"
    region        = var.aws_region
    admin_emails  = var.admin_emails
    viewer_emails = var.viewer_emails
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.flask_app.id
}

output "cognito_domain" {
  description = "Cognito hosted UI domain"
  value       = "https://${var.project_name}-auth.auth.${var.aws_region}.amazoncognito.com"
}

output "cognito_login_url" {
  description = "URL for Cognito hosted login"
  value       = "https://${var.project_name}-auth.auth.${var.aws_region}.amazoncognito.com/login?client_id=${aws_cognito_user_pool_client.flask_app.id}&response_type=code&scope=email+openid+profile&redirect_uri=${urlencode(var.cognito_callback_urls[0])}"
}
