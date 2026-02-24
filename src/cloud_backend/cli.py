"""
Ami Cloud Backend CLI — Admin operations via sub2api.

Usage:
    cd src/cloud_backend
    python -m cli create-admin --email admin@example.com --password <password>
    python -m cli list-users
"""

import argparse
import asyncio
import sys
import os
from pathlib import Path

# Ensure project root is in path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def _get_sub2api_client():
    """Create a Sub2APIClient from config/env."""
    from core.config_service import CloudConfigService
    config = CloudConfigService()

    admin_key_env = config.get("sub2api.admin_api_key_env", "SUB2API_ADMIN_API_KEY")
    admin_key = os.environ.get(admin_key_env)
    if not admin_key:
        print(f"Error: {admin_key_env} environment variable required")
        sys.exit(1)

    from services.sub2api_client import Sub2APIClient
    return Sub2APIClient(
        base_url=config.get("llm.proxy_url"),
        admin_api_key=admin_key,
    )


def create_admin(args):
    """Create an admin user or promote existing user to admin."""
    client = _get_sub2api_client()

    async def _run():
        import httpx
        # Try to create user first
        try:
            user = await client.create_user(args.email, args.password, args.username or "")
            user_id = user["id"]
            print(f"Created user: id={user_id}, email={args.email}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                print(f"User {args.email} already exists, promoting to admin...")
                # Need to find user ID — list users and search
                result = await client.list_users(1, 100, args.email)
                users = result.get("users", result) if isinstance(result, dict) else result
                user_id = None
                for u in (users or []):
                    if u.get("email") == args.email:
                        user_id = u["id"]
                        break
                if not user_id:
                    print(f"Error: Could not find user {args.email}")
                    sys.exit(1)
            else:
                print(f"Error: {e}")
                sys.exit(1)

        # Promote to admin
        try:
            await client.update_user(user_id, role="admin")
            print(f"User {args.email} (id={user_id}) is now admin.")
        except Exception as e:
            print(f"Error promoting to admin: {e}")
            sys.exit(1)

        # Create API key
        try:
            token_data = await client.login(args.email, args.password)
            key_data = await client.create_api_key_for_user(token_data["access_token"], name="admin-cli")
            print(f"API key created: {key_data['key'][:10]}...")
        except Exception as e:
            print(f"Warning: Could not create API key: {e}")

    asyncio.run(_run())


def list_users(args):
    """List all users."""
    client = _get_sub2api_client()

    async def _run():
        result = await client.list_users(1, 100)
        users = result.get("users", result) if isinstance(result, dict) else result

        if not users:
            print("No users found.")
            return

        print(f"{'ID':>6}  {'Username':<20}  {'Email':<30}  {'Role':<8}  {'Status':<10}")
        print("-" * 80)
        for u in users:
            print(
                f"{u.get('id', ''):>6}  {u.get('username', ''):<20}  {u.get('email', ''):<30}  "
                f"{u.get('role', 'user'):<8}  {u.get('status', 'active'):<10}"
            )
        total = result.get("total", len(users)) if isinstance(result, dict) else len(users)
        print(f"\nTotal: {total} users")

    asyncio.run(_run())


def main():
    parser = argparse.ArgumentParser(description="Ami Cloud Backend CLI")
    subparsers = parser.add_subparsers(dest="command")

    # create-admin
    p_admin = subparsers.add_parser("create-admin", help="Create or promote admin user")
    p_admin.add_argument("--email", required=True)
    p_admin.add_argument("--password", required=True)
    p_admin.add_argument("--username", default=None)

    # list-users
    subparsers.add_parser("list-users", help="List all users")

    args = parser.parse_args()

    if args.command == "create-admin":
        create_admin(args)
    elif args.command == "list-users":
        list_users(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
