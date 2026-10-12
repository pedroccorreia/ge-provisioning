provider "google" {
  user_project_override = true
  billing_project       = var.billing_project
}

data "external" "workspace_token" {
  program = [
    "python3",
    "${path.module}/get_workspace_token.py",
    "--sa", var.sa_email,
    "--admin", var.workspace_admin_email,
    "--scopes",
    "https://www.googleapis.com/auth/admin.directory.group",
    "https://www.googleapis.com/auth/admin.directory.group.member"
  ]
}

provider "googleworkspace" {
  customer_id  = var.workspace_customer_id
  access_token = data.external.workspace_token.result.token
}


