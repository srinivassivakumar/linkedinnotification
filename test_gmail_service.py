from app.services.gmail_service import get_gmail_service

service = get_gmail_service()

profile = service.users().getProfile(
    userId="me"
).execute()

print("Gmail service connected")
print("Email:", profile["emailAddress"])