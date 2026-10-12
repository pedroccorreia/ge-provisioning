# Locals to construct environment details, services, and connectors
locals {
  environment_details = {
    "non-prod" = {
      display_name = "Non-Prod"
    }
    "prod" = {
      display_name = "Prod"
    }
  }

  environments = {
    for env in var.environments : env => {
      display_name = lookup(local.environment_details, env, { display_name = title(env) }).display_name
      project_id   = "${var.project_id_prefix}${var.customer_id}-${env}"
    }
  }

  # Map of all services that need to be enabled per customer environment project
  project_services = merge([
    for env_key, env_val in local.environments : {
      for svc in [
        "discoveryengine.googleapis.com",
        "cloudidentity.googleapis.com",
        "admin.googleapis.com",
        "gmail.googleapis.com",
        "calendar-json.googleapis.com",
        "iamcredentials.googleapis.com",
        "iam.googleapis.com"
      ] : "${env_key}-${svc}" => {
        project_id = google_project.projects[env_key].project_id
        service    = svc
      }
    }
  ]...)

  # Map of all connector types per customer environment project
  environment_connectors = merge([
    for env_key, env_val in local.environments : {
      for type in ["gmail", "calendar"] :
      "${env_key}-${type}" => {
        env_key      = env_key
        type         = type
        data_source  = type == "gmail" ? "google_mail" : "google_calendar"
        display_name = type == "gmail" ? "Gmail" : "Google Calendar"
        project_id   = google_project.projects[env_key].project_id
      }
    }
  ]...)
}

# 0. Provision GCP Projects per Customer Environment
resource "google_project" "projects" {
  for_each        = local.environments
  name            = substr("${var.customer_name} ${each.value.display_name}", 0, 30)
  project_id      = each.value.project_id
  folder_id       = var.folder_id
  org_id          = var.folder_id == null ? var.org_id : null
  billing_account = var.billing_account
}

# 1. Enable GCP Services per Customer Environment Project
resource "google_project_service" "services" {
  for_each           = local.project_services
  project            = each.value.project_id
  service            = each.value.service
  disable_on_destroy = false
}

# 1.5 IAM bindings & IdP settings for Discovery Engine
resource "google_project_iam_member" "sa_discoveryengine_admin" {
  for_each = local.environments
  project  = google_project.projects[each.key].project_id
  role     = "roles/discoveryengine.admin"
  member   = "serviceAccount:${var.sa_email}"
}

resource "null_resource" "configure_idp" {
  for_each = local.environments

  triggers = {
    project_id = google_project.projects[each.key].project_id
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/configure_discovery_engine_idp.py --project ${google_project.projects[each.key].project_id} --sa ${var.sa_email}"
  }

  depends_on = [
    google_project_service.services,
    google_project_iam_member.sa_discoveryengine_admin
  ]
}

# 2. Provision Google Workspace Customer Environment Groups
# NOTE: In order for this to work we will need it to be uncommented in the future.
# resource "googleworkspace_group" "admins" {
#   for_each    = local.environments
#   email       = "${var.customer_id}-${each.key}-admins@${var.company_domain}"
#   name        = "${var.customer_name} (${each.value.display_name}) Admins"
#   description = "Administrators for ${var.customer_name} ${each.value.display_name} environment using Gemini Enterprise."
# }
# 
# resource "googleworkspace_group" "users" {
#   for_each    = local.environments
#   email       = "${var.customer_id}-${each.key}-users@${var.company_domain}"
#   name        = "${var.customer_name} (${each.value.display_name}) Users"
#   description = "Standard users for ${var.customer_name} ${each.value.display_name} environment using Gemini Enterprise."
# }
# 
# # IAM Member bindings for Admin Groups (roles/discoveryengine.admin)
# resource "google_project_iam_member" "group_admins" {
#   for_each = local.environments
#   project  = google_project.projects[each.key].project_id
#   role     = "roles/discoveryengine.admin"
#   member   = "group:${googleworkspace_group.admins[each.key].email}"
# }
# 
# # IAM Member bindings for Standard User Groups (roles/discoveryengine.user)
# resource "google_project_iam_member" "group_users" {
#   for_each = local.environments
#   project  = google_project.projects[each.key].project_id
#   role     = "roles/discoveryengine.user"
#   member   = "group:${googleworkspace_group.users[each.key].email}"
# }

# 3. Provision Gmail & Calendar Data Connectors per Customer Environment Project
resource "google_discovery_engine_data_connector" "connectors" {
  for_each                = local.environment_connectors
  project                 = each.value.project_id
  location                = var.location
  collection_id           = "${each.value.type}-collection"
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
    null_resource.configure_idp
  ]
}

# 5. Provision 1 Unified Gemini Enterprise Search App per Customer Environment Project
resource "google_discovery_engine_search_engine" "engines" {
  for_each          = local.environments
  project           = google_project.projects[each.key].project_id
  location          = var.location
  collection_id     = "default_collection"
  engine_id         = "${var.customer_id}-${each.key}-search-engine"
  display_name      = "${var.customer_name} (${each.value.display_name}) Search App"
  industry_vertical = "GENERIC"
  app_type          = "APP_TYPE_INTRANET"

  data_store_ids = [
    basename(google_discovery_engine_data_connector.connectors["${each.key}-gmail"].entities[0].data_store),
    basename(google_discovery_engine_data_connector.connectors["${each.key}-calendar"].entities[0].data_store)
  ]

  search_engine_config {
    search_tier    = "SEARCH_TIER_STANDARD"
    search_add_ons = ["SEARCH_ADD_ON_LLM"]
  }

  depends_on = [
    google_discovery_engine_data_connector.connectors
  ]
}

