terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "6.14.1" }
  }
  backend "s3" {}
}
provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = ["524097108092"]
}
variable "monthly_limit_usd" {
  type        = number
  description = "Recurring account-wide monthly allowance in USD, confirmed by the owner."
  default     = 50
  validation {
    condition     = var.monthly_limit_usd > 0
    error_message = "Provide a positive, separately approved USD budget amount."
  }
}
variable "notification_email" {
  type = string
  validation {
    condition     = can(regex("^[^@ ]+@[^@ ]+\\.[^@ ]+$", var.notification_email))
    error_message = "Provide a notification email, not a secret."
  }
}
resource "aws_budgets_budget" "account" {
  name              = "My Monthly Cost Budget"
  budget_type       = "COST"
  limit_amount      = tostring(var.monthly_limit_usd)
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "2026-05-01_00:00"
  time_period_end   = "2087-06-15_00:00"
  cost_types {
    include_credit             = false
    include_refund             = false
    include_tax                = true
    include_support            = true
    include_discount           = true
    include_subscription       = true
    include_other_subscription = true
    include_upfront            = true
    include_recurring          = true
    use_blended                = false
    use_amortized              = false
  }
  dynamic "notification" {
    for_each = toset([50, 80, 100])
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.notification_email]
    }
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.notification_email]
  }
  lifecycle { prevent_destroy = true }
}
