# Gemini Enterprise License Allocation & Troubleshooting Guide

This document captures the complete findings, architectural design, Google API requirements, and actionable next steps for managing Gemini Enterprise licenses across customer environment GCP projects (e.g. `prod` and `non-prod`).

---

## 1. Executive Summary & Configuration

### Subscription Overview
* **Subscription Name**: `customer_main_reservation`
* **Subscription ID**: `05eab18d-9cd5-4ba6-966f-ff796c7d27a8`
* **Billing Account License Config ID**: `ca1a2f23-797f-4cf7-ab6f-74fd5f3ca651`
* **Billing Account ID**: `0111AA-12FED7-0F6152`
* **Subscription Tier**: `Gemini Enterprise Standard`
* **Total Subscription Capacity**: 5 seats
* **Target Quota Distribution**: Allocated across customer environments (e.g., 4 seats for `prod`, 1 seat for `non-prod`)

### Customer Environment Quota Allocations
Configured in [`config/license_allocations.json`](file:///Users/pcorreia/dev/ge/affiliate-provisioning/config/license_allocations.json):

| Environment | Project ID | Project Number | Allocated Quota | Status |
| :--- | :--- | :---: | :---: | :---: |
| **Production** | `rwg-prod` | `1067043213672` | 4 seats | Active |
| **Non-Production** | `rwg-non-prod` | `193224435442` | 1 seat | Active |

---

## 2. Architecture & Operational Workflow

```mermaid
flowchart TD
    subgraph BillingLevel["Cloud Billing Account (0111AA-12FED7-0F6152)"]
        Sub["Gemini Enterprise Subscription (5 Seats)<br/><code>ca1a2f23-797f-4cf7-ab6f-74fd5f3ca651</code>"]
    end

    subgraph Distribution["distributeLicenseConfig (scripts/allocate_licenses.py --distribute)"]
        D1["Distribute 4 seats"]
        D2["Distribute 1 seat"]
    end

    subgraph Projects["Customer Environment Projects (User Store Auto-Register: ON)"]
        P1["Production (rwg-prod)"]
        P2["Non-Production (rwg-non-prod)"]
    end

    Sub --> D1 --> P1
    Sub --> D2 --> P2
```

---

## 3. Operational CLI Commands

### 1. Distribute Subscription Seats from Billing Account to Projects
Distributes seat quota from the central Billing Account pool to target affiliate project numbers:
```bash
# Dry run preview
python3 scripts/allocate_licenses.py --distribute --dry-run

# Execute distribution
python3 scripts/allocate_licenses.py --distribute
```

### 2. Configure Auto-Registration on Target Projects
Binds each project's `default_user_store` to its distributed license config so users automatically receive seats upon login:
```bash
# Dry run preview
python3 scripts/allocate_licenses.py --configure-auto-register --dry-run

# Apply configuration
python3 scripts/allocate_licenses.py --configure-auto-register
```

### 3. Verify Active Allocations & Status
Displays the real-time license configurations and assigned quota across all customer environment projects:
```bash
python3 scripts/allocate_licenses.py --list
```

### 4. Verify End-User Search Access
Log in to the customer search application using an Incognito window:
* **Production Console**: [Vertex AI Search - Production App](https://console.cloud.google.com/gen-app-builder/engines?project=rwg-prod)

---

## 4. Minimal IAM Permission Requirements

To execute seat distribution from the Cloud Billing Account, the executing principal requires:
* `discoveryengine.billingAccountLicenseConfigs.distribute` on Billing Account `0111AA-12FED7-0F6152`.

---

## Appendix: Archived Legacy Findings & Deprecations

> [!NOTE]
> The following findings document the evolution from legacy project-level licensing to the current Billing Account model:

1. **Project-Level Creation Deprecated**:
   * Google Cloud returned: `"License Config creation has been deprecated at the project level for Gemini Enterprise."`
   * Direct creation via `projects.locations.licenseConfigs.create` is no longer supported.
2. **Central Subscription Architecture**:
   * Subscriptions are created at the Billing Account level and provisioned to project numbers via `billingAccounts.billingAccountLicenseConfigs.distributeLicenseConfig`.
   * Unused quota can be released back to the central pool using `billingAccounts.billingAccountLicenseConfigs.retractLicenseConfig`.
3. **Multi-Project Account Access**:
   * A single user principal (e.g. `pcorreia@pcorreia.altostrat.com`) can access multiple affiliate projects independently.

