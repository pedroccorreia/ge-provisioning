# Gemini Enterprise Affiliate Provisioning IaC

This repository contains the Terraform Infrastructure as Code (IaC) configuration to set up Gemini Enterprise integration (Vertex AI Search) with Google Workspace Gmail and Google Calendar connectors, alongside Google Workspace Groups for Australian affiliates.

## Architecture Overview

- **GCP Projects**: 7 separate projects (one per affiliate) containing Vertex AI Search collections, connectors, and apps.
- **Affiliate Groups**: 7 Australian real estate affiliate groups (Admins and Users) prefixed with `rwg-` (e.g. `rwg-toorak-users`).

---

## Prerequisites

Before running the Terraform deployment, ensure you have completed the following setup:

### 1. Google Cloud Platform (GCP)
- A GCP project ID with billing enabled.
- Your user or service account must have permissions to enable APIs and manage Vertex AI Search (Discovery Engine) resources.

### 2. Google Workspace
- A Google Workspace domain (e.g. `example.com`) and Customer ID (e.g. `C01234567`).
- A Workspace administrator account.
- **Domain-Wide Delegation**: You must set up a Service Account in the GCP Console and grant it Domain-Wide Delegation in the Google Workspace Admin console with the following OAuth scopes:
  - `https://www.googleapis.com/auth/admin.directory.group`
  - `https://www.googleapis.com/auth/admin.directory.group.member`

---

## Configuration Variables

Create a `terraform.tfvars` file to configure your deployment values:

```hcl
project_id_prefix      = "mycompany-" # Optional prefix for project IDs
billing_account        = "012345-6789AB-CDEF01" # Mandatory billing account ID
folder_id              = "12345678901" # Optional GCP folder ID to place projects under
org_id                 = "98765432109" # Optional GCP organization ID (if folder_id is null)
company_domain         = "your-workspace-domain.com"
workspace_customer_id  = "C01234567"
workspace_admin_email  = "admin-impersonator@your-workspace-domain.com"
```

*Note: `workspace_admin_email` is the email address of a Workspace administrator that the service account will impersonate to manage the groups.*

---

## Deployment Steps

### 1. Authenticate with Google Cloud
Ensure your local terminal is authenticated with your GCP account:
```bash
gcloud auth application-default login
```

### 2. Set Google Workspace Credentials
Expose the path to your service account key file (with domain-wide delegation enabled) as an environment variable so the `googleworkspace` provider can authenticate:
```bash
export GOOGLEWORKSPACE_CREDENTIALS="/path/to/your/service-account-key.json"
```

### 3. Initialize Terraform
Initialize the working directory and install the required providers (`google`, `googleworkspace`, `null`):
```bash
terraform init
```

### 4. Plan the Deployment
Run a dry-run to see exactly what resources will be created:
```bash
terraform plan
```

### 5. Apply the Changes
Apply the configuration to provision the groups, connectors, and search engines:
```bash
terraform apply
```

---

## Post-Deployment Actions

To complete the setup and make the Gemini Enterprise search active:
1. **Workspace Project Authorization**: In the Google Workspace Admin Console, authorize the GCP Project ID to access your Workspace data.
2. **Add Group Members**: Add affiliate employees and administrators to their respective `rwg-*-users` and `rwg-*-admins` Google Groups.
3. **Assign Licenses**: Assign Gemini Enterprise licenses using the automated allocation script (`scripts/allocate_licenses.py`).

---

## Gemini Enterprise License Allocation & Distribution

Licenses are provisioned centrally at the **Cloud Billing Account** level (`0111AA-12FED7-0F6152`) and distributed to affiliate project numbers via automated API workflows.

### 1. Configure Seat Distribution
Edit [`config/license_allocations.json`](file:///Users/pcorreia/dev/ge/affiliate-provisioning/config/license_allocations.json) to set your billing account, subscription license config ID, and quota distribution per project:

```json
{
  "billing_account": "0111AA-12FED7-0F6152",
  "license_config_id": "ca1a2f23-797f-4cf7-ab6f-74fd5f3ca651",
  "subscription_id": "05eab18d-9cd5-4ba6-966f-ff796c7d27a8",
  "subscription_tier": "Gemini Enterprise Standard",
  "location": "global",
  "allocations": [
    {
      "project_id": "rwg-double-bay",
      "project_number": "1067043213672",
      "affiliate_name": "Double Bay",
      "seat_count": 1,
      "status": "active"
    }
  ]
}
```

### 2. Distribute Seats to Projects
Preview and execute the distribution of subscription quota from the Billing Account to project numbers:

```bash
# Dry run
python3 scripts/allocate_licenses.py --distribute --dry-run

# Execute distribution
python3 scripts/allocate_licenses.py --distribute
```

### 3. Configure Auto-Registration on User Login
Configure each target project's `default_user_store` to automatically bind users to its local distributed license on first login:

```bash
# Dry run
python3 scripts/allocate_licenses.py --configure-auto-register --dry-run

# Apply configuration
python3 scripts/allocate_licenses.py --configure-auto-register
```

### 4. Verify Active Allocations
Check the active license configs and assigned quota across all affiliate projects:

```bash
python3 scripts/allocate_licenses.py --list
```


