from app.services.connection_repository import (
    get_connection_by_id
)

from app.services.connection_processor import (
    process_and_send_for_approval
)


CONNECTION_ID = 2


connection = get_connection_by_id(
    CONNECTION_ID
)


if connection is None:
    raise RuntimeError(
        f"Connection {CONNECTION_ID} not found."
    )


person = {
    "name":
        connection["name"],

    "current_title":
        connection["current_title"],

    "linkedin_url":
        connection["linkedin_url"]
}


print("=" * 60)
print("REPROCESSING EXISTING CONNECTION")
print("=" * 60)

print("ID:", CONNECTION_ID)
print("Name:", person["name"])
print("Title:", person["current_title"])
print("LinkedIn:", person["linkedin_url"])

print()


result = process_and_send_for_approval(
    CONNECTION_ID,
    person
)


print()
print("=" * 60)
print("FINAL RESULT")
print("=" * 60)

print(result)