import json
import time
import subprocess
import urllib.request
import urllib.parse
import sys

def get_workspace_token(sa_email, admin_email, scopes):
    now = int(time.time())
    payload = {
        "iss": sa_email,
        "sub": admin_email,
        "scope": " ".join(scopes),
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600
    }
    payload_str = json.dumps(payload)
    
    # Sign JWT using user active gcloud session
    token_proc = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True, check=True
    )
    user_token = token_proc.stdout.strip()
        
    url = f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{sa_email}:signJwt"
    req_body = json.dumps({"payload": payload_str}).encode("utf-8")
    
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    with urllib.request.urlopen(req) as response:
        resp_data = json.loads(response.read().decode("utf-8"))
        signed_jwt = resp_data["signedJwt"]
        
    # Exchange signed JWT for Access Token
    token_url = "https://oauth2.googleapis.com/token"
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": signed_jwt
    }).encode("utf-8")
    
    token_req = urllib.request.Request(token_url, data=data, method="POST")
    with urllib.request.urlopen(token_req) as response:
        token_resp = json.loads(response.read().decode("utf-8"))
        return token_resp["access_token"]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sa", required=True)
    parser.add_argument("--admin", required=True)
    parser.add_argument("--scopes", nargs="+", required=True)
    args = parser.parse_args()
    
    try:
        token = get_workspace_token(args.sa, args.admin, args.scopes)
        # Output must be JSON formatted for terraform external data source
        print(json.dumps({"token": token}))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
