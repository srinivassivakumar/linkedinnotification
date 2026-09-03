from app.services.gmail_service import get_gmail_service

service = get_gmail_service()

labels = service.users().labels().list(userId="me").execute().get("labels", [])

label_id = None

for label in labels:
    if label["name"] == "LinkedInAccepted":
        label_id = label["id"]
        break

if not label_id:
    raise RuntimeError("LinkedInAccepted label not found")

print("✅ Label found:", label_id)

result = service.users().messages().list(
    userId="me",
    labelIds=[label_id],
    maxResults=20
).execute()

messages = result.get("messages", [])

print("Messages found:", len(messages))

for item in messages:
    msg = service.users().messages().get(
        userId="me",
        id=item["id"],
        format="metadata",
        metadataHeaders=["From", "Subject"]
    ).execute()

    headers = {
        h["name"]: h["value"]
        for h in msg["payload"].get("headers", [])
    }

    print("\nMessage ID:", item["id"])
    print("From:", headers.get("From"))
    print("Subject:", headers.get("Subject"))