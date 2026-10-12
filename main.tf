# 0. Provision GCP Projects per Affiliate
resource "google_project" "projects" {
  for_each        = var.affiliates
  name            = "${each.value.name} Gemini Project"
  project_id      = "${var.project_id_prefix}${each.key}"
  folder_id       = var.folder_id
  org_id          = var.folder_id == null ? var.org_id : null
  billing_account = var.billing_account
}

# Locals to flatten services and connectors per affiliate project
locals {
  # Map of all services that need to be enabled per affiliate project
  project_services = merge([
    for aff_key, aff_val in var.affiliates : {
      for svc in [
        "discoveryengine.googleapis.com",
        "cloudidentity.googleapis.com",
        "admin.googleapis.com",
        "gmail.googleapis.com",
        "calendar-json.googleapis.com",
        "iamcredentials.googleapis.com",
        "iam.googleapis.com"
      ] : "${aff_key}-${svc}" => {
        project_id = google_project.projects[aff_key].project_id
        service    = svc
      }
    }
  ]...)

  # Map of all connector types per affiliate project
  affiliate_connectors = merge([
    for aff_key, aff_val in var.affiliates : {
      for type in ["gmail", "calendar"] :
      "${aff_key}-${type}" => {
        affiliate_key = aff_key
        type          = type
        data_source   = type == "gmail" ? "google_mail" : "google_calendar"
        display_name  = type == "gmail" ? "Gmail" : "Google Calendar"
        project_id    = google_project.projects[aff_key].project_id
      }
    }
  ]...)
}

# 1. Enable GCP Services per Affiliate Project
resource "google_project_service" "services" {
  for_each           = local.project_services
  project            = each.value.project_id
  service            = each.value.service
  disable_on_destroy = false
}

# 1.5 IAM bindings & IdP settings for Discovery Engine
resource "google_project_iam_member" "sa_discoveryengine_admin" {
  for_each = var.affiliates
  project  = google_project.projects[each.key].project_id
  role     = "roles/discoveryengine.admin"
  member   = "serviceAccount:${var.sa_email}"
}

resource "null_resource" "configure_idp" {
  for_each = var.affiliates

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

# 2. Provision Google Workspace Affiliate Groups
# NOTE: In order for this to work we will need it to be uncommented in the future.
# resource "googleworkspace_group" "admins" {
#   for_each    = var.affiliates
#   email       = "${each.key}-admins@${var.company_domain}"
#   name        = "${each.value.name} Admins"
#   description = "Administrators for the ${each.value.name} (${each.value.region}) affiliate using Gemini Enterprise."
# }
# 
# resource "googleworkspace_group" "users" {
#   for_each    = var.affiliates
#   email       = "${each.key}-users@${var.company_domain}"
#   name        = "${each.value.name} Users"
#   description = "Standard users for the ${each.value.name} (${each.value.region}) affiliate using Gemini Enterprise."
# }
# 
# # IAM Member bindings for Affiliate Admin Groups (roles/discoveryengine.admin)
# resource "google_project_iam_member" "group_admins" {
#   for_each = var.affiliates
#   project  = google_project.projects[each.key].project_id
#   role     = "roles/discoveryengine.admin"
#   member   = "group:${googleworkspace_group.admins[each.key].email}"
# }
# 
# # IAM Member bindings for Affiliate Standard User Groups (roles/discoveryengine.user)
# resource "google_project_iam_member" "group_users" {
#   for_each = var.affiliates
#   project  = google_project.projects[each.key].project_id
#   role     = "roles/discoveryengine.user"
#   member   = "group:${googleworkspace_group.users[each.key].email}"
# }

# 3. Provision Gmail & Calendar Data Connectors per Affiliate Project
resource "google_discovery_engine_data_connector" "connectors" {
  for_each                = local.affiliate_connectors
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

# 5. Provision 1 Unified Gemini Enterprise Search App per Affiliate Project
resource "google_discovery_engine_search_engine" "engines" {
  for_each          = var.affiliates
  project           = google_project.projects[each.key].project_id
  location          = var.location
  collection_id     = "default_collection"
  engine_id         = "${each.key}-search-engine"
  display_name      = "${each.value.name} Search App"
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
