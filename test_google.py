import os
from dotenv import load_dotenv

# Load environment variables BEFORE importing modules that use them
load_dotenv()

from bot.google_services import list_upcoming_events, list_recent_emails, list_drive_files

def test_google_services():
    print("🔍 Testing Google Services Connection...\n")

    # 1. Check Environment Variables
    print("1. Checking Environment Variables:")
    sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    delegated_user = os.getenv("GOOGLE_DELEGATED_USER")
    
    print(f"   - GOOGLE_SERVICE_ACCOUNT_FILE: {sa_file}")
    if sa_file and os.path.exists(sa_file):
        print("     ✅ File exists.")
    else:
        print("     ❌ File NOT found or not set.")

    print(f"   - GOOGLE_DELEGATED_USER: {delegated_user}")
    if delegated_user:
        print("     ✅ User set.")
    else:
        print("     ⚠️ User NOT set (Domain-wide delegation might fail if needed).")
    print("\n")

    # 2. Test Calendar
    print("2. Testing Calendar API:")
    try:
        events = list_upcoming_events()
        print(f"   ✅ Success! Result:\n{events}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    print("\n")

    # 3. Test Gmail
    print("3. Testing Gmail API:")
    try:
        emails = list_recent_emails()
        print(f"   ✅ Success! Result:\n{emails}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    print("\n")

    # 4. Test Drive
    print("4. Testing Drive API:")
    try:
        files = list_drive_files()
        print(f"   ✅ Success! Result:\n{files}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    print("\n")

if __name__ == "__main__":
    test_google_services()
