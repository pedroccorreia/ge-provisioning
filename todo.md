# Gemini Enterprise Deployment Checklist

This checklist tracks the end-to-end deployment stages for provisioning Gemini Enterprise across customer environments.

## Stage 1: Foundation Infrastructure
- [ ] Configure `terraform.tfvars` from `terraform.tfvars.example` with customer identifiers and billing details.
- [ ] Ensure `enable_connectors = false` for initial foundation deployment.
- [ ] Run `terraform init` and `terraform apply` to provision:
  - Environment GCP Projects
  - Required GCP APIs (`discoveryengine`, `cloudidentity`, `gmail`, `calendar-json`, `drive`, `chat`)
  - Discovery Engine Service Agent identity (`google_project_service_identity`)
  - Location Identity Provider configured to `GSUITE` (`google_discovery_engine_acl_config`)
  - Cloud Identity User Groups (`google_cloud_identity_group`)
  - User Store with auto-registration enabled (`google_discovery_engine_user_store`)
  - Automatic generation of `config/license_allocations.json`

## Stage 2: Workspace Admin Domain-Wide Delegation (DWD)
- [ ] Run `terraform output dwd_checklist` to display service agent details and OAuth scopes.
- [ ] Open the Google Workspace Admin Console: [API Controls > Domain-Wide Delegation](https://admin.google.com/ac/owl/domainwidedelegation).
- [ ] Click **Add new** API client:
  - **Client ID**: Service Agent Email (`service-<PROJECT_NUMBER>@gcp-sa-discoveryengine.iam.gserviceaccount.com`)
  - **OAuth Scopes**: Copy and paste the comma-separated scopes from `oauth_scopes_csv` output:
    - `https://www.googleapis.com/auth/admin.directory.user.readonly`
    - `https://www.googleapis.com/auth/admin.directory.group.readonly`
    - `https://www.googleapis.com/auth/admin.directory.group.member.readonly`
    - `https://www.googleapis.com/auth/gmail.readonly`
    - `https://www.googleapis.com/auth/calendar.readonly`
    - `https://www.googleapis.com/auth/drive.readonly`
    - `https://www.googleapis.com/auth/chat.spaces.readonly`
    - `https://www.googleapis.com/auth/chat.messages.readonly`
    - `https://www.googleapis.com/auth/chat.memberships.readonly`
  - Click **Authorize**.
- [ ] In the Workspace Admin Console, allow the GCP Project IDs to access Workspace data if prompted.

## Stage 3: Workspace Connectors & Gemini Enterprise Engines
- [ ] Enable connectors by setting `enable_connectors = true` in `terraform.tfvars` (or `-var="enable_connectors=true"`).
- [ ] Run `terraform apply` to provision:
  - Federated Data Connectors (`google_mail`, `google_calendar`, `google_drive`, `google_chat`)
  - Unified Search Engine (`google_discovery_engine_search_engine`)
  - Governed Assistant (`google_discovery_engine_assistant`)
  - Engine IAM bindings for user groups (`roles/discoveryengine.user`)

## Stage 4: License Distribution & Auto-Registration
- [ ] Distribute seats from Cloud Billing Account pool to target projects:
  ```bash
  python3 scripts/allocate_licenses.py --distribute
  ```
- [ ] If not already configured by Terraform, verify auto-registration:
  ```bash
  python3 scripts/allocate_licenses.py --configure-auto-register
  ```

## Stage 5: Verification & End-User Access
- [ ] Run the end-to-end verification script:
  ```bash
  python3 scripts/verify.py
  ```
- [ ] Add pilot users to the provisioned Cloud Identity user group (`<customer_id>-<env>-users@<domain>`).
- [ ] Test end-user search and assistant access via the Vertex AI Search application console.
