import csv
import json
import sys
import argparse
import urllib.request
import urllib.error

def main():
    parser = argparse.ArgumentParser(description="Bulk invite users from a CSV file.")
    parser.add_argument("--csv", default="employees.csv", help="Path to the CSV file")
    parser.add_argument("--token", required=True, help="JWT token of the TENANT_ADMIN or PLATFORM_ADMIN")
    parser.add_argument("--tenant", required=True, help="The UUID of the tenant to invite users into")
    parser.add_argument("--url", default="http://localhost:8000/v1/tenants/{}/invitations", help="API URL")
    
    args = parser.parse_args()
    
    # Read CSV
    invitees = []
    try:
        with open(args.csv, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'email' in row and 'full_name' in row:
                    invitees.append({
                        "email": row['email'].strip(),
                        "full_name": row['full_name'].strip()
                    })
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)
        
    if not invitees:
        print("No valid rows found in CSV.")
        sys.exit(1)
        
    # Prepare payload
    payload = {
        "invitees": invitees,
        "role_name": "USER",
        "expires_in_hours": 48
    }
    
    data = json.dumps(payload).encode('utf-8')
    url = args.url.format(args.tenant)
    
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Bearer {args.token}')
    
    print(f"Sending {len(invitees)} invites to tenant {args.tenant}...")
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            print("\n✅ Success!")
            print(f"Total Invited: {result.get('total_invited')}")
            print(f"Total Skipped: {result.get('total_skipped')}")
            if result.get('skipped'):
                print("Skipped details:", json.dumps(result.get('skipped'), indent=2))
    except urllib.error.HTTPError as e:
        print(f"\nHTTP Error {e.code}: {e.reason}")
        print(e.read().decode())
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    main()
