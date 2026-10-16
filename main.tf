# Locals to construct environment details, services, and connectors
locals {
  environment_details = {
    "non-prod" = { display_name = "Non-Production" }
    "prod"     = { display_name = "Production" }
    "dev"      = { display_name = "Development" }
    "pilot"    = { display_name = "Pilot" }
    "staging"  = { display_name = "Staging" }
  }

  environments = {
    for env in var.environments : env => {
      display_name = lookup(local.environment_details, env, { display_name = title(replace(env, "-", " ")) }).display_name
      project_id   = "${var.project_id_prefix}${var.customer_id}-${env}"
      seat_count   = lookup(var.seat_allocations, env, 0)
    }
  }

  connector_meta = {
    "google_mail" = {
      display_name = "Gmail"
      service      = "gmail.googleapis.com"
      collection   = "gmail-collection"
    }
    "google_calendar" = {
      display_name = "Google Calendar"
      service      = "calendar-json.googleapis.com"
      collection   = "calendar-collection"
    }
    "google_drive" = {
      display_name = "Google Drive"
      service      = "drive.googleapis.com"
      collection   = "drive-collection"
    }
    "google_chat" = {
      display_name = "Google Chat"
      service      = "chat.googleapis.com"
      collection   = "chat-collection"
    }
  }

  # Map of all services that need to be enabled per customer environment project
  base_services = [
    "discoveryengine.googleapis.com",
    "cloudidentity.googleapis.com",
    "admin.googleapis.com",
    "gmail.googleapis.com",
    "calendar-json.googleapis.com",
    "drive.googleapis.com",
    "chat.googleapis.com",
    "iamcredentials.googleapis.com",
    "iam.googleapis.com"
  ]

  project_services = merge([
    for env_key, env_val in local.environments : {
      for svc in local.base_services : "${env_key}-${svc}" => {
        project_id = google_project.projects[env_key].project_id
        service    = svc
      }
    }
  ]...)

  # Workspace connectors per environment (when enabled)
  environment_connectors = var.enable_connectors ? {
    for pair in setproduct(keys(local.environments), tolist(var.workspace_connectors)) :
    "${pair[0]}-${pair[1]}" => {
      env_key       = pair[0]
      connector     = pair[1]
      data_source   = pair[1]
      display_name  = lookup(local.connector_meta, pair[1], { display_name = title(replace(pair[1], "_", " ")), service = "", collection = "${replace(pair[1], "_", "-")}-collection" }).display_name
      collection_id = lookup(local.connector_meta, pair[1], { display_name = "", service = "", collection = "${replace(pair[1], "_", "-")}-collection" }).collection
      project_id    = google_project.projects[pair[0]].project_id
    }
  } : {}

  # Domain-Wide Delegation OAuth scopes required for Workspace connectors & user directory
  dwd_scopes = [
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/admin.directory.group.readonly",
    "https://www.googleapis.com/auth/admin.directory.group.member.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.memberships.readonly"
  ]
}

# 0. Provision GCP Projects per Customer Environment
resource "google_project" "projects" {
  for_each        = local.environments
  name            = substr("${var.customer_name} ${each.value.display_name}", 0, 30)
  project_id      = each.value.project_id
  folder_id       = var.folder_id
  org_id          = var.folder_id == null ? var.org_id : null
  billing_account = var.billing_account
  deletion_policy = contains(["prod", "production"], lower(each.key)) ? "PREVENT" : "DELETE"
}

# 1. Enable GCP Services per Customer Environment Project
resource "google_project_service" "services" {
  for_each           = local.project_services
  project            = each.value.project_id
  service            = each.value.service
  disable_on_destroy = false
}

# 1.5 Pre-create Discovery Engine Service Agent Identity
resource "google_project_service_identity" "discoveryengine_sa" {
  provider = google-beta
  for_each = local.environments
  project  = google_project.projects[each.key].project_id
  service  = "discoveryengine.googleapis.com"

  depends_on = [google_project_service.services]
}

# Optional Provisioner Service Account IAM binding
resource "google_project_iam_member" "sa_discoveryengine_admin" {
  for_each = var.sa_email != null ? local.environments : {}
  project  = google_project.projects[each.key].project_id
  role     = "roles/discoveryengine.admin"
  member   = "serviceAccount:${var.sa_email}"

  depends_on = [google_project_service.services]
}

# 2. Configure Discovery Engine Location Identity Provider (GSuite IdP)
resource "google_discovery_engine_acl_config" "idp" {
  for_each = local.environments
  project  = google_project.projects[each.key].project_id
  location = var.location

  idp_config {
    idp_type = "GSUITE"
  }

  depends_on = [
    google_project_service.services,
    google_project_service_identity.discoveryengine_sa
  ]
}

# 3. Provision Cloud Identity User Groups
resource "google_cloud_identity_group" "users" {
  for_each     = local.environments
  display_name = "${var.customer_name} (${each.value.display_name}) Users"
  parent       = "customers/${var.workspace_customer_id}"

  group_key {
    id = "${var.customer_id}-${each.key}-users@${var.company_domain}"
  }

  labels = {
    "cloudidentity.googleapis.com/groups.discussion_forum" = ""
  }

  depends_on = [google_project_service.services]
}

# 4. Provision Discovery Engine User Store with Auto-Registration
resource "google_discovery_engine_user_store" "default" {
  for_each                           = local.environments
  project                            = google_project.projects[each.key].project_id
  location                           = var.location
  user_store_id                      = "default_user_store"
  default_license_config             = lookup(var.license_config_names, each.key, null)
  enable_license_auto_register       = lookup(var.license_config_names, each.key, null) != null
  enable_expired_license_auto_update = lookup(var.license_config_names, each.key, null) != null

  depends_on = [
    google_project_service.services,
    google_discovery_engine_acl_config.idp
  ]
}

# 5. Provision Workspace Data Connectors per Customer Environment Project (Staged)
resource "google_discovery_engine_data_connector" "connectors" {
  for_each                = local.environment_connectors
  project                 = each.value.project_id
  location                = var.location
  collection_id           = each.value.collection_id
  collection_display_name = "${each.value.display_name} Collection"
  data_source             = each.value.data_source
  params                  = {}
  refresh_interval        = "0s"
  connector_modes         = ["FEDERATED"]

  entities {
    entity_name = each.value.data_source
  }

  depends_on = [
    google_project_service.services,
    google_discovery_engine_acl_config.idp,
    google_project_service_identity.discoveryengine_sa
  ]
}

# 6. Provision Unified Gemini Enterprise Search App per Customer Environment Project
resource "google_discovery_engine_search_engine" "engines" {
  for_each          = var.enable_connectors ? local.environments : {}
  project           = google_project.projects[each.key].project_id
  location          = var.location
  collection_id     = "default_collection"
  engine_id         = "${var.customer_id}-${each.key}-search-engine"
  display_name      = "${var.customer_name} (${each.value.display_name}) Search App"
  industry_vertical = "GENERIC"
  app_type          = "APP_TYPE_INTRANET"

  data_store_ids = [
    for connector_type in var.workspace_connectors :
    basename(google_discovery_engine_data_connector.connectors["${each.key}-${connector_type}"].entities[0].data_store)
  ]

  search_engine_config {
    search_tier    = "SEARCH_TIER_STANDARD"
    search_add_ons = ["SEARCH_ADD_ON_LLM"]
  }

  depends_on = [
    google_discovery_engine_data_connector.connectors
  ]
}

# 7. Grant End-User Search Access Scoped to the Engine
resource "google_discovery_engine_search_engine_iam_member" "users" {
  for_each      = var.enable_connectors ? local.environments : {}
  project       = google_project.projects[each.key].project_id
  location      = var.location
  collection_id = google_discovery_engine_search_engine.engines[each.key].collection_id
  engine_id     = google_discovery_engine_search_engine.engines[each.key].engine_id
  role          = "roles/discoveryengine.user"
  member        = "group:${google_cloud_identity_group.users[each.key].group_key[0].id}"
}

# 8. Provision Governed Gemini Enterprise Assistant
resource "google_discovery_engine_assistant" "default" {
  for_each           = var.enable_connectors ? local.environments : {}
  project            = google_project.projects[each.key].project_id
  location           = var.location
  collection_id      = google_discovery_engine_search_engine.engines[each.key].collection_id
  engine_id          = google_discovery_engine_search_engine.engines[each.key].engine_id
  assistant_id       = "default_assistant"
  display_name       = "${var.customer_name} Assistant"
  web_grounding_type = "WEB_GROUNDING_TYPE_GOOGLE_SEARCH"

  generation_config {
    default_language = "en"
    system_instruction {
      additional_system_instruction = var.assistant_instructions
    }
  }

  depends_on = [
    google_discovery_engine_search_engine.engines
  ]
}

# 9. Emit License Allocations Configuration as Single Source of Truth
resource "local_file" "license_allocations" {
  filename = "${path.module}/config/license_allocations.json"
  content = jsonencode({
    licensing_project = coalesce(var.billing_project, try(values(google_project.projects)[0].project_id, ""))
    billing_account   = var.billing_account
    license_config_id = var.license_config_id
    subscription_id   = var.subscription_id
    subscription_tier = var.subscription_tier
    location          = var.location
    allocations = [
      for k, env in local.environments : {
        project_id       = google_project.projects[k].project_id
        project_number   = google_project.projects[k].number
        environment      = k
        environment_name = env.display_name
        seat_count       = env.seat_count
        status           = "active"
      }
    ]
  })
}
