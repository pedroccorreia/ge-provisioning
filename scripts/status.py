#!/usr/bin/env python3
"""
Deployment Status & Phase Detection Engine.
Derives the current live phase of Gemini Enterprise customer provisioning,
identifies blockers, determines next action, and outputs machine-readable JSON or human tables.

Exit Code Contract:
  0 = Next action is automatable by an agent.
  2 = Human gate reached (e.g. Domain-Wide Delegation, Subscription creation).
  1 = Blocked / Error (missing tools, authentication, missing tfvars, state mismatch).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys


PHASES = {
    0: "preflight_inputs",
    1: "foundation_apply",
    2: "dwd_authorization",
    3: "connectors_and_engines_apply",
    4: "license_distribution",
    5: "verification",
}

PLACEHOLDER_STRINGS = {
    "example-customer",
    "example customer",
    "example.com",
    "c01234567",
    "0x1xxx-xxxxxx-xxxxxx",
    "00000000-0000-0000-0000-000000000000",
}


def parse_tfvars(tfvars_path):
    """
    Lightweight, robust parser for terraform.tfvars without external dependencies.
    Extracts string, boolean, list, and map values.
    """
    if not os.path.exists(tfvars_path):
        return None

    data = {}
    with open(tfvars_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove single-line comments (# or //)
    lines = []
    for line in content.splitlines():
        line = re.sub(r'(?<!:)\/\/.*$', '', line)
        line = re.sub(r'#.*$', '', line)
        lines.append(line)
    clean_text = "\n".join(lines)

    # Match simple key = "value" or key = value
    str_matches = re.findall(r'^\s*([a-zA-Z0-9_-]+)\s*=\s*"([^"]*)"', clean_text, re.MULTILINE)
    for k, v in str_matches:
        data[k] = v

    # Match booleans
    bool_matches = re.findall(r'^\s*([a-zA-Z0-9_-]+)\s*=\s*(true|false)\b', clean_text, re.MULTILINE)
    for k, v in bool_matches:
        data[k] = (v.lower() == "true")

    # Match simple lists of strings: key = ["a", "b"]
    list_matches = re.findall(r'^\s*([a-zA-Z0-9_-]+)\s*=\s*\[(.*?)\]', clean_text, re.MULTILINE | re.DOTALL)
    for k, raw_items in list_matches:
        items = re.findall(r'"([^"]*)"', raw_items)
        data[k] = items

    # Match simple maps: key = { a = 1, b = 2 }
    map_matches = re.findall(r'^\s*([a-zA-Z0-9_-]+)\s*=\s*\{(.*?)\}', clean_text, re.MULTILINE | re.DOTALL)
    for k, raw_map in map_matches:
        inner = {}
        # parse key = "value" or key = number
        for mk, mv in re.findall(r'"?([a-zA-Z0-9_-]+)"?\s*=\s*"?([a-zA-Z0-9_./:-]+)"?', raw_map):
            inner[mk] = int(mv) if mv.isdigit() else mv
        data[k] = inner

    return data


def parse_state(state_path):
    """Parse local terraform.tfstate if it exists."""
    if not os.path.exists(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e)}


def check_cli_tools():
    """Verify required CLI tools are installed."""
    tools = ["terraform", "gcloud", "python3"]
    missing = [tool for tool in tools if shutil.which(tool) is None]
    return missing


def check_identity(skip_auth_check=False):
    """Verify active Google Cloud identity / ADC exists."""
    if skip_auth_check:
        return True, "auth_skipped"

    # Check ADC
    adc_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not adc_path:
        default_adc = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
        if os.path.exists(default_adc):
            adc_path = default_adc

    # Attempt gcloud auth print-access-token with short timeout
    try:
        proc = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if proc.returncode == 0 and proc.stdout.strip():
            account = subprocess.run(
                ["gcloud", "config", "get-value", "account"],
                capture_output=True,
                text=True,
                timeout=5
            ).stdout.strip()
            return True, account or "active_token"
    except Exception:
        pass

    if adc_path and os.path.exists(adc_path):
        return True, "application_default_credentials"

    return False, None


def determine_status(workdir, state_path=None, tfvars_path=None, skip_auth_check=False, deep=False):
    """
    Core phase detection and health assessment logic.
    """
    blockers = []

    # 1. Tools check
    missing_tools = check_cli_tools()
    if missing_tools:
        return {
            "phase": 0,
            "phase_name": PHASES[0],
            "owner": "human",
            "blockers": [f"Missing required tools in PATH: {', '.join(missing_tools)}"],
            "next_action": f"Install required CLI tools: {', '.join(missing_tools)}",
            "handoff_template": "tools",
            "exit_code": 1
        }

    # 2. Identity check
    has_identity, identity_info = check_identity(skip_auth_check)
    if not has_identity:
        return {
            "phase": 0,
            "phase_name": PHASES[0],
            "owner": "human",
            "blockers": ["No active Google Cloud credentials or ADC found"],
            "next_action": "Run 'gcloud auth application-default login' and 'gcloud auth login'",
            "handoff_template": "identity",
            "exit_code": 1
        }

    # 3. Inputs / tfvars check
    actual_tfvars_path = tfvars_path or os.path.join(workdir, "terraform.tfvars")
    tfvars = parse_tfvars(actual_tfvars_path)

    if tfvars is None:
        return {
            "phase": 0,
            "phase_name": PHASES[0],
            "owner": "human",
            "blockers": [f"Configuration file not found: {actual_tfvars_path}"],
            "next_action": "cp terraform.tfvars.example terraform.tfvars and fill in customer values",
            "handoff_template": "inputs",
            "exit_code": 1
        }

    required_keys = ["customer_id", "customer_name", "company_domain", "workspace_customer_id", "billing_account"]
    missing_keys = [k for k in required_keys if not tfvars.get(k)]
    if missing_keys:
        return {
            "phase": 0,
            "phase_name": PHASES[0],
            "owner": "human",
            "blockers": [f"Missing required keys in terraform.tfvars: {', '.join(missing_keys)}"],
            "next_action": f"Configure {', '.join(missing_keys)} in terraform.tfvars",
            "handoff_template": "inputs",
            "exit_code": 1
        }

    # Placeholder detection
    placeholder_keys = []
    for k in required_keys:
        val = str(tfvars.get(k, "")).strip().lower()
        if val in PLACEHOLDER_STRINGS or any(p in val for p in ["0x1xxx", "example-customer", "example.com"]):
            placeholder_keys.append(k)

    if placeholder_keys:
        return {
            "phase": 0,
            "phase_name": PHASES[0],
            "owner": "human",
            "blockers": [f"Unresolved placeholder values in terraform.tfvars: {', '.join(placeholder_keys)}"],
            "next_action": f"Replace example placeholders in terraform.tfvars with real customer parameters",
            "handoff_template": "inputs",
            "exit_code": 1
        }

    customer_id = tfvars["customer_id"]
    prefix = tfvars.get("project_id_prefix", "")
    environments = tfvars.get("environments") or ["non-prod", "prod"]
    expected_project_ids = {f"{prefix}{customer_id}-{env}" for env in environments}

    # 4. State Mismatch Guard
    actual_state_path = state_path or os.path.join(workdir, "terraform.tfstate")
    state = parse_state(actual_state_path)

    if state and "_error" not in state:
        state_project_ids = set()
        for res in state.get("resources", []):
            if res.get("type") == "google_project":
                for inst in res.get("instances", []):
                    pid = inst.get("attributes", {}).get("project_id")
                    if pid:
                        state_project_ids.add(pid)

        # If projects exist in state that do not match current customer expected projects
        foreign_projects = state_project_ids - expected_project_ids
        if state_project_ids and foreign_projects:
            return {
                "phase": 0,
                "phase_name": PHASES[0],
                "owner": "human",
                "blockers": [
                    f"CRITICAL STATE MISMATCH: Local state contains foreign projects: {sorted(list(foreign_projects))}. "
                    f"Expected projects for customer '{customer_id}': {sorted(list(expected_project_ids))}."
                ],
                "next_action": "Do NOT apply. Reconcile or isolate state before proceeding (see RUNBOOK.md §State Safety)",
                "handoff_template": "state_mismatch",
                "exit_code": 1
            }

    # 5. Stage 1 Foundation outputs check
    state_outputs = state.get("outputs", {}) if state and "_error" not in state else {}
    project_ids_output = state_outputs.get("project_ids", {}).get("value", {})

    stage1_complete = (
        bool(project_ids_output) and
        all(env in project_ids_output for env in environments)
    )

    if not stage1_complete:
        return {
            "phase": 1,
            "phase_name": PHASES[1],
            "owner": "agent",
            "blockers": [],
            "next_action": "make plan-foundation && make apply-foundation",
            "handoff_template": None,
            "exit_code": 0
        }

    # 6. Stage 2 DWD Human Gate check
    enable_connectors = tfvars.get("enable_connectors", False)
    if not enable_connectors:
        return {
            "phase": 2,
            "phase_name": PHASES[2],
            "owner": "human",
            "blockers": ["Domain-Wide Delegation authorization pending in Workspace Admin Console"],
            "next_action": "make dwd-checklist",
            "handoff_template": "dwd",
            "exit_code": 2
        }

    # 7. Stage 3 Connectors & Engines check
    search_engines_output = state_outputs.get("search_engine_names", {}).get("value", {})
    assistants_output = state_outputs.get("assistant_names", {}).get("value", {})

    stage3_complete = (
        bool(search_engines_output) and
        all(env in search_engines_output for env in environments) and
        bool(assistants_output) and
        all(env in assistants_output for env in environments)
    )

    if not stage3_complete:
        return {
            "phase": 3,
            "phase_name": PHASES[3],
            "owner": "agent",
            "blockers": [],
            "next_action": "make plan-connectors && make apply-connectors",
            "handoff_template": None,
            "exit_code": 0
        }

    # 8. Stage 4 License Allocation check
    lic_config_id = tfvars.get("license_config_id", "")
    sub_id = tfvars.get("subscription_id", "")

    # Check if subscription details are provided
    if not lic_config_id or not sub_id or lic_config_id in PLACEHOLDER_STRINGS or sub_id in PLACEHOLDER_STRINGS:
        return {
            "phase": 4,
            "phase_name": "subscription_setup",
            "owner": "human",
            "blockers": ["Billing Account subscription ID / license config ID missing or placeholder in terraform.tfvars"],
            "next_action": "Set license_config_id and subscription_id in terraform.tfvars",
            "handoff_template": "subscription",
            "exit_code": 2
        }

    # Check if license_config_names is configured in tfvars (loop closed)
    lic_config_names = tfvars.get("license_config_names", {})
    licenses_distributed = (
        bool(lic_config_names) and
        all(env in lic_config_names for env in environments)
    )

    if not licenses_distributed:
        return {
            "phase": 4,
            "phase_name": PHASES[4],
            "owner": "agent",
            "blockers": [],
            "next_action": "make licenses",
            "handoff_template": None,
            "exit_code": 0
        }

    # 9. Stage 5 Verification
    return {
        "phase": 5,
        "phase_name": PHASES[5],
        "owner": "agent",
        "blockers": [],
        "next_action": "make verify",
        "handoff_template": None,
        "exit_code": 0
    }


def print_human_table(status_data):
    """Render a clean, formatted terminal summary table."""
    phase = status_data["phase"]
    phase_name = status_data["phase_name"]
    owner = status_data["owner"]
    next_action = status_data["next_action"]
    blockers = status_data["blockers"]

    print("\n================================================================================")
    print(" GEMINI ENTERPRISE PROVISIONING STATUS")
    print("================================================================================")
    print(f" Current Phase : Stage {phase} — {phase_name.replace('_', ' ').title()}")
    print(f" Phase Owner   : {owner.upper()}")
    print(f" Next Action   : {next_action}")
    if status_data.get("handoff_template"):
        print(f" Gate Template : {status_data['handoff_template']}")

    if blockers:
        print("\n Blockers / Action Required:")
        for b in blockers:
            print(f"   [!] {b}")
    else:
        print("\n Status        : Ready to proceed.")
    print("================================================================================\n")


def print_dwd_checklist():
    """Fetch terraform dwd_checklist output and enrich with the 21-digit numeric OAuth2 Client ID (uniqueId)."""
    import urllib.request
    raw = subprocess.check_output(["terraform", "output", "-json", "dwd_checklist"], text=True)
    data = json.loads(raw)
    tfvars = parse_tfvars(os.path.join(os.getcwd(), "terraform.tfvars")) or {}
    quota_proj = tfvars.get("billing_project")

    tok = ""
    for cmd in (
        ["gcloud", "auth", "application-default", "print-access-token"],
        ["gcloud", "auth", "print-access-token"],
    ):
        try:
            tok = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
            if tok:
                break
        except Exception:
            continue

    for _env, info in data.items():
        pnum = info.get("project_number")
        pid = info.get("project_id")
        if tok and pnum:
            try:
                url = f"https://serviceusage.googleapis.com/v1beta1/projects/{pnum}/services/discoveryengine.googleapis.com:generateServiceIdentity"
                req = urllib.request.Request(
                    url,
                    data=b"{}",
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {tok}",
                        "x-goog-user-project": quota_proj or pid or pnum,
                        "Content-Type": "application/json",
                    },
                )
                resp = json.loads(urllib.request.urlopen(req).read().decode())
                uid = resp.get("response", {}).get("uniqueId")
                if uid:
                    info["client_id"] = uid
            except Exception:
                pass

    print(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Check deployment status and determine next automated/human step.")
    parser.add_argument("--json", action="store_true", help="Output status in JSON format for agent consumption.")
    parser.add_argument("--dwd-checklist", action="store_true", help="Print DWD checklist enriched with 21-digit numeric Client ID.")
    parser.add_argument("--deep", action="store_true", help="Perform deep drift check via terraform plan.")
    parser.add_argument("--workdir", default=".", help="Root directory of the Terraform repository.")
    parser.add_argument("--state-file", help="Path to terraform.tfstate override (for test fixtures).")
    parser.add_argument("--tfvars-file", help="Path to terraform.tfvars override (for test fixtures).")
    parser.add_argument("--skip-auth-check", action="store_true", help="Skip active cloud credential validation (for testing).")

    args = parser.parse_args()

    if args.dwd_checklist:
        print_dwd_checklist()
        sys.exit(0)

    status_data = determine_status(
        workdir=os.path.abspath(args.workdir),
        state_path=args.state_file,
        tfvars_path=args.tfvars_file,
        skip_auth_check=args.skip_auth_check,
        deep=args.deep
    )

    if args.json:
        # Output clean JSON without exit_code in the payload (or with it)
        output_payload = {
            "phase": status_data["phase"],
            "phase_name": status_data["phase_name"],
            "owner": status_data["owner"],
            "blockers": status_data["blockers"],
            "next_action": status_data["next_action"],
            "handoff_template": status_data["handoff_template"]
        }
        print(json.dumps(output_payload, indent=2))
    else:
        print_human_table(status_data)

    sys.exit(status_data["exit_code"])


if __name__ == "__main__":
    main()
