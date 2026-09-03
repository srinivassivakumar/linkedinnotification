from app.db import create_tables
from app.services.connection_repository import (
    save_connection,
    update_connection_result
)


# Create database/table
create_tables()


# Fake connection for testing
person = {
    "name": "Rohan Sharma",
    "current_title": "Founder & CEO at XYZ AI",
    "linkedin_url": "https://www.linkedin.com/in/example"
}


# Save person
connection_id = save_connection(person)

print("Connection saved.")
print("Connection ID:", connection_id)


# Fake AI result
result = {
    "type": "founder",
    "company": "XYZ AI",

    "company_summary":
        "AI software development company.",

    "relevant_skills": [
        "RAG",
        "AWS",
        "MLOps"
    ],

    "reason":
        "Srinivas has relevant AI and cloud experience.",

    "message":
        "Hi Rohan, thanks for connecting. "
        "I would be interested in learning more "
        "about XYZ AI and exploring how I could "
        "contribute as the company grows.",

    "company_url":
        "https://www.xyzai.io/"
}


# Update database with AI result
update_connection_result(
    connection_id,
    result
)

print("AI result saved.")
print("Status: awaiting_approval")