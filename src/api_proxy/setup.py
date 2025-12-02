#!/usr/bin/env python3
"""
Setup script for API Proxy

Helps initialize database and generate required keys
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def generate_keys():
    """Generate encryption and JWT keys"""
    from src.api_proxy.services.encryption_service import EncryptionService
    import secrets

    print("Generating security keys...")
    print()

    # Generate Fernet encryption key
    encryption_key = EncryptionService.generate_encryption_key()
    print(f"ENCRYPTION_KEY={encryption_key}")

    # Generate JWT secret (64 characters)
    jwt_secret = secrets.token_urlsafe(48)
    print(f"JWT_SECRET={jwt_secret}")

    # Generate admin password (16 characters)
    admin_password = secrets.token_urlsafe(12)
    print(f"ADMIN_PASSWORD={admin_password}")

    print()
    print("Add these to your .env file")


def init_database():
    """Initialize database and create tables"""
    from src.api_proxy.database.connection import init_db, create_all_tables
    from src.api_proxy.config import get_config

    print("Initializing database...")

    try:
        # Load config
        config = get_config()
        print(f"Database URL: {config.database.url}")

        # Initialize connection
        init_db()
        print("Database connection established")

        # Create tables
        create_all_tables()
        print("Database tables created successfully")

        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def create_admin_user():
    """Create admin user"""
    from src.api_proxy.database.connection import get_db
    from src.api_proxy.services.user_service import get_user_service
    from src.api_proxy.config import get_config

    print("\nCreating admin user...")

    try:
        config = get_config()
        user_service = get_user_service()

        with get_db() as db:
            # Check if admin exists
            admin = user_service.get_user_by_username(db, config.admin.username)

            if admin:
                print(f"Admin user '{config.admin.username}' already exists")
                return

            # Create admin user
            admin = user_service.create_user(
                db=db,
                username=config.admin.username,
                email=config.admin.email,
                password=config.admin.password,
                is_admin=True
            )

            api_key = user_service.get_plaintext_api_key(admin)

            print(f"Admin user created successfully")
            print(f"  Username: {admin.username}")
            print(f"  Email: {admin.email}")
            print(f"  API Key: {api_key}")
            print()
            print("Please save these credentials securely")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main setup function"""
    import argparse

    parser = argparse.ArgumentParser(description="API Proxy Setup")
    parser.add_argument(
        "command",
        choices=["generate-keys", "init-db", "create-admin", "all"],
        help="Setup command to run"
    )

    args = parser.parse_args()

    if args.command == "generate-keys":
        generate_keys()

    elif args.command == "init-db":
        if init_database():
            print("Database initialization complete")
        else:
            sys.exit(1)

    elif args.command == "create-admin":
        create_admin_user()

    elif args.command == "all":
        print("Running full setup...")
        print()
        print("=" * 60)
        print("Step 1: Generate Keys")
        print("=" * 60)
        generate_keys()
        print()

        print("=" * 60)
        print("Step 2: Initialize Database")
        print("=" * 60)
        if not init_database():
            sys.exit(1)
        print()

        print("=" * 60)
        print("Step 3: Create Admin User")
        print("=" * 60)
        create_admin_user()
        print()

        print("=" * 60)
        print("Setup complete!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Copy the generated keys to your .env file")
        print("2. Start the server: python -m src.api_proxy.main")
        print("3. Access the API docs: http://localhost:8080/docs")


if __name__ == "__main__":
    main()
