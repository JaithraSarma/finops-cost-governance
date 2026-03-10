# ─────────────────────────────────────────────────────────────
# Variables for FinOps Cost Governance Infrastructure
# ─────────────────────────────────────────────────────────────

variable "project_name" {
  description = "Short name used as prefix for all resources"
  type        = string
  default     = "finops"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus2"
}

variable "tags" {
  description = "Default tags applied to every resource"
  type        = map(string)
  default = {
    project     = "finops-cost-governance"
    owner       = "platform-engineering"
    managed-by  = "terraform"
  }
}

# ── Budget thresholds ──────────────────────────────────────

variable "daily_budget_limit" {
  description = "Daily cost budget in USD"
  type        = number
  default     = 500
}

variable "monthly_budget_limit" {
  description = "Monthly cost budget in USD"
  type        = number
  default     = 15000
}

variable "cost_anomaly_threshold_percent" {
  description = "% daily cost increase to trigger anomaly alert"
  type        = number
  default     = 20
}

# ── Notification channels ─────────────────────────────────

variable "slack_webhook_url" {
  description = "Slack incoming webhook URL for cost alerts"
  type        = string
  default     = ""
  sensitive   = true
}

variable "teams_webhook_url" {
  description = "Microsoft Teams webhook URL for cost alerts"
  type        = string
  default     = ""
  sensitive   = true
}
