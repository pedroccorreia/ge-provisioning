# Deployment Checklist

- [x] Configure keyless Domain-Wide Delegation token generation (`get_workspace_token.py`)
- [x] Configure Discovery Engine Location Identity Provider (`configure_discovery_engine_idp.py`) to `GSUITE`
- [x] Grant IAM permissions for Service Agents and Provisioner Service Account
- [ ] Authorize Discovery Engine Service Agent Client IDs per environment project in Workspace Admin Console with DWD scopes:
  - `admin.directory.user.readonly`
  - `admin.directory.group.readonly`
  - `admin.directory.group.member.readonly`
  - `gmail.readonly`
  - `calendar.readonly`
- [ ] Complete Domain-Wide Delegation token propagation wait (5 minutes)
- [ ] Run full `terraform apply` to provision customer environment projects, data connectors, and search engines
- [ ] Verify ACTIVE status for all connectors and search engines across configured environments

