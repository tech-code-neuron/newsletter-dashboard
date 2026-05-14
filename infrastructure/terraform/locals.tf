# ============================================================================
# REIT Sheet - Local Values
# ============================================================================
# Computed values and common configurations used across resources

# -----------------------------------------------------------------------------
# Common Tags
# -----------------------------------------------------------------------------
# These tags are applied to ALL resources for:
# - Cost tracking and allocation
# - Resource organization and filtering
# - Compliance and governance
# - Operational clarity

locals {
  common_tags = {
    # Core identification
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Owner       = "reitsheet"

    # Purpose and context
    Application = "reit-newsletter-automation"
    Purpose     = "press-release-automation"

    # Cost and compliance
    CostCenter = "reit-newsletter"
    Compliance = "personal-project"

    # Operational metadata
    Repository         = "github-tech-code-neuron-newsletter-dashboard"
    TerraformWorkspace = terraform.workspace
    DeployedBy         = "claude-code"

    # Contact and support
    Contact = "alerts-reitsheet-co"

    # Note: LastUpdated tag removed - timestamp() prevents imports and causes drift
  }

  # Resource-specific tag generators
  lambda_tags = merge(local.common_tags, {
    ResourceType = "lambda"
    Service      = "compute"
  })

  storage_tags = merge(local.common_tags, {
    ResourceType = "storage"
    Service      = "data-storage"
  })

  queue_tags = merge(local.common_tags, {
    ResourceType = "queue"
    Service      = "messaging"
  })

  database_tags = merge(local.common_tags, {
    ResourceType = "database"
    Service      = "data-persistence"
  })

  monitoring_tags = merge(local.common_tags, {
    ResourceType = "monitoring"
    Service      = "observability"
  })

  iam_tags = merge(local.common_tags, {
    ResourceType = "iam"
    Service      = "security"
  })
}

# -----------------------------------------------------------------------------
# Computed Resource Names
# -----------------------------------------------------------------------------

locals {
  # S3
  s3_bucket_name = "${var.project_name}-email-ingest"

  # SQS
  parse_queue_name          = "${var.project_name}-email-parse-queue"
  parse_dlq_name            = "${var.project_name}-email-parse-dlq"
  scrape_queue_name         = "${var.project_name}-scrape-queue"
  scrape_dlq_name           = "${var.project_name}-scrape-dlq"
  playwright_queue_name     = "${var.project_name}-playwright-scraper-queue"
  playwright_dlq_name       = "${var.project_name}-playwright-scraper-dlq"
  simple_scraper_queue_name = "${var.project_name}-simple-scraper-queue"
  simple_scraper_dlq_name   = "${var.project_name}-simple-scraper-dlq"

  # DynamoDB
  inbound_log_table = "${var.project_name}-inbound-log"
  reit_news_table   = "${var.project_name}-reit-news"

  # Lambda
  producer_function           = "${var.project_name}-producer"
  parser_function             = "${var.project_name}-parser"
  enricher_function           = "${var.project_name}-enricher"
  scraper_function            = "${var.project_name}-scraper"
  playwright_scraper_function = "${var.project_name}-playwright-scraper"
  simple_scraper_function     = "${var.project_name}-simple-scraper"
  scraper_router_function     = "${var.project_name}-scraper-router"

  # IAM
  lambda_role_name   = "${var.project_name}-lambda-role"
  lambda_policy_name = "${var.project_name}-lambda-policy"

  # CloudWatch
  parse_dlq_alarm  = "${var.project_name}-parse-dlq-alarm"
  scrape_dlq_alarm = "${var.project_name}-scrape-dlq-alarm"
}
