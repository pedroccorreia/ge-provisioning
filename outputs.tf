# NOTE: In order for this to work we will need it to be uncommented in the future.
# output "admin_group_emails" {
#   description = "Emails of the provisioned Administrator Google Groups per environment"
#   value       = { for k, v in googleworkspace_group.admins : k => v.email }
# }
# 
# output "user_group_emails" {
#   description = "Emails of the provisioned User Google Groups per environment"
#   value       = { for k, v in googleworkspace_group.users : k => v.email }
# }

output "data_connector_names" {
  description = "Full resource names of the provisioned Data Connectors per environment"
  value       = { for k, v in google_discovery_engine_data_connector.connectors : k => v.name }
}

output "search_engine_names" {
  description = "Full resource names of the provisioned Search Engines per environment"
  value       = { for k, v in google_discovery_engine_search_engine.engines : k => v.name }
}

output "project_ids" {
  description = "The project IDs of the created customer environment projects"
  value       = { for k, v in google_project.projects : k => v.project_id }
}


