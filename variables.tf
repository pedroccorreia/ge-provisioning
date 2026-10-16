variable "project_id_prefix" {
  type        = string
  description = "An optional prefix to prepend to each customer project ID to ensure global uniqueness"
  default     = ""
}

variable "customer_id" {
  type        = string
  description = "Short identifier/slug for the customer (used in project IDs and resource names, e.g. acme)"
}

variable "customer_name" {
  type        = string
  description = "The human-readable display name of the customer (e.g. Acme Corp)"
}

variable "environments" {
  type        = set(string)
  description = "Configurable list/set of environments to provision for the customer (e.g. ['non-prod', 'prod'] or ['dev', 'pilot', 'prod'])"
  default     = ["non-prod", "prod"]

  validation {
    condition     = length(var.environments) > 0
    error_message = "At least one environment must be specified in var.environments."
  }
}

variable "location" {
  type        = string
  description = "The location for the Discovery Engine resources (e.g., global, us, eu)"
  default     = "global"
}

variable "company_domain" {
  type        = string
  description = "The primary domain name for the Google Workspace tenant (e.g., example.com)"
}

variable "workspace_customer_id" {
  type        = string
  description = "The Google Workspace Customer ID (e.g., C01234567)"
}

variable "workspace_admin_email" {
  type        = string
  description = "The email address of a Google Workspace Administrator (optional)"
  default     = null
}

variable "folder_id" {
  type        = string
  description = "The ID of the GCP Folder where the projects should be created (optional)"
  default     = null
}

variable "org_id" {
  type        = string
  description = "The ID of the GCP Organization where the projects should be created (optional, if not using a folder)"
  default     = null
}

variable "billing_account" {
  type        = string
  description = "The billing account ID to associate with the created projects"
}

variable "billing_project" {
  type        = string
  description = "The GCP project ID to use for API quota and billing overrides"
  default     = null
}

variable "sa_email" {
  type        = string
  description = "The email address of the GCP service account used for provisioning (optional)"
  default     = null
}

variable "workspace_connectors" {
  type        = set(string)
  description = "Set of Google Workspace connector types to provision (e.g. google_mail, google_calendar, google_drive, google_chat)"
  default     = ["google_mail", "google_calendar", "google_drive", "google_chat"]
}

variable "enable_connectors" {
  type        = bool
  description = "Whether to provision Discovery Engine Workspace data connectors. Set to false for initial foundation apply, then true after Domain-Wide Delegation is authorized."
  default     = false
}

variable "assistant_instructions" {
  type        = string
  description = "System instruction / prompt preamble for the Gemini Enterprise assistant"
  default     = "You are an enterprise AI assistant helping employees find information across Google Workspace and internal knowledge bases. Provide accurate, helpful, and concise answers based on available enterprise data."
}

variable "seat_allocations" {
  type        = map(number)
  description = "Map of environment names to seat counts allocated (e.g. { prod = 4, non-prod = 1 })"
  default = {
    prod     = 4
    non-prod = 1
  }
}

variable "license_config_names" {
  type        = map(string)
  description = "Optional map of environment name to full license config resource name (e.g. projects/{project}/locations/{location}/licenseConfigs/{id})"
  default     = {}
}

variable "license_config_id" {
  type        = string
  description = "The Billing Account License Config ID for Gemini Enterprise"
  default     = ""
}

variable "subscription_id" {
  type        = string
  description = "The Gemini Enterprise subscription ID"
  default     = ""
}

variable "subscription_tier" {
  type        = string
  description = "The Gemini Enterprise subscription tier"
  default     = "Gemini Enterprise Standard"
}
