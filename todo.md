# Deployment Checklist

- [x] Configure keyless Domain-Wide Delegation token generation (`get_workspace_token.py`)
- [x] Configure Discovery Engine Location Identity Provider (`configure_discovery_engine_idp.py`) to `GSUITE`
- [x] Grant IAM permissions for Service Agents and Provisioner Service Account
- [x] Authorize 7 Discovery Engine Service Agent Client IDs in Workspace Admin Console with DWD scopes:
  - `admin.directory.user.readonly`
  - `admin.directory.group.readonly`
  - `admin.directory.group.member.readonly`
  - `gmail.readonly`
  - `calendar.readonly`
- [x] Update `main.tf` connector `params` to include `super_admin_email_address`
- [ ] Complete Domain-Wide Delegation token propagation wait (5 minutes)
- [ ] Run full `terraform apply` to provision all 14 data connectors and 14 search engines
- [ ] Verify ACTIVE status for all connectors and search engines
