"""
Create test user for AgentCrafter Chrome Extension

This script uses baseapp.yaml (via ConfigService) to connect to the user database.
"""
import sys
from pathlib import Path

# Ensure we're in the correct directory
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from database import SessionLocal, User, init_db, get_database_url
from auth import auth_service

def create_test_user():
    # Print configuration info
    print("=" * 60)
    print("AgentCrafter Test User Creation")
    print("=" * 60)
    print(f"Database URL: {get_database_url()}")
    print("Configuration: Using baseapp.yaml (via ConfigService)")
    print("=" * 60)
    
    # Initialize database first
    print("\nInitializing database...")
    init_db()
    
    db = SessionLocal()
    
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.username == "demo").first()
        if existing_user:
            print("⚠️  User 'demo' already exists")
            print("Username: demo")
            print("Password: demo123")
            return
        
        # Create test user
        test_user = User(
            username="demo",
            email="demo@example.com",
            hashed_password=auth_service.get_password_hash("demo123"),
            full_name="Demo User",
            is_active=True,
            is_admin=False
        )
        
        db.add(test_user)
        db.commit()
        
        print("✅ Test user created successfully")
        print("=" * 40)
        print("Username: demo")
        print("Password: demo123")
        print("=" * 40)
        print("You can now login with these credentials")
        
    except Exception as e:
        print(f"❌ Error creating test user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_test_user()
