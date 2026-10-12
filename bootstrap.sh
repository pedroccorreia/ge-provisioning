#!/bin/bash
set -e

# Load configurations
BOOTSTRAP_PROJECT="${BOOTSTRAP_PROJECT:-affiliates-bootstrap}"
SA_NAME="gemini-provisioner"
SA_EMAIL="${SA_NAME}@${BOOTSTRAP_PROJECT}.iam.gserviceaccount.com"

echo "=== Stage 1: Creating GCP Service Account ==="
if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project "${BOOTSTRAP_PROJECT}" &>/dev/null; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Gemini IaC Provisioner" \
    --project "${BOOTSTRAP_PROJECT}"
  echo "Service account created."
else
  echo "Service account already exists."
fi

echo "=== Stage 2: Granting IAM Roles to User ==="
ACTIVE_USER=$(gcloud config get-value account)
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --member="user:${ACTIVE_USER}" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --project "${BOOTSTRAP_PROJECT}" --quiet

echo "=== Stage 3: Fetching Unique Client ID for Domain-Wide Delegation ==="
CLIENT_ID=$(gcloud iam service-accounts describe "${SA_EMAIL}" \
  --project "${BOOTSTRAP_PROJECT}" \
  --format="value(uniqueId)")

echo ""
echo "=========================================================================="
echo "ACTION REQUIRED: Configure Google Workspace Domain-Wide Delegation"
echo "=========================================================================="
echo "1. Open the Google Workspace Admin Console:"
echo "   https://admin.google.com/ac/owl/domainwidedelegation"
echo "2. Click 'Add new'."
echo "3. Enter the Client ID:"
echo "   ${CLIENT_ID}"
echo "4. Under 'OAuth Scopes', copy and paste the following comma-separated list:"
echo "   https://www.googleapis.com/auth/admin.directory.group,https://www.googleapis.com/auth/admin.directory.group.member"
echo "5. Click 'Authorize'."
echo "=========================================================================="
echo ""
read -p "Once you have completed the Workspace authorization steps above, press [Enter] to run Terraform..."

# Copy python helpers to workspace
cp scripts/*.py .

# Initialize and Apply Terraform
terraform init
terraform apply -var="sa_email=${SA_EMAIL}"
