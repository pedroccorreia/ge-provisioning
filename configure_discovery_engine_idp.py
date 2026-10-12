import json
import subprocess
import urllib.request
import sys

def configure_idp(project_id, sa_email):
    # Retrieve user token to perform the resource operation
    token_proc = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True, check=True
    )
    user_token = token_proc.stdout.strip()
    
    url = f"https://discoveryengine.googleapis.com/v1beta/projects/{project_id}/locations/global/aclConfig"
    req_body = json.dumps({
        "idpConfig": {
            "idpType": "GSUITE"
        }
    }).encode("utf-8")
    
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json",
            "x-goog-user-project": project_id
        },
        method="PATCH"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Successfully configured IdP for project {project_id}")
    except Exception as e:
        print(f"Failed to configure IdP for project {project_id}: {e}", file=sys.stderr)
        if hasattr(e, 'read'):
            print(e.read().decode('utf-8'), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--sa", required=True)
    args = parser.parse_args()
    
    configure_idp(args.project, args.sa)
