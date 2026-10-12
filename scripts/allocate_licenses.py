#!/usr/bin/env python3
import json
import argparse
import subprocess
import urllib.request
import urllib.error
import sys
import os

def get_access_token():
    """Retrieve access token using gcloud auth."""
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"],
            text=True
        ).strip()
        return token
    except Exception as e:
        print(f"Error getting access token: {e}", file=sys.stderr)
        sys.exit(1)

def make_request(url, method="GET", body=None, token=None, project_id=None):
    """Execute REST API request to Discovery Engine API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    if project_id:
        headers["x-goog-user-project"] = project_id

    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"HTTP Error {e.code} for {url}: {err_body}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"Request failed for {url}: {e}", file=sys.stderr)
        raise

def get_license_configs(project_id, location, token):
    """Fetch all licenseConfigs for the licensing project."""
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/{location}/licenseConfigs"
    res = make_request(url, token=token, project_id=project_id)
    return res.get("licenseConfigs", [])

def get_user_licenses(project_id, location, token):
    """Fetch all assigned userLicenses for default_user_store."""
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/{location}/userStores/default_user_store/userLicenses"
    res = make_request(url, token=token, project_id=project_id)
    return res.get("userLicenses", [])

def list_allocations(central_project_id, location, token, config_data=None):
    """Display detailed summary of billing subscription and customer environment seat distributions."""
    print(f"\n=======================================================")
    print(f" Gemini Enterprise Licensing Summary")
    print(f"=======================================================\n")

    billing_account = config_data.get("billing_account") if config_data else "0111AA-12FED7-0F6152"
    sub_name = config_data.get("subscription_id", "N/A") if config_data else "N/A"
    sub_tier = config_data.get("subscription_tier", "Gemini Enterprise") if config_data else "Gemini Enterprise"

    print(f"Billing Account      : {billing_account}")
    print(f"Subscription ID      : {sub_name}")
    print(f"Subscription Tier    : {sub_tier}")
    print(f"Location             : {location}\n")

    allocations = config_data.get("allocations", []) if config_data else []
    print("Customer Environment Projects & Seat Allocations:")
    for item in allocations:
        p_id = item.get("project_id", "unknown")
        p_num = item.get("project_number", "")
        env_label = item.get("environment_name") or item.get("environment") or item.get("affiliate_name") or p_id
        target_seats = item.get("seat_count", 0)

        # Query project-level license configs
        try:
            cfgs = get_license_configs(p_id, location, token)
            active_cfg = next((c for c in cfgs if c.get("state") == "ACTIVE"), None)
            if active_cfg:
                cfg_name = active_cfg.get("name", "").split("/")[-1]
                count = active_cfg.get("licenseCount", "0")
                state = active_cfg.get("state", "UNKNOWN")
                print(f"  • {env_label:<16} | Project: {p_id:<18} | Seats: {count} ({state}) | Config: {cfg_name}")
            else:
                status_str = "Skipped (0 seats)" if target_seats == 0 else "No Active Config"
                print(f"  • {env_label:<16} | Project: {p_id:<18} | Status: {status_str}")
        except Exception as e:
            print(f"  • {env_label:<16} | Project: {p_id:<18} | Error: {e}")
    print()

def distribute_license_config(billing_account, license_config_id, project_number, seat_count, token, central_project="affiliates-bootstrap", location="global", dry_run=False):
    """Distribute licenseConfig seats from Billing Account level to target GCP project number."""
    url = f"https://discoveryengine.googleapis.com/v1beta/billingAccounts/{billing_account}/billingAccountLicenseConfigs/{license_config_id}:distributeLicenseConfig"
    payload = {
        "projectNumber": str(project_number),
        "location": location,
        "licenseCount": str(seat_count)
    }
    print(f"  • Distributing {seat_count} seat(s) to Project Number {project_number}...")
    if dry_run:
        return {}

    return make_request(url, method="POST", body=payload, token=token, project_id=central_project)

def configure_auto_register(target_project_id, location, full_license_config_name, token, seat_count=None, dry_run=False):
    """Configure default_user_store on target project to enable automatic license registration on user login."""
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{target_project_id}/locations/{location}/userStores/default_user_store?updateMask=defaultLicenseConfig,enableLicenseAutoRegister,enableExpiredLicenseAutoUpdate"
    payload = {
        "defaultLicenseConfig": full_license_config_name,
        "enableLicenseAutoRegister": True,
        "enableExpiredLicenseAutoUpdate": True
    }

    cfg_short = full_license_config_name.split("/")[-1]
    quota_str = f" [Seats: {seat_count}]" if seat_count is not None else ""
    print(f"  • Project: {target_project_id:<18}{quota_str:<15} -> Setting defaultLicenseConfig: {cfg_short} (Auto-Register: ON)")
    if dry_run:
        return {}

    return make_request(url, method="PATCH", body=payload, token=token, project_id=target_project_id)

def batch_update_licenses(project_id, location, license_config_full_name, user_license_updates, token, delete_unassigned=False):
    """Invoke batchUpdateUserLicenses REST endpoint."""
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/{location}/userStores/default_user_store:batchUpdateUserLicenses"
    
    payload = {
        "inlineSource": {
            "userLicenses": user_license_updates
        },
        "deleteUnassignedUserLicenses": delete_unassigned
    }

    return make_request(url, method="POST", body=payload, token=token, project_id=project_id)

def load_config(config_file):
    """Load configuration from JSON file."""
    if not os.path.exists(config_file):
        print(f"Config file not found: {config_file}", file=sys.stderr)
        sys.exit(1)
    with open(config_file, "r") as f:
        return json.load(f)

def main():
    parser = argparse.ArgumentParser(description="Distribute and configure Gemini Enterprise licenses across GCP customer environment projects.")
    parser.add_argument("--list", action="store_true", help="List license configs and seat quotas across all customer environment projects.")
    parser.add_argument("--distribute", action="store_true", help="Distribute subscription seats from Billing Account to project numbers.")
    parser.add_argument("--configure-auto-register", action="store_true", help="Configure projects to auto-provision licenses upon user login.")
    parser.add_argument("--retract", action="store_true", help="Retract distributed licenses back to the Billing Account pool.")
    parser.add_argument("--config-file", default="config/license_allocations.json", help="Path to JSON configuration file.")
    parser.add_argument("--billing-account", help="Override Billing Account ID (e.g. 0111AA-12FED7-0F6152).")
    parser.add_argument("--license-config", help="Override license config ID (e.g. ca1a2f23-797f-4cf7-ab6f-74fd5f3ca651).")
    parser.add_argument("--project", help="Override caller GCP Project ID.")
    parser.add_argument("--location", default="global", help="GCP Location (default: global).")
    parser.add_argument("--target-project", help="Target project ID for single project operations.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate changes without calling GCP write endpoints.")

    args = parser.parse_args()
    token = get_access_token()

    # Load configuration
    config_data = {}
    if os.path.exists(args.config_file):
        config_data = load_config(args.config_file)

    project_id = args.project or config_data.get("licensing_project") or "affiliates-bootstrap"
    billing_account = args.billing_account or config_data.get("billing_account") or "0111AA-12FED7-0F6152"
    license_config_id = args.license_config or config_data.get("license_config_id") or "ca1a2f23-797f-4cf7-ab6f-74fd5f3ca651"
    location = args.location or config_data.get("location") or "global"

    if args.list:
        list_allocations(project_id, location, token, config_data=config_data)
        return

    if not args.distribute and not args.configure_auto_register and not args.retract:
        parser.print_help()
        print("\nNote: Specify --list, --distribute, --configure-auto-register, or --retract.")
        return

    # If --distribute is requested
    if args.distribute:
        print(f"\n=======================================================")
        print(f" Distributing Subscription Seats from Billing Account")
        print(f" Billing Account : {billing_account}")
        print(f" License Config  : {license_config_id}")
        print(f"=======================================================\n")
        
        allocations = config_data.get("allocations", [])
        for item in allocations:
            p_id = item.get("project_id")
            p_num = item.get("project_number")
            seats = item.get("seat_count", 0)
            if p_num and seats > 0:
                print(f"Project: {p_id:<18} (Project #{p_num}) - Allocating {seats} seat(s)")
                distribute_license_config(
                    billing_account=billing_account,
                    license_config_id=license_config_id,
                    project_number=p_num,
                    seat_count=seats,
                    token=token,
                    central_project=project_id,
                    location=location,
                    dry_run=args.dry_run
                )
            elif p_num:
                print(f"Project: {p_id:<18} (Project #{p_num}) - Skipped (0 seats)")
        if args.dry_run:
            print("\n[DRY RUN] No distribution changes executed.")
        else:
            print("\nSeat distribution successfully requested across projects!")
        return

    # If --configure-auto-register is requested
    if args.configure_auto_register:
        print(f"\n=======================================================")
        print(f" Configuring Auto-Registration on User Login")
        print(f"=======================================================\n")
        
        allocations = config_data.get("allocations", [])
        target_projects = [args.target_project] if args.target_project else [item.get("project_id") for item in allocations if item.get("seat_count", 0) > 0]
        
        for t_proj in target_projects:
            if not t_proj:
                continue
            cfgs = get_license_configs(t_proj, location, token)
            active_cfg = next((c for c in cfgs if c.get("state") == "ACTIVE"), None)
            if not active_cfg:
                print(f"  • Project: {t_proj:<18} -> Skipping (No active distributed licenseConfig found)")
                continue
            
            full_cfg_name = active_cfg["name"]
            seat_count = active_cfg.get("licenseCount", "1")
            configure_auto_register(t_proj, location, full_cfg_name, token, seat_count=seat_count, dry_run=args.dry_run)

        if not args.target_project:
            for item in allocations:
                if item.get("seat_count", 0) == 0:
                    print(f"  • Project: {item.get('project_id'):<18} -> Skipped (0 seats allocated)")

        if args.dry_run:
            print("\n[DRY RUN] No changes executed.")
        else:
            print("\nAuto-registration configuration successfully applied to all target projects!")
        return

    # If --retract is requested
    if args.retract:
        print(f"\n=======================================================")
        print(f" Retracting Subscription Seats back to Billing Account")
        print(f" Billing Account : {billing_account}")
        print(f" License Config  : {license_config_id}")
        print(f"=======================================================\n")
        
        allocations = config_data.get("allocations", [])
        target_projects = [args.target_project] if args.target_project else [item.get("project_id") for item in allocations]
        
        for t_proj in target_projects:
            if not t_proj:
                continue
            cfgs = get_license_configs(t_proj, location, token)
            active_cfg = next((c for c in cfgs if c.get("state") == "ACTIVE"), None)
            if active_cfg:
                full_cfg_name = active_cfg["name"]
                print(f"  • Retracting license from {t_proj} ({full_cfg_name.split('/')[-1]})...")
                if not args.dry_run:
                    retract_url = f"https://discoveryengine.googleapis.com/v1beta/billingAccounts/{billing_account}/billingAccountLicenseConfigs/{license_config_id}:retractLicenseConfig"
                    make_request(retract_url, method="POST", body={"licenseConfig": full_cfg_name, "fullRetract": True}, token=token, project_id=project_id)
        
        if args.dry_run:
            print("\n[DRY RUN] No changes executed.")
        else:
            print("\nRetraction complete.")
        return

if __name__ == "__main__":
    main()
