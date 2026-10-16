#!/usr/bin/env python3
"""
Post-deployment verification script for Gemini Enterprise customer environments.
Checks connectors, search engine, assistant, user store, and license configs.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def get_access_token():
    """Retrieve access token using gcloud auth."""
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"],
            text=True
        ).strip()
        if not token:
            raise ValueError("Empty token returned by gcloud auth")
        return token
    except Exception as e:
        print(f"Error obtaining GCP access token: {e}", file=sys.stderr)
        print("Please authenticate with 'gcloud auth application-default login' or 'gcloud auth login'", file=sys.stderr)
        sys.exit(1)


def make_request(url, method="GET", body=None, token=None, project_id=None):
    """Execute REST API request to Google Cloud APIs."""
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
        return {"_error": e.code, "_message": err_body}
    except Exception as e:
        return {"_error": -1, "_message": str(e)}


def check_data_connectors(project_id, location, token):
    """Check status of federated data connectors."""
    # List collections first
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/{location}/collections"
    cols = make_request(url, token=token, project_id=project_id)
    if "_error" in cols:
        return [("Collections", "ERROR", f"HTTP {cols['_error']}: {cols['_message']}")]

    results = []
    collections = cols.get("collections", [])
    if not collections:
        results.append(("Data Connectors", "WARN", "No collections found in project"))
        return results

    found_connectors = False
    for col in collections:
        col_name = col.get("name", "")
        col_id = col_name.split("/")[-1]
        c_url = f"https://discoveryengine.googleapis.com/v1beta/{col_name}/dataConnector"
        c_res = make_request(c_url, token=token, project_id=project_id)
        if "_error" in c_res:
            continue
        found_connectors = True
        state = c_res.get("state", "UNKNOWN")
        data_source = c_res.get("dataSource", col_id)
        results.append((f"Connector ({data_source})", state, f"Collection: {col_id}"))

    if not found_connectors:
        results.append(("Data Connectors", "WARN", "No active data connectors found (enable_connectors may be false)"))

    return results


def check_search_engine(project_id, location, token):
    """Check search engine configuration."""
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/{location}/collections/default_collection/engines"
    res = make_request(url, token=token, project_id=project_id)
    if "_error" in res:
        return [("Search Engine", "ERROR", f"HTTP {res['_error']}: {res['_message']}")]

    engines = res.get("engines", [])
    if not engines:
        return [("Search Engine", "WARN", "No search engine provisioned in default_collection")]

    results = []
    for eng in engines:
        eng_id = eng.get("name", "").split("/")[-1]
        disp_name = eng.get("displayName", eng_id)
        data_stores = eng.get("dataStoreIds", [])
        results.append((f"Search App ({eng_id})", "ACTIVE", f"DisplayName: '{disp_name}', DataStores: {len(data_stores)}"))
    return results


def check_assistant(project_id, location, token, engine_id="default_assistant"):
    """Check governed assistant."""
    # List assistants under engines
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/{location}/collections/default_collection/engines"
    engines_res = make_request(url, token=token, project_id=project_id)
    if "_error" in engines_res or not engines_res.get("engines"):
        return [("Assistant", "SKIPPED", "No search engine available")]

    results = []
    for eng in engines_res.get("engines", []):
        eng_name = eng.get("name")
        a_url = f"https://discoveryengine.googleapis.com/v1beta/{eng_name}/assistants/default_assistant"
        a_res = make_request(a_url, token=token, project_id=project_id)
        if "_error" in a_res:
            results.append(("Assistant (default_assistant)", "WARN", f"Not found or inaccessible (HTTP {a_res['_error']})"))
        else:
            grounding = a_res.get("webGroundingType", "DISABLED")
            results.append(("Assistant (default_assistant)", "ACTIVE", f"Web Grounding: {grounding}"))
    return results


def check_user_store(project_id, location, token):
    """Check default_user_store auto-registration settings."""
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/{location}/userStores/default_user_store"
    res = make_request(url, token=token, project_id=project_id)
    if "_error" in res:
        return [("User Store", "ERROR", f"HTTP {res['_error']}: {res['_message']}")]

    auto_reg = res.get("enableLicenseAutoRegister", False)
    auto_update = res.get("enableExpiredLicenseAutoUpdate", False)
    def_cfg = res.get("defaultLicenseConfig", "None")
    cfg_short = def_cfg.split("/")[-1] if def_cfg else "None"

    status = "ACTIVE" if auto_reg else "WARN"
    details = f"Auto-Register: {auto_reg}, Auto-Update: {auto_update}, DefaultConfig: {cfg_short}"
    return [("User Store (default_user_store)", status, details)]


def check_license_configs(project_id, location, token):
    """Check project-level license configurations."""
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/{location}/licenseConfigs"
    res = make_request(url, token=token, project_id=project_id)
    if "_error" in res:
        return [("License Configs", "ERROR", f"HTTP {res['_error']}: {res['_message']}")]

    cfgs = res.get("licenseConfigs", [])
    if not cfgs:
        return [("License Configs", "WARN", "No distributed license configs found for this project")]

    results = []
    for c in cfgs:
        cfg_name = c.get("name", "").split("/")[-1]
        state = c.get("state", "UNKNOWN")
        seats = c.get("licenseCount", "0")
        results.append((f"License Config ({cfg_name})", state, f"Seats: {seats}"))
    return results


def print_row(component, status, details):
    status_icon = {
        "ACTIVE": "[PASS]",
        "STATE_ACTIVE": "[PASS]",
        "WARN": "[WARN]",
        "ERROR": "[FAIL]",
        "SKIPPED": "[SKIP]"
    }.get(status, f"[{status}]")
    print(f"  {status_icon:<8} | {component:<32} | {details}")


def verify_project(project_id, location, token, expected_seats=None):
    print(f"\n================================================================================")
    print(f" Verifying Environment Project: {project_id}")
    print(f" Location: {location}")
    print(f"================================================================================")

    all_checks = []
    all_checks.extend(check_user_store(project_id, location, token))
    all_checks.extend(check_license_configs(project_id, location, token))
    all_checks.extend(check_data_connectors(project_id, location, token))
    all_checks.extend(check_search_engine(project_id, location, token))
    all_checks.extend(check_assistant(project_id, location, token))

    has_failures = False
    for comp, stat, det in all_checks:
        print_row(comp, stat, det)
        if stat in ("ERROR", "FAIL"):
            has_failures = True

    console_url = f"https://console.cloud.google.com/gen-app-builder/engines?project={project_id}"
    print(f"\n  • Gemini Enterprise Console : {console_url}\n")
    return not has_failures


def main():
    parser = argparse.ArgumentParser(description="Verify Gemini Enterprise provisioned components across environments.")
    parser.add_argument("--config-file", default="config/license_allocations.json", help="Path to license allocations configuration file.")
    parser.add_argument("--project", help="Verify a single GCP project ID directly.")
    parser.add_argument("--location", default="global", help="Discovery Engine location (default: global).")

    args = parser.parse_args()

    projects_to_verify = []

    if args.project:
        projects_to_verify.append({"project_id": args.project})
    elif os.path.exists(args.config_file):
        try:
            with open(args.config_file, "r") as f:
                cfg = json.load(f)
                args.location = cfg.get("location", args.location)
                for item in cfg.get("allocations", []):
                    p_id = item.get("project_id")
                    if p_id:
                        projects_to_verify.append({
                            "project_id": p_id,
                            "seat_count": item.get("seat_count", 0)
                        })
        except Exception as e:
            print(f"Error loading configuration file {args.config_file}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # If user explicitly specified a non-existent config file:
        if args.config_file != "config/license_allocations.json":
            print(f"Error: Configuration file not found: {args.config_file}", file=sys.stderr)
            sys.exit(1)
        # Fallback: query terraform outputs
        try:
            tf_out = subprocess.check_output(["terraform", "output", "-json", "project_ids"], text=True)
            proj_map = json.loads(tf_out)
            for env, p_id in proj_map.items():
                projects_to_verify.append({"project_id": p_id})
        except Exception:
            print("No config file found and could not read terraform output. Specify --project <ID> directly.", file=sys.stderr)
            sys.exit(1)

    if not projects_to_verify:
        print("No projects identified for verification.", file=sys.stderr)
        sys.exit(1)

    token = get_access_token()

    print("\nStarting Gemini Enterprise Post-Deployment Verification...")
    overall_success = True
    for proj in projects_to_verify:
        success = verify_project(
            project_id=proj["project_id"],
            location=args.location,
            token=token,
            expected_seats=proj.get("seat_count")
        )
        if not success:
            overall_success = False

    if not overall_success:
        print("Verification completed with ERRORS.", file=sys.stderr)
        sys.exit(1)
    else:
        print("Verification completed successfully.\n")


if __name__ == "__main__":
    main()
